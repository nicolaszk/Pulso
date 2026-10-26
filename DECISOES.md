# Pulso: decisões e documentação técnica

Priorização da fila de cirurgias eletivas (Desafio 1, 9ª Hackatona · Fin-x · PUCRS · Hospital São Lucas).

- **Parte I · Decisões:** abordagem, usuário, por quê e o que ficou de fora.
- **Parte II · Documentação técnica:** arquitetura, módulos, banco, API, LLM, frontend, configuração, execução e testes.

---

# Parte I · Decisões

**Abordagem:** motor de regras determinístico, que reavalia o paciente a cada evento clínico e propõe mudanças de nível. O médico regulador aprova ou rejeita cada proposta. O LLM só reescreve, em linguagem clara, fatos que o motor já calculou.

## Usuário

| Usuário | O que faz no Pulso | Por quê |
|---|---|---|
| **Médico regulador** (principal) | Revisa a caixa de pedidos de mudança, aprova ou rejeita com motivo escrito e consulta a fila e cada paciente (com as marcações e pendências dele) | É quem responde pela fila. O sistema propõe e ele decide; nenhuma mudança de nível acontece sem ele. |
| Paciente (secundário) | Consulta só o próprio encaminhamento: nível, posição na fila, situação e tempo de espera | Transparência sem expor a fila de terceiros. |

## Abordagem, por camada

### 1. Limpeza (`fila_cirurgica/priorizacao/limpeza.py`)

- **Nada é apagado.** Cada solicitação recebe um status (`ativa`, `duplicata`, `saiu`) com o motivo. Eventos rejeitados vão para a quarentena com a causa.
- **Duplicatas** (22, mesmo paciente e procedimento): fundidas na solicitação mais antiga, que tem o tempo de espera real. Os eventos são remapeados para ela.
- **Saídas** registradas só no texto (17) saem da fila com a evidência. Os eventos de saída durante a espera (5) viram pedido `sair` para o médico.
- **"Não deseja operar no momento"** sem contato registrado continua ativa: a desistência precisa ser confirmada antes.
- CID sem ponto e em maiúsculas; prioridade sem acento; município na grafia mais comum (62 → 38).
- 9 eventos órfãos vão para a quarentena; 7 duplicados são descartados.
- **Flags manuais** (`flag_oncologico`, `flag_piora`, `flag_diabetico`) não entram na decisão. Elas erram com frequência; o motor recalcula a partir de CID, eventos e texto, e a divergência vira marcação `flag_divergente`.

**Por quê:** a limpeza fica auditável (cada correção vai para o relatório da carga) e nenhum caso some sem explicação.

### 2. Motor de priorização (`fila_cirurgica/priorizacao`)

- **8 níveis**, adaptados do SWALIS, em ordem fixa (G1 se divide em G1a e G1b; para o paciente, os dois aparecem como "nível 1 de 7"). Cada nível tem um prazo:

  | Nível | Critério | Prazo |
  |---|---|---|
  | G1a | Oncológico em progressão | 15 d |
  | G1b | Agudo não oncológico | 15 d |
  | G2 | Oncológico confirmado | 21 d |
  | G3 | Suspeita oncológica | 60 d |
  | G4 | Deterioração recente | 60 d |
  | G5 | Alta carga de sintomas | 60 d |
  | G6 | Sintomático moderado | 180 d |
  | G7 | Eletivo estável | 360 d |

