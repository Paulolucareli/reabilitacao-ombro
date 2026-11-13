import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from core import Store, grade, learner_id, role_for, load_content, export_csv

@pytest.fixture
def content(): return load_content()
@pytest.fixture
def store(tmp_path): return Store('sqlite:///'+str(tmp_path/'results.db'))

def test_grade_and_validation(content):
    bank,_=content
    good={q['id']:q['answer'] for q in bank['questions']}
    assert grade(bank,good)==30
    assert grade(bank,{k:(v+1)%4 for k,v in good.items()})==0
    with pytest.raises(ValueError):grade(bank,{})
    with pytest.raises(ValueError):grade(bank,dict(good,Q01=None))
    with pytest.raises(ValueError):grade(bank,dict(good,Q01=True))

def test_persistence_idempotence_isolation_and_delete(store,content):
    bank,sources=content;answers={q['id']:q['answer'] for q in bank['questions']}
    def save(_): return store.save('same-id','student-a',bank,answers,sources)
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(save,range(8)))
    assert all(r['correct']==30 for r in results)
    assert len(Store(store.url).own('student-a'))==1
    assert store.own('student-b')==[]
    with pytest.raises(ValueError):store.save('same-id','student-b',bank,answers,sources)
    assert len(store.all())==1
    store.delete_learner('student-a');assert store.all()==[]

def test_auth_roles_and_pseudonym():
    assert role_for('teacher@x',False,['teacher@x'],[]) is None
    assert role_for('teacher@x','true',['teacher@x'],[]) is None
    assert role_for(' Teacher@X ',True,['teacher@x'],[])=='teacher'
    assert role_for('student@x',True,['teacher@x'],['student@x'])=='student'
    assert role_for('stranger@x',True,['teacher@x'],['student@x']) is None
    assert learner_id('a'*32,'issuer','one')==learner_id('a'*32,'issuer','one')
    assert learner_id('a'*32,'issuer','one')!=learner_id('a'*32,'issuer','two')
    with pytest.raises(ValueError):learner_id('short','issuer','one')

def test_csv_and_retention(store,content):
    bank,sources=content;answers={q['id']:q['answer'] for q in bank['questions']}
    store.save('=malicious','student-a',bank,answers,sources)
    data=list(csv.reader(io.StringIO(export_csv(store.all(),True).decode('utf-8-sig')),delimiter=';'))
    assert len(data)==31 and data[1][0]=="'=malicious"
    store.purge(180); assert len(store.all())==1
    with store.connect() as conn: conn.execute("UPDATE attempts SET created_at='2000-01-01T00:00:00+00:00'")
    store.purge(180);assert not store.all()

def test_pdf_provenance_and_pages(content):
    import hashlib,pymupdf
    from core import ROOT
    bank,sources=content
    for key,src in sources.items():
        path=ROOT/src['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==src['sha256']
        with pymupdf.open(path) as pdf:
            assert len(pdf)==src['pages']
            for q in bank['questions']:
                for ref in q['refs']:
                    if ref['source']==key: assert len(pdf[ref['page']-1].get_text().strip())>5
