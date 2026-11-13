import hashlib
import json
import os
import uuid
from pathlib import Path
import streamlit as st
from core import ROOT, Store, export_csv, learner_id, load_content, role_for
from email_results import RESULTS_TO, make_submission, send_result, validate_student, result_csv

st.set_page_config(page_title='Ombro · Aprender e avaliar', page_icon='◉', layout='centered')
st.markdown('''<style>
.block-container{max-width:960px;padding-top:2rem}h1,h2,h3{letter-spacing:-.03em}
.stApp{background:#f6f8fb}div[data-testid="stMetric"]{background:white;border-radius:12px;padding:16px}
.stButton button{min-height:44px}section[data-testid="stSidebar"]{background:#eaf1f5}
</style>''', unsafe_allow_html=True)

def config(key, default=None):
    if key in os.environ:
        return os.environ[key]
    try:
        return st.secrets.get(key, default)
    except FileNotFoundError:
        return default

def emails(key):
    raw = config(key, [])
    return raw.split(',') if isinstance(raw, str) else list(raw)

email_mode = str(config('RESULT_MODE', 'email')).lower() == 'email' and str(config('DEMO_MODE', 'false')).lower() != 'true'

def identity():
    if email_mode:
        return 'student', 'sessao', False
    demo = str(config('DEMO_MODE', 'false')).lower() == 'true'
    if demo:
        st.warning('Demonstração local · dados de teste. Não use este modo com alunos reais.')
        role = st.sidebar.selectbox('Explorar como', ['Aluno', 'Professor'])
        return ('teacher' if role == 'Professor' else 'student'), 'demonstracao', True
    try:
        has_auth = bool(st.secrets.get('auth'))
    except FileNotFoundError:
        has_auth = False
    if not has_auth:
        st.info('Configure o acesso institucional para disponibilizar a turma. Consulte o guia de publicação. Para testar localmente, use DEMO_MODE=true.')
        st.stop()
    if not st.user.is_logged_in:
        st.title('Reabilitação do ombro')
        st.write('Aprenda com as aulas. Avalie sua compreensão. Revise os slides.')
        if st.button('Entrar com minha conta', type='primary'):
            st.login()
        st.stop()
    role = role_for(st.user.get('email',''), st.user.get('email_verified'), emails('TEACHER_EMAILS'), emails('STUDENT_EMAILS'))
    if not role:
        st.error('Esta conta não está autorizada para a turma. Solicite acesso ao professor.')
        if st.button('Sair'): st.logout()
        st.stop()
    secret = str(config('PSEUDONYM_SECRET', ''))
    try:
        sid = learner_id(secret, st.user.get('iss'), st.user.get('sub'))
    except ValueError:
        st.error('Configuração de identidade incompleta. O administrador deve conferir o guia.')
        st.stop()
    if st.sidebar.button('Sair da conta'):
        st.session_state.clear()
        st.logout()
    return role, sid, False

role, sid, demo = identity()
# Invalida respostas e feedback se houver troca de identidade na mesma sessão.
if st.session_state.get('identity') != (sid, role):
    st.session_state.clear()
    st.session_state.identity = (sid, role)
try:
    bank, sources = load_content()
except (ValueError, OSError, KeyError):
    st.error('Não foi possível validar o conteúdo. Consulte o administrador.')
    st.stop()
store = None
if not email_mode:
    url = 'sqlite:///'+str(ROOT/'data/demo.db') if demo else str(config('DATABASE_URL',''))
    if not demo and not url.startswith(('postgres://','postgresql://')):
        st.error('Configure DATABASE_URL com PostgreSQL para gravar os resultados da turma.')
        st.stop()
    try:
        store = Store(url)
    except Exception:
        st.error('Armazenamento indisponível. As avaliações não podem ser entregues agora.')
        st.stop()

@st.cache_data(show_spinner=False)
def slide(source_id, page, expected_sha):
    import pymupdf
    path = ROOT/sources[source_id]['file']
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
        raise ValueError('PDF diferente da edição utilizada na avaliação.')
    with pymupdf.open(path) as document:
        return document[page-1].get_pixmap(matrix=pymupdf.Matrix(1.25,1.25), annots=False).tobytes('png')