- **Regra de ouro por construção:** todo CID `C*` (e toda biópsia positiva) cai em G1a ou G2, acima de qualquer paciente sem urgência. A regra é conferida de novo na saída; se for violada, nada é gravado.
- **Texto livre** é lido por termos com tratamento de negação, frase a frase: "sem sinais de encarceramento" não conta como encarceramento. Por isso as 10 hérnias K40.9 com essa frase ficam fora de G1b.
- **Ordem dentro do nível** = (data limite efetiva, nº de sinais ↓, dor ↓, data de entrada, id). A data limite é a entrada mais o prazo do nível; quem está mais atrasado vem primeiro.
- **Classificadores plugáveis** (`classificadores/`) devolvem só a data limite, nunca uma posição. O orquestrador valida o contrato, aplica os limites e usa o plano B por paciente se algo falhar.
- **Versão das regras** (`REGRAS_VERSAO`): mesma entrada + mesma data + mesma versão = mesma fila. A fila é determinística e reproduzível.
- **Marcações** (revisão humana) e **pendências** (operacionais) saem da mesma triagem:
  - marcações: `atualizar_cid` (biópsia positiva com CID não oncológico, 23 casos), `conflito_laudos`, `somente_texto`, `texto_antigo`, `confirmar_saida_g4`, `dados_faltantes`;
  - pendências: `nao_atendeu_2x`, `faltas_2x`, `hba1c_alta`, `sem_contato`.

**Por quê:** o dataset não tem desfecho para treinar nem calibrar pesos. Regras explícitas são auditáveis, cada posição tem a justificativa do motor e a regra de ouro vale por construção, sem depender de modelo.

### 3. Eventos e decisão humana (`backend/src/pipeline`)

- **Carga:** cada solicitação ativa é triada só pelo cadastro, e isso forma a fila oficial inicial. Os 1.489 eventos válidos entram como pendentes.
- **Processamento:** os eventos são processados um a um, por data. A cada evento, o paciente é reavaliado com todos os eventos até aquela data, sem vazamento de futuro. Se o motor quer outro nível, abre um `solicitacao_mudanca` com as evidências; se o nível não muda, só o desempate e a justificativa se atualizam.
- **Fila oficial × recomendada:** a fila oficial (`fila_priorizada`) só muda quando o médico aprova. A recomendada (view `fila_recomendada`) é a ordem do motor com todos os pedidos aprovados.
- **Travas:**
  - cada aprovação renumera a fila e reconfere a regra de ouro na mesma transação; se falhar, nada muda;
  - CID `C*` nunca é rebaixado (no código e com `CHECK` no banco);
  - rejeitar exige motivo escrito;
  - um pedido novo substitui o pendente do mesmo paciente.
- **Resultado no dataset:** 1.225 eventos sem mudança de nível; 136 pedidos abertos, 8 substituídos por evidência mais forte; 128 à espera do médico (123 para subir, 5 para sair).

**Por quê:** a fila tem histórico e cada mudança tem dono e motivo. O motor pode errar sem que o erro chegue à fila oficial.

### 4. Explicação em linguagem clara (`backend/src/pipeline/explicacao.py`)

- O LLM recebe os **fatos** do motor (nível, prazo, espera, evidências com data, alertas, pendências, pedido aberto) e devolve de 2 a 3 frases. Não decide e não muda a ordem.
- **Conferência determinística** recusa o texto que traga número, data, nível ou termo oncológico fora dos fatos, ou que diga "sem pendências" quando há. Há uma nova tentativa com o motivo; se falhar de novo, vale a justificativa do motor.
- **Modelo local** de até 4B (gemma4:e4b via Ollama). Os dados de saúde não saem da máquina e não há custo por chamada.
  - Na mesma amostra, llama3.2, qwen3:4b e gemma3:4b passaram na conferência, mas erraram o que ela não pega: leram posição como nível e atribuíram o CID ao diagnóstico errado.
  - Provedores hospedados (Groq, Gemini, OpenRouter) são opcionais.
- **Cache pelo hash dos fatos:** os mesmos fatos dão o mesmo texto. Os textos ficam versionados em `db/explicacoes.jsonl`, então um clone não precisa de LLM. Sem texto em cache, a API gera na hora; sem LLM no ar, volta para a justificativa do motor.

**Por quê:** a justificativa técnica é precisa, mas difícil de ler. O LLM entra só onde ajuda a leitura, e a conferência impede que ele invente.

