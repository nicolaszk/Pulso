# -*- coding: utf-8 -*-
"""O coracao da Maquina do Tempo: reavaliacao incremental por evento.

`reavaliar(row, eventos, data)` re-roda o motor de filas (montar_estado -> triar) com
os eventos ate `data`. E a mesma semantica de producao
(backend/src/pipeline/processamento.reavaliar -> avaliacao.avaliar), so que pura e
standalone: depende apenas de `priorizacao`.

`processar_eventos(row, eventos)` alimenta os eventos de um paciente UM A UM, em ordem,
e a cada novo evento reavalia o paciente, registrando uma Transicao quando o grupo muda.
Sem vazamento de futuro por construcao: cada reavaliacao so enxerga os eventos ate a
data do evento corrente.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from priorizacao import config as regras
from priorizacao.sinais import _dia, montar_estado
from priorizacao.triagem import triar


@dataclass
class Reavaliacao:
    data: date | None
    fila: str
    ordem_fila: int
    motivos: list = field(default_factory=list)
    marcacoes: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    sinais: list = field(default_factory=list)


@dataclass
class Transicao:
    data: date | None           # data do evento que disparou a mudanca
    evento_gatilho: dict        # o evento (tipo, resultado, descricao, ...)
    fila_de: str
    fila_para: str
    ordem_de: int
    ordem_para: int
    sentido: str                # "sobe" (prioridade maior) ou "desce"
    motivos: list = field(default_factory=list)  # por que o motor colocou nesta fila


def _data_evento(ev: dict) -> date | None:
    return _dia(ev.get("data_evento"))


def _ordenar(eventos: list[dict]) -> list[dict]:
    """Ordem de processamento: por data e, no mesmo dia, pelo evento_id (igual a producao)."""
    return sorted(eventos, key=lambda e: (_data_evento(e) or date.min, str(e.get("evento_id") or "")))


def reavaliar(row: dict, eventos: list[dict], data) -> Reavaliacao:
    """Reavalia UM paciente na `data`, com os eventos ate essa data.

    `row`: a solicitacao ja limpa (uma linha de Limpeza.solicitacoes, como dict).
    `eventos`: eventos do paciente; so os de `data_evento <= data` tem efeito.
    """
    ref = _dia(data)
    # dias_em_fila e recalculado a partir de `data` (como avaliacao.avaliar)
    sol = {k: v for k, v in row.items() if k != "dias_em_fila"}
    ate = [e for e in eventos if ref is None or (_data_evento(e) is not None and _data_evento(e) <= ref)]
    est = montar_estado(sol, ate, ref)
    tri = triar(est, ref, pendencias_saida=sol.get("pendencias_saida") or [])
    return Reavaliacao(
        data=ref,
        fila=tri.fila,
        ordem_fila=regras.ORDEM_FILA[tri.fila],
        motivos=list(tri.motivos),
        marcacoes=list(tri.marcacoes),
        pendencias=list(tri.pendencias),
        sinais=list(tri.rotulos),
    )


def triagem_de_entrada(row: dict) -> Reavaliacao:
    """A fila do paciente so pelo cadastro, sem eventos (a fila inicial da producao)."""
    return reavaliar(row, [], _dia(row.get("data_entrada_fila")))


def processar_eventos(row: dict, eventos: list[dict]) -> list[Transicao]:
    """Alimenta os eventos um a um e devolve as transicoes de grupo.

    Parte da triagem de entrada (so cadastro) e, a cada novo evento, reavalia o paciente
    com os eventos ate a data daquele evento; registra uma Transicao quando o grupo muda.
    """
    ordenados = _ordenar(eventos)
    anterior = triagem_de_entrada(row)
    transicoes: list[Transicao] = []
    for i, ev in enumerate(ordenados):
        atual = reavaliar(row, ordenados[: i + 1], _data_evento(ev))
        if atual.ordem_fila != anterior.ordem_fila:
            transicoes.append(Transicao(
                data=_data_evento(ev),
                evento_gatilho=ev,
                fila_de=anterior.fila,
                fila_para=atual.fila,
                ordem_de=anterior.ordem_fila,
                ordem_para=atual.ordem_fila,
                sentido="sobe" if atual.ordem_fila < anterior.ordem_fila else "desce",
                motivos=atual.motivos,
            ))
            anterior = atual
    return transicoes
