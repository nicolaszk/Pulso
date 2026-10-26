# Dicionário de dados

Data de referência: **23/10/2026**. Todos os arquivos são CSV UTF-8, separador vírgula, datas `AAAA-MM-DD`.

## fila_cirurgica.csv — uma linha por solicitação cirúrgica (941)

| Coluna | Tipo | Domínio / exemplo | Observações |
|---|---|---|---|
| `solicitacao_id` | texto | `SOL-2025-00318` | Chave única da solicitação. Liga com `eventos_clinicos.csv`. |
| `paciente_id` | texto | `PAC-00412` | Um paciente pode ter mais de uma solicitação (procedimentos diferentes **ou** solicitações duplicadas). |
| `nome_paciente` | texto | sintético | Pode haver variação de grafia entre registros da mesma pessoa. |
| `sexo` | texto | `F`, `M` | |
| `idade` | inteiro | 18–92 | |
| `municipio` | texto | `Porto Alegre`, `Pelotas` | Grafia inconsistente em uma pequena parte (maiúsculas/minúsculas). |
| `uf` | texto | `RS` | |
| `distancia_hospital_km` | inteiro | 1–800 | Distância aproximada do município até o hospital. Pode estar vazia. |
| `procedimento_id` | texto | `PROC004` | Chave para `procedimentos.csv`. |
| `procedimento` | texto | `Colecistectomia videolaparoscopica` | Redundante com o catálogo, por conveniência. |
| `especialidade` | texto | `Cirurgia Geral`, `Oncologia`… | |
| `cid_principal` | texto | `C50.9`, `K40.9`, `K409` | CID-10. **Nem sempre tem o ponto**: normalize antes de comparar. `C*` = neoplasia maligna. Códigos `D37–D48` e `R91` são lesões de comportamento incerto / achados suspeitos. |
| `cid_descricao` | texto | | Descrição do CID principal. |
| `cid_secundario` | texto | `I10`, `E11.9` | Comorbidade codificada, quando houver. Frequentemente vazio. |
| `asa` | inteiro | 1–4 | Estado físico ASA. Pode estar vazio. |
| `comorbidades` | texto | `HAS; DM2; obesidade` ou `nenhuma` | Lista separada por `; `. Pode estar incompleta em relação ao texto livre. |
| `intensidade_dor_eva` | inteiro | 0–10 | Escala visual analógica. Pode estar vazia. Doença grave pode ter dor baixa. |
| `limitacao_funcional` | texto | `nenhuma`, `leve`, `moderada`, `grave` | Pode estar vazia. |
| `justificativa_clinica` | texto livre | | Texto do médico solicitante. Varia de muito pobre ("Solicito cirurgia.") a muito informativo. Pode conter sinais de agravamento que não aparecem nas colunas. Abreviações comuns: pct, PS, AP (anatomopatológico), Bx, US, TC, RNM, HAS, DM, Hb. |
| `observacoes` | texto livre | | Anotações da regulação, call center e enfermagem (contato, transporte, piora relatada, desistência, cirurgia feita em outro serviço…). Frequentemente vazio. |
| `data_entrada_fila` | data | | |
| `dias_em_fila` | inteiro | | `23/10/2026 − data_entrada_fila`. |
| `prioridade_regulacao` | texto | `alta`, `media`, `baixa` | Prioridade **manual** atribuída na inclusão. Ruidosa, raramente revisada. Pequena parte com variação de grafia (`Alta`, `Média`) ou vazia. |
| `data_ultima_revisao_prioridade` | data | | Na maioria dos casos é igual à data de entrada (nunca foi revisada). |
| `flag_oncologico` | texto | `sim`, `nao` | Flag manual do cadastro. **Nem sempre bate com o CID.** |
| `flag_diabetico` | texto | `sim`, `nao` | Flag manual. Nem sempre bate com as comorbidades, o texto ou os exames. |
| `flag_piora_clinica` | texto | `sim`, `nao` | Flag manual, desatualizada: muitos pacientes que pioraram (ver eventos) estão com `nao`, e vice-versa. |
| `hba1c_ultima` | decimal | `7.4` | *Pré-operatório, opcional.* Última HbA1c registrada **no cadastro**, que pode estar desatualizada em relação aos eventos. |
| `data_hba1c_ultima` | data | | *Pré-operatório, opcional.* |
| `avaliacao_pre_anestesica` | texto | `realizada`, `pendente`, `vencida` | *Pré-operatório, opcional.* |
| `exames_pre_op_validos` | texto | `sim`, `nao` | *Pré-operatório, opcional.* |

