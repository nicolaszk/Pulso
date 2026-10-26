# -*- coding: utf-8 -*-
"""Testes obrigatorios da especificacao (passos 1 a 6)."""
import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest

from conftest import DATASET

from priorizacao import carga_inicial, montar_estado, ordenar_filas, triar
from priorizacao.classificadores import REGISTRO
from priorizacao.limpeza import _cid_exibicao, _cid_normal, limpar
from priorizacao.carga import carregar
from priorizacao.saida import RegraDeOuroViolada, gerar_saida
from priorizacao.texto import buscar_termo, normalizar, termo_negado
from priorizacao import config

REF = pd.Timestamp("2026-10-23")


def _sol(**kw):
    base = dict(solicitacao_id="S1", paciente_id="P1", cid="M179", cid_exibicao="M17.9",
                oncologico=False, dor=None, limitacao=None, data_entrada_fila=pd.Timestamp("2025-01-01"),
                prioridade_manual="media", txt_justificativa="", txt_observacoes="",
                justificativa_clinica="", hba1c_ultima=None, data_hba1c_ultima=None,
                flag_oncologico="nao", flag_piora_clinica="nao", flag_diabetico="nao",
                comorbidades="", cid_secundario="", duplicata_fundida=False, irma_com_evento=False)
    base.update(kw)
    return base


def _ev(dias_atras, tipo, resultado=None, valor=None, desc="", eid="E1"):
    return dict(evento_id=eid, data_evento=REF - pd.Timedelta(days=dias_atras), tipo_evento=tipo,
                resultado=resultado, valor_numerico=valor, descricao=desc, origem="teste")


# ------------------------------------------------------------------ normalizacao de CID
def test_normalizacao_cid():
    assert _cid_normal("K409") == _cid_normal("k40.9") == "K409"
    assert _cid_exibicao("K409") == "K40.9"
    assert _cid_normal(" C50.9 ") == "C509"
    assert _cid_exibicao("C509") == "C50.9"


# ------------------------------------------------------------------ negacao
def test_negacao_encarceramento_nao_ativa_agudo():
    t = normalizar("Abaulamento aos esforcos. Sem sinais de encarceramento.")
    assert buscar_termo(t, config.TERMOS_AGUDO) is None
    assert termo_negado(t, "encarcer")


def test_negacao_frase_anterior_ativa_alarme():
    t = normalizar("Sem sinais de malignidade. Lesao com sangramento espontaneo.")
    frase = buscar_termo(t, config.TERMOS_ALARME)
    assert frase is not None and "sangramento espontaneo" in frase


# ------------------------------------------------------------------ laudos em sequencia
def test_laudos_em_sequencia():
    eventos = [_ev(300, "biopsia", "negativo", eid="E1"),
               _ev(200, "biopsia", "inconclusivo", eid="E2"),
               _ev(100, "biopsia", "positivo", eid="E3")]
    est = montar_estado(_sol(), eventos, REF)
    assert est.maligno and est.conflito_laudos
    assert triar(est, REF).fila in ("G1a", "G2")


# ------------------------------------------------------------------ lote vazio e data passada
def test_lote_vazio_e_data_passada():
    est = montar_estado(_sol(), [], REF)              # zero eventos
    assert triar(est, REF).fila == "G7"
    est2 = montar_estado(_sol(data_entrada_fila=pd.Timestamp("2021-01-01")),
                         [_ev(0, "pronto_socorro", "observacao")], pd.Timestamp("2022-01-01"))
    assert triar(est2, pd.Timestamp("2022-01-01")).fila  # nao quebra


def test_tipo_de_evento_ausente_nao_quebra():
    est = montar_estado(_sol(), [_ev(10, "contato_telefonico", "atendeu")], REF)
    assert est.n_sinais() >= 0


# ------------------------------------------------------------------ monotonicidade
def test_monotonicidade_ps_nunca_rebaixa():
    base = _sol(dor=5)                       # G6
    est0 = montar_estado(base, [], REF)
    t0 = triar(est0, REF)
    est1 = montar_estado(base, [_ev(10, "pronto_socorro", "observacao")], REF)
    t1 = triar(est1, REF)
    assert config.ORDEM_FILA[t1.fila] <= config.ORDEM_FILA[t0.fila]
    assert t1.fila == "G4"


# ------------------------------------------------------------------ expiracao
def test_piora_expirada_nao_sustenta_g4_sozinha():
    est = montar_estado(_sol(), [_ev(181, "pronto_socorro", "observacao")], REF)
    t = triar(est, REF)
    assert t.fila == "G4"
    assert any(m["marcacao"] == "confirmar_saida_g4" for m in t.marcacoes)
    assert not est.piora_recente and est.piora_qualquer


def test_maligno_nunca_sai_de_g1a_g2():
    est = montar_estado(_sol(cid="C509", oncologico=True),
                        [_ev(400, "pronto_socorro", "observacao")], REF)
    assert triar(est, REF).fila in ("G1a", "G2")


# ------------------------------------------------------------------ contrato dos classificadores
class _ClassificadorRuim:
    nome, versao, filas = "ruim", "9.9.9", {"G2"}

    def avaliar(self, pacientes, data_referencia):
        linhas = [{"solicitacao_id": s, "data_limite_efetiva": "2099-01-01",
                   "componentes": [], "confianca": 1.0} for s in pacientes["solicitacao_id"]]
        linhas.append({"solicitacao_id": "FANTASMA", "data_limite_efetiva": "2099-01-01",
                       "componentes": [], "confianca": 1.0})   # id a mais
        return pd.DataFrame(linhas)