### 5. Máquina do Tempo (`fila_cirurgica/maquina_tempo`)

- Replay determinístico do log de eventos: cada paciente é reavaliado a cada evento, só com o que se sabia naquela data. O módulo não toca na fila oficial nem no banco.
- Mede o que o motor teria feito durante a espera:
  - 123 pacientes promovidos de nível, 100 deles com prioridade manual baixa ou média;
  - mediana de 66 dias desde a primeira promoção;
  - 33 oncológicos com prioridade manual baixa.
- A antecipação de PS ou internação (3 de 103) é reportada como secundária, porque o n é pequeno.

**Por quê:** é uma medida retrospectiva do ganho sobre a regulação manual, sem precisar de desfecho real.

### 6. Persistência e API

- **PostgreSQL 16**, que guarda o registro imutável (solicitações, eventos com `processado_em`), o estado do motor por paciente, os pedidos, o histórico da fila e as explicações.
- **FastAPI**, com docker compose: banco + API, carregando o dataset na primeira subida.
- **Entregável:** `GET /export/fila_priorizada.csv` ou `python -m src.pipeline exportar` (a fila recomendada, com 897 posições). O verificador oficial passa: regra de ouro respeitada, com o último oncológico na posição 265 e o primeiro paciente sem urgência na 266. As 44 solicitações fora do arquivo são 22 duplicatas, 17 saídas e 5 pedidos de saída; os 5 oncológicos entre elas são duplicatas, e a solicitação original de cada um está na fila.

### 7. Frontend (`Pulso-Frontend`)

- **Área profissional:** visão geral, fila, paciente (com marcações e pendências) e revisão humana (caixa de pedidos com evidências, explicação e posição estimada, e o botão "Processar até novo pedido", que lê os eventos um a um e para quando surge um pedido novo). Lê e decide direto na API.
- **Área pública:** o paciente consulta o próprio encaminhamento (nível, posição na fila, situação e tempo de espera).
- **`/pipeline`:** a página mostra o pipeline por dentro, com os dados reais (limpeza, motor, eventos, decisão, Máquina do Tempo, recibos).

## O que ficou de fora, de propósito

| Fora | Por quê |
|---|---|
| **LLM decidindo nível, risco ou ordem** | Testamos o LLM como avaliador (experimento JEV, com Ollama). Em amostras de 20 pacientes: AUC 0,46–0,53 para piora em 90 dias, contra 0,525 da prioridade manual, e o medgemma colocou 10 de 10 pacientes sem urgência em A2. Não é reproduzível nem auditável o suficiente para ordenar uma fila. |
| **Modelo de risco treinado (JEV com regressão logística)** | Não há desfecho real. O rótulo proxy (piora em 90 dias) tem 158 positivos, e os eventos se concentram perto da data de referência, então o modelo se apoiaria em atributos estáticos. Ficou como trabalho futuro, nunca como peso na ordem. |
| **Score ponderado 0–100 dentro do nível** | Pesos sem desfecho para calibrar seriam arbitrários. O prazo vencido é critério clínico já aceito (SWALIS) e explicável. |
| **Prioridade manual e flags manuais como entrada** | Erram com frequência. Servem só de linha de base (Máquina do Tempo) e para marcar divergências. |
| **Município, distância, idade e sexo na ordem** | Equidade: o lugar na fila não depende de onde a pessoa mora nem de quem ela é, só de dado clínico. |
| **Rebaixamento e saída automáticos** | Só pedidos para o médico. Desistência sem contato confirmado continua na fila. |
| **Agendamento de sala, pré-operatório e cancelamentos** | Fora do escopo do desafio (priorização). A HbA1c alta só vira pendência de preparo. |
| **Autenticação real** | O CRM identifica quem decide, para o histórico. Login de verdade é infraestrutura, não o problema do desafio. |
| **Consulta pública ligada à API** | O dataset não tem CPF nem data de nascimento; a tela pública usa dados locais de exemplo. |
| **LLM hospedado por padrão** | Dados de saúde: o padrão é local. Provedor hospedado só por escolha explícita (`PULSO_LLM_PROVIDER`). |

