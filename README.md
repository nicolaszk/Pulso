# Pulso — Backend

9ª Hackatona de Engenharia de Software 2026 (Fin-x, PUCRS, Hospital São Lucas), Desafio 1: Priorização Inteligente da Fila Cirúrgica.

## Situação

O pipeline funciona de ponta a ponta sobre o dataset completo (backend/), com a API usada pelo frontend, as explicações em linguagem clara e a máquina do tempo.
Ainda não feito: JEV no pipeline, os agentes de monitoramento, DECISOES.md (veja [ideas/ROADMAP.md](ideas/ROADMAP.md)).

## Rodar (máquina limpa)

Precisa só do Docker.

    docker compose up -d --build

A primeira subida leva cerca de um minuto: o container `api` espera o Postgres, roda `python -m src.pipeline rodar --se-vazio` (CSVs -> limpeza -> eventos -> Postgres -> eventos um a um) e sobe a API. Nas subidas seguintes o banco já está carregado e esse passo é pulado.

- API: http://localhost:8000/docs (o CORS libera o frontend nas portas 5173 e 5174 de `localhost` e `127.0.0.1`; para outros endereços, use `PULSO_CORS` com as origens separadas por vírgula)
- Acompanhar a carga: `docker compose logs -f api`
- Recarregar os dados do zero (apaga o banco, inclusive as decisões tomadas): `docker compose exec api python -m src.pipeline rodar --recriar`
- Estado da demo (a subida acima processa todos os eventos, então a caixa do médico fica com os 128 pedidos e o botão de processar eventos não tem mais nada): carregue de novo e processe só até a caixa ter 3 pedidos, deixando os outros eventos pendentes:

      docker compose exec api python -m src.pipeline carregar --recriar --ate-pedidos 3

- Explicações sem texto em cache são geradas na hora pelo Ollama que roda na sua máquina (`PULSO_LLM_URL` no docker-compose.yml aponta o container para ele). Sem o Ollama ou sem o modelo (`ollama pull gemma4:e4b`), vale o texto padrão (template). Veja "Explicações em linguagem clara" abaixo.
- Zerar tudo, inclusive o volume: `docker compose down -v`
- Frontend: veja [../Pulso-Frontend](../Pulso-Frontend). A entrada do médico usa um CRM de `GET /medicos` (ex.: `CRM-RS 900001`) e qualquer senha com 4+ caracteres.

Sem Docker para a API (precisa de Python 3.10+; o Postgres continua vindo do Docker):

    docker compose up -d db
    python3 -m venv .venv && . .venv/bin/activate
    pip install -r backend/requirements.txt
    cd backend
    python -m src.pipeline rodar --recriar     # CSVs -> limpeza -> eventos -> Postgres -> eventos um a um (~7 s)
    # ou, para a demo: carrega e processa eventos só até a caixa do médico ter 3 pedidos;
    # o resto fica pendente para o botão de processar eventos (POST /eventos/processar)
    python -m src.pipeline carregar --recriar --ate-pedidos 3
    python -m src.pipeline exportar            # saida/fila_priorizada.csv
    python ../ideas/data/dataset/verificar_fila_priorizada.py saida/fila_priorizada.csv
    uvicorn src.main:app --reload              # API: http://localhost:8000/docs
    python -m pytest                           # usa um banco separado, pulso_teste

No Windows (cmd), as linhas de preparação são `python -m venv .venv` e `.venv\Scripts\activate` (PowerShell: `.venv\Scripts\Activate.ps1`); rode antes `set PYTHONUTF8=1` para os arquivos com acento serem lidos em UTF-8.

Se o `uvicorn` local e o container `api` rodarem juntos, os dois ocupam a porta 8000 (um em IPv4, outro em IPv6) e as requisições podem cair em qualquer um; rode só um (`docker compose stop api` deixa só o banco no Docker).

## API

Lista completa, com os formatos de entrada e saída, em http://localhost:8000/docs.

| Rota | O que devolve ou faz |
|---|---|
| `GET /resumo` | Contagens: solicitações por situação, eventos processados/pendentes/em quarentena, tamanho de cada nível, pedidos de mudança por tipo/situação, prazo estourado, conferência da regra de ouro |
| `GET /fila?modo=oficial\|recomendada` | A fila com posição, nível, data limite, justificativa e dados do paciente e do procedimento (`limite` até 1000) |
| `GET /solicitacoes/{id}` | Uma solicitação: paciente, eventos, estado do motor, marcações, pedidos de mudança e histórico de decisões |
| `GET /mudancas?status=pendente\|todas` | A caixa do médico; `com_explicacao=true` inclui o texto em linguagem clara já gerado |
| `POST /mudancas/{id}/decisao` | `{"decisao": "aprovar"\|"rejeitar", "medico_id": 1, "motivo": "..."}`; rejeitar exige motivo |
| `GET /solicitacoes/{id}/explicacao`, `GET /mudancas/{id}/explicacao` | Explicação em linguagem clara (LLM, com o template como reserva); `gerar=false` só lê o cache |
| `POST /eventos` | Registra um evento clínico novo e o processa na hora |
| `POST /eventos/processar?limite=N` | Processa os próximos N eventos pendentes; a resposta diz quantos pedidos novos foram abertos (`aberta`) |
| `GET /marcacoes?severidade=` | Marcações do motor que pedem olho humano, das mais graves para as menos |
| `GET /pendencias` | Pendências operacionais (contato, faltas, HbA1c, saídas a confirmar) |
| `GET /dados` | Relatório da carga, eventos em quarentena, solicitações fora da fila |
| `GET /maquina-tempo` | Manchete da máquina do tempo (veja abaixo) |
| `GET /medicos` | Médicos (a entrada do frontend procura pelo CRM) |
| `GET /export/fila_priorizada.csv?modo=` | O CSV entregável (`com_explicacao=true` usa o texto do LLM onde houver) |

