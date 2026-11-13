from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from core import ROOT, Store, load_content

@pytest.fixture
def app(monkeypatch,tmp_path):
    monkeypatch.setenv('DEMO_MODE','true')
    # Demonstração tem banco próprio; substituímos o Store para isolar o teste.
    original=Store.__init__
    monkeypatch.setattr(Store,'__init__',lambda self,url:original(self,'sqlite:///'+str(tmp_path/'demo.db')))
    return AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()

def by_label(items,label): return next(item for item in items if item.label==label)

def test_learning_and_no_early_answers(app):
    assert not app.exception
    assert app.title[0].value=='Reabilitação do ombro'
    assert len(app.get('video'))==1
    by_label(app.radio,'Área').set_value('Meu resultado').run()
    assert not app.exception and 'Entregue' in app.info[0].value

def test_complete_exam_feedback_and_navigation(app):
    bank,_=load_content()
    by_label(app.radio,'Área').set_value('Avaliação').run()
    by_label(app.checkbox,'Li estas informações').check().run()
    assert by_label(app.button,'Entregar avaliação').disabled
    by_label(app.radio,'Selecione uma alternativa').set_value(bank['questions'][0]['answer']).run()
    by_label(app.button,'Próxima').click().run()
    assert app.subheader[0].value.startswith('2.')
    by_label(app.button,'Anterior').click().run()
    assert by_label(app.radio,'Selecione uma alternativa').value==bank['questions'][0]['answer']
    for i,q in enumerate(bank['questions']):
        by_label(app.selectbox,'Ir para questão').set_value(i).run()
        by_label(app.radio,'Selecione uma alternativa').set_value(q['answer']).run()
        assert not app.exception
    by_label(app.checkbox,'Revisei minhas respostas e desejo entregar').check().run()
    by_label(app.button,'Entregar avaliação').click().run()
    assert not app.exception
    by_label(app.radio,'Área').set_value('Meu resultado').run()
    assert app.metric[0].value=='10.00 / 10'
    assert len(app.expander)==30
    # Renderização real de um slide original.
    app.checkbox[0].check().run()
    assert not app.exception
    assert not any("slide não" in warning.value for warning in app.warning)
    assert any(node.type in ('imgs','image','image_list') for node in app)
    by_label(app.selectbox,'Explorar como').set_value('Professor').run()
    assert not app.exception and app.title[0].value=='Painel do professor'
    assert app.metric[0].value=='1'
    assert len(app.get('download_button'))==2

def test_default_is_closed(monkeypatch):
    monkeypatch.setenv('DEMO_MODE','false')
    app=AppTest.from_file(str(ROOT/'app.py')).run()
    assert not app.exception
    assert not app.get('video') and not app.get('dataframe')
