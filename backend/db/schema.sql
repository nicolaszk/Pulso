-- Pulso · schema PostgreSQL (essencial para o Desafio 1)
--
-- Entrada: a fila cirúrgica, os eventos durante a espera e os catálogos do dataset.
-- Saída:   a fila priorizada (posição + justificativa), que é o entregável do case.
-- Hospital e médico não existem no dataset: são gerados de forma sintética pelo seed.
-- Pipeline (backend/src/pipeline): eventos entram como fila de processamento, o motor
-- avalia um por um e abre solicitacao_mudanca para um médico aprovar.
--
-- Uso: python -m src.pipeline rodar --recriar   (de backend/; aplica este schema e carrega os CSVs)
--  ou: psql -d pulso -f db/schema.sql -f db/seed.sql

BEGIN;

DROP VIEW IF EXISTS solicitacao_ativa, fila_recomendada;
DROP TABLE IF EXISTS explicacao, fila_historico, solicitacao_mudanca, estado_paciente, features_paciente,
    evento_quarentena, execucao, fila_priorizada, evento_clinico, solicitacao, paciente,
    medico, procedimento, hospital, especialidade, swalis_classe, fila_grupo CASCADE;

-- Catálogos ------------------------------------------------------------------

CREATE TABLE especialidade (
    id   smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome text NOT NULL UNIQUE
);

CREATE TABLE hospital (
    id        smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome      text    NOT NULL UNIQUE,
    municipio text    NOT NULL,
    uf        char(2) NOT NULL DEFAULT 'RS'
);

CREATE TABLE medico (
    id               integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome             text     NOT NULL,
    crm              text     NOT NULL UNIQUE,
    especialidade_id smallint NOT NULL REFERENCES especialidade (id),
    hospital_id      smallint NOT NULL REFERENCES hospital (id)
);

CREATE TABLE procedimento (
    id                text     PRIMARY KEY CHECK (id ~ '^PROC[0-9]{3}$'),
    nome              text     NOT NULL,
    especialidade_id  smallint NOT NULL REFERENCES especialidade (id),
    porte             text     NOT NULL CHECK (porte IN ('pequeno', 'medio', 'grande', 'especial')),
    risco_cirurgico   smallint NOT NULL CHECK (risco_cirurgico BETWEEN 1 AND 5),
    duracao_media_min smallint NOT NULL CHECK (duracao_media_min > 0),
    necessita_uti     text     NOT NULL CHECK (necessita_uti IN ('sim', 'nao', 'eventual'))
);

-- Referência opcional do case (classes de urgência com prazo máximo)
CREATE TABLE swalis_classe (
    classe            text     PRIMARY KEY CHECK (classe IN ('A1', 'A2', 'B', 'C', 'D')),
    descricao         text     NOT NULL,
    prazo_maximo_dias smallint NOT NULL CHECK (prazo_maximo_dias > 0),
    exemplos          text
);

-- As 8 filas do motor (fila_cirurgica/priorizacao/config.py), em ordem fixa.
-- Cada uma refina uma classe SWALIS com o mesmo prazo.
CREATE TABLE fila_grupo (
    codigo        text     PRIMARY KEY,
    nome          text     NOT NULL,
    ordem         smallint NOT NULL UNIQUE,
    prazo_dias    smallint NOT NULL CHECK (prazo_dias > 0),
    classe_swalis text     NOT NULL REFERENCES swalis_classe (classe)
);

-- Fila -----------------------------------------------------------------------

CREATE TABLE paciente (
    id                    text     PRIMARY KEY CHECK (id ~ '^PAC-[0-9]{5}$'),
    nome                  text     NOT NULL,
    sexo                  char(1)  NOT NULL CHECK (sexo IN ('F', 'M')),
    idade                 smallint NOT NULL CHECK (idade BETWEEN 0 AND 120),  -- na data de referência
    municipio             text     NOT NULL,                                  -- grafia normalizada
    uf                    char(2)  NOT NULL DEFAULT 'RS',
    distancia_hospital_km smallint CHECK (distancia_hospital_km >= 0),
    comorbidades          text[]   NOT NULL DEFAULT '{}'                      -- 'nenhuma' vira {}
);