---

# Parte II · Documentação técnica

## 1. Arquitetura

```mermaid
flowchart LR
  CSV[CSVs do desafio<br/>ideas/data/dataset] --> CARGA
  subgraph Backend [Pulso-Backend · Python 3.12]
    CARGA[carga.py<br/>limpeza + triagem só pelo cadastro] --> PG[(PostgreSQL 16)]
    PROC[processamento.py<br/>evento a evento] --> PG
    MOTOR[[fila_cirurgica/priorizacao<br/>motor de regras, puro]] -.-> CARGA
    MOTOR -.-> PROC
    FILA[fila.py<br/>decisão + renumeração] --> PG
    EXP[explicacao.py<br/>fatos → LLM → conferência] --> PG
    API[FastAPI · main.py] --> CONS[consultas.py] --> PG
    API --> FILA
    API --> PROC
    API --> EXP
    MT[[fila_cirurgica/maquina_tempo<br/>replay]] -.-> API
  end
  EXP <--> LLM[Ollama local<br/>gemma4:e4b]
  WEB[Pulso-Frontend<br/>React 19 + Vite] -- HTTP/JSON --> API
```

- **Dois repositórios:** `Pulso-Backend` (motor, pipeline, banco e API) e `Pulso-Frontend` (SPA).
- **O motor é uma biblioteca pura,** sem banco e sem rede. O backend a importa por paciente (`avaliacao.avaliar`) para a carga, o processamento de eventos e a varredura. A Máquina do Tempo usa as mesmas funções em replay.
- **O backend é o dono do estado.** Guarda a fila oficial, o que o motor recomenda, os pedidos, as decisões, o histórico e as explicações. O frontend só lê e chama ações.

## 2. Estrutura do repositório (`Pulso-Backend`)

| Pasta | Conteúdo |
|---|---|
| `fila_cirurgica/priorizacao/` | Motor: `carga` (lê os CSVs + sha256), `limpeza`, `texto` (busca com negação), `sinais` (`montar_estado`), `triagem` (`triar`), `classificadores/` (data limite), `saida` (ordem, regra de ouro, justificativa), `config` (regras + `REGRAS_VERSAO`), `banco` (SQLite da CLI standalone) |
| `fila_cirurgica/maquina_tempo/` | `motor` (reavaliação incremental por evento), `replay` (carga e posição numa data), `metricas` (promoções, antecipação, consistência), CLI |
| `backend/src/` | `config` (env), `db` (conexão psycopg), `llm` (cliente OpenAI-compatível), `main` (FastAPI) |
| `backend/src/pipeline/` | `carga`, `avaliacao`, `processamento`, `fila`, `consultas`, `explicacao`, CLI (`__main__`) |
| `backend/tests/` | Testes de integração com Postgres (banco `pulso_teste`) |
| `db/` | `schema.sql`, `seed.sql` + `gerar_seed.py` (caminho só SQL), `explicacoes.jsonl` (textos do LLM versionados) |
| `ideas/` | Dataset do desafio, verificador oficial, `build_features.py` (features por paciente) e notas de planejamento |
| `resultados/` | `fila_priorizada.csv` (+ versão com explicação) e métricas do verificador |

## 3. Stack

