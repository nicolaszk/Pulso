"""Gera os dados estáticos da página do pipeline (/pipeline) a partir do pipeline real.

Roda o pipeline num banco separado (pulso_historia), processa os eventos um por um
registrando o que cada um causou, e cruza com a definição de "sem urgência" do verificador.

Uso (com o Postgres do docker compose do backend no ar):
    docker exec pulso-backend-db-1 psql -U pulso -d pulso -c "CREATE DATABASE pulso_historia"
    cd Pulso-Backend/backend && ../.venv/bin/python ../../Pulso-Frontend/scripts/dados_historia.py ../../Pulso-Frontend/src/pages/publico/pipeline/dados
    docker exec pulso-backend-db-1 psql -U pulso -d pulso -c "DROP DATABASE pulso_historia"
"""
import json
import os
import re
import sys
from pathlib import Path

BACK = Path.cwd().parent  # roda de dentro de Pulso-Backend/backend
sys.path.insert(0, str(BACK / "backend"))
os.environ["DATABASE_URL"] = "postgresql://pulso:pulso@localhost:5432/pulso_historia"

import pandas as pd  # noqa: E402

from src import db  # noqa: E402
from src.pipeline import carga, processamento  # noqa: E402

OUT = Path(sys.argv[1])
FILAS = ["G1a", "G1b", "G2", "G3", "G4", "G5", "G6", "G7"]
TIPOS = ["contato_telefonico", "hba1c", "pronto_socorro", "falta", "biopsia",
         "exame_imagem", "consulta_reavaliacao", "internacao"]
ACOES = {"sem_mudanca": 0, "aberta": 1, "atualizada": 2, "obsoleta": 3}

with db.conectar() as con:
    carga.carregar(con, None, None, True)
    inicial = {r["solicitacao_id"]: r for r in con.execute(
        "SELECT solicitacao_id, fila, posicao_final FROM fila_priorizada").fetchall()}
    ativos = sorted(inicial, key=lambda s: inicial[s]["posicao_final"])  # 902, ordem oficial
    indice = {s: i for i, s in enumerate(ativos)}

    # Cada evento: [tipo, ação, substituiu, paciente (índice em ativos, -1 = fora), fila que o motor
    # recomenda depois dele (-1 = sair, -2 = paciente fora da fila ativa)]
    stream = []
    while True:
        ev = con.execute("""SELECT id, tipo_evento, solicitacao_id FROM evento_clinico
                            WHERE processado_em IS NULL ORDER BY data_evento, id LIMIT 1""").fetchone()
        if ev is None:
            break
        r = processamento.processar_evento(con, ev["id"])
        acao = r["acao"] if r else "sem_mudanca"
        substituiu = 1 if r and r.get("substituiu") else 0
        sid = ev["solicitacao_id"]
        fila = -2
        if sid in indice:
            est = con.execute("SELECT fila, sair FROM estado_paciente WHERE solicitacao_id = %s", (sid,)).fetchone()
            fila = -1 if est["sair"] else FILAS.index(est["fila"])
        stream.append([TIPOS.index(ev["tipo_evento"]), ACOES[acao], substituiu, indice.get(sid, -1), fila])

    rec = {r["solicitacao_id"]: r for r in con.execute(
        "SELECT posicao, solicitacao_id, fila, justificativa FROM fila_recomendada").fetchall()}
    sols = {r["id"]: r for r in con.execute(
        """SELECT s.id, s.cid_principal, s.prioridade_regulacao, s.data_entrada_fila, p.nome AS proc
           FROM solicitacao s JOIN procedimento p ON p.id = s.procedimento_id
           WHERE s.status = 'ativa'""").fetchall()}
    bio_pos = {r["solicitacao_id"] for r in con.execute(
        """SELECT DISTINCT solicitacao_id FROM evento_clinico
           WHERE tipo_evento = 'biopsia' AND resultado = 'positivo'""").fetchall()}
    resumo_mud = con.execute(
        "SELECT status, count(*) AS n FROM solicitacao_mudanca GROUP BY 1").fetchall()

# --- "sem urgência clínica" exatamente como o verificador oficial
ds = BACK / "ideas/data/dataset"
fila = pd.read_csv(ds / "fila_cirurgica.csv")
ev = pd.read_csv(ds / "eventos_clinicos.csv", parse_dates=["data_evento"])
src = (BACK / "ideas/data/dataset/verificar_fila_priorizada.py").read_text()
KW = eval(re.search(r"KW_ALARME = (\(.*?\))\n", src, re.S).group(1))
CID_URGENTE = {"I200", "K403", "K400", "K420", "K430", "K800", "N132", "I832"}
f = fila.set_index("solicitacao_id")
f["cid"] = f.cid_principal.str.upper().str.replace(".", "", regex=False)
f["onco"] = f.cid.str.startswith("C")
piora = set(ev[ev.tipo_evento.isin(["pronto_socorro", "internacao"])
               | ((ev.tipo_evento == "biopsia") & (ev.resultado == "positivo"))
               | ((ev.tipo_evento == "exame_imagem") & (ev.resultado == "progressao"))
               | ((ev.tipo_evento == "consulta_reavaliacao") & (ev.resultado == "piora"))].solicitacao_id)