def review(row):
    snap = json.loads(row['snapshot'])
    st.header('Seu resultado')
    a,b,c = st.columns(3)
    a.metric('Nota', f"{10*row['correct']/row['total']:.2f} / 10")
    b.metric('Acertos', f"{row['correct']} / {row['total']}")
    c.metric('Aproveitamento', f"{100*row['correct']/row['total']:.0f}%")
    st.caption(f"Tentativa {row['attempt_id']} · edição {row['version']} · {row['created_at'][:10]}")
    if email_mode:
        st.caption('Nome e e-mail informados pelo aluno, sem verificação de identidade.')
        st.download_button('Baixar meu resultado', result_csv(row), 'meu_resultado.csv', 'text/csv')
    else:
        st.download_button('Baixar meu resultado', export_csv([row], True), 'meu_resultado.csv', 'text/csv')
    st.subheader('Gabarito comentado')
    for q in snap['bank']['questions']:
        chosen = snap['answers'][q['id']]
        ok = chosen == q['answer']
        with st.expander(f"{'✓' if ok else '○'} {q['id']} · {q['topic']}"):
            st.write(q['stem'])
            st.write('Sua resposta: '+q['options'][chosen])
            st.success('Resposta correta: '+q['options'][q['answer']])
            st.write(q['comment'])
            for ref in q['refs']:
                src = snap['sources'][ref['source']]
                st.caption(f"{src['title']} · página {ref['page']} do PDF")
                if st.checkbox(f"Ver slide original · {ref['page']}",key=f"slide_{row['attempt_id']}_{q['id']}_{ref['source']}_{ref['page']}"):
                    try:
                        st.image(slide(ref['source'], ref['page'], src['sha256']), width='stretch')
                    except Exception:
                        st.warning('Este slide não está disponível nesta edição. O comentário foi preservado.')

def teacher():
    st.title('Painel do professor')
    st.caption('Somente contas autorizadas · códigos de aluno em vez de nomes ou e-mails')
    rows = store.all()
    st.info('Cada entrega é uma tentativa. Novas tentativas são permitidas; o histórico é mantido. Exibição limitada às 10.000 tentativas mais recentes.')
    if not rows:
        st.write('Nenhuma avaliação entregue ainda.')
        return
    codes = sorted({r['student_id'] for r in rows})
    selected = st.selectbox('Filtrar aluno', ['Todos']+codes)
    rows = [r for r in rows if selected == 'Todos' or r['student_id']==selected]
    a,b,c = st.columns(3)
    a.metric('Tentativas',len(rows));b.metric('Alunos',len({r['student_id'] for r in rows}))
    c.metric('Nota média',f"{sum(10*r['correct']/r['total'] for r in rows)/len(rows):.2f}")
    table = [{k:v for k,v in r.items() if k!='snapshot'} for r in rows]
    st.dataframe(table, hide_index=True, width='stretch')
    st.download_button('Exportar resultados (CSV)',export_csv(rows),'resultados.csv','text/csv')
    st.download_button('Exportar respostas por questão (CSV)',export_csv(rows,True),'respostas.csv','text/csv')
    counts = {}
    for r in rows:
        snap=json.loads(r['snapshot'])
        for q in snap['bank']['questions']:
            label=q['id']+' · '+q['topic'];num,den=counts.get(label,(0,0))
            counts[label]=(num+(snap['answers'][q['id']]==q['answer']),den+1)
    st.subheader('Acertos por questão')
    st.dataframe([{'Questão':key,'Acertos (%)':round(100*n/d,1)} for key,(n,d) in counts.items()],hide_index=True,width='stretch')
    with st.expander('Privacidade e exclusão'):
        st.write('As exclusões abaixo são permanentes no banco ativo. As cópias de segurança devem seguir a mesma política institucional.')
        delete_code = st.selectbox('Código para excluir',codes)
        confirmed = st.checkbox('Confirmo a exclusão de todas as tentativas deste código')
        if st.button('Excluir tentativas do código',disabled=not confirmed):
            store.delete_learner(delete_code);st.rerun()
        days = int(config('RETENTION_DAYS',180))
        confirm_purge = st.checkbox(f'Confirmo apagar tentativas com mais de {days} dias')
        if st.button('Aplicar prazo de retenção',disabled=not confirm_purge):
            store.purge(days);st.rerun()

if role == 'teacher':
    area=st.sidebar.radio('Área',['Resultados','Aulas e animações'])
    if area=='Resultados':
        try: teacher()
        except Exception: st.error('Não foi possível consultar ou alterar os resultados. Tente novamente.')
        st.stop()
