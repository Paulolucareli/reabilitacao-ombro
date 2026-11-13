# Ombro · Aprender e avaliar

Aplicativo Streamlit com duas videoaulas, quatro animações de 24 segundos, 30 questões de múltipla escolha, nota, gabarito comentado e acesso às páginas originais dos PDFs. No modo atual, os resultados são enviados por e-mail ao professor, sem login dos alunos e sem banco de notas. Consulte `LEIA_PRIMEIRO.txt` para configurar o envio. O aplicativo só confirma o envio depois da aceitação pelo serviço, que não garante chegada à caixa de entrada.

## Experimentar no computador

Requer Python 3.14 e acesso à internet somente para instalar as dependências. No Mac, abra `INICIAR_DEMO.command`. Também é possível executar no Terminal, dentro desta pasta:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DEMO_MODE=true streamlit run app.py --server.address=127.0.0.1
```

Abra http://localhost:8501. No menu, alterne entre Aluno e Professor para testar. A demonstração usa `data/demo.db`, separado do banco da turma. O modo demonstração permite trocar de perfil e **deve ficar restrito ao computador local**. Sem `DEMO_MODE=true` e sem autenticação configurada, o aplicativo mantém o acesso fechado.

O aluno encontra vídeos antes das animações e da avaliação. Não há bloqueio por tempo assistido. É necessário responder às 30 questões para entregar. Cada questão vale o mesmo; nota = acertos ÷ 30 × 10. Não há corte automático de aprovação. Novas tentativas são permitidas e ficam no histórico. Ao final, o aluno abre cada comentário e marca “Ver slide original” para visualizar a página. As respostas em andamento ficam na sessão; fechar ou recarregar o navegador pode perdê-las. As entregas confirmadas permanecem no banco.

## Materiais incluídos

| Uso | Arquivo no projeto | Fonte |
|---|---|---|
| Aula geral | assets/videos/ombro.mp4 | Reabilitação_do_Ombro.mp4 |
| Aula de atletas preferida | assets/videos/atleta.mp4 | Reabilitação_do_Ombro_no_Atleta.mp4 |
| Slides gerais | assets/pdfs/ombro_v2.pdf | Aula_Reabilitacao_Ombro_v2.pdf, 74 páginas, caminho confirmado pelo professor |
| Slides de atletas | assets/pdfs/atletas_2026.pdf | Reabilitação dos membros superiores 2026.pdf, 69 páginas |

`Reabilitação_dos_MMSS.mp4` e o PDF antigo de atletas não são distribuídos. O sufixo `(1)` citado na solicitação não foi usado como critério de versão: foi utilizado o PDF de 74 páginas confirmado pelo usuário. Os PDFs foram copiados integralmente, sem modificar o conteúdo. `content/sources.json` registra quantidade de páginas e SHA-256. A numeração citada é a página física do PDF, começando em 1.

O banco completo para revisão editorial está em `QUESTOES.md`; a versão estruturada está em `content/questions.json`. São 3 questões de anatomia/biomecânica, 4 de discinese, 7 de dor relacionada ao manguito, 4 de trauma, 4 de artroplastia e 8 de esporte. O gabarito não fica acessível pela interface do aluno antes da entrega. Mantenha o repositório privado, pois o arquivo de conteúdo contém o gabarito.

## Fluxo opcional com login e banco de resultados

As seções abaixo sobre PostgreSQL, autenticação, histórico e painel referem-se ao modo opcional `RESULT_MODE="database"`. No modo padrão `email`, siga `LEIA_PRIMEIRO.txt`; o painel de professor não fica disponível e os resultados existem apenas na sessão e nos e-mails enviados.

### Opção principal: Streamlit Community Cloud + PostgreSQL externo

1. Crie um repositório **privado** com o conteúdo desta pasta. Não inclua `.streamlit/secrets.toml`, `.env`, `data/`, resultados ou arquivos de backup. Os dois vídeos têm menos de 50 MB cada; os PDFs têm cerca de 30 MB cada. Preserve a privacidade do repositório e o controle de acesso aos materiais.
2. Providencie PostgreSQL persistente, com backup e TLS. Crie um banco e uma credencial exclusivos para este aplicativo. A conexão precisa poder criar a tabela `attempts` na primeira inicialização e depois consultar, inserir e excluir seus registros. A URL externa deve exigir TLS (`sslmode=require` ou a configuração mais forte indicada pelo provedor).
3. Configure um cliente OpenID Connect no provedor institucional ou Google, habilitado para fornecer `iss`, `sub`, `email` e `email_verified=true`. Cadastre a URL de retorno `https://SEU-APP.streamlit.app/oauth2callback`. O exemplo usa Google. Provedores sem o atributo booleano de e-mail verificado ficam bloqueados pelo aplicativo; não remova essa verificação sem definir uma validação equivalente.
4. Em Streamlit Community Cloud, selecione o repositório e `app.py`, usando Python 3.14. Nas configurações de segredos, cole a estrutura de `.streamlit/secrets.toml.example` com os valores reais. Use a URL definitiva em `redirect_uri`. Não ative `DEMO_MODE`.
5. Defina `TEACHER_EMAILS` com os professores e `STUDENT_EMAILS` com a lista explícita da turma. Não há inscrição pública nem liberação automática por domínio. Gere dois segredos aleatórios diferentes com `python -c "import secrets; print(secrets.token_urlsafe(48))"`: um para `PSEUDONYM_SECRET` e outro para `auth.cookie_secret`. Guarde-os fora do repositório. Mudar o primeiro altera os códigos de aluno; preserve-o para manter o histórico associado.
6. Restrinja também o acesso ao aplicativo no serviço de hospedagem aos integrantes da turma. O login no código controla as telas e consultas. Para materiais restritos, é importante que a hospedagem ou um proxy de identidade controle **todas** as rotas, inclusive mídia e WebSocket: URLs de mídia já obtidas em uma sessão não devem ser tratadas como proteção de direitos de acesso por si só.
7. Faça o roteiro de homologação abaixo com duas contas de alunos e uma de professor antes de convidar a turma.

