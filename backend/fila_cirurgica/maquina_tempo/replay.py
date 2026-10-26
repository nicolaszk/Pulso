# -*- coding: utf-8 -*-
"""Driver historico: carrega os CSVs e roda a reavaliacao por evento (motor.py).

Carrega e limpa o dataset UMA vez (mesma carga de priorizacao.pipeline.carga_inicial) e,
para cada solicitacao ativa, a maquina do tempo = `motor.processar_eventos`.

`ranquear`/`posicao_em` recalculam a POSICAO na fila de prioridades numa data D
(classificadores + saida._chave_ordem, como carga_inicial). Sao caros (re-ranqueiam a
coorte inteira), entao sao usados so para os casos de demo, nao no backtest.
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

from priorizacao import config
from priorizacao.carga import carregar
from priorizacao.classificadores import REGISTRO, ordenar_filas
from priorizacao.limpeza import limpar
from priorizacao.pipeline import _iso
from priorizacao.saida import _chave_ordem
from priorizacao.sinais import _dia, montar_estado
from priorizacao.triagem import triar

from . import motor

# Eventos que caracterizam deterioracao (nomes de priorizacao.config.TIPOS_EVENTO)
EVENTOS_AGUDOS = {"pronto_socorro", "internacao"}
SINAIS_PRECOCES = {
    ("contato_telefonico", "relata_piora"),
    ("consulta_reavaliacao", "piora"),
    ("exame_imagem", "progressao"),
    ("biopsia", "positivo"),
}


def carregar_dataset(dataset, ref=config.DATA_REFERENCIA_PADRAO):
    """(ativas: list[dict], eventos_por_sol: dict[str, list[dict]]) na data `ref`.

    Mesma carga/limpeza de carga_inicial: duplicatas fundidas, saidas por observacao
    marcadas; so as solicitacoes ativas entram.
    """
    ref = pd.Timestamp(ref)
    brutos = carregar(dataset)
    lp = limpar(brutos.fila, brutos.eventos, brutos.procedimentos, ref)
    ativas = lp.solicitacoes[lp.solicitacoes["status"] == "ativa"].to_dict("records")
    eventos_por_sol: dict[str, list] = {}
    for ev in (lp.eventos.to_dict("records") if not lp.eventos.empty else []):
        eventos_por_sol.setdefault(ev["solicitacao_id"], []).append(ev)
    return ativas, eventos_por_sol


def linha_do_tempo(row: dict, eventos_sol: list[dict]) -> list[motor.Transicao]:
    """A maquina do tempo de um paciente: as transicoes de grupo, evento a evento."""
    return motor.processar_eventos(row, eventos_sol)


# --------------------------------------------------------------- posicao na fila (so demo)
def ranquear(ativas: list[dict], eventos_por_sol: dict, D) -> list[dict]:
    """Reconstroi a fila priorizada inteira na data D (posicao + posicao_fila).

    Replica o ranking de carga_inicial: triagem de cada ativo com os eventos ate D,
    data-limite pelos classificadores e ordenacao por saida._chave_ordem. So considera
    quem ja entrou na fila ate D.
    """
    ref = pd.Timestamp(D)
    dia = _dia(D)
    estados, triagens = {}, {}
    for row in ativas:
        entrada = _dia(row.get("data_entrada_fila"))
        if entrada is not None and dia is not None and entrada > dia:
            continue  # ainda nao entrou na fila nesta data
        sid = row["solicitacao_id"]
        sol = {k: v for k, v in row.items() if k != "dias_em_fila"}
        ate = [e for e in eventos_por_sol.get(sid, [])
               if _dia(e.get("data_evento")) is not None and _dia(e.get("data_evento")) <= dia]
        est = montar_estado(sol, ate, ref)
        estados[sid] = est
        triagens[sid] = triar(est, ref, pendencias_saida=sol.get("pendencias_saida") or [])

    triados = pd.DataFrame([{"solicitacao_id": sid, "fila": triagens[sid].fila,
                             "data_entrada_fila": estados[sid].data_entrada} for sid in triagens])
    limites = {r["solicitacao_id"]: r for r in ordenar_filas(triados, REGISTRO, ref).to_dict("records")}

    detalhe = []
    for sid, est in estados.items():
        detalhe.append({
            "solicitacao_id": sid,
            "fila": triagens[sid].fila,
            "ordem_fila": config.ORDEM_FILA[triagens[sid].fila],
            "data_limite_efetiva": limites[sid]["data_limite_efetiva"],
            "n_sinais": est.n_sinais(),
            "dor": est.dor,
            "data_entrada_iso": _iso(est.data_entrada),
        })
    ordenados = sorted(detalhe, key=_chave_ordem)
    contagem: Counter = Counter()
    for i, r in enumerate(ordenados, start=1):
        contagem[r["fila"]] += 1
        r["posicao"] = i
        r["posicao_fila"] = contagem[r["fila"]]
    return ordenados


def posicao_em(ativas: list[dict], eventos_por_sol: dict, D, solicitacao_id: str) -> dict | None:
    """Posicao de uma solicitacao na fila priorizada na data D (None se nao esta na fila)."""
    fila = ranquear(ativas, eventos_por_sol, D)
    total = len(fila)
    for r in fila:
        if r["solicitacao_id"] == solicitacao_id:
            return {"posicao": r["posicao"], "posicao_fila": r["posicao_fila"],
                    "fila": r["fila"], "total": total}
    return None
