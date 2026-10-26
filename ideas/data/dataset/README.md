# Dataset — Desafio 1: Priorização Inteligente da Fila Cirúrgica

9ª Hackatona de Engenharia de Software · 2026 · Fin-x · PUCRS · Hospital São Lucas

**Dados 100% sintéticos. Nenhum paciente real. Uso livre.**
**Data de referência: 23/10/2026** (todos os `dias_em_fila` e os eventos foram calculados em relação a esta data).

## Arquivos

| Arquivo | Linhas | O que é |
|---|---|---|
| `fila_cirurgica.csv` | 941 | A fila: uma linha por solicitação cirúrgica, já com os dados do paciente, diagnóstico, dor, limitação, tempo de espera, prioridade manual da regulação e textos livres. |
| `eventos_clinicos.csv` | ~1.500 | O que aconteceu durante a espera: biópsias, HbA1c, pronto-socorro, internações, exames de imagem, reavaliações, contatos telefônicos e faltas. |
| `procedimentos.csv` | 23 | Catálogo de procedimentos: especialidade, porte, risco cirúrgico (1 a 5), duração média e necessidade de UTI. |
| `referencias/swalis.csv` | 5 | Um framework possível de urgência (classes A1 a D com prazo máximo). Opcional. |
| `dicionario_dados.md` | — | Descrição de cada coluna, domínios e observações. |
| `verificar_fila_priorizada.py` | — | Verificador da regra de ouro para o `fila_priorizada.csv` que a sua equipe vai entregar. |

Formato: CSV, separador vírgula, UTF-8 (sem BOM), datas em `AAAA-MM-DD`, decimais com ponto.

## Avisos importantes

- **Como num sistema real, os dados têm defeitos.** Flags que não batem com o diagnóstico ou com os eventos, solicitações duplicadas, informação importante que só aparece no texto livre, prioridade manual que erra com frequência, campos vazios, CID às vezes sem ponto (`K409` e `K40.9` são o mesmo código), município com grafia inconsistente, alguns eventos apontando para solicitações que já saíram da fila. Tratar isso faz parte do desafio.
- **Não existe classe de urgência pronta.** O SWALIS é só uma referência possível.
- **Regra de ouro:** nenhum paciente com neoplasia maligna (CID iniciado por `C`) pode ficar abaixo de um paciente sem urgência clínica. Use o CID, não a flag.
- `eventos_clinicos.csv` se liga à fila por `solicitacao_id` (e também traz `paciente_id`). Quando um paciente tem mais de uma solicitação, os eventos podem estar ligados a apenas uma delas.
- Os campos de preparo pré-operatório (`hba1c_ultima`, `avaliacao_pre_anestesica`, `exames_pre_op_validos`) são opcionais e não são avaliados.

## Exemplos rápidos

### Python (pandas)

```python
import pandas as pd

REF = pd.Timestamp("2026-10-23")
fila = pd.read_csv("fila_cirurgica.csv", parse_dates=["data_entrada_fila"])
eventos = pd.read_csv("eventos_clinicos.csv", parse_dates=["data_evento"])
procs = pd.read_csv("procedimentos.csv")

# normalizações básicas
fila["cid"] = fila["cid_principal"].str.upper().str.replace(".", "", regex=False)
fila["oncologico"] = fila["cid"].str.startswith("C")
fila["prioridade"] = fila["prioridade_regulacao"].str.lower().str.replace("é", "e")

print(len(fila), "solicitações;", fila["oncologico"].sum(), "oncológicas")
print(pd.crosstab(fila["oncologico"], fila["prioridade"]))

# quem piorou nos últimos 180 dias?
recentes = eventos[eventos["data_evento"] >= REF - pd.Timedelta(days=180)]
piora = recentes[recentes["tipo_evento"].isin(["pronto_socorro", "internacao"])]
print(fila[fila["solicitacao_id"].isin(piora["solicitacao_id"])].shape[0], "pacientes com PS/internação recente")

# biópsia positiva em quem ainda não tem CID C*
bx = eventos[(eventos["tipo_evento"] == "biopsia") & (eventos["resultado"] == "positivo")]
suspeitos = fila[fila["solicitacao_id"].isin(bx["solicitacao_id"]) & ~fila["oncologico"]]
print(suspeitos[["solicitacao_id", "cid_principal", "justificativa_clinica"]].head())

# série de HbA1c por paciente
hba = eventos[eventos["tipo_evento"] == "hba1c"].sort_values("data_evento")
serie = hba.groupby("solicitacao_id")["valor_numerico"].agg(["first", "last", "size"])
print(serie[(serie["size"] >= 2) & (serie["last"] - serie["first"] >= 1.0)].head())
```

