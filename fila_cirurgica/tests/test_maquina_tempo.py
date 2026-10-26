# -*- coding: utf-8 -*-
"""Testes da Maquina do Tempo (motor de reavaliacao por evento + metricas)."""
import csv
from datetime import date

import pandas as pd
import pytest

from conftest import DATASET

from maquina_tempo import motor, replay
from maquina_tempo.motor import processar_eventos, reavaliar, triagem_de_entrada
from priorizacao import config


def _sol(**kw):
    base = dict(solicitacao_id="S1", paciente_id="P1", cid="M179", cid_exibicao="M17.9",
                oncologico=False, dor=None, limitacao=None, data_entrada_fila=pd.Timestamp("2026-01-01"),
                prioridade_manual="media", txt_justificativa="", txt_observacoes="",
                justificativa_clinica="", hba1c_ultima=None, data_hba1c_ultima=None,
                flag_oncologico="nao", flag_piora_clinica="nao", flag_diabetico="nao",
                comorbidades="", cid_secundario="", duplicata_fundida=False, irma_com_evento=False,
                pendencias_saida=[])
    base.update(kw)
    return base


def _ev(dia_iso, tipo, resultado=None, valor=None, desc="", eid="E1"):
    return dict(evento_id=eid, data_evento=pd.Timestamp(dia_iso), tipo_evento=tipo,
                resultado=resultado, valor_numerico=valor, descricao=desc, origem="teste")


# ------------------------------------------------------------------ reavaliacao por evento
def test_promocao_no_primeiro_sinal_antecipa_o_agudo():
    """relata_piora no dia 10 promove de G7 para G4; o PS so vem no dia 40 (30 dias depois)."""
    row = _sol()
    eventos = [_ev("2026-01-11", "contato_telefonico", "relata_piora", eid="E1"),
               _ev("2026-02-10", "pronto_socorro", "atendido_liberado", eid="E2")]

    assert triagem_de_entrada(row).fila == "G7"
    trans = processar_eventos(row, eventos)

    assert len(trans) == 1, "o PS nao deve gerar nova transicao: ja estava em G4"
    t = trans[0]
    assert t.sentido == "sobe" and t.fila_de == "G7" and t.fila_para == "G4"
    assert t.data == date(2026, 1, 11)
    # antecipacao ate o evento agudo
    assert (date(2026, 2, 10) - t.data).days == 30


# ------------------------------------------------------------------ sem vazamento de futuro
def test_sem_vazamento_de_futuro():
    """Uma biopsia futura nao pode alterar a reavaliacao de uma data anterior.

    montar_estado conta biopsia 'em qualquer data'; so o fatiamento por data do motor
    da maquina do tempo evita que o futuro vaze para o passado.
    """
    row = _sol()
    futura = [_ev("2026-05-01", "biopsia", "positivo", eid="E1")]

    antes = reavaliar(row, futura, "2026-03-01")   # biopsia ainda nao aconteceu
    sem = reavaliar(row, [], "2026-03-01")
    depois = reavaliar(row, futura, "2026-06-01")   # biopsia ja aconteceu

    assert antes.fila == sem.fila == "G7"
    assert antes.ordem_fila == sem.ordem_fila
    assert depois.fila in ("G1a", "G2")


# ------------------------------------------------------------------ regra de ouro
def test_regra_de_ouro_oncologico_nunca_sai_de_g1a_g2():
    """Paciente C* permanece em {G1a, G2} em toda reavaliacao, aconteca o que acontecer."""
    row = _sol(cid="C509", cid_exibicao="C50.9", oncologico=True)
    eventos = [_ev("2026-02-01", "exame_imagem", "estavel", eid="E1"),
               _ev("2026-03-01", "contato_telefonico", "relata_melhora", eid="E2"),
               _ev("2026-04-01", "biopsia", "negativo", eid="E3")]

    assert triagem_de_entrada(row).fila in ("G1a", "G2")
    ordenados = motor._ordenar(eventos)
    for i in range(len(ordenados)):
        r = reavaliar(row, ordenados[: i + 1], ordenados[i]["data_evento"])
        assert r.fila in ("G1a", "G2"), f"oncologico escapou para {r.fila}"
    for t in processar_eventos(row, eventos):
        assert t.fila_para in ("G1a", "G2")


# ------------------------------------------------------------------ posicao (demo) bate com a fila oficial
def test_posicao_em_reproduz_fila_oficial():
    """ranquear/posicao_em na data de referencia reproduzem a fila_priorizada.csv oficial.

    Confere que o ranking sob demanda da maquina do tempo = o ranking de carga_inicial.
    """
    oficial_csv = DATASET.parents[2] / "fila_cirurgica" / "saida" / "fila_priorizada.csv"
    if not oficial_csv.exists():
        pytest.skip("saida/fila_priorizada.csv ausente (rode a carga inicial)")

    ativas, evs = replay.carregar_dataset(DATASET)
    fila = {r["solicitacao_id"]: r["posicao"] for r in replay.ranquear(ativas, evs, config.DATA_REFERENCIA_PADRAO)}
    with open(oficial_csv, newline="") as f:
        oficial = {row["solicitacao_id"]: int(row["posicao"]) for row in csv.DictReader(f)}

    comuns = set(fila) & set(oficial)
    assert len(comuns) == len(oficial), "conjunto de solicitacoes difere da fila oficial"
    assert all(fila[sid] == oficial[sid] for sid in comuns), "posicoes divergem da fila oficial"
    # posicao_em concorda com o ranking completo
    algum = next(iter(oficial))
    assert replay.posicao_em(ativas, evs, config.DATA_REFERENCIA_PADRAO, algum)["posicao"] == oficial[algum]
