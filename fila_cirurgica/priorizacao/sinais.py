# -*- coding: utf-8 -*-
"""Passo 3 - Sinais por paciente.

montar_estado(solicitacao, eventos, data_referencia) -> Estado e uma funcao PURA:
depende so do paciente e da data de referencia, sem olhar os outros. E isso que
permite o passo 7 recalcular apenas quem mudou.

Robustez: funciona com zero eventos, com um tipo de evento ausente e com qualquer
data de referencia passada.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from . import config
from .texto import buscar_termo

# Sinais que expiram em 180 d (exceto se maligno, para os clinicos de evento)
_EXPIRA_COM_MALIGNO = {"progressao_imagem", "reavaliacao_piora", "pronto_socorro", "internacao"}


@dataclass
class Evidencia:
    tipo: str
    data: str | None
    origem: str | None
    trecho: str | None
    evento_id: str | None = None
    somente_texto: bool = False

    def como_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class Estado:
    solicitacao_id: str
    paciente_id: str
    data_entrada: date | None
    dias_em_fila: int
    cid: str
    cid_exibicao: str
    oncologico: bool
    dor: float | None
    limitacao: int | None
    prioridade_manual: str
    justificativa: str
    justificativa_tamanho: int

    maligno: bool = False
    conflito_laudos: bool = False
    cid_urgente: bool = False
    cid_incerto: bool = False
    biopsia_positiva: bool = False
    biopsia_negativa: bool = False
    biopsia_inconclusiva: bool = False

    # sinais de evento validos na data de referencia
    progressao_imagem: bool = False
    reavaliacao_piora: bool = False
    pronto_socorro: bool = False
    internacao: bool = False
    relata_piora: bool = False
    melhora: bool = False

    texto_agudo: bool = False
    texto_alarme: bool = False
    texto_suspeita: bool = False
    obs_piora: bool = False

    piora_recente: bool = False   # algum evento de piora valido (<=180 d)
    piora_qualquer: bool = False  # algum evento de piora durante a espera (qualquer idade)
    ultima_piora: date | None = None

    hba1c_atual: float | None = None
    faltas: int = 0
    nao_atendeu: int = 0

    flag_oncologico: bool = False
    flag_piora: bool = False
    flag_diabetico: bool = False
    diabetico_dado: bool = False
    irma_com_evento: bool = False
    duplicata_fundida: bool = False
    dados_faltantes: bool = False

    sinais_validos: set = field(default_factory=set)
    sinais_historico: set = field(default_factory=set)
    evidencias: dict = field(default_factory=dict)

    def n_sinais(self) -> int:
        return len(self.sinais_validos)


def _dia(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        import pandas as pd
        ts = pd.Timestamp(v)
        return None if ts is None or ts != ts else ts.date()  # NaT != NaT
    except Exception:
        try:
            return datetime.fromisoformat(str(v)[:10]).date()
        except ValueError:
            return None


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def montar_estado(solicitacao: dict, eventos: list[dict], data_referencia) -> Estado:
    ref = _dia(data_referencia)
    entrada = _dia(solicitacao.get("data_entrada_fila"))
    cid = str(solicitacao.get("cid") or "")
    oncologico = bool(solicitacao.get("oncologico", cid.startswith("C")))
    dor = _num(solicitacao.get("dor"))
    lim = solicitacao.get("limitacao")
    lim = int(lim) if lim is not None and lim == lim else None
    just = solicitacao.get("justificativa_clinica") or solicitacao.get("txt_justificativa") or ""
    dias = solicitacao.get("dias_em_fila")
    if dias is None and ref and entrada:
        dias = (ref - entrada).days

    est = Estado(
        solicitacao_id=str(solicitacao.get("solicitacao_id")),
        paciente_id=str(solicitacao.get("paciente_id")),
        data_entrada=entrada,
        dias_em_fila=int(dias) if dias is not None else 0,
        cid=cid,
        cid_exibicao=str(solicitacao.get("cid_exibicao") or cid),
        oncologico=oncologico,
        dor=dor,
        limitacao=lim,
        prioridade_manual=str(solicitacao.get("prioridade_manual") or "nao_informada"),
        justificativa=str(just),
        justificativa_tamanho=len(str(just).strip()),
        irma_com_evento=bool(solicitacao.get("irma_com_evento", False)),
        duplicata_fundida=bool(solicitacao.get("duplicata_fundida", False)),
    )
    est.dados_faltantes = dor is None or lim is None

    # ------------------------------------------------------------------ cadastro / CID
    est.cid_urgente = cid in config.CID_URGENTES
    est.cid_incerto = bool(re.match(config.REGEX_CID_INCERTO, cid))
    if oncologico:
        _ativar(est, "oncologico", Evidencia("oncologico", None, "cadastro", f"CID {est.cid_exibicao}"))

    # ------------------------------------------------------------------ eventos
    eventos = eventos or []
    reg = []
    for ev in eventos:
        d = _dia(ev.get("data_evento"))
        reg.append((d, ev))
    reg.sort(key=lambda x: (x[0] or date.min))

    def evs(tipo=None, resultado=None, durante_espera=False):
        for d, ev in reg:
            if tipo is not None and ev.get("tipo_evento") != tipo:
                continue
            if resultado is not None and ev.get("resultado") != resultado:
                continue
            if durante_espera and (d is None or entrada is None or d < entrada):
                continue
            yield d, ev

    def evid_evento(nome, lista):
        for d, ev in lista[-2:]:
            _add_evid(est, nome, Evidencia(nome, d.isoformat() if d else None,
                      ev.get("origem"), ev.get("descricao"), ev.get("evento_id")))

    # biopsias em qualquer data
    bp = list(evs("biopsia", "positivo"))
    bn = list(evs("biopsia", "negativo"))
    bi = list(evs("biopsia", "inconclusivo"))
    if bp:
        est.biopsia_positiva = True
        _ativar(est, "biopsia_positiva", None); evid_evento("biopsia_positiva", bp)
    if bn:
        est.biopsia_negativa = True
        _ativar(est, "biopsia_negativa", None); evid_evento("biopsia_negativa", bn)
    if bi:
        est.biopsia_inconclusiva = True
        _ativar(est, "biopsia_inconclusiva", None); evid_evento("biopsia_inconclusiva", bi)

    est.maligno = oncologico or est.biopsia_positiva
    if est.maligno:
        _ativar(est, "maligno", Evidencia("maligno", None, "derivado",
                "CID C" if oncologico else "biopsia positiva"))
    est.conflito_laudos = est.biopsia_positiva and est.biopsia_negativa
    if est.conflito_laudos:
        _ativar(est, "conflito_laudos", Evidencia("conflito_laudos", None, "derivado",
                "biopsia positiva e negativa"))
    if est.cid_urgente:
        _ativar(est, "cid_urgente", Evidencia("cid_urgente", None, "cadastro", f"CID {est.cid_exibicao}"))
    if est.cid_incerto:
        _ativar(est, "cid_incerto", Evidencia("cid_incerto", None, "cadastro", f"CID {est.cid_exibicao}"))

    # sinais de piora por evento (durante a espera), com expiracao de 180 d
    def piora_evento(nome, lista, com_maligno):
        if not lista:
            return
        ultima = lista[-1][0]
        if ultima and ultima > (est.ultima_piora or date.min):
            est.ultima_piora = ultima
        recente = ultima is not None and ref is not None and (ref - ultima).days <= config.JANELA_PIORA_DIAS
        valido = recente or (com_maligno and est.maligno)
        est.piora_qualquer = True
        if valido:
            setattr(est, nome, True)
            _add_evid_lista(est, nome, lista)
            if recente:
                est.piora_recente = True
        else:
            est.sinais_historico.add(nome)

    piora_evento("progressao_imagem", list(evs("exame_imagem", "progressao", durante_espera=True)), True)
    piora_evento("reavaliacao_piora", list(evs("consulta_reavaliacao", "piora", durante_espera=True)), True)
    piora_evento("pronto_socorro", list(evs("pronto_socorro", durante_espera=True)), True)
    piora_evento("internacao", list(evs("internacao", durante_espera=True)), True)
    piora_evento("relata_piora", list(evs("contato_telefonico", "relata_piora", durante_espera=True)), False)

    # melhora (so informativo)
    melhoras = (list(evs("contato_telefonico", "relata_melhora"))
                + list(evs("consulta_reavaliacao", "melhora"))
                + list(evs("consulta_reavaliacao", "estavel"))
                + list(evs("exame_imagem", "estavel")))
    if melhoras:
        est.melhora = True
        _add_evid_lista(est, "melhora", sorted(melhoras, key=lambda x: x[0] or date.min))

    est.faltas = sum(1 for _ in evs("falta"))
    est.nao_atendeu = sum(1 for _ in evs("contato_telefonico", "nao_atendeu"))

    # hba1c: a mais recente entre cadastro e eventos
    hb_cad_v = _num(solicitacao.get("hba1c_ultima"))
    hb_cad_d = _dia(solicitacao.get("data_hba1c_ultima"))
    hb = [(hb_cad_d, hb_cad_v)] if hb_cad_v is not None else []
    for d, ev in evs("hba1c"):
        hb.append((d, _num(ev.get("valor_numerico"))))
    hb = [(d, v) for d, v in hb if v is not None]
    if hb:
        hb.sort(key=lambda x: x[0] or date.min)
        est.hba1c_atual = hb[-1][1]

    # ------------------------------------------------------------------ texto
    txt_just = solicitacao.get("txt_justificativa") or ""
    txt_obs = solicitacao.get("txt_observacoes") or ""
    for nome, termos, origem, texto in (
        ("texto_agudo", config.TERMOS_AGUDO, "justificativa", txt_just),
        ("texto_alarme", config.TERMOS_ALARME, "justificativa", txt_just),
        ("texto_suspeita", config.TERMOS_SUSPEITA, "justificativa", txt_just),
        ("obs_piora", config.TERMOS_OBS_PIORA, "observacoes", txt_obs),
    ):
        frase = buscar_termo(texto, termos)
        if frase:
            setattr(est, nome, True)
            _ativar(est, nome, Evidencia(nome, None, origem, frase, somente_texto=True))

    # flags manuais vs dados (so para alerta)
    est.flag_oncologico = str(solicitacao.get("flag_oncologico") or "").strip().lower() == "sim"
    est.flag_piora = str(solicitacao.get("flag_piora_clinica") or "").strip().lower() == "sim"
    est.flag_diabetico = str(solicitacao.get("flag_diabetico") or "").strip().lower() == "sim"
    sec = str(solicitacao.get("cid_secundario") or "").upper()
    com = str(solicitacao.get("comorbidades") or "").lower()
    est.diabetico_dado = bool(re.match(r"E1[0-4]", sec)) or "dm" in com or "diabet" in com or bool(hb)

    # rotulos derivados
    if est.piora_recente:
        est.sinais_validos.add("piora")
    if (est.dor is not None and est.dor >= 7) or est.limitacao == 3:
        est.sinais_validos.add("sintoma_alto")

    return est


def _ativar(est: Estado, nome: str, evid: Evidencia | None) -> None:
    est.sinais_validos.add(nome)
    if evid is not None:
        est.evidencias.setdefault(nome, []).append(evid.como_dict())


def _add_evid(est: Estado, nome: str, evid: Evidencia) -> None:
    est.evidencias.setdefault(nome, []).append(evid.como_dict())


def _add_evid_lista(est: Estado, nome: str, lista: list) -> None:
    est.sinais_validos.add(nome)
    for d, ev in lista[-2:]:
        _add_evid(est, nome, Evidencia(nome, d.isoformat() if d else None,
                  ev.get("origem"), ev.get("descricao"), ev.get("evento_id")))
