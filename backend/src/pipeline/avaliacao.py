"""Avaliacao de UMA solicitacao com o motor de fila_cirurgica/priorizacao.

avaliar(solicitacao, eventos, data) e pura: depende so do paciente, dos eventos dele e
da data. Encadeia os passos 3 a 5 do motor (sinais -> triagem -> classificador) e monta
a justificativa no mesmo formato do entregavel.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .. import config  # noqa: F401  (coloca fila_cirurgica/ no sys.path)
from priorizacao import config as regras
from priorizacao.classificadores import REGISTRO, ordenar_filas
from priorizacao.pipeline import _TEXTO_MOTIVO, _data_br, _motivo_texto, _sem_urgencia
from priorizacao.sinais import montar_estado
from priorizacao.triagem import triar


@dataclass
class Avaliacao:
    solicitacao_id: str
    data_calculo: str
    fila: str
    data_limite_efetiva: str
    n_sinais: int
    dor: int | None
    oncologico: bool
    sem_urgencia: bool
    motivos: list
    motivo_texto: str
    justificativa: str
    sinais: list
    evidencias: dict
    marcacoes: list
    pendencias: list
    proxima_revisao: str | None
    evidencias_motivo: list = field(default_factory=list)  # evidencias dos sinais que decidiram a fila
    sair: bool = False
    evidencia_saida: str | None = None
    eventos_saida: list = field(default_factory=list)

    @property
    def ordem_fila(self) -> int:
        return regras.ORDEM_FILA[self.fila]

    @property
    def classe_swalis(self) -> str:
        return CLASSE_SWALIS[self.fila]

    def proposta(self) -> dict:
        """O que entra na fila oficial se um medico aprovar a mudanca."""
        return {"fila": self.fila, "data_limite_efetiva": self.data_limite_efetiva, "n_sinais": self.n_sinais,
                "dor": self.dor, "justificativa": self.justificativa, "marcacoes": self.marcacoes,
                "classe_swalis": self.classe_swalis}


# Cada fila do motor refina uma classe SWALIS com o mesmo prazo
CLASSE_SWALIS = {"G1a": "A1", "G1b": "A1", "G2": "A2", "G3": "B", "G4": "B", "G5": "B", "G6": "C", "G7": "D"}


def avaliar(solicitacao: dict, eventos: list[dict], data) -> Avaliacao:
    """`solicitacao`: solicitacao.dados_motor. `eventos`: os ja processados, com
    evento_id, data_evento, tipo_evento, resultado, valor_numerico, descricao, origem."""
    ref = pd.Timestamp(data)
    sol = {k: v for k, v in solicitacao.items() if k != "dias_em_fila"}  # recalculado na data
    est = montar_estado(sol, eventos, ref)
    tri = triar(est, ref, pendencias_saida=sol.get("pendencias_saida") or [])

    triado = pd.DataFrame([{"solicitacao_id": est.solicitacao_id, "fila": tri.fila,
                            "data_entrada_fila": est.data_entrada}])
    limite = ordenar_filas(triado, REGISTRO, ref).iloc[0]
    marcacoes = list(tri.marcacoes) + [{"marcacao": m, "severidade": "media"}
                                       for m in limite["marcacoes_classificador"]]

    saidas = [e for e in eventos if e.get("resultado") in regras.SAIDA_RESULTADOS_EVENTO]
    evidencia_saida = None
    if saidas:
        e = saidas[0]
        evidencia_saida = (f"{e['tipo_evento']}={e['resultado']} em {_data_br(str(e['data_evento']))}: "
                           f"{e.get('descricao') or ''}").strip()

    motivo_texto = _motivo_texto(est, tri.motivos)
    av = Avaliacao(
        solicitacao_id=est.solicitacao_id,
        data_calculo=ref.date().isoformat(),
        fila=tri.fila,
        data_limite_efetiva=limite["data_limite_efetiva"],
        n_sinais=est.n_sinais(),
        dor=int(est.dor) if est.dor is not None else None,
        oncologico=est.oncologico,
        sem_urgencia=_sem_urgencia(est),
        motivos=[_TEXTO_MOTIVO.get(m, m) for m in tri.motivos],
        motivo_texto=motivo_texto,
        justificativa="",
        sinais=sorted(est.sinais_validos),
        evidencias=est.evidencias,
        marcacoes=marcacoes,
        pendencias=tri.pendencias,
        proxima_revisao=tri.proxima_revisao,
        evidencias_motivo=[ev for m in tri.motivos for ev in est.evidencias.get(m, [])],
        sair=bool(saidas),
        evidencia_saida=evidencia_saida,
        eventos_saida=[e["evento_id"] for e in saidas],
    )
    av.justificativa = justificativa(av, est.data_entrada)
    return av


def justificativa(av: Avaliacao, data_entrada) -> str:
    """Formato de priorizacao/saida.py, sem a posicao (ela muda a cada aprovacao)."""
    partes = [f"{av.fila} {regras.NOME_FILA[av.fila]}"]
    if av.motivo_texto:
        partes.append(av.motivo_texto)
    entrada = _data_br(data_entrada.isoformat()) if data_entrada else "?"
    partes.append(f"entrada {entrada}, data limite {_data_br(av.data_limite_efetiva)}")
    altas = [m["marcacao"] for m in av.marcacoes if m["severidade"] == "alta"]
    if altas:
        partes.append("ATENCAO: " + ", ".join(altas))
    return " | ".join(partes)