### Node.js

```bash
npm install csv-parse
```

```js
const fs = require("fs");
const { parse } = require("csv-parse/sync");

const ler = (f) => parse(fs.readFileSync(f, "utf8"), { columns: true, skip_empty_lines: true });
const fila = ler("fila_cirurgica.csv");
const eventos = ler("eventos_clinicos.csv");

const cid = (r) => r.cid_principal.toUpperCase().replace(".", "");
const onco = fila.filter((r) => cid(r).startsWith("C"));
console.log(fila.length, "solicitações;", onco.length, "oncológicas");

// eventos por solicitação
const porSolicitacao = new Map();
for (const e of eventos) {
  if (!porSolicitacao.has(e.solicitacao_id)) porSolicitacao.set(e.solicitacao_id, []);
  porSolicitacao.get(e.solicitacao_id).push(e);
}
const REF = new Date("2026-10-23");
const piorando = fila.filter((r) =>
  (porSolicitacao.get(r.solicitacao_id) || []).some(
    (e) => ["pronto_socorro", "internacao"].includes(e.tipo_evento) &&
           (REF - new Date(e.data_evento)) / 86400000 <= 180));
console.log(piorando.length, "pacientes com PS/internação nos últimos 180 dias");
```

### SQL (DuckDB — `pip install duckdb` ou o binário)

```sql
CREATE TABLE fila      AS SELECT * FROM read_csv_auto('fila_cirurgica.csv');
CREATE TABLE eventos   AS SELECT * FROM read_csv_auto('eventos_clinicos.csv');
CREATE TABLE procs     AS SELECT * FROM read_csv_auto('procedimentos.csv');

-- oncológicos por prioridade manual
SELECT lower(prioridade_regulacao) AS prioridade, count(*) AS n
FROM fila
WHERE upper(replace(cid_principal, '.', '')) LIKE 'C%'
GROUP BY 1 ORDER BY 1;

-- quem espera mais de um ano, por especialidade
SELECT especialidade, count(*) FILTER (WHERE dias_em_fila > 365) AS mais_de_1_ano, count(*) AS total
FROM fila GROUP BY 1 ORDER BY 2 DESC;

-- eventos de piora nos últimos 180 dias, por solicitação
SELECT f.solicitacao_id, f.cid_principal, f.prioridade_regulacao,
       count(*) FILTER (WHERE e.tipo_evento IN ('pronto_socorro','internacao')) AS ps_ou_internacao,
       max(e.data_evento) AS ultimo_evento
FROM fila f JOIN eventos e USING (solicitacao_id)
WHERE e.data_evento >= DATE '2026-10-23' - INTERVAL 180 DAY
GROUP BY 1,2,3 HAVING ps_ou_internacao > 0
ORDER BY ps_ou_internacao DESC;

-- duplicidade: mesmo paciente, mesmo procedimento
SELECT paciente_id, procedimento_id, count(*) AS n, string_agg(solicitacao_id, ', ') AS solicitacoes
FROM fila GROUP BY 1,2 HAVING count(*) > 1;
```

## Entregável comum: `fila_priorizada.csv`

Colunas obrigatórias: `solicitacao_id`, `posicao`, `justificativa`. Uma linha por solicitação que a sua solução considera ativa (vale explicar no `DECISOES.md` o que ficou de fora e por quê). Antes de entregar, rode:

```bash
python verificar_fila_priorizada.py caminho/para/fila_priorizada.csv
```

O verificador confere o formato, a cobertura da fila e a regra de ouro com uma definição conservadora de "sem urgência clínica". É uma ferramenta de autoconferência da equipe: a avaliação da banca é feita pela demonstração e pelo pitch.