| Camada | Escolha | Motivo |
|---|---|---|
| Motor | Python + pandas, funções puras | Determinístico, testável por paciente, sem estado |
| Banco | PostgreSQL 16 | Transações para decisão + renumeração, `CHECK` e índice parcial como travas, views, `jsonb` para evidências |
| API | FastAPI + psycopg 3 | Tipagem dos corpos (pydantic), docs em `/docs`, SQL direto (sem ORM) |
| LLM | Ollama local (`gemma4:e4b`), cliente `openai` | Uma interface para local e hospedado (Groq, Gemini, OpenRouter) |
| Frontend | React 19, React Router 7, Tailwind 4, Vite, TypeScript | SPA leve, sem biblioteca de estado |
| Execução | Docker Compose (`db` + `api`) | Um comando sobe banco, carga e API |

## 4. Fluxo de dados

| Passo | Onde | O que acontece |
|---|---|---|
| 1. Leitura | `priorizacao/carga.py` | Os 3 CSVs como vieram + sha256 de cada um (registrados em `execucao`) |
| 2. Limpeza | `priorizacao/limpeza.py` | Normaliza, funde duplicatas, marca saídas e põe eventos inválidos em quarentena; o relatório vai para `execucao.relatorio` |
| 3. Carga | `pipeline/carga.py` | Catálogos, pacientes, solicitações e eventos (todos com `processado_em` vazio); `fila_priorizada` inicial = triagem só pelo cadastro; importa `db/explicacoes.jsonl` |
| 4. Processamento | `pipeline/processamento.py` | Eventos pendentes por (data, id). Para cada um: `avaliar` o paciente com os eventos até aquela data → grava `estado_paciente` → `reconciliar` com a fila oficial |
| 5. Reconciliação | `processamento.reconciliar` | Mesmo nível: atualiza o desempate e a justificativa e renumera (sem pedido). Outro nível ou saída: abre, atualiza ou substitui o `solicitacao_mudanca` pendente. Rebaixar `C*` nunca. |
| 6. Decisão | `pipeline/fila.py` | Aprovar: aplica o nível, renumera, reconfere a regra de ouro e grava `fila_historico`, tudo numa transação. Rejeitar: exige motivo. |
| 7. Varredura | `processamento.varrer` | Reavalia a fila inteira numa data (sinais que expiram, prazos que vencem); rodada diária |
| 8. Saída | `consultas.csv_fila` | `fila_priorizada.csv` (modo `recomendada` por padrão, ou `oficial`) |

**Ordem da fila,** a mesma no Python e no SQL: `(ordem do nível, data_limite_efetiva, n_sinais DESC, dor DESC, data de entrada, id)`. `saida._chave_ordem` e `fila.ORDEM_SQL` implementam a mesma chave. O teste `test_recomendada_igual_ao_lote_do_motor` garante que a view `fila_recomendada` bate posição a posição com o lote do motor.

## 5. Motor (`fila_cirurgica/priorizacao`)

- **`montar_estado(solicitacao, eventos, data)`** é uma função pura. Extrai os sinais do CID, dos eventos até a data e do texto, e devolve um `Estado` com malignidade, piora recente, dor, limitação, sinais com evidência, data de entrada e outros campos.
- **`triar(estado, data)`** decide o nível (G1a–G7) e devolve motivos, marcações, pendências e próxima revisão. Invariante: maligno ⇒ G1a ou G2.
- **Classificadores** (`classificadores/`): cada nível tem um classificador registrado em `REGISTRO`.
  - O contrato é `avaliar(pacientes, data) → data_limite_efetiva`, nunca uma posição.
  - O orquestrador (`base.py`) valida ids e limites e aplica o plano B por paciente.
  - Padrão (`prazo_padrao`): data limite = entrada + prazo do nível.
- **Texto** (`texto.py`): normaliza (minúsculas, sem acento) e busca termos frase a frase. Um termo não conta se um negador (`NEGACAO_ANTES`) aparece até 3 palavras antes dele.
- **Versionamento:** qualquer mudança em `config.py` exige subir `REGRAS_VERSAO` (hoje 2.0.0), que é gravada em cada `execucao`.
- **CLI standalone** (gera `saida/` + SQLite, sem Postgres): `python -m priorizacao carga --dataset ../ideas/data/dataset --data-referencia 2026-10-23 --saida saida/ --recriar`.

