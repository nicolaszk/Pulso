# -*- coding: utf-8 -*-
"""Agregacoes da Maquina do Tempo: o numero que vai para o pitch.

A metrica principal (`promocoes`) e o que o motor de reavaliacao por evento faz de fato:
quantos pacientes ele PROMOVEU de fila durante a espera, reagindo a eventos, e como isso
diverge da prioridade dada pela regulacao manual. Replay retrospectivo e determinístico,
sem vazamento de futuro (motor.py). Reportamos n e distribuicao (mediana + quartis).

`antecipacao` e uma estatistica secundaria e honesta (n pequeno neste dataset): casos em
que ainda havia um sinal clinico registrado antes de uma ida ao PS/internacao.

Uma unica passada por paciente (`analisar`) alimenta as tres agregacoes.
"""
from __future__ import annotations

import collections
import statistics
from dataclasses import dataclass, field
from datetime import date

from priorizacao import config
from priorizacao.sinais import _dia

from . import replay
from .motor import Transicao, processar_eventos, reavaliar, triagem_de_entrada
from .replay import EVENTOS_AGUDOS, SINAIS_PRECOCES

# Prioridades manuais que o sistema entende como "nao prioritarias" (o motor promoveu mesmo assim).
# "nao_informada" fica de fora: prioridade desconhecida nao e o mesmo que baixa/media.
PRIORIDADE_BAIXA = {"baixa", "media"}


def _prioridade(valor) -> str:
    """Normaliza a prioridade manual; vazia/'nan'/desconhecida vira 'nao_informada'."""
    s = str(valor if valor is not None else "").strip().lower()
    return s if s in ("baixa", "media", "alta") else "nao_informada"


def _dia_ev(ev: dict) -> date | None:
    return _dia(ev.get("data_evento"))


def _ordenar(eventos: list[dict]) -> list[dict]:
    return sorted(eventos, key=lambda e: (_dia_ev(e) or date.min, str(e.get("evento_id") or "")))


def _quantil(ordenados: list[int], q: float) -> int:
    if not ordenados:
        return 0
    return ordenados[min(len(ordenados) - 1, int(round(q * (len(ordenados) - 1))))]


def _distribuicao(valores: list[int]) -> dict:
    v = sorted(valores)
    if not v:
        return {}
    return {"mediana": int(statistics.median(v)), "media": round(statistics.mean(v), 1),
            "p25": _quantil(v, 0.25), "p75": _quantil(v, 0.75), "min": v[0], "max": v[-1]}


# --------------------------------------------------------------- uma passada por paciente
@dataclass
class Analise:
    solicitacao_id: str
    prioridade: str
    oncologico: bool
    fila_entrada: str
    subidas: list[Transicao] = field(default_factory=list)   # transicoes de subida durante a espera
    marcacoes_finais: set = field(default_factory=set)       # marcacoes do motor na data de referencia
    teve_agudo: bool = False
    sinal_antes: dict | None = None                          # sinal clinico antes do 1o PS/internacao
    data_primeira_promocao: date | None = None
    dias_desde_promocao: int | None = None


def analisar(ativas: list[dict], eventos_por_sol: dict, ref=config.DATA_REFERENCIA_PADRAO) -> list[Analise]:
    """Roda o motor por evento UMA vez por paciente e extrai o que as metricas precisam."""
    hoje = _dia(ref)
    out = []
    for row in ativas:
        sid = row["solicitacao_id"]
        entrada = _dia(row.get("data_entrada_fila"))
        evs = _ordenar(eventos_por_sol.get(sid, []))

        subidas = [t for t in processar_eventos(row, evs)
                   if t.sentido == "sobe" and t.data is not None and (entrada is None or t.data >= entrada)]
        primeira = subidas[0].data if subidas else None

        agudos = [d for e in evs if (d := _dia_ev(e)) is not None
                  and e.get("tipo_evento") in EVENTOS_AGUDOS and (entrada is None or d >= entrada)]
        sinal_antes = None
        if agudos:
            primeiro_agudo = min(agudos)
            precoces = [(d, e) for e in evs if (d := _dia_ev(e)) is not None
                        and (e.get("tipo_evento"), e.get("resultado")) in SINAIS_PRECOCES
                        and (entrada is None or d >= entrada) and d < primeiro_agudo]
            if precoces:
                data_sinal, ev_sinal = min(precoces, key=lambda x: x[0])
                sinal_antes = {"solicitacao_id": sid, "data_sinal": data_sinal.isoformat(),
                               "sinal": f"{ev_sinal.get('tipo_evento')}/{ev_sinal.get('resultado')}",
                               "data_agudo": primeiro_agudo.isoformat(), "dias": (primeiro_agudo - data_sinal).days}

        out.append(Analise(
            solicitacao_id=sid,
            prioridade=_prioridade(row.get("prioridade_manual")),
            oncologico=bool(row.get("oncologico")),
            fila_entrada=triagem_de_entrada(row).fila,
            subidas=subidas,
            marcacoes_finais={m["marcacao"] for m in reavaliar(row, evs, ref).marcacoes},
            teve_agudo=bool(agudos),
            sinal_antes=sinal_antes,
            data_primeira_promocao=primeira,
            dias_desde_promocao=(hoje - primeira).days if (hoje and primeira) else None,
        ))
    return out