def test_contrato_corrige_classificador():
    triados = pd.DataFrame([{"solicitacao_id": "S1", "fila": "G2",
                             "data_entrada_fila": pd.Timestamp("2025-01-01")}])
    out = ordenar_filas(triados, {"G2": _ClassificadorRuim()}, REF)
    assert out.attrs["falhas"]                       # fila caiu para o padrao
    linha = out.iloc[0]
    assert linha["classificador"] == "prazo_padrao"
    # data cortada ao limite da fila (entrada + prazo = 2025-01-22), nunca 2099
    assert linha["data_limite_efetiva"] <= "2025-01-22"


def test_contrato_limites_e_plano_b():
    triados = pd.DataFrame([{"solicitacao_id": "S1", "fila": "G2",
                             "data_entrada_fila": pd.Timestamp("2025-01-01")}])

    class BaixaConfianca:
        nome, versao, filas = "baixa", "1.0.0", {"G2"}

        def avaliar(self, pacientes, data_referencia):
            return pd.DataFrame([{"solicitacao_id": "S1", "data_limite_efetiva": None,
                                  "componentes": [], "confianca": 0.1}])
    out = ordenar_filas(triados, {"G2": BaixaConfianca()}, REF)
    assert "revisao_classificador" in out.iloc[0]["marcacoes_classificador"]


# ------------------------------------------------------------------ regra de ouro
def test_regra_de_ouro_interrompe_gravacao(tmp_path):
    # onco em posicao pior que um paciente calmo -> deve levantar e NAO escrever arquivos
    detalhe = [
        dict(solicitacao_id="CALMO", paciente_id="P1", fila="G3", ordem_fila=config.ORDEM_FILA["G3"],
             prazo=60, dias_em_fila=10, data_entrada_iso="2025-01-01", data_limite_efetiva="2025-01-10",
             n_sinais=1, dor=1, cid_exibicao="D37", oncologico=False, rotulos=[], motivos=[],
             motivo_texto="", marcacoes=[], pendencias=[], proxima_revisao=None,
             classificador="prazo_padrao", classificador_versao="1.0.0", componentes=[],
             prioridade_manual="baixa", sem_urgencia=True),
        dict(solicitacao_id="ONCO", paciente_id="P2", fila="G7", ordem_fila=config.ORDEM_FILA["G7"],
             prazo=360, dias_em_fila=10, data_entrada_iso="2025-01-01", data_limite_efetiva="2025-12-01",
             n_sinais=1, dor=0, cid_exibicao="C50.9", oncologico=True, rotulos=[], motivos=[],
             motivo_texto="", marcacoes=[], pendencias=[], proxima_revisao=None,
             classificador="prazo_padrao", classificador_versao="1.0.0", componentes=[],
             prioridade_manual="alta", sem_urgencia=False),
    ]
    with pytest.raises(RegraDeOuroViolada):
        gerar_saida(detalhe, [], [], [], total_csv=2, saida_dir=str(tmp_path), data_referencia="2026-10-23")
    assert not (tmp_path / "fila_priorizada.csv").exists()


# ------------------------------------------------------------------ dataset: cobertura, determinismo, idempotencia
@pytest.mark.skipif(not DATASET.exists(), reason="dataset indisponivel")
def test_cobertura_total(tmp_path):
    r = carga_inicial(DATASET, "2026-10-23", str(tmp_path / "f.sqlite"), str(tmp_path / "out"), recriar=True)
    assert r.total_csv == r.ativas + r.duplicatas + r.saidas
    assert all(ok for _, ok, _ in r.checagens)


@pytest.mark.skipif(not DATASET.exists(), reason="dataset indisponivel")
def test_determinismo(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    carga_inicial(DATASET, "2026-10-23", str(a / "f.sqlite"), str(a), recriar=True)
    carga_inicial(DATASET, "2026-10-23", str(b / "f.sqlite"), str(b), recriar=True)
    for nome in ("fila_priorizada.csv", "fila_detalhada.csv", "fora_da_fila.csv"):
        assert (a / nome).read_bytes() == (b / nome).read_bytes()


@pytest.mark.skipif(not DATASET.exists(), reason="dataset indisponivel")
def test_idempotencia_eventos_duplicados():
    brutos = carregar(DATASET)
    dobro = brutos.eventos.copy()
    dobro["evento_id"] = dobro["evento_id"].astype(str) + "-BIS"   # ids novos, mesmo conteudo
    juntos = pd.concat([brutos.eventos, dobro], ignore_index=True)
    base = limpar(brutos.fila.copy(), brutos.eventos.copy(), brutos.procedimentos, REF)
    dup = limpar(brutos.fila.copy(), juntos, brutos.procedimentos, REF)
    # os eventos duplicados sao descartados -> mesmo conjunto valido por hash
    assert set(base.eventos["hash_conteudo"]) == set(dup.eventos["hash_conteudo"])
    assert dup.descartados_duplicados >= len(brutos.eventos) - base.descartados_duplicados


@pytest.mark.skipif(not DATASET.exists(), reason="dataset indisponivel")
def test_banco_tem_versao_e_itens(tmp_path):
    bco = tmp_path / "f.sqlite"
    r = carga_inicial(DATASET, "2026-10-23", str(bco), str(tmp_path / "out"), recriar=True)
    con = sqlite3.connect(str(bco))
    assert con.execute("SELECT COUNT(*) FROM fila_versao").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM fila_item").fetchone()[0] == r.ativas
    con.close()
