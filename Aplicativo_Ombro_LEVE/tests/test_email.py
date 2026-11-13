import base64
import json
from urllib.error import URLError

import pytest
from streamlit.testing.v1 import AppTest
import email_results
from core import ROOT, Store, load_content
from email_results import make_submission, send_result, validate_student, result_csv


def submission():
    bank, sources = load_content()
    return make_submission('Aluno de teste', 'aluno@example.com', bank,
                           {q['id']: q['answer'] for q in bank['questions']}, sources)


def test_payload_and_confirmation(monkeypatch):
    row = submission()
    requests = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"id":"test-receipt"}'
    def fake(request, timeout):
        requests.append(request)
        assert timeout == 20
        return Response()
    monkeypatch.setattr(email_results, 'urlopen', fake)
    assert send_result(row, 'test-key', 'App <onboarding@resend.dev>') == 'test-receipt'
    send_result(row, 'test-key', 'App <onboarding@resend.dev>')
    assert requests[0].data == requests[1].data
    assert requests[0].get_header('Idempotency-key') == requests[1].get_header('Idempotency-key')
    payload = json.loads(requests[0].data)
    assert payload['to'] == ['paulolucareli@uni9.pro.br']
    assert '30 / 30' in payload['text'] and 'Aluno de teste' in payload['text']
    assert base64.b64decode(payload['attachments'][0]['content']) == result_csv(row)
    monkeypatch.setattr(Response, 'read', lambda self: b'{"message":"bad response"}')
    with pytest.raises(ValueError): send_result(row, 'test-key', 'sender@example.com')
    monkeypatch.setattr(email_results, 'urlopen', lambda *a, **kw: (_ for _ in ()).throw(URLError('offline')))
    with pytest.raises(URLError): send_result(row, 'test-key', 'sender@example.com')


def test_input_and_csv():
    for name, email in [('', 'aluno@example.com'), ('Ana', 'a@b\r\nBcc:x@y.com'), ('Ana', 'inválido')]:
        with pytest.raises(ValueError): validate_student(name, email)
    row = submission()
    row['student_name'] = '=2+2'
    assert "'=2+2" in result_csv(row).decode('utf-8-sig')


def by_label(items, label): return next(item for item in items if item.label == label)


def test_email_ui_retry_and_no_database(monkeypatch):
    monkeypatch.setenv('DEMO_MODE', 'false')
    monkeypatch.setenv('RESULT_MODE', 'email')
    monkeypatch.setenv('RESEND_API_KEY', 'test-key')
    monkeypatch.setenv('EMAIL_FROM', 'sender@example.com')
    monkeypatch.setattr(Store, '__init__', lambda *a: pytest.fail('No database should be opened'))
    attempts = []
    def fake_send(row, *args):
        attempts.append(dict(row))
        if len(attempts) == 1: raise URLError('offline')
        return 'test-receipt'
    monkeypatch.setattr(email_results, 'send_result', fake_send)
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()
    assert not app.exception and len(app.get('video')) == 1
    assert not any(item.label == 'Explorar como' for item in app.selectbox)
    by_label(app.radio, 'Área').set_value('Avaliação').run()
    by_label(app.checkbox, 'Li estas informações').check().run()
    by_label(app.text_input, 'Nome completo').set_value('Aluno de teste').run()
    by_label(app.text_input, 'Seu e-mail').set_value('aluno@example.com').run()
    bank, _ = load_content()
    app.session_state['answers'] = {q['id']: q['answer'] for q in bank['questions']}
    app.run()
    by_label(app.checkbox, 'Revisei minhas respostas e desejo entregar').check().run()
    by_label(app.button, 'Entregar avaliação').click().run()
    assert not app.exception and app.error
    assert 'completed' not in app.session_state
    assert by_label(app.text_input, 'Nome completo').disabled
    by_label(app.button, 'Entregar avaliação').click().run()
    assert not app.exception and app.session_state['completed']
    assert attempts[0] == attempts[1]
    by_label(app.radio, 'Área').set_value('Meu resultado').run()
    assert not app.exception and app.metric[0].value == '10.00 / 10'
    assert 'aceitou' in app.success[0].value
    by_label(app.radio, 'Área').set_value('Avaliação').run()
    assert not app.get('button') or not any(b.label == 'Entregar avaliação' for b in app.button)


def test_unconfigured_email_allows_lessons_not_delivery(monkeypatch):
    monkeypatch.setenv('DEMO_MODE', 'false')
    monkeypatch.setenv('RESULT_MODE', 'email')
    monkeypatch.setenv('RESEND_API_KEY', '')
    app = AppTest.from_file(str(ROOT/'app.py')).run()
    assert not app.exception and len(app.get('video')) == 1
    by_label(app.radio, 'Área').set_value('Avaliação').run()
    assert not app.exception and 'aguarda configuração' in app.info[0].value
    assert not app.button


def test_all_questions_with_next_button_and_email(monkeypatch):
    monkeypatch.setenv('DEMO_MODE', 'false')
    monkeypatch.setenv('RESULT_MODE', 'email')
    monkeypatch.setenv('RESEND_API_KEY', 'test-key')
    monkeypatch.setenv('EMAIL_FROM', 'sender@example.com')
    sent = []
    def fake_send(row, *args):
        sent.append(row)
        return 'navigation-receipt'
    monkeypatch.setattr(email_results, 'send_result', fake_send)
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()
    by_label(app.radio, 'Área').set_value('Avaliação').run()
    by_label(app.checkbox, 'Li estas informações').check().run()
    by_label(app.text_input, 'Nome completo').set_value('Aluno de teste').run()
    by_label(app.text_input, 'Seu e-mail').set_value('aluno@example.com').run()
    bank, _ = load_content()
    for index, question in enumerate(bank['questions']):
        assert app.subheader[0].value.startswith(f'{index+1}. ')
        by_label(app.radio, 'Selecione uma alternativa').set_value(question['answer']).run()
        assert not app.exception
        if index < 29:
            by_label(app.button, 'Próxima').click().run()
    assert len(app.session_state['answers']) == 30
    by_label(app.checkbox, 'Revisei minhas respostas e desejo entregar').check().run()
    by_label(app.button, 'Entregar avaliação').click().run()
    assert not app.exception and len(sent) == 1 and sent[0]['correct'] == 30