## 6. Banco (`db/schema.sql`)

| Grupo | Tabelas / views | Papel |
|---|---|---|
| Catálogos | `especialidade`, `hospital`, `medico`, `procedimento`, `swalis_classe`, `fila_grupo` | Domínio. `fila_grupo` guarda os 8 níveis com ordem, prazo e classe SWALIS. |
| Entrada | `paciente`, `solicitacao`, `evento_clinico` | Registro do dataset. `solicitacao.status` ∈ {ativa, duplicata, saiu} com `duplicata_de`. `evento_clinico.processado_em` vazio = evento pendente. |
| Execução | `execucao`, `evento_quarentena` | Cada carga, processamento ou varredura com a versão das regras, os hashes e o relatório; eventos rejeitados com o motivo |
| Motor | `estado_paciente`, `features_paciente` | O que o motor recomenda hoje para cada ativa (nível, data limite, sinais, evidências, marcações, pendências); features para o detalhe do paciente |
| Fila e decisão | `fila_priorizada`, `solicitacao_mudanca`, `fila_historico` | Fila oficial (`posicao_inicial` manual × `posicao_final`); pedidos com evidências e status; cada mudança aplicada, com o médico |
| LLM | `explicacao` | Texto por (alvo, id, hash dos fatos, provedor, modelo); status `ok` ou `rejeitada` com o motivo |
| Views | `fila_recomendada`, `solicitacao_ativa` | Ordem do motor com todos os pedidos aprovados; ativas com `dias_em_fila` e `oncologico` |

**Travas no banco:**
- `CHECK (NOT (oncologico AND tipo = 'descer'))`: nenhum `C*` é rebaixado;
- índice único parcial `mudanca_pendente_uidx`: no máximo um pedido pendente por solicitação;
- `CHECK` de domínio nos status e tipos.

## 7. API (`backend/src/main.py`)

Docs interativas em `http://localhost:8000/docs`. CORS liberado para `PULSO_CORS`.

| Método e rota | Uso |
|---|---|
| `GET /resumo` | Contagens por nível (oficial × recomendada), eventos, pedidos, regra de ouro |
| `GET /fila?modo=oficial\|recomendada&fila=&limite=&offset=` | Fila paginada, com nome, idade e procedimento |
| `GET /solicitacoes/{id}` | Detalhe: cadastro, estado do motor, eventos, pedidos, features |
| `GET /solicitacoes/{id}/explicacao?gerar=` | Explicação do paciente: cache, ou gera com o LLM, ou template |
| `GET /mudancas?status=pendente\|todas&com_explicacao=` | Caixa do médico. `posicao_proposta` = se só este for aprovado (gravada no evento); `posicao_recomendada` = na fila recomendada de agora |
| `GET /mudancas/{id}` · `GET /mudancas/{id}/explicacao` | Pedido e a explicação dele |
| `POST /mudancas/{id}/decisao` | `{decisao: aprovar\|rejeitar, medico_id, motivo}`; 409 se for inválida ou se violaria a regra de ouro |
| `POST /eventos` | Evento novo: registra e processa na hora |
| `POST /eventos/processar?limite=N` | Tira os próximos N eventos pendentes (demo passo a passo) |
| `GET /pendencias` · `GET /marcacoes?severidade=` | Pendências operacionais e marcações do motor |
| `GET /dados` | Relatório da carga, quarentena e solicitações fora da fila |
| `GET /medicos` | Médicos (o CRM identifica quem decide) |
| `GET /maquina-tempo` | Manchete da Máquina do Tempo (em cache por dataset e data) |
| `GET /export/fila_priorizada.csv?modo=&com_explicacao=` | Entregável |

## 8. CLI do pipeline (de `backend/`)

