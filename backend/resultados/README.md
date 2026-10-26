# Resultados

Fila priorizada gerada pelo pipeline no dataset completo do desafio (data de referência 23/10/2026),
com todos os 1.489 eventos processados.

| Arquivo | Conteúdo |
|---|---|
| `fila_priorizada.csv` | O entregável: `solicitacao_id, posicao, justificativa`. A justificativa é a do motor (nível, evidências com data, entrada e data limite). |
| `fila_priorizada_com_explicacao.csv` | Mesma fila, mesma ordem; a justificativa é o texto em linguagem clara do LLM (gemma4:e4b), conferido contra os fatos do motor. |

As duas são a fila recomendada: a ordem do motor como se o médico aprovasse todos os pedidos de mudança.

## Verificador oficial

`python ideas/data/dataset/verificar_fila_priorizada.py` passa nos dois arquivos:

    RESULTADO: OK — regra de ouro respeitada e formato válido

| Indicador do verificador | Resultado |
|---|---|
| Regra de ouro (nenhum CID C* abaixo de paciente sem urgência clínica) | respeitada |
| Último oncológico / primeiro paciente sem urgência clínica | posição 265 / posição 266 |
| Oncológicos no primeiro terço da fila | 100% (172 de 172) |
| Posição mediana dos oncológicos | 177 de 897 |
| PS ou internação nos últimos 180 dias na primeira metade | 100% |
| Pacientes sem urgência clínica no último terço | 94% |

A regra de ouro também é conferida pelo backend a cada aprovação (`regra de ouro fila_priorizada: ok`,
`regra de ouro fila_recomendada: ok` no `resumo`).

## Cobertura

941 solicitações no CSV de entrada, 897 posições na fila. As 44 que ficam fora:

| Motivo | Quantas |
|---|---|
| Duplicata, fundida na solicitação mais antiga | 22 |
| Saída registrada nas observações (desistência, cirurgia em outro serviço) | 17 |
| Evento de saída durante a espera (pedido para tirar da fila) | 5 |

Os 5 oncológicos que o verificador aponta como fora do arquivo são duplicatas. A solicitação original de cada
um está na fila:

| Duplicata | Original | Posição |
|---|---|---|
| SOL-2023-00088 | SOL-2023-00074 | 1 |
| SOL-2026-00864 | SOL-2026-00460 | 33 |
| SOL-2026-01014 | SOL-2026-00743 | 194 |
| SOL-2026-00816 | SOL-2026-00809 | 208 |
| SOL-2026-00865 | SOL-2026-00852 | 221 |

## Fila por nível

| Nível | Pacientes |
|---|---|
| G1a Oncológico em progressão | 53 |
| G1b Agudo não oncológico | 70 |
| G2 Oncológico confirmado | 142 |
| G3 Suspeita oncológica | 16 |
| G4 Deterioração recente | 118 |
| G5 Alta carga de sintomas | 95 |
| G6 Sintomático moderado | 194 |
| G7 Eletivo estável | 209 |

## Eventos e explicações

- 1.489 eventos válidos processados um a um por data: 1.225 sem mudança de nível, 136 pedidos abertos
  (8 deles substituídos por evidência mais forte), 128 pedidos à espera do médico (123 para subir, 5 para sair).
- 9 eventos órfãos em quarentena, 7 eventos repetidos descartados.
- Explicações: 897 de 897 posições com texto do LLM. Cada texto passou pela checagem determinística
  (nenhum número, data, nível ou termo oncológico fora dos fatos); a ordem da fila não depende do LLM.

## Como reproduzir

Com o Postgres do `docker compose` no ar, de dentro de `backend/`:

    python -m src.pipeline rodar --recriar
    python -m src.pipeline exportar --saida ../resultados/fila_priorizada.csv
    python -m src.pipeline exportar --explicacao --saida ../resultados/fila_priorizada_com_explicacao.csv
    python ../ideas/data/dataset/verificar_fila_priorizada.py ../resultados/fila_priorizada.csv
