"""Regras de avaliação, persistência e exportação; sem dependência de interface."""
import csv
import hashlib
import hmac
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def load_content():
    bank = json.loads((ROOT / 'content/questions.json').read_text())
    sources = json.loads((ROOT / 'content/sources.json').read_text())
    validate_bank(bank, sources)
    return bank, sources

def validate_bank(bank, sources):
    qs = bank['questions']
    if len(qs) != 30 or len({q['id'] for q in qs}) != 30:
        raise ValueError('O banco deve conter 30 questões com identificadores únicos.')
    for q in qs:
        if len(q['options']) != 4 or len(set(q['options'])) != 4:
            raise ValueError('Cada questão deve ter quatro alternativas distintas.')
        if type(q['answer']) is not int or not 0 <= q['answer'] < 4 or not q['comment'] or not q['refs']:
            raise ValueError('Gabarito, comentário ou fonte inválidos.')
        for ref in q['refs']:
            if ref['source'] not in sources or not 1 <= ref['page'] <= sources[ref['source']]['pages']:
                raise ValueError('Referência de slide inválida.')

def grade(bank, answers):
    qs = bank['questions']
    if set(answers) != {q['id'] for q in qs}:
        raise ValueError('Responda às 30 questões antes de entregar.')
    if any(type(v) is not int or not 0 <= v < 4 for v in answers.values()):
        raise ValueError('Resposta inválida.')
    return sum(answers[q['id']] == q['answer'] for q in qs)

def learner_id(secret, issuer, subject):
    if len(secret) < 32 or not issuer or not subject:
        raise ValueError('Identidade ou segredo de pseudonimização inválidos.')
    return hmac.new(secret.encode(), json.dumps([issuer, subject]).encode(), hashlib.sha256).hexdigest()[:20]

def role_for(email, verified, teachers, students):
    if verified is not True:
        return None
    email = email.strip().casefold()
    if email in {x.strip().casefold() for x in teachers}:
        return 'teacher'
    if email in {x.strip().casefold() for x in students}:
        return 'student'
    return None

class Store:
    def __init__(self, url):
        self.url = url
        self.postgres = url.startswith(('postgresql://', 'postgres://'))
        if not self.postgres:
            if not url.startswith('sqlite:///'):
                raise ValueError('Use PostgreSQL ou sqlite:///caminho.')
            Path(url[10:]).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY, student_id TEXT NOT NULL, created_at TEXT NOT NULL,
                version TEXT NOT NULL, correct INTEGER NOT NULL, total INTEGER NOT NULL,
                snapshot TEXT NOT NULL)''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_attempt_student ON attempts(student_id, created_at)')

    @contextmanager
    def connect(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=10)
        else:
            conn = sqlite3.connect(self.url[10:], timeout=15)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, conn, sql, params=()):
        return conn.execute(sql.replace('?', '%s') if self.postgres else sql, params)

    def save(self, attempt_id, student_id, bank, answers, sources):
        correct = grade(bank, answers)
        snapshot = json.dumps({'bank': bank, 'answers': answers, 'sources': sources}, ensure_ascii=False)
        with self.connect() as conn:
            self.execute(conn, 'INSERT INTO attempts VALUES (?,?,?,?,?,?,?) ON CONFLICT(attempt_id) DO NOTHING',
                         (attempt_id, student_id, datetime.now(timezone.utc).isoformat(), bank['version'], correct, 30, snapshot))
            row = self.execute(conn, 'SELECT * FROM attempts WHERE attempt_id=? AND student_id=?', (attempt_id, student_id)).fetchone()
            if row is None:
                raise ValueError('Identificador de tentativa indisponível.')
            return dict(row)

    def own(self, student_id):
        with self.connect() as conn:
            return [dict(r) for r in self.execute(conn, 'SELECT * FROM attempts WHERE student_id=? ORDER BY created_at DESC LIMIT 1000', (student_id,)).fetchall()]

    def all(self):
        # Invocado somente depois da autorização de professor na interface.
        with self.connect() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM attempts ORDER BY created_at DESC LIMIT 10000').fetchall()]

    def delete_learner(self, student_id):
        with self.connect() as conn:
            self.execute(conn, 'DELETE FROM attempts WHERE student_id=?', (student_id,))

    def purge(self, days):
        if type(days) is not int or days < 1:
            raise ValueError('Prazo inválido.')
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.connect() as conn:
            self.execute(conn, 'DELETE FROM attempts WHERE created_at < ?', (cutoff,))

def safe_cell(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else text

def export_csv(rows, detailed=False):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, delimiter=';')
    writer.writerow(['tentativa', 'codigo_aluno', 'data_utc', 'versao', 'acertos', 'total', 'nota_0_10'] +
                    (['questao', 'tema', 'resposta', 'gabarito', 'acertou'] if detailed else []))
    for row in rows:
        base = [row['attempt_id'], row['student_id'], row['created_at'], row['version'], row['correct'], row['total'], round(10*row['correct']/row['total'], 2)]
        if detailed:
            snap = json.loads(row['snapshot'])
            for q in snap['bank']['questions']:
                answer = snap['answers'][q['id']]
                writer.writerow([safe_cell(v) for v in base + [q['id'],q['topic'],q['options'][answer],q['options'][q['answer']],answer == q['answer']]])
        else:
            writer.writerow([safe_cell(v) for v in base])
    return ('\ufeff'+stream.getvalue()).encode('utf-8')
