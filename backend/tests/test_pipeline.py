"""Pipeline de ponta a ponta: carga, processamento evento a evento, pedidos e decisao do medico."""
import subprocess
import sys

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src import config
from src.pipeline import consultas, fila, processamento

from conftest import carregar_tudo
from priorizacao import carga_inicial


def _ordem(con, tabela):
    pos = "posicao_final" if tabela == "fila_priorizada" else "posicao"
    return [r["solicitacao_id"] for r in con.execute(f"SELECT solicitacao_id FROM {tabela} ORDER BY {pos}").fetchall()]


def _aprovar_todas(con, medico=1):
    n = 0
    while pend := consultas.mudancas(con, "pendente", limite=1):
        fila.decidir(con, pend[0]["id"], True, medico, "teste")
        n += 1
    return n


# ---------------------------------------------------------------------------- carga + processamento
def test_carga_e_processamento(banco, con):
    assert banco["solicitacoes"] == 941
    assert banco["quarentena"] == 9 and banco["eventos_repetidos_descartados"] == 7
    assert banco["processamento"]["pendentes"] == 0
    assert banco["processamento"]["eventos"] == banco["eventos_pendentes"] == 1489
    n = con.execute("SELECT count(*) AS n FROM fila_priorizada").fetchone()["n"]
    assert _posicoes(con) == list(range(1, n + 1))
    r = consultas.resumo(con)
    assert all(g["ok"] for g in r["regra_de_ouro"].values())


def _posicoes(con):
    return [r["p"] for r in con.execute("SELECT posicao_final AS p FROM fila_priorizada ORDER BY 1").fetchall()]


def test_recomendada_igual_ao_lote_do_motor(banco, con, tmp_path):
    """Processar os eventos um por um chega na mesma fila que o motor em lote (fila_cirurgica)."""
    carga_inicial(config.DATASET, config.DATA_REFERENCIA, tmp_path / "fila.sqlite", tmp_path, recriar=True)
    lote = pd.read_csv(tmp_path / "fila_priorizada.csv").sort_values("posicao")
    assert _ordem(con, "fila_recomendada") == list(lote["solicitacao_id"])


def test_pedidos_respeitam_as_regras(banco, con):
    # no maximo um pendente por solicitacao (indice parcial unico) e nunca rebaixar CID C*
    assert con.execute("""SELECT count(*) AS n FROM solicitacao_mudanca m JOIN solicitacao s ON s.id = m.solicitacao_id
                          WHERE m.tipo = 'descer' AND s.cid_principal LIKE 'C%'""").fetchone()["n"] == 0
    # todo pendente aponta para uma fila diferente da oficial, ou e uma saida
    errados = con.execute("""SELECT count(*) AS n FROM solicitacao_mudanca m
                             JOIN fila_priorizada fp ON fp.solicitacao_id = m.solicitacao_id
                             WHERE m.status = 'pendente' AND m.fila_proposta = fp.fila""").fetchone()["n"]
    assert errados == 0
    # a fila oficial so mudou por aprovacao: nada aprovado ainda, nada no historico
    assert con.execute("SELECT count(*) AS n FROM fila_historico").fetchone()["n"] == 0


def test_aprovar_todas_iguala_oficial_a_recomendada(banco, con, tmp_path):
    assert _aprovar_todas(con) > 0
    assert _ordem(con, "fila_priorizada") == _ordem(con, "fila_recomendada")
    assert _posicoes(con) == list(range(1, len(_posicoes(con)) + 1))
    saida = consultas.exportar(con, tmp_path / "fila_priorizada.csv", "oficial")
    v = subprocess.run([sys.executable, str(config.DATASET / "verificar_fila_priorizada.py"), str(saida)],
                       capture_output=True, text=True)
    assert v.returncode == 0, v.stdout


def test_rejeitar_exige_motivo_e_nao_muda_a_fila(banco, con):
    m = consultas.mudancas(con, "pendente", limite=1)[0]
    antes = _ordem(con, "fila_priorizada")
    with pytest.raises(fila.DecisaoInvalida):
        fila.decidir(con, m["id"], False, 1, "")
    fila.decidir(con, m["id"], False, 1, "paciente reavaliado em consulta, sem mudanca")
    assert _ordem(con, "fila_priorizada") == antes
    assert consultas.mudanca(con, m["id"])["status"] == "rejeitada"
    with pytest.raises(fila.DecisaoInvalida):  # ja decidido
        fila.decidir(con, m["id"], True, 1)


