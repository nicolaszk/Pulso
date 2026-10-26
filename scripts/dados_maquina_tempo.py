"""Gera os dados estáticos da seção Máquina do Tempo da página do pipeline (/pipeline).

Roda o módulo fila_cirurgica/maquina_tempo do backend (replay determinístico do log de eventos,
sem banco) e guarda a manchete, a distribuição e a linha do tempo da SOL-2026-00610 ("a 621").

Uso (não precisa do Postgres):
    cd Pulso-Backend/fila_cirurgica && ../.venv/bin/python ../../Pulso-Frontend/scripts/dados_maquina_tempo.py ../../Pulso-Frontend/src/pages/publico/pipeline/dados
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))  # roda de dentro de Pulso-Backend/fila_cirurgica

from priorizacao import config  # noqa: E402

from maquina_tempo import metricas, replay  # noqa: E402
from maquina_tempo.motor import processar_eventos, triagem_de_entrada  # noqa: E402

OUT = Path(sys.argv[1])
DATASET = Path.cwd().parent / "ideas" / "data" / "dataset"
REF = config.DATA_REFERENCIA_PADRAO
HEROI = "SOL-2026-00610"

ativas, eventos = replay.carregar_dataset(DATASET, REF)
analises = metricas.analisar(ativas, eventos, REF)
p = metricas.promocoes(analises)
a = metricas.antecipacao(analises)

row = next(r for r in ativas if r["solicitacao_id"] == HEROI)
transicoes = processar_eventos(row, eventos.get(HEROI, []))
subidas = [t for t in transicoes if t.sentido == "sobe"]
p1 = replay.posicao_em(ativas, eventos, subidas[0].data, HEROI)
ph = replay.posicao_em(ativas, eventos, REF, HEROI)

dados = {
    "data_referencia": str(REF),
    "ativas": len(ativas),
    "promocoes": {
        "n": p["n_promovidos"],
        "por_prioridade_manual": p["por_prioridade_manual"],
        "baixa_ou_media": p["prioridade_baixa_ou_media"],
        "de_g6_g7": p["de_eletivo_ou_moderado"],
        "saltos": p["saltos"],
        "dias": p["dias_desde_promocao"],
        # dias desde a 1a promoção, um por paciente promovido (para o histograma)
        "dias_todos": sorted(a_.dias_desde_promocao for a_ in analises
                             if a_.subidas and a_.dias_desde_promocao is not None),
    },
    "antecipacao": {"n_agudos": a["n_agudos"], "n_com_sinal": a["n_com_sinal"], "dias": a["dias"]},
    "consistencia": metricas.consistencia(analises),
    "heroi": {
        "solicitacao_id": HEROI,
        "prioridade_manual": metricas._prioridade(row.get("prioridade_manual")),
        "fila_entrada": triagem_de_entrada(row).fila,
        "transicoes": [{
            "data": t.data.isoformat(),
            "evento": f"{t.evento_gatilho.get('tipo_evento')}/{t.evento_gatilho.get('resultado')}",
            "de": t.fila_de,
            "para": t.fila_para,
        } for t in transicoes],
        "primeira_promocao": {"data": subidas[0].data.isoformat(), **p1},
        "hoje": {"data": str(REF), **ph},
    },
}
(OUT / "maquina_tempo.json").write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{p['n_promovidos']} promovidos de {len(ativas)} ativas; {HEROI}: {p1['posicao']}/{p1['total']} -> {ph['posicao']}/{ph['total']}")