else:
    area=st.sidebar.radio('Área',['Aulas e animações','Avaliação','Meu resultado'])
    if not email_mode: st.sidebar.caption(f'Seu código: {sid}')

if area=='Aulas e animações':
    st.caption('APRENDER · PRATICAR · REVISAR')
    st.title('Reabilitação do ombro')
    st.write('Duas aulas, quatro mecanismos e uma avaliação para consolidar o raciocínio clínico.')
    st.info('Comece pelos vídeos e explore as animações. Quando estiver pronto, abra a avaliação. Não é necessário repetir as aulas para iniciar a prova.')
    st.header('1. Videoaulas')
    video=st.selectbox('Escolha a aula',['Reabilitação do ombro','Reabilitação do ombro no atleta'])
    video_path = ROOT/'assets/videos'/('ombro.mp4' if video=='Reabilitação do ombro' else 'atleta.mp4')
    if video_path.is_file():
        st.video(str(video_path))
    else:
        st.info('Esta versão está sem os vídeos. Adicione ombro.mp4 e atleta.mp4 em assets/videos para disponibilizar as aulas. As animações e a avaliação continuam disponíveis.')
    with st.expander('Referências e uso do conteúdo'):
        st.write('Conteúdo educacional para profissionais e estudantes. Condutas e prazos dos slides precisam ser contextualizados; não são protocolos individuais de atendimento.')
        st.write('Ombro v2: 74 páginas. Atletas 2026: 69 páginas. Os slides associados às questões aparecem após a entrega. Os PDFs completos não são disponibilizados para download pelo aplicativo.')
    st.header('2. Mecanismos em movimento')
    animation=st.selectbox('Explore um mecanismo',['Ritmo escapuloumeral','Pares de força','Discinese e alamento','Luxação anterior'])
    idx=['Ritmo escapuloumeral','Pares de força','Discinese e alamento','Luxação anterior'].index(animation)
    st.iframe((ROOT/'content/animations.html').read_text().replace('__SCENE__',str(idx)),height='content',alt=animation)
    st.caption('Esquemas originais em 2D, simplificados para ensino. Não reproduzem uma medição individual nem substituem o exame clínico. Controles por teclado disponíveis.')
    if role=='student': st.write('Próximo passo: abra **Avaliação** no menu.')