CREATE TABLE solicitacao (
    id                             text     PRIMARY KEY CHECK (id ~ '^SOL-[0-9]{4}-[0-9]{5}$'),
    paciente_id                    text     NOT NULL REFERENCES paciente (id),
    procedimento_id                text     NOT NULL REFERENCES procedimento (id),
    hospital_id                    smallint NOT NULL REFERENCES hospital (id),
    medico_solicitante_id          integer  NOT NULL REFERENCES medico (id),

    -- Diagnóstico: CID sempre normalizado (maiúsculas, sem ponto). C* = neoplasia maligna.
    cid_principal                  text     NOT NULL CHECK (cid_principal ~ '^[A-Z][0-9]{2,3}$'),
    cid_descricao                  text     NOT NULL,
    cid_secundario                 text     CHECK (cid_secundario ~ '^[A-Z][0-9]{2,3}$'),

    -- Estado clínico na inclusão (vazio = não informado)
    asa                            smallint CHECK (asa BETWEEN 1 AND 4),
    intensidade_dor_eva            smallint CHECK (intensidade_dor_eva BETWEEN 0 AND 10),
    limitacao_funcional            text     CHECK (limitacao_funcional IN ('nenhuma', 'leve', 'moderada', 'grave')),
    justificativa_clinica          text     NOT NULL,
    observacoes                    text,

    data_entrada_fila              date     NOT NULL,

    -- Prioridade manual de hoje: só serve como baseline de comparação
    prioridade_regulacao           text     CHECK (prioridade_regulacao IN ('alta', 'media', 'baixa')),
    data_ultima_revisao_prioridade date     NOT NULL,

    -- Preparo pré-operatório (opcional no case)
    hba1c_ultima                   numeric(3, 1) CHECK (hba1c_ultima BETWEEN 3 AND 20),
    data_hba1c_ultima              date,
    avaliacao_pre_anestesica       text     NOT NULL CHECK (avaliacao_pre_anestesica IN ('realizada', 'pendente', 'vencida')),
    exames_pre_op_validos          boolean  NOT NULL,

    -- Limpeza: nada é apagado, só marcado
    status                         text     NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'duplicata', 'saiu')),
    duplicata_de                   text     REFERENCES solicitacao (id),
    motivo_status                  text,

    -- Linha limpa que o motor lê (textos fundidos das duplicatas, dor/limitação 0..3, flags)
    dados_motor                    jsonb,

    CHECK (data_ultima_revisao_prioridade >= data_entrada_fila),
    CHECK ((hba1c_ultima IS NULL) = (data_hba1c_ultima IS NULL)),
    CHECK ((status = 'duplicata') = (duplicata_de IS NOT NULL)),
    CHECK ((status = 'ativa') = (motivo_status IS NULL))
);

CREATE INDEX solicitacao_paciente_idx ON solicitacao (paciente_id);
CREATE INDEX solicitacao_status_idx ON solicitacao (status);

CREATE TABLE evento_clinico (
    id             text     PRIMARY KEY CHECK (id ~ '^EVT-[0-9]{6}$'),
    solicitacao_id text     NOT NULL REFERENCES solicitacao (id),
    data_evento    date     NOT NULL,
    tipo_evento    text     NOT NULL,
    resultado      text     NOT NULL,
    valor_numerico numeric(4, 1),  -- HbA1c em % ou dias de internação
    descricao      text     NOT NULL,
    origem         text     NOT NULL,

    -- Pipeline: o evento entra pendente e o motor processa um por um, por data
    solicitacao_id_original text,                       -- antes de fundir a duplicata no mestre
    hash_conteudo  text     UNIQUE,                     -- mesmo conteúdo = mesmo evento
    recebido_em    timestamptz NOT NULL DEFAULT now(),
    processado_em  timestamptz,                         -- NULL = ainda não processado

    CHECK (
        CASE tipo_evento
            WHEN 'biopsia'              THEN resultado IN ('positivo', 'negativo', 'inconclusivo')
            WHEN 'hba1c'                THEN resultado = 'resultado' AND valor_numerico IS NOT NULL
            WHEN 'pronto_socorro'       THEN resultado IN ('atendido_liberado', 'observacao')
            WHEN 'internacao'           THEN resultado = 'alta' AND valor_numerico IS NOT NULL
            WHEN 'exame_imagem'         THEN resultado IN ('estavel', 'progressao')
            WHEN 'consulta_reavaliacao' THEN resultado IN ('piora', 'estavel', 'melhora')
            WHEN 'contato_telefonico'   THEN resultado IN ('atendeu', 'nao_atendeu', 'relata_piora', 'relata_melhora',
                                                           'informou_cirurgia_outro_servico', 'desistiu')
            WHEN 'falta'                THEN resultado IN ('consulta', 'exame', 'avaliacao_pre_anestesica')
            ELSE false
        END
    ),
    CHECK (valor_numerico IS NULL OR tipo_evento IN ('hba1c', 'internacao'))
);

CREATE INDEX evento_solicitacao_data_idx ON evento_clinico (solicitacao_id, data_evento);
CREATE INDEX evento_pendente_idx ON evento_clinico (data_evento, id) WHERE processado_em IS NULL;

-- Pipeline -------------------------------------------------------------------

