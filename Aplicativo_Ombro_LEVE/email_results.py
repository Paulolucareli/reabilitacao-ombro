"""Entrega por HTTPS; não armazena resultados em disco."""
import base64
import csv
import io
import json
import re
import uuid
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

from core import grade

RESULTS_TO = 'paulolucareli@uni9.pro.br'


def validate_student(name, email):
    name, email = name.strip(), email.strip()
    if not 2 <= len(name) <= 120 or any(ord(c) < 32 for c in name):
        raise ValueError('Informe seu nome completo, com até 120 caracteres.')
    if len(email) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+", email):
        raise ValueError('Informe um e-mail válido.')
    return name, email


def make_submission(name, email, bank, answers, sources):
    name, email = validate_student(name, email)
    return {
        'attempt_id': str(uuid.uuid4()), 'student_id': 'identificacao-informada',
        'student_name': name, 'student_email': email,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'version': bank['version'], 'correct': grade(bank, answers),
        'total': len(bank['questions']),
        'snapshot': json.dumps({'bank': bank, 'answers': answers, 'sources': sources}, ensure_ascii=False),
    }


def safe_cell(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def result_csv(row):
    snapshot = json.loads(row['snapshot'])
    buf = io.StringIO(newline='')
    writer = csv.writer(buf, delimiter=';')
    writer.writerow(['Tentativa', 'Nome informado', 'E-mail informado', 'Data UTC', 'Versão', 'Nota', 'Questão', 'Enunciado', 'Resposta', 'Gabarito', 'Acertou'])
    for q in snapshot['bank']['questions']:
        choice = snapshot['answers'][q['id']]
        writer.writerow([safe_cell(v) for v in [
            row['attempt_id'], row['student_name'], row['student_email'], row['created_at'], row['version'],
            f"{10*row['correct']/row['total']:.2f}", q['id'], q['stem'],
            q['options'][choice], q['options'][q['answer']], choice == q['answer'],
        ]])
    return buf.getvalue().encode('utf-8-sig')


def email_payload(row, sender):
    snapshot = json.loads(row['snapshot'])
    lines = [
        'Avaliação de aprendizagem — Reabilitação do ombro',
        f"Nome informado: {row['student_name']}", f"E-mail informado: {row['student_email']}",
        'Identificação informada pelo aluno, sem verificação de identidade.',
        f"Tentativa: {row['attempt_id']}", f"Data UTC: {row['created_at']}",
        f"Versão: {row['version']}", f"Nota: {10*row['correct']/row['total']:.2f} / 10",
        f"Acertos: {row['correct']} / {row['total']}", '',
    ]
    for q in snapshot['bank']['questions']:
        choice = snapshot['answers'][q['id']]
        lines.extend([f"{q['id']}: {q['stem']}",
                      'Resposta: ' + q['options'][choice],
                      'Gabarito: ' + q['options'][q['answer']], ''])
    return {
        'from': sender, 'to': [RESULTS_TO],
        'subject': f"Avaliação Ombro — tentativa {row['attempt_id']}",
        'text': '\n'.join(lines),
        'attachments': [{'filename': 'resultado_ombro.csv',
                         'content': base64.b64encode(result_csv(row)).decode('ascii')}],
    }


def send_result(row, api_key, sender):
    if not api_key or not sender:
        raise ValueError('Envio ainda não configurado.')
    # As chaves do serviço expiram em 24 h. Evita repetir uma entrega ambígua após esse prazo.
    if datetime.now(timezone.utc) - datetime.fromisoformat(row['created_at']) >= timedelta(hours=23):
        raise ValueError('Prazo de reenvio encerrado. Contate o professor com o código da tentativa.')
    request = Request('https://api.resend.com/emails',
        data=json.dumps(email_payload(row, sender), ensure_ascii=False).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json',
                 'User-Agent': 'OmbroAprendizagem/1.0',
                 'Idempotency-Key': 'ombro/' + row['attempt_id']}, method='POST')
    with urlopen(request, timeout=20) as response:
        if not 200 <= response.status < 300:
            raise ValueError('O serviço não aceitou o envio.')
        receipt = json.loads(response.read())
    if not isinstance(receipt, dict) or not isinstance(receipt.get('id'), str) or not receipt['id']:
        raise ValueError('O serviço não retornou um comprovante de envio.')
    return receipt['id']