# --------------------------------------------------------------- agregacoes (sobre as analises)
def promocoes(analises: list[Analise]) -> dict:
    """Pacientes que o motor promoveu de fila durante a espera, reagindo a eventos."""
    com_subida = [a for a in analises if a.subidas]
    por_prioridade: collections.Counter = collections.Counter(a.prioridade for a in com_subida)
    saltos: collections.Counter = collections.Counter(
        f"{a.fila_entrada}->{a.subidas[-1].fila_para}" for a in com_subida)
    casos = [{
        "solicitacao_id": a.solicitacao_id,
        "fila_entrada": a.fila_entrada,
        "fila_final": a.subidas[-1].fila_para,
        "ganho_ordem": config.ORDEM_FILA[a.fila_entrada] - config.ORDEM_FILA[a.subidas[-1].fila_para],
        "prioridade_manual": a.prioridade,
        "data_primeira_promocao": a.data_primeira_promocao.isoformat() if a.data_primeira_promocao else None,
        "dias_desde_promocao": a.dias_desde_promocao,
        "gatilho": f"{a.subidas[0].evento_gatilho.get('tipo_evento')}/{a.subidas[0].evento_gatilho.get('resultado')}",
    } for a in com_subida]
    return {
        "n_promovidos": len(com_subida),
        "por_prioridade_manual": dict(por_prioridade),
        "prioridade_baixa_ou_media": sum(n for p, n in por_prioridade.items() if p in PRIORIDADE_BAIXA),
        "de_eletivo_ou_moderado": sum(1 for a in com_subida if a.fila_entrada in ("G6", "G7")),
        "saltos": dict(saltos.most_common()),
        "dias_desde_promocao": _distribuicao([a.dias_desde_promocao for a in com_subida
                                              if a.dias_desde_promocao is not None]),
        "casos": sorted(casos, key=lambda c: (-c["ganho_ordem"], -(c["dias_desde_promocao"] or 0))),
    }


def antecipacao(analises: list[Analise]) -> dict:
    """Secundaria: sinal clinico registrado antes de uma ida ao PS/internacao (durante a espera)."""
    casos = [a.sinal_antes for a in analises if a.sinal_antes is not None]
    return {"n_agudos": sum(1 for a in analises if a.teve_agudo), "n_com_sinal": len(casos),
            "dias": _distribuicao([c["dias"] for c in casos]),
            "casos": sorted(casos, key=lambda c: -c["dias"])}


def consistencia(analises: list[Analise]) -> dict:
    """Achados determinísticos que o motor ja expoe (o manual nem sempre pegou)."""
    return {
        "oncologico_prioridade_baixa": sum(1 for a in analises if a.oncologico and a.prioridade == "baixa"),
        "oncologico_prioridade_media": sum(1 for a in analises if a.oncologico and a.prioridade == "media"),
        "biopsia_positiva_cid_nao_oncologico": sum(1 for a in analises if "atualizar_cid" in a.marcacoes_finais),
        "prazo_estourado": sum(1 for a in analises if "prazo_estourado" in a.marcacoes_finais),
    }


def resumo(dataset, ref=config.DATA_REFERENCIA_PADRAO) -> dict:
    """Payload da manchete: promocoes (principal) + antecipacao + consistencia, numa so passada."""
    ativas, eventos_por_sol = replay.carregar_dataset(dataset, ref)
    analises = analisar(ativas, eventos_por_sol, ref)
    return {
        "data_referencia": str(ref),
        "ativas": len(ativas),
        "promocoes": promocoes(analises),
        "antecipacao": antecipacao(analises),
        "consistencia": consistencia(analises),
    }