CREATE TABLE execucao (
    id             integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo           text        NOT NULL CHECK (tipo IN ('carga', 'processamento', 'varredura')),
    data_referencia date       NOT NULL,
    regras_versao  text        NOT NULL,
    hashes         jsonb,                               -- sha256 dos CSVs lidos
    relatorio      jsonb,                               -- cada correção da limpeza (problema, quantidade, ação)
    iniciada_em    timestamptz NOT NULL DEFAULT now(),
    terminada_em   timestamptz
);

-- Eventos rejeitados na limpeza, com o motivo (nada some em silêncio)
CREATE TABLE evento_quarentena (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evento_id   text    NOT NULL,
    motivo      text    NOT NULL,
    registro    jsonb   NOT NULL,
    execucao_id integer REFERENCES execucao (id)
);

-- Visão do motor sobre cada solicitação ativa, com todos os eventos já processados.
-- É o que o motor recomenda; a fila oficial (fila_priorizada) só muda com aprovação.
CREATE TABLE estado_paciente (
    solicitacao_id      text     PRIMARY KEY REFERENCES solicitacao (id),
    data_calculo        date     NOT NULL,
    fila                text     NOT NULL REFERENCES fila_grupo (codigo),
    sair                boolean  NOT NULL DEFAULT false,  -- evento de saída (desistência, operou fora)
    data_limite_efetiva date     NOT NULL,
    n_sinais            smallint NOT NULL,
    dor                 smallint,
    sem_urgencia        boolean  NOT NULL,
    motivos             jsonb    NOT NULL,
    justificativa       text     NOT NULL,
    sinais              jsonb    NOT NULL,
    evidencias          jsonb    NOT NULL,
    marcacoes           jsonb    NOT NULL,
    pendencias          jsonb    NOT NULL,
    proxima_revisao     date,
    ultimo_evento_id    text     REFERENCES evento_clinico (id),
    atualizado_em       timestamptz NOT NULL DEFAULT now()
);

-- Features de ideas/data/build_features.py na data de referência (JEV, score, detalhe do paciente)
CREATE TABLE features_paciente (
    solicitacao_id  text  PRIMARY KEY REFERENCES solicitacao (id),
    data_referencia date  NOT NULL,
    features        jsonb NOT NULL
);

-- Saída ----------------------------------------------------------------------

-- Uma linha por solicitação ativa. O entregável do case (fila_priorizada.csv) é
-- solicitacao_id, posicao_final AS posicao, justificativa.
--   posicao_inicial: ordem do método atual (prioridade manual, depois data de entrada),
--                    preenchida pelo seed; é a base do "antes e depois"
--   posicao_final:   ordem do Pulso, preenchida pelo motor junto com a justificativa
-- É a fila OFICIAL: depois da carga, só muda quando um médico aprova uma solicitacao_mudanca.
-- Ordem: fila, data limite, mais sinais, mais dor, entrada, id (posições renumeradas a cada aprovação).
CREATE TABLE fila_priorizada (
    solicitacao_id  text        PRIMARY KEY REFERENCES solicitacao (id),
    posicao_inicial integer     NOT NULL UNIQUE CHECK (posicao_inicial > 0),
    posicao_final   integer     CHECK (posicao_final > 0),
    justificativa   text        CHECK (justificativa <> ''),
    classe_swalis   text        REFERENCES swalis_classe (classe),
    gerada_em       timestamptz NOT NULL DEFAULT now(),

    fila                text     REFERENCES fila_grupo (codigo),
    posicao_fila        integer  CHECK (posicao_fila > 0),
    data_limite_efetiva date,
    n_sinais            smallint,
    dor                 smallint,
    marcacoes           jsonb    NOT NULL DEFAULT '[]',
    atualizada_em       timestamptz,

    -- adiável: a renumeração troca várias posições no mesmo UPDATE
    CONSTRAINT fila_priorizada_posicao_final_key UNIQUE (posicao_final) DEFERRABLE INITIALLY DEFERRED,
    CHECK ((posicao_final IS NULL) = (justificativa IS NULL))
);