## Pipeline (backend/src/pipeline)

| Passo | Código | O que faz |
|---|---|---|
| 1 leitura | fila_cirurgica/priorizacao/carga.py | os 3 CSVs como vieram + sha256 |
| 2 limpeza | fila_cirurgica/priorizacao/limpeza.py | CID, prioridade, município; 22 duplicatas fundidas na mais antiga; 17 saídas registradas em observacoes; 9 eventos órfãos em quarentena, 7 repetidos descartados |
| 3 eventos | carga.py | 1.489 eventos válidos, ligados à solicitação mestre, entram como pendentes |
| 4 banco | carga.py, db/schema.sql | catálogos, pacientes, solicitações, eventos; fila inicial = cada solicitação ativa triada só pelo cadastro (sem eventos) |
| 5 processamento | processamento.py | eventos pendentes um a um, por data: retria o paciente com todos os eventos já processados; se o motor quer outro nível (ou o evento é uma saída), abre uma solicitacao_mudanca para um médico |

- A fila oficial (fila_priorizada) só muda quando um médico aprova um pedido: `POST /mudancas/{id}/decisao` ou `python -m src.pipeline decidir ID aprovar --medico 1`. Rejeitar exige um motivo escrito. Dentro do mesmo nível, os desempates e a justificativa acompanham os eventos sem precisar de pedido.
- Cada aprovação renumera a fila e confere de novo a regra de ouro na mesma transação; se falhar, nada muda. Um CID C* nunca é rebaixado (no código e com CHECK no banco).
- fila_recomendada (view) é a fila como se todos os pedidos fossem aprovados; `exportar` gera ela por padrão (`--modo oficial` para a oficial). Ela bate posição a posição com o motor em lote (test_recomendada_igual_ao_lote_do_motor).
- Motor (níveis G1a-G7, sinais, negação, classificadores): [fila_cirurgica/README.md](fila_cirurgica/README.md). Banco: [db/README.md](db/README.md). build_features.py preenche features_paciente (para o JEV e o detalhe do paciente).

### Explicações em linguagem clara (LLM, opcional)

backend/src/pipeline/explicacao.py: um LLM reescreve os fatos do motor (nível, data limite, espera, evidências com datas e trechos, alertas, pendências, pedido aguardando o médico) em 2 ou 3 frases. Ele nunca muda a fila.
Depois de cada resposta, uma conferência determinística recusa qualquer número ou data, código ou nome de nível, ou termo oncológico que não esteja nos fatos, e também "não há pendências/alertas" quando os fatos têm alguns; há uma nova tentativa com o motivo e, se falhar de novo, vale o texto do template. Os textos ficam em cache na tabela `explicacao`, pela hash dos fatos (mesmos fatos, mesmo texto; um evento novo gera outro).

    OLLAMA_NUM_PARALLEL=4 ollama serve && ollama pull gemma4:e4b   # local (padrão); ou PULSO_LLM_PROVIDER=groq + GROQ_API_KEY
    python -m src.pipeline explicar mudancas --limite 0    # caixa do médico inteira (128 pedidos, ~8 min)
    python -m src.pipeline explicar fila --limite 50       # topo da fila (--limite 0 = todos os 897, ~1 h)
    python -m src.pipeline exportar --explicacao           # justificativa = texto do LLM onde houver

Modelo (local, até 4B, mesma amostra de 16 textos, M3 Pro): gemma4:e4b (padrão, 4B efetivos), cerca de 4 s por texto com 4 em paralelo e o menor número de erros;
gemma4:e2b, cerca de 2 s por texto, mais erros, a maioria pega pela conferência e corrigida na nova tentativa (`PULSO_LLM_MODEL=gemma4:e2b`).
llama3.2, qwen3:4b e gemma3:4b passaram na conferência, mas escreveram coisas erradas que ela não consegue ver (posição lida como nível, "sem pendências" quando havia, CID ligado ao diagnóstico errado).

Os textos gerados ficam versionados em db/explicacoes.jsonl (fatos de entrada + texto + modelo): `rodar --recriar` importa esse arquivo, então um clone ou uma recarga não precisam de LLM para este dataset.
`explicar` atualiza o arquivo; textos gerados na hora pela API são salvos com `python -m src.pipeline salvar-explicacoes`.

### Máquina do Tempo (impacto medido)

`fila_cirurgica/maquina_tempo/` (módulo irmão de `priorizacao`): rebobina o log de eventos e reavalia cada paciente a cada novo evento. Mede quantos pacientes o motor teria promovido de fila durante a espera e o gap com a prioridade manual. Determinístico, sem vazamento de futuro, não toca na fila oficial.

    cd fila_cirurgica && python -m maquina_tempo            # manchete + top casos
    python -m maquina_tempo --caso SOL-2025-00478           # linha do tempo de 1 paciente

API: `GET /maquina-tempo` serve a mesma manchete (em cache; o dataset é estático).

## Entregáveis

- [X] Repositório público com o histórico de commits do evento (até as 18h de sábado, 24/10)
- [X] Este README roda a solução numa máquina limpa
- [X] DECISOES.md: abordagem, usuário principal, por quê, o que ficou de fora de propósito
- [X] Solução funcionando sobre o dataset completo
- [X] fila_priorizada.csv (solicitacao_id, posicao, justificativa), passando em `python ideas/data/dataset/verificar_fila_priorizada.py fila_priorizada.csv` (meta: 14h)
- [ ] Pitch de 5 minutos às 19h