O armazenamento local do Streamlit Community Cloud **não garante persistência**. Por isso, o aplicativo exige PostgreSQL quando não está em demonstração. O código não aceita SQLite para os resultados reais da turma. Documentação oficial: [conexões e persistência](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data), [autenticação](https://docs.streamlit.io/develop/concepts/connections/authentication), [publicação](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).

### Alternativa: servidor institucional com Docker

Esta opção precisa de Docker e Docker Compose, não instalados nem testados neste computador.

1. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e configure identidade, listas de acesso e segredos. Em produção, troque a URL de retorno pela URL HTTPS definitiva.
2. Crie `.env` local contendo `POSTGRES_PASSWORD=` seguido de um segredo aleatório forte. Use caracteres alfanuméricos para evitar problemas na URL do exemplo. Esse arquivo é ignorado pelo Git.
3. Execute `docker compose up --build -d`. O Compose configura a conexão ao banco da rede interna e mantém os resultados no volume `resultados`. A porta do PostgreSQL não é publicada. A porta do aplicativo fica vinculada a 127.0.0.1.
4. Coloque o serviço atrás de proxy HTTPS institucional com suporte a WebSocket e controle de identidade cobrindo também as rotas de mídia. Configure domínio e retorno OIDC. Nunca exponha a demonstração.
5. Programe backups do PostgreSQL, restauração testada e retenção institucional. Não use `docker compose down -v`: isso remove o volume de resultados.

O Dockerfile usa usuário sem privilégios administrativos e oferece verificação de saúde. Os materiais permanecem no servidor; não dependem de links públicos de vídeo.

## Dados pessoais e controles de acesso

O banco grava código pseudônimo, data UTC, versão, respostas e nota. Não grava nomes, e-mails, diagnóstico de aluno ou texto livre. O código é calculado a partir da identidade autenticada e de um segredo; **pseudonimização não equivale a anonimização**. O aluno pode informar seu código ao professor para identificação e exclusão. Listas de e-mail ficam na configuração de acesso e o provedor processa o login.

Professores autorizados consultam e exportam todas as tentativas; alunos consultam somente o próprio histórico. A autenticação e a autorização são verificadas antes de acessar os registros. Respostas e gabaritos são avaliados no servidor. CSV usa UTF-8 com BOM, separador `;` e proteção contra fórmulas de planilha. Pode ser aberto no Excel. Há exportação de resumo e de respostas por questão.

O painel permite exclusão por código e aplicação do prazo de retenção (`RETENTION_DAYS`, padrão 180 dias), mediante confirmação. A retenção é aplicada **manualmente pelo responsável**, não por um agendamento oculto. A instituição deve escolher o prazo adequado, comunicar o responsável e aplicar a mesma política aos backups. O aplicativo não solicita dados clínicos dos alunos. Os slides e vídeos originais podem conter imagens e dados de casos clínicos: mantenha-os restritos à turma e confira as permissões de uso antes de disponibilizá-los. As perguntas não reproduzem iniciais, idade exata ou calendário competitivo dos casos.

O aplicativo é de aprendizagem com tentativas repetidas e gabarito posterior. Não oferece fiscalização de prova, bloqueio contra compartilhamento de respostas ou certificação de identidade além do login institucional. A infraestrutura externa e sua configuração também precisam proteger os dados.

## Diferenças de versão e revisão pedagógica

Consulte `REVISAO_CONTEUDO.md`. O PDF de atletas de 2026 prevalece na avaliação esportiva. O caso da nadadora é **sem rotura**. Há aviso antes das questões e no comentário correspondente. Percentuais de luxação anterior variam entre os PDFs; nenhuma questão cobra esses percentuais. Os esquemas não apresentam compressão como explicação única da dor.

Não foi feita uma transcrição e comparação integral dos áudios dos vídeos. O aviso de versão permanece visível para não sugerir que todas as diferenças foram verificadas. O professor deve conferir os dois vídeos e aprovar o conteúdo clínico antes de aplicar a avaliação à turma. Não é necessário alterar o código para revisar o banco JSON, mas a versão deve ser incrementada e as páginas precisam ser conferidas novamente.

Cada entrega guarda uma cópia da versão das questões, das respostas e das referências. Trocar o banco não altera notas antigas. Se mudar os PDFs, os slides antigos deixam de ser exibidos quando o SHA-256 divergir; os comentários e as notas originais continuam preservados. Para manter revisão visual de provas antigas, mantenha a edição dos PDFs usada naquela turma ou amplie o projeto para um acervo por versão.

## Testes automáticos

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Os testes usam dados sintéticos e bancos temporários: acertos e validação de respostas, identidade e permissões, gravação concorrente e idempotente, isolamento por aluno, exclusão/retenção, exportação e proteção contra fórmulas, integridade dos PDFs, navegação da prova inteira, entrega, nota, visualização de um slide e painel do professor. A execução local passou com 8 testes. A interface das quatro animações foi revisada em navegador, inclusive em largura de 390 px. O fluxo real do provedor OIDC, o PostgreSQL externo, o build Docker e a hospedagem ainda precisam de homologação no ambiente escolhido.

## Roteiro de homologação da publicação

- Entrar com conta não autorizada: nenhuma aula, questão ou resultado deve ser liberado.
- Entrar com aluno A: não deve existir opção de professor. Assistir aos dois vídeos, testar áudio e avanço, alternar as quatro animações e usar pausa/reinício/barra de tempo.
- Abrir a avaliação: verificar que o aviso de dados é exibido, que não existe gabarito e que a entrega incompleta permanece bloqueada. Responder, navegar para trás, verificar a preservação das escolhas e entregar.
- Ver nota e conferir manualmente pelo menos um acerto e um erro com os slides originais. Reabrir o aplicativo e confirmar o histórico entregue.
- Entrar com aluno B: o resultado do aluno A não deve aparecer.
- Entrar com professor: conferir tentativas, médias, filtro por código e os dois CSVs. Abrir os arquivos no Excel e comparar contagens.
- Reiniciar o serviço/hospedagem: confirmar que os dados PostgreSQL continuam disponíveis. Simular indisponibilidade de banco em ambiente de teste e confirmar que a entrega não é apresentada como concluída.
- Em uma cópia de teste, aplicar exclusão e retenção; confirmar que backups podem ser restaurados e seguem o prazo escolhido.
- Testar celular, teclado e permissões de acesso de toda a hospedagem, incluindo mídia.