-- Pedido do motor para mudar alguém de fila. Só vale depois que um médico aprova.
--   subir/descer: troca de fila; sair: evento de desistência ou cirurgia em outro serviço.
--   substituida: um evento novo trouxe outro destino; obsoleta: o motor voltou para a fila atual.
CREATE TABLE solicitacao_mudanca (
    id               integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    solicitacao_id   text        NOT NULL REFERENCES solicitacao (id),
    tipo             text        NOT NULL CHECK (tipo IN ('subir', 'descer', 'sair')),
    oncologico       boolean     NOT NULL,              -- CID C*: nunca é rebaixado
    fila_atual       text        NOT NULL REFERENCES fila_grupo (codigo),
    fila_proposta    text        REFERENCES fila_grupo (codigo),
    posicao_atual    integer     NOT NULL,
    posicao_proposta integer,                           -- estimada na fila oficial do momento
    motivo           text        NOT NULL CHECK (motivo <> ''),
    evidencias       jsonb       NOT NULL DEFAULT '[]',
    proposta         jsonb       NOT NULL,              -- o que entra na fila oficial se aprovada
    evento_id        text        REFERENCES evento_clinico (id),  -- evento que disparou (NULL = varredura)
    data_referencia  date        NOT NULL,
    status           text        NOT NULL DEFAULT 'pendente'
                                 CHECK (status IN ('pendente', 'aprovada', 'rejeitada', 'substituida', 'obsoleta')),
    criada_em        timestamptz NOT NULL DEFAULT now(),
    atualizada_em    timestamptz NOT NULL DEFAULT now(),
    medico_id        integer     REFERENCES medico (id),
    decidida_em      timestamptz,
    motivo_decisao   text,

    CHECK ((tipo = 'sair') = (fila_proposta IS NULL)),
    CHECK (NOT (oncologico AND tipo = 'descer')),
    CHECK ((status IN ('aprovada', 'rejeitada')) = (medico_id IS NOT NULL AND decidida_em IS NOT NULL)),
    CHECK (status <> 'rejeitada' OR coalesce(motivo_decisao, '') <> '')
);

-- No máximo um pedido pendente por solicitação
CREATE UNIQUE INDEX mudanca_pendente_uidx ON solicitacao_mudanca (solicitacao_id) WHERE status = 'pendente';

-- Toda mudança aplicada na fila oficial
CREATE TABLE fila_historico (
    id             integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    solicitacao_id text        NOT NULL REFERENCES solicitacao (id),
    mudanca_id     integer     NOT NULL REFERENCES solicitacao_mudanca (id),
    acao           text        NOT NULL CHECK (acao IN ('mudanca', 'saida')),
    de_fila        text,
    para_fila      text,
    de_posicao     integer,
    para_posicao   integer,
    medico_id      integer     NOT NULL REFERENCES medico (id),
    registrado_em  timestamptz NOT NULL DEFAULT now()
);

-- Texto em linguagem clara escrito por um LLM a partir dos fatos do motor (backend/src/pipeline/explicacao.py).
-- Nunca muda a fila. Chave = hash dos fatos: os mesmos fatos dão o mesmo texto; um evento novo gera outro.
-- rejeitada: o texto citou número, data, fila ou termo oncológico que não está nos fatos (vale o template).
CREATE TABLE explicacao (
    id              integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alvo            text        NOT NULL CHECK (alvo IN ('solicitacao', 'mudanca')),
    alvo_id         text        NOT NULL,
    hash_fatos      text        NOT NULL,
    fatos           text        NOT NULL,
    status          text        NOT NULL CHECK (status IN ('ok', 'rejeitada')),
    texto           text,
    motivo_rejeicao text,
    provedor        text        NOT NULL,
    modelo          text        NOT NULL,
    tentativas      smallint    NOT NULL,
    latencia_s      real,
    criada_em       timestamptz NOT NULL DEFAULT now(),

    UNIQUE (alvo, alvo_id, hash_fatos, provedor, modelo),
    CHECK ((status = 'ok') = (texto IS NOT NULL))
);

-- Fila que o motor recomenda com tudo o que já foi processado (como se todos os pedidos
-- fossem aprovados). Mesma ordem da fila oficial.
CREATE VIEW fila_recomendada AS
SELECT row_number() OVER w AS posicao,
       e.solicitacao_id, e.fila, e.data_limite_efetiva, e.justificativa, e.sem_urgencia,
       s.cid_principal LIKE 'C%' AS oncologico
FROM estado_paciente e
JOIN fila_grupo g ON g.codigo = e.fila
JOIN solicitacao s ON s.id = e.solicitacao_id
WHERE s.status = 'ativa' AND NOT e.sair
WINDOW w AS (ORDER BY g.ordem, e.data_limite_efetiva, e.n_sinais DESC, coalesce(e.dor, -1) DESC,
                      s.data_entrada_fila, e.solicitacao_id COLLATE "C");

-- Fila ativa com os campos derivados que a priorização usa o tempo todo.
-- 23/10/2026 é a data de referência do dataset.
CREATE VIEW solicitacao_ativa AS
SELECT s.*,
       DATE '2026-10-23' - s.data_entrada_fila AS dias_em_fila,
       s.cid_principal LIKE 'C%'               AS oncologico
FROM solicitacao s
WHERE s.status = 'ativa';

COMMIT;
