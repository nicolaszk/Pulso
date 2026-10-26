"""Explicacao pelo LLM: conferencia contra os fatos, cache e queda para o template (LLM falso)."""
import pytest
from fastapi.testclient import TestClient

from src import db
from src.llm import LLMIndisponivel
from src.pipeline import explicacao as ex, processamento

BOM = {"texto": "O sistema pede uma mudanca de fila com base nos eventos registrados. A decisao e do medico."}
INVENTADO = {"texto": "O paciente piorou em 01/01/1990 e precisa operar."}


class LLMFalso:
    provedor, modelo = "falso", "teste"

    def __init__(self, *respostas):
        self.respostas, self.chamadas = list(respostas), 0

    def json(self, sistema, usuario):
        self.chamadas += 1
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r, 0.1


def _pedido(con):
    return con.execute("""SELECT id FROM solicitacao_mudanca WHERE status = 'pendente' AND tipo <> 'sair'
                          ORDER BY id LIMIT 1""").fetchone()["id"]


# ---------------------------------------------------------------------------- conferencia (sem banco)
FATOS = ("Fila indicada pelo sistema: Eletivo estavel (G7), prazo de 360 dias.\n"
         "Entrada na fila: 15/09/2023. Espera ate 23/10/2026: 1134 dias.\n"
         "Diagnostico: CID K40.9, Hernia inguinal.\n"
         "Pendencias: faltou duas ou mais vezes.")


def test_conferir_aceita_o_que_esta_nos_fatos():
    assert ex.conferir("Esta em Eletivo estavel desde 15/09/2023, ha 1134 dias; o prazo e de 360 dias. "
                       "Sem alertas; o paciente faltou duas ou mais vezes.", FATOS) == []


@pytest.mark.parametrize("texto, problema", [
    ("Esperando desde 12/03/2021.", "numeros ou datas"),
    ("Esta na fila G1a.", "fila que nao esta nos fatos"),
    ("Paciente com cancer de colon.", "termo oncologico"),
    ("", "texto vazio"),
    ("Esta em Deterioracao recente.", "fila que nao esta nos fatos"),
    ("Nao ha pendencias para o medico.", "nao ha pendencias"),
])
def test_conferir_recusa_o_que_nao_esta_nos_fatos(texto, problema):
    assert any(problema in p for p in ex.conferir(texto, FATOS))


def test_cortar_fica_no_limite_e_termina_em_frase():
    texto = " ".join(["Esta frase tem umas quarenta letras ok."] * 20)
    cortado = ex._cortar(texto)
    assert len(cortado) <= ex.LIMITE and cortado.endswith(".")


# ---------------------------------------------------------------------------- geracao e cache
def test_texto_aceito_vai_para_o_cache(con):
    mid = _pedido(con)
    r = ex.explicar(con, "mudanca", mid, LLMFalso(BOM))
    assert r["fonte"] == "llm" and r["texto"] == BOM["texto"] and not r["em_cache"]
    nenhum = LLMFalso()  # quebraria se fosse chamado
    r2 = ex.explicar(con, "mudanca", mid, nenhum)
    assert r2["em_cache"] and r2["texto"] == BOM["texto"] and nenhum.chamadas == 0
    assert ex.em_cache(con, "mudanca", mid) == BOM["texto"]


def test_texto_inventado_tenta_de_novo_e_cai_no_template(con):
    mid = _pedido(con)
    llm = LLMFalso(INVENTADO, INVENTADO)
    r = ex.explicar(con, "mudanca", mid, llm)
    motivo = con.execute("SELECT motivo FROM solicitacao_mudanca WHERE id = %s", (mid,)).fetchone()["motivo"]
    assert r["fonte"] == "template" and r["texto"] == motivo and "1990" in r["motivo"]
    assert llm.chamadas == 2
    # o mesmo modelo nao e chamado de novo para os mesmos fatos
    outra = LLMFalso()
    assert ex.explicar(con, "mudanca", mid, outra)["fonte"] == "template" and outra.chamadas == 0