elif area=='Avaliação':
    st.title('Avaliação de aprendizagem')
    if email_mode:
        st.caption(f'Resultados enviados ao professor: {RESULTS_TO}')
        if not config('RESEND_API_KEY') or not config('EMAIL_FROM'):
            st.info('As aulas estão disponíveis. O envio das avaliações aguarda configuração pelo professor.')
            st.stop()
        if st.session_state.get('email_error'):
            st.error(st.session_state.email_error)
            st.caption('O reenvio utiliza a mesma identificação e as mesmas respostas. Não feche esta página.')
    if st.session_state.get('completed'):
        st.success('Avaliação entregue. Abra Meu resultado para revisar os comentários e slides.')
        if st.button('Iniciar nova tentativa'):
            for key in list(st.session_state):
                if key not in ('identity', 'student_name', 'student_email'): del st.session_state[key]
            st.rerun()
        st.stop()
    st.caption('30 questões · quatro alternativas · nota de 0 a 10 · peso igual')
    with st.expander('Como seus dados são usados',expanded=not st.session_state.get('notice',False)):
        if email_mode:
            st.write(f'Na entrega, seu nome e e-mail informados, respostas, nota, data e versão serão enviados a {RESULTS_TO} pelo serviço Resend. Não há verificação de identidade. O aplicativo não mantém banco de notas; o professor guarda os resultados em seu e-mail. O Resend processa e pode manter registros do envio conforme sua política. Para solicitar exclusão, contate o professor. As respostas e o resultado ficam nesta sessão e podem ser perdidos ao fechar ou recarregar a página.')
        else:
            st.write(f'O professor recebe seu código, respostas, nota, data e versão da prova. Nome e e-mail não são gravados no banco de resultados. Prazo de referência: {config("RETENTION_DAYS",180)} dias, aplicado pelo responsável no painel. Para solicitar exclusão, informe seu código ao professor. As respostas em andamento ficam nesta sessão e podem ser perdidas ao fechar ou recarregar a página.')
        st.checkbox('Li estas informações',key='notice')
    if not st.session_state.get('notice'): st.stop()
    if email_mode:
        locked = bool(st.session_state.get('pending_email') or st.session_state.get('completed'))
        name = st.text_input('Nome completo', key='student_name', max_chars=120, disabled=locked)
        email = st.text_input('Seu e-mail', key='student_email', max_chars=254, disabled=locked)
        try:
            validate_student(name, email)
        except ValueError as exc:
            st.info(str(exc))
            st.stop()

    st.session_state.setdefault('answers',{})
    st.session_state.setdefault('question_selector',st.session_state.get('position',0))
    st.session_state.setdefault('attempt_id',str(uuid.uuid4()))
    answers=st.session_state.answers
    st.progress(len(answers)/30,text=f'{len(answers)} de 30 respondidas')
    position=st.selectbox('Ir para questão',range(30),key='question_selector',format_func=lambda i:f'{i+1:02}')
    st.session_state.position=position
    q=bank['questions'][position]
    st.caption(q['topic']);st.subheader(f"{position+1}. {q['stem']}")
    def record_answer(question_id, widget_key):
        value=st.session_state.get(widget_key)
        if value is not None: st.session_state.answers[question_id]=value
    chosen=st.radio('Selecione uma alternativa',range(4),index=answers.get(q['id']),format_func=lambda i:f"{'ABCD'[i]}. {q['options'][i]}",key=f"choice_{q['id']}",disabled=bool(st.session_state.get('pending_email')),on_change=record_answer,args=(q['id'],f"choice_{q['id']}"))
    if chosen is not None: answers[q['id']]=chosen
    a,b=st.columns(2)
    def move(delta):
        # Atualiza o seletor ANTES de recriar os widgets no próximo ciclo.
        # Apagar a chave após renderizar o seletor permite que o navegador
        # restaure o número antigo e desfaça o avanço dos botões.
        st.session_state.question_selector=max(0,min(29,st.session_state.question_selector+delta))
        st.session_state.position=st.session_state.question_selector
    a.button('Anterior',disabled=position==0,on_click=move,args=(-1,))
    b.button('Próxima',disabled=position==29,on_click=move,args=(1,))
    missing=[str(i+1) for i,item in enumerate(bank['questions']) if item['id'] not in answers]
    if missing: st.caption('Pendentes: '+', '.join(missing))
    else: st.info('Todas as 30 questões foram respondidas. Marque a confirmação abaixo e clique em Entregar avaliação.')
    confirm=st.checkbox('Revisei minhas respostas e desejo entregar',disabled=bool(missing))
    if st.button('Entregar avaliação',type='primary',disabled=bool(missing) or not confirm):
        if email_mode:
            try:
                if 'pending_email' not in st.session_state:
                    st.session_state.pending_email = make_submission(name, email, bank, answers, sources)
                row = st.session_state.pending_email
                receipt = send_result(row, str(config('RESEND_API_KEY', '')), str(config('EMAIL_FROM', '')))
                st.session_state.email_result = dict(row, email_receipt=receipt)
                st.session_state.completed = row['attempt_id']
                st.session_state.pop('email_error', None)
            except Exception:
                st.session_state.email_error = 'O envio não foi confirmado. Suas respostas foram mantidas nesta sessão. Tente entregar novamente; se persistir, contate o professor.'
            st.rerun()
        else:
            try:
                row=store.save(st.session_state.attempt_id,sid,bank,answers,sources)
                st.session_state.completed=row['attempt_id']
                st.success('Entrega gravada. Abra Meu resultado para revisar.')
                st.rerun()
            except Exception:
                st.error('A entrega não foi confirmada. Suas respostas foram mantidas nesta sessão. Tente novamente; a mesma entrega não será duplicada.')

elif area=='Meu resultado':
    if email_mode:
        rows = [st.session_state.email_result] if st.session_state.get('email_result') else []
        if rows:
            st.success('O serviço de e-mail aceitou o envio ao professor. Isso não garante a chegada à caixa de entrada.')
            st.caption(f"Protocolo de envio: {rows[0]['email_receipt']} · Guarde seu resultado antes de fechar a página.")
    else:
        try: rows=store.own(sid)
        except Exception: st.error('Resultados indisponíveis no momento.');st.stop()
    if not rows:
        st.title('Meu resultado');st.info('Entregue a avaliação para ver nota, comentários e slides originais.')
    else:
        chosen=st.selectbox('Tentativa',range(len(rows)),format_func=lambda i:rows[i]['created_at'][:19].replace('T',' ')+' UTC · '+str(rows[i]['correct'])+'/30')
        review(rows[chosen])