def test_aprovar_move_o_paciente_e_registra(banco, con):
    m = [x for x in consultas.mudancas(con, "pendente", limite=500) if x["tipo"] == "subir"][0]
    r = fila.decidir(con, m["id"], True, 2)
    assert r["para"]["fila"] == m["fila_proposta"]
    assert r["para"]["posicao_final"] < r["de"]["posicao_final"]
    h = con.execute("SELECT * FROM fila_historico WHERE mudanca_id = %s", (m["id"],)).fetchone()
    assert h["medico_id"] == 2 and h["de_fila"] == m["fila_atual"]


def test_saida_aprovada_tira_da_fila(banco, con):
    m = [x for x in consultas.mudancas(con, "pendente", limite=500) if x["tipo"] == "sair"][0]
    fila.decidir(con, m["id"], True, 1)
    sid = m["solicitacao_id"]
    assert con.execute("SELECT status FROM solicitacao WHERE id = %s", (sid,)).fetchone()["status"] == "saiu"
    assert con.execute("SELECT 1 FROM fila_priorizada WHERE solicitacao_id = %s", (sid,)).fetchone() is None
    assert _posicoes(con) == list(range(1, len(_posicoes(con)) + 1))


# ---------------------------------------------------------------------------- API (grava de verdade: recarrega no fim)
@pytest.fixture
def api(banco):
    from src.main import app
    yield TestClient(app)
    carregar_tudo()


def test_api_evento_novo_abre_pedido_e_medico_aprova(api, con):
    # paciente eletivo estavel, sem eventos e sem pedido: biopsia positiva deve pedir G2
    alvo = con.execute("""SELECT fp.solicitacao_id, fp.posicao_final FROM fila_priorizada fp
                          WHERE fp.fila = 'G7' AND NOT EXISTS (SELECT 1 FROM evento_clinico e WHERE e.solicitacao_id = fp.solicitacao_id)
                            AND NOT EXISTS (SELECT 1 FROM solicitacao_mudanca m WHERE m.solicitacao_id = fp.solicitacao_id)
                          ORDER BY fp.posicao_final LIMIT 1""").fetchone()
    ev = {"solicitacao_id": alvo["solicitacao_id"], "data_evento": "2026-10-23", "tipo_evento": "biopsia",
          "resultado": "positivo", "descricao": "AP: carcinoma.", "origem": "laboratorio de patologia"}
    r = api.post("/eventos", json=ev)
    assert r.status_code == 201, r.text
    mud = r.json()["mudanca"]
    assert mud["acao"] == "aberta" and mud["tipo"] == "subir"
    assert api.post("/eventos", json=ev).status_code == 422  # mesmo conteudo de novo

    pedido = api.get(f"/mudancas/{mud['mudanca_id']}").json()
    assert pedido["fila_proposta"] == "G2" and pedido["status"] == "pendente"
    assert api.post(f"/mudancas/{mud['mudanca_id']}/decisao", json={"decisao": "rejeitar", "medico_id": 1}).status_code == 409
    r = api.post(f"/mudancas/{mud['mudanca_id']}/decisao", json={"decisao": "aprovar", "medico_id": 1})
    assert r.status_code == 200, r.text
    d = api.get(f"/solicitacoes/{alvo['solicitacao_id']}").json()
    assert d["fila_oficial"]["fila"] == "G2" and d["fila_oficial"]["posicao"] < alvo["posicao_final"]


def test_api_maquina_tempo(api):
    r = api.get("/maquina-tempo")
    assert r.status_code == 200, r.text
    d = r.json()
    p = d["promocoes"]
    assert d["ativas"] > 0
    assert p["n_promovidos"] > 0
    assert p["prioridade_baixa_ou_media"] <= p["n_promovidos"]
    assert len(p["casos"]) == p["n_promovidos"]
    assert set(p["dias_desde_promocao"]) >= {"mediana", "p25", "p75"}
    assert api.get("/resumo").json()["regra_de_ouro"]["fila_priorizada"]["ok"]
    csv = api.get("/export/fila_priorizada.csv", params={"modo": "oficial"}).text
    assert csv.startswith("solicitacao_id,posicao,justificativa")