def test_segunda_tentativa_corrige(con):
    r = ex.explicar(con, "mudanca", _pedido(con), LLMFalso(INVENTADO, BOM))
    assert r["fonte"] == "llm" and r["tentativas"] == 2


def test_llm_fora_do_ar_usa_template_e_nao_grava(con):
    mid = _pedido(con)
    r = ex.explicar(con, "mudanca", mid, LLMFalso(LLMIndisponivel("ollama fora do ar")))
    assert r["fonte"] == "template" and "fora do ar" in r["motivo"]
    assert con.execute("SELECT count(*) AS n FROM explicacao WHERE alvo_id = %s", (str(mid),)).fetchone()["n"] == 0


def test_evento_novo_muda_os_fatos_e_invalida_o_texto(con):
    sid = con.execute("""SELECT e.solicitacao_id FROM estado_paciente e WHERE e.fila = 'G7' AND NOT EXISTS
                         (SELECT 1 FROM solicitacao_mudanca m WHERE m.solicitacao_id = e.solicitacao_id)
                         ORDER BY 1 LIMIT 1""").fetchone()["solicitacao_id"]
    ex.explicar(con, "solicitacao", sid, LLMFalso({"texto": "Esta em Eletivo estavel."}))
    assert ex.em_cache(con, "solicitacao", sid) == "Esta em Eletivo estavel."
    evento = processamento.registrar_evento(con, {
        "solicitacao_id": sid, "data_evento": "2026-10-23", "tipo_evento": "pronto_socorro",
        "resultado": "observacao", "descricao": "Dor intensa.", "origem": "UPA"})
    processamento.processar_evento(con, evento)
    assert ex.em_cache(con, "solicitacao", sid) is None


def test_fatos_do_paciente_trazem_fila_espera_e_eventos(con):
    sid = con.execute("""SELECT solicitacao_id FROM estado_paciente WHERE fila = 'G2' ORDER BY 1 LIMIT 1""").fetchone()[
        "solicitacao_id"]
    fatos, template = ex.fatos(con, "solicitacao", sid)
    assert "Oncologico confirmado (G2), prazo de 21 dias" in fatos
    assert "Espera ate 23/10/2026" in fatos and "Eventos registrados" in fatos
    assert template.startswith("G2 Oncologico confirmado")


def test_cache_salvo_em_arquivo_volta_depois_de_apagar(con, tmp_path):
    mid = _pedido(con)
    ex.explicar(con, "mudanca", mid, LLMFalso(BOM))
    arquivo, n = ex.salvar_cache(con, tmp_path / "explicacoes.jsonl")
    assert n >= 1
    con.execute("DELETE FROM explicacao")
    assert ex.em_cache(con, "mudanca", mid) is None
    assert ex.importar_cache(con, arquivo) == n
    nenhum = LLMFalso()
    assert ex.explicar(con, "mudanca", mid, nenhum)["texto"] == BOM["texto"] and nenhum.chamadas == 0


# ---------------------------------------------------------------------------- API
@pytest.fixture
def api_falsa(banco):
    from src.main import app, obter_llm
    app.dependency_overrides[obter_llm] = lambda: LLMFalso(BOM)
    yield TestClient(app)
    app.dependency_overrides.clear()
    with db.conectar() as c:
        c.execute("DELETE FROM explicacao WHERE provedor = 'falso'")


def test_api_explica_pedido_e_lista_na_caixa(api_falsa):
    pend = api_falsa.get("/mudancas", params={"limite": 1}).json()[0]
    r = api_falsa.get(f"/mudancas/{pend['id']}/explicacao").json()
    assert r["fonte"] == "llm" and r["texto"] == BOM["texto"]
    caixa = api_falsa.get("/mudancas", params={"limite": 1, "com_explicacao": True}).json()
    assert caixa[0]["explicacao"] == BOM["texto"]
    assert api_falsa.get("/mudancas/999999/explicacao").status_code == 404
