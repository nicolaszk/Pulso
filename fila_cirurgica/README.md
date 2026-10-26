# Priorizacao da fila cirurgica (passos 1 a 6)

Recebe os CSVs da fila cirurgica, trata os dados, divide cada solicitacao em uma
de 8 filas de urgencia (G1a a G7) e grava a primeira versao da fila ordenada num
banco SQLite. Implementa a carga inicial (passos 1 a 6) e deixa os ganchos
prontos para a reavaliacao por evento (passo 7).

**Regra de ouro (inegociavel):** nenhum paciente com CID iniciado por `C` fica
abaixo de um paciente sem urgencia clinica. Nenhum oncologico e rebaixado.

## Estrutura

```
priorizacao/
  config.py            # constantes e REGRAS_VERSAO (2.0.0)
  carga.py             # passo 1: le os 3 CSVs + hashes
  limpeza.py           # passo 2: normaliza, funde duplicatas, quarentena, relatorio
  texto.py             # normalizacao e busca com negacao
  sinais.py            # passo 3: montar_estado (funcao pura por paciente)
  triagem.py           # passo 4: triar (decide a fila)
  classificadores/
    __init__.py        # registro fila -> classificador
    base.py            # Protocol + orquestrador (limites, validacao, plano B)
    prazo_padrao.py    # classificador padrao (data limite = entrada + prazo)
  saida.py             # passo 6: ordem final, regra de ouro, arquivos
  banco.py             # SQLite: esquema e gravacao em transacao
  pipeline.py          # carga_inicial(dataset, data_referencia, banco, saida)
  __main__.py          # CLI
tests/                 # testes obrigatorios da especificacao
```

## Instalacao

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Uso

```bash
.venv/bin/python -m priorizacao carga \
  --dataset ../ideas/data/dataset \
  --data-referencia 2026-10-23 \
  --banco saida/fila.sqlite \
  --saida saida/ --recriar
```

Sem `--dataset`, usa `ideas/data/dataset` do repositorio. O terminal imprime o
relatorio de limpeza, o tamanho de cada fila e o resultado das checagens. O
codigo de saida e `0` so se todas as checagens passarem (`2` se a regra de ouro
for violada — nesse caso nada e gravado).

## As 8 filas (ordem fixa)

| Ordem | Fila | Criterio | Prazo |
|---|---|---|---|
| 1 | G1a | Oncologico em progressao | 15 d |
| 2 | G1b | Agudo nao oncologico | 15 d |
| 3 | G2 | Oncologico confirmado | 21 d |
| 4 | G3 | Suspeita oncologica | 60 d |
| 5 | G4 | Deterioracao recente | 60 d |
| 6 | G5 | Alta carga de sintomas | 60 d |
| 7 | G6 | Sintomatico moderado | 180 d |
| 8 | G7 | Eletivo estavel | 360 d |

Invariante garantida pela triagem: `maligno => fila em {G1a, G2}`.

## Saidas (pasta `saida/`)

| Arquivo | Conteudo |
|---|---|
| `fila_priorizada.csv` | entregavel oficial: `solicitacao_id, posicao, justificativa` |
| `fila_detalhada.csv` | uma linha por ativa: fila, posicao na fila, data limite, sinais, marcacoes, pendencias, proxima revisao, classificador |
| `fora_da_fila.csv` | duplicatas (com o mestre) e saidas (com a evidencia) |
| `quarentena.csv` | eventos rejeitados e o motivo |
| `revisao_humana.csv` | marcacoes por severidade |
| `pendencias.csv` | pendencias operacionais |
| `relatorio_carga.md` | cada correcao do passo 2, tamanho das filas, checagens |
| `fila.sqlite` | registro imutavel + versoes da fila (esquema em `banco.py`) |

## Testes

```bash
.venv/bin/python -m pytest tests/ -q
```

Cobrem: normalizacao de CID, negacao no texto, laudos em sequencia, lote vazio e
data passada, idempotencia, monotonicidade, expiracao, cobertura total, contrato
dos classificadores, regra de ouro e determinismo.

## Resultado no dataset (data 2026-10-23)

- 941 solicitacoes lidas, 919 unicas, 897 ativas, 22 duplicatas, 22 saidas.
- 9 eventos na quarentena (solicitacao inexistente), 7 duplicados descartados.
- As 10 hernias K40.9 com "sem sinais de encarceramento" ficam fora de G1b.
- Os 23 pacientes com biopsia positiva e CID nao-`C` ficam em G1a/G2, com `atualizar_cid`.
- Todo CID `C` em G1a ou G2.
- `verificar_fila_priorizada.py`: **"OK — regra de ouro respeitada e formato valido"**.
- Carga completa em menos de 1 s.

## Ganchos para o passo 7

`montar_estado`, `triar` e `avaliar` sao funcoes de um paciente so (um evento novo
recalcula apenas o paciente dele). A tabela `evento` tem `hash_conteudo` unico e
`data_recebimento`; `proxima_revisao` esta indexada; `data_limite_efetiva` e a
chave de ordem; `REGRAS_VERSAO` acompanha cada versao da fila; as tabelas
`mudanca` e `decisao_regulador` ja existem vazias para a caixa do regulador.