```bash
python -m src.pipeline rodar --recriar                   # carga + todos os eventos
python -m src.pipeline carregar --recriar --ate-pedidos 3 # demo: para quando a caixa tiver 3 pedidos
python -m src.pipeline processar [--limite N | --ate-pedidos N]
python -m src.pipeline mudancas [--status pendente|todas]
python -m src.pipeline decidir ID aprovar|rejeitar --medico 1 [--motivo "..."]
python -m src.pipeline aprovar-todas --medico 1          # fila oficial = recomendada
python -m src.pipeline varrer [--data AAAA-MM-DD]
python -m src.pipeline explicar mudancas|fila [--limite N] [--paralelo 4]
python -m src.pipeline salvar-explicacoes                # grava db/explicacoes.jsonl
python -m src.pipeline exportar [--modo recomendada|oficial] [--saida ...] [--explicacao]
python -m src.pipeline resumo
```

## 9. Explicações por LLM (`backend/src/pipeline/explicacao.py`, `backend/src/llm.py`)

1. **Fatos:** `fatos(alvo, id)` monta um texto com nível, prazo, espera, motivo técnico, até 6 eventos recentes, evidências, alertas, pendências e o pedido aberto.
2. **Chave:** `sha256(VERSAO + prompt de sistema + fatos)`. Um evento novo muda os fatos e invalida o texto.
3. **Busca, em ordem:**
   - texto `ok` em cache;
   - recusa anterior do mesmo modelo para esses fatos (nesse caso vale o template, sem chamar de novo);
   - chamada ao LLM (JSON, temperatura 0).
4. **Conferência** (`conferir`): o texto é recusado se tiver mais de 400 caracteres ou trouxer número, código ou nome de nível, termo oncológico ou negação de pendência que não esteja nos fatos. Há uma nova tentativa com o motivo; se falhar de novo, grava `rejeitada` e vale o template.
5. **LLM fora do ar** (`LLMIndisponivel`): responde com o template e não grava nada; a próxima chamada tenta de novo.
6. **Persistência:** `salvar_cache` grava os textos aceitos em `db/explicacoes.jsonl`, em ordem estável. A carga importa o arquivo, então um clone não precisa de LLM.
7. **Provedor** (`llm.py`): o cliente é compatível com a API OpenAI. `PULSO_LLM_PROVIDER` ∈ {ollama, groq, gemini, openrouter}; `PULSO_LLM_URL` sobrepõe o endereço (no compose: `host.docker.internal:11434`).

## 10. Máquina do Tempo (`fila_cirurgica/maquina_tempo`)

- `motor.processar_eventos(row, eventos)` alimenta os eventos um a um e devolve as `Transicao` de nível. Cada reavaliação só enxerga os eventos até a data do evento corrente.
- `metricas.resumo(dataset, data)` faz uma passada por paciente e calcula `promocoes` (métrica principal), `antecipacao` (secundária) e `consistencia`.
- `replay.posicao_em(D)` reconstrói a posição na fila numa data. É cara (re-ranqueia a coorte inteira), então só serve para casos de demonstração.
- CLI, de `fila_cirurgica/`: `python -m maquina_tempo [--json | --caso SOL-...]`. API: `GET /maquina-tempo`.

## 11. Frontend (`Pulso-Frontend`)

| Rota | Tela | Dados |
|---|---|---|
| `/` | Consulta pública do paciente | Local (`src/data`, `src/store`): o dataset não tem CPF |
| `/como-funciona` | Como a fila é organizada (público) | Estático |
| `/pipeline` | O pipeline por dentro, em rolagem | JSON estático gerado do pipeline real (`scripts/dados_historia.py`, `scripts/dados_maquina_tempo.py`) |
| `/profissional/entrar` | Entrada pelo CRM | `GET /medicos` |
| `/profissional/visao` | Visão geral | `GET /resumo`, `GET /marcacoes` |
| `/profissional/fila` | Fila oficial | `GET /fila` |
| `/profissional/pacientes/:id` | Detalhe e explicação | `GET /solicitacoes/{id}`, `.../explicacao` |
| `/profissional/revisao` | Caixa do médico | `GET /mudancas`, `POST /mudancas/{id}/decisao`, `POST /eventos/processar`, `GET /mudancas/{id}/explicacao` |