txt = f.justificativa_clinica.fillna("").str.lower().str.contains(KW, regex=True)
f["calmo"] = ((~f.onco) & (f.intensidade_dor_eva.fillna(0) <= 3)
              & f.limitacao_funcional.fillna("nenhuma").isin(["nenhuma", "leve"])
              & ~f.cid.isin(CID_URGENTE) & ~f.index.isin(piora) & ~txt)

# --- ordem manual de hoje: prioridade (alta, média, baixa, vazia), depois data de entrada
PRI = {"alta": 0, "media": 1, "baixa": 2}
final = sorted(rec, key=lambda s: rec[s]["posicao"])  # 897
manual = sorted(final, key=lambda s: (PRI.get(sols[s]["prioridade_regulacao"], 3),
                                      sols[s]["data_entrada_fila"], s))
pos_manual = {s: i + 1 for i, s in enumerate(manual)}

# Um ponto por solicitação ativa (902), na ordem oficial de hoje (só cadastro).
# [fila inicial, fila final (-1 = sai), flags, posição manual (0 = sai), posição recomendada]
# flags: 1 = CID C*, 2 = sem urgência (verificador), 4 = biópsia positiva sem CID C*
pontos = []
for s in ativos:
    fl = (1 if f.at[s, "onco"] else 0) | (2 if f.at[s, "calmo"] else 0) \
        | (4 if (s in bio_pos and not f.at[s, "onco"]) else 0)
    pontos.append([FILAS.index(inicial[s]["fila"]),
                   FILAS.index(rec[s]["fila"]) if s in rec else -1,
                   fl, pos_manual.get(s, 0), rec[s]["posicao"] if s in rec else 0])

heroi = "SOL-2026-00610"
dados = {
    "heroi": ativos.index(heroi),
    "pontos": pontos,
    "eventos": stream,
}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "fila.json").write_text(json.dumps(dados, separators=(",", ":")))
recibos = [[rec[s]["posicao"], s, rec[s]["fila"], sols[s]["cid_principal"], sols[s]["proc"],
            rec[s]["justificativa"]] for s in final]
(OUT / "recibos.json").write_text(json.dumps(recibos, ensure_ascii=False, separators=(",", ":")))

# --- conferência dos números do roteiro
calmo_m = [pos_manual[s] for s in final if f.at[s, "calmo"]]
onco_m = [pos_manual[s] for s in final if f.at[s, "onco"]]
onco_r = [rec[s]["posicao"] for s in final if f.at[s, "onco"]]
calmo_r = [rec[s]["posicao"] for s in final if f.at[s, "calmo"]]
cont = {k: 0 for k in ACOES}
for _, a, *_ in stream:
    cont[[k for k, v in ACOES.items() if v == a][0]] += 1
print("eventos", len(stream), cont, "substituiu", sum(e[2] for e in stream))
print("mudancas", [(r["status"], r["n"]) for r in resumo_mud])
print("ativos", len(ativos), "final", len(final))
print("manual: primeiro calmo", min(calmo_m), "| onco", len(onco_m), "min", min(onco_m),
      "| onco baixa", sum(1 for s in final if f.at[s, "onco"] and sols[s]["prioridade_regulacao"] == "baixa"),
      "| calmo alta", sum(1 for s in final if f.at[s, "calmo"] and sols[s]["prioridade_regulacao"] == "alta"))
print("recomendada: ultimo onco", max(onco_r), "primeiro calmo", min(calmo_r))
print("heroi manual", pos_manual[heroi], "oficial", inicial[heroi]["posicao_final"],
      "rec", rec[heroi]["posicao"], rec[heroi]["fila"])
print("bio+ sem C na final:", sum(1 for s in final if s in bio_pos and not f.at[s, "onco"]),
      "| em G1a/G2:", sum(1 for s in final if s in bio_pos and not f.at[s, "onco"] and rec[s]["fila"] in ("G1a", "G2")))
print("inicial por fila", {q: sum(1 for p in pontos if FILAS[p[0]] == q) for q in FILAS})
print("final por fila", {q: sum(1 for p in pontos if p[1] >= 0 and FILAS[p[1]] == q) for q in FILAS})
print("onco fora de G1a/G2 na final:", sum(1 for p in pontos if p[2] & 1 and p[1] not in (0, 2)))
print("onco fora de G1a/G2 só com cadastro:", sum(1 for p in pontos if p[2] & 1 and p[0] not in (0, 2)))
# a última fila recomendada de cada paciente nos eventos tem de bater com a fila recomendada final
ultima = {i: p[0] for i, p in enumerate(pontos)}
for e in stream:
    if e[3] >= 0:
        ultima[e[3]] = e[4]
print("trajetórias que não fecham com a final:", sum(1 for i, p in enumerate(pontos) if ultima[i] != p[1]))
atual = {i: p[0] for i, p in enumerate(pontos)}
mudou = 0
for e in stream:
    if e[3] >= 0 and e[4] != atual[e[3]]:
        mudou += 1
        atual[e[3]] = e[4]
print("eventos que mudam a fila recomendada:", mudou)