## eventos_clinicos.csv — o que aconteceu durante a espera (~1.500)

| Coluna | Tipo | Observações |
|---|---|---|
| `evento_id` | texto | `EVT-000123`. Único. Há alguns eventos duplicados (mesmo conteúdo, ids diferentes). |
| `solicitacao_id` | texto | Chave para a fila. Alguns eventos apontam para solicitações que **não estão** mais na fila. |
| `paciente_id` | texto | |
| `data_evento` | data | Pode ser anterior à entrada na fila: a biópsia que gerou a solicitação, ou idas ao PS / internações do histórico citado pelo médico. Nem tudo que o texto cita tem evento registrado. |
| `tipo_evento` | texto | ver tabela abaixo |
| `resultado` | texto | depende do tipo (ver abaixo) |
| `valor_numerico` | decimal | HbA1c em % (`hba1c`) ou dias de internação (`internacao`). Vazio nos demais. |
| `descricao` | texto livre | Laudo, motivo do atendimento, anotação do contato. |
| `origem` | texto | `laboratorio`, `laboratorio de patologia`, `radiologia`, `call center`, `ambulatorio`, `UPA …`, `PS Hospital Sao Lucas`, `Hospital Sao Lucas` |

| `tipo_evento` | `resultado` possíveis | O que revela |
|---|---|---|
| `biopsia` | `positivo`, `negativo`, `inconclusivo` | Positivo = malignidade confirmada. Pode existir mesmo quando o CID da fila ainda é benigno/incerto. |
| `hba1c` | `resultado` (valor em `valor_numerico`) | Série ao longo do tempo. Acima de 8,5% costuma indicar diabetes descontrolado para cirurgia eletiva. |
| `pronto_socorro` | `atendido_liberado`, `observacao` | Ida ao PS/UPA pelo problema cirúrgico ou relacionado. |
| `internacao` | `alta` (dias em `valor_numerico`) | Internação durante a espera. |
| `exame_imagem` | `estavel`, `progressao` | Controle de imagem. |
| `consulta_reavaliacao` | `piora`, `estavel`, `melhora` | Reavaliação ambulatorial. |
| `contato_telefonico` | `atendeu`, `nao_atendeu`, `relata_piora`, `relata_melhora`, `informou_cirurgia_outro_servico`, `desistiu` | Call center. |
| `falta` | `consulta`, `exame`, `avaliacao_pre_anestesica` | Não compareceu. |

## procedimentos.csv (23)

| Coluna | Observações |
|---|---|
| `procedimento_id` | `PROC001`…`PROC023` |
| `procedimento` | nome |
| `especialidade` | |
| `porte` | `pequeno`, `medio`, `grande`, `especial` |
| `risco_cirurgico` | 1 (catarata) a 5 (revascularização do miocárdio) |
| `duracao_media_min` | minutos de sala |
| `necessita_uti` | `sim`, `nao`, `eventual` |

## referencias/swalis.csv (5) — opcional

| Coluna | Observações |
|---|---|
| `classe` | `A1`, `A2`, `B`, `C`, `D` |
| `descricao` | critério clínico da classe |
| `prazo_maximo_dias` | 15, 21, 60, 180, 360 |
| `exemplos` | exemplos ilustrativos |

Adaptado do modelo SWALIS (Surgical Waiting List Information System), usado para classificar urgência de cirurgias eletivas. Não há mapeamento pronto no dataset: ele deve ser construído pela equipe a partir de diagnóstico, dor, limitação, texto e eventos.