- **`src/api/`:** `cliente.ts` (fetch tipado, erro `ErroApi`), `tipos.ts` (contratos da API), `useApi.ts` (carregar, erro, recarregar), `rotulos.ts` (códigos do motor → texto).
- **Sessão:** em `sessionStorage` (`store/auth.tsx`). `RotaProtegida` guarda a área profissional; o `medico_id` da sessão vai em cada decisão.
- **Pendências e dados da carga** não têm tela própria: as pendências aparecem no detalhe de cada paciente, e o relatório da carga está em `GET /dados` e na página `/pipeline`.
- **Caixa do médico:** um card sem texto pronto pede a explicação ao backend, um de cada vez, só para os cards da página. A chave inclui `atualizada_em`, então um evento novo pede outro texto.

## 12. Configuração

| Variável | Padrão | Uso |
|---|---|---|
| `DATABASE_URL` | `postgresql://pulso:pulso@localhost:5432/pulso` | Banco |
| `PULSO_DATASET` | `ideas/data/dataset` | Pasta dos CSVs |
| `PULSO_DATA_REFERENCIA` | `2026-10-23` | "Hoje" do dataset |
| `PULSO_EXPLICACOES` | `db/explicacoes.jsonl` | Cache de textos do LLM (vazio = desligado) |
| `PULSO_CORS` | `http://localhost:5173,http://127.0.0.1:5173` | Origens do frontend |
| `PULSO_LLM_PROVIDER` / `PULSO_LLM_MODEL` | `ollama` / `gemma4:e4b` | Provedor e modelo |
| `PULSO_LLM_URL` | do provedor | Endereço da API do LLM |
| `PULSO_LLM_REASONING` | `none` (Ollama), `low` (Groq) | Esforço de raciocínio |
| `GROQ_API_KEY` / `GEMINI_API_KEY` / `OPENROUTER_API_KEY` | — | Provedores hospedados |
| `VITE_API_URL` (frontend) | `http://localhost:8000` | Endereço da API |

Os valores vêm do ambiente, de `backend/.env` ou do `.env` da raiz.

## 13. Execução

```bash
# Backend: banco + carga (na primeira subida) + API em :8000
docker compose up -d --build
docker compose exec api python -m src.pipeline carregar --recriar --ate-pedidos 3   # estado da demo
docker compose exec api python -m src.pipeline rodar --recriar                      # todos os eventos

# LLM local (opcional; sem ele vale a justificativa do motor)
OLLAMA_NUM_PARALLEL=4 ollama serve && ollama pull gemma4:e4b

# Frontend em :5173
cd ../Pulso-Frontend && npm install && npm run dev
```

Para zerar tudo, volume do banco incluído: `docker compose down -v`.

## 14. Testes

| Suíte | Comando | Cobre |
|---|---|---|
| Motor (20) | `cd fila_cirurgica && python -m pytest -q` | Normalização de CID, negação, laudos em sequência, idempotência, monotonicidade, expiração, cobertura, contrato dos classificadores, regra de ouro, determinismo, Máquina do Tempo |
| Backend (25) | `cd backend && python -m pytest -q` | Carga e processamento, recomendada = lote do motor, regras dos pedidos, aprovar, rejeitar e sair, evento novo pela API, conferência do LLM, cache e invalidação, LLM fora do ar |
| Entregável | `python ideas/data/dataset/verificar_fila_priorizada.py resultados/fila_priorizada.csv` | Formato, cobertura e regra de ouro (verificador oficial) |

Os testes do backend usam um banco separado (`pulso_teste`) e um LLM falso; não precisam do Ollama.
