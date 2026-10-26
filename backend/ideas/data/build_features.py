"""Clean the surgical queue dataset and build one feature row per active request.

Outputs (in --out):
  features.csv   active queue as of --asof, all features (model, rules, readiness, baseline)
  removed.csv    requests taken out of the queue and why (duplicates, exits)
  train_h{N}.csv features as of (--asof - N days) + label "worsening in the next N days", for the risk model

Usage:
  python data/build_features.py [--data data/dataset] [--out out] [--asof 2026-10-23] [--horizon 90]
"""
import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

REF = pd.Timestamp("2026-10-23")

# Urgent non-oncologic CIDs, same set the official verifier uses
CID_URGENTE = {"I200", "K403", "K400", "K420", "K430", "K800", "N132", "I832"}
CID_INCERTO = r"^(D3[7-9]|D4[0-8]|R91)"

LIMITACAO = {"nenhuma": 0, "leve": 1, "moderada": 2, "grave": 3}
PORTE = {"pequeno": 1, "medio": 2, "grande": 3, "especial": 4}
UTI = {"nao": 0, "eventual": 1, "sim": 2}

COMORBIDADES = {
    "has": "has", "dm2": "dm", "obesidade": "obesidade", "tabagismo": "tabagismo", "dpoc": "dpoc",
    "cardiopatia isquemica": "cardiopatia_isquemica", "icc": "icc", "drc": "drc",
    "anticoagulacao oral": "anticoagulacao", "fibrilacao atrial": "fa",
}

# Events that count as clinical worsening
PIORA_TIPOS = {"pronto_socorro", "internacao"}
PIORA_RESULTADOS = {"progressao", "piora", "relata_piora"}
SAIDA_RESULTADOS = {"desistiu", "informou_cirurgia_outro_servico"}

# Regex stand-ins for the LLM text extraction. Same categories the LLM will return.
TXT_FLAGS = {
    "txt_obstrucao": r"encarcer|estrangul|suboclus|retencao urinaria aguda|hidronefrose",
    "txt_infeccao": r"colangite|sepse|pancreatite",
    "txt_sangramento": r"enterorragia|melena|hematemese|sangramento espontaneo|transfund|hemoptise",
    "txt_progressao_tumoral": r"crescimento rapido|linfonodo.*(?:fixo|palpavel)|perda ponderal|disfagia|rouquidao|psa em elevacao|massa anexial|ca-125",
    "txt_cardiorresp": r"angina em repouso|sincope|dessaturacao|retencao de co2",
    "txt_funcional": r"acamad|ulcera de pressao|quedas de repeticao|perda de funcao|dano neurologico|glaucoma facomorfico",
    "txt_suspeita_malignidade": r"carcinoma|maligno|suspeit|atipia|bi-rads ?[45]|pi-rads ?[45]|bethesda (?:iv|v|vi)\b",
    "txt_piora": r"piora|agrav|progress",
}
TXT_VAGA = r"^(solicito cirurgia|indicacao cirurgica|conforme laudo anexo|paciente com indicacao)"

OBS_FLAGS = {
    "obs_piora": r"piora|agilizar",
    "obs_internacao": r"intern|\bupa\b",
    "obs_sem_contato": r"sem sucesso|sem novo contato|fora de area",
    "obs_transporte": r"tfd|transporte|desloc",
}
OBS_SAIDA = r"desist|nao deseja mais operar|operou pelo convenio|cirurgia em outro servico"

# Inputs for the risk model (JEV). Everything else in features.csv is for rules, readiness or the baseline.
MODEL_FEATURES = [
    "idade", "sexo_f", "asa", "asa_faltante", "n_comorbidades",
    *[f"com_{v}" for v in COMORBIDADES.values()], "diabetico",
    "onco", "cid_incerto", "cid_urgente", "biopsia_positiva",
    "risco_cirurgico", "porte", "uti",
    "dor_eva", "dor_faltante", "limitacao", "limitacao_faltante",
    "piora_30d", "piora_90d", "piora_180d", "dias_desde_ultima_piora",
    "ps_180d", "internacao_180d", "dias_internado_180d", "progressao_imagem_180d",
    "reaval_piora_180d", "reaval_melhora_180d", "relata_piora_180d", "relata_melhora_180d", "faltas_180d",
    "hba1c_modelo", "sem_hba1c", "hba1c_delta",
    "dias_em_fila", "dias_desde_revisao",
    *TXT_FLAGS, "txt_vaga",
]


def norm_text(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    # crude negation: drop "sem <word>" / "sem sinais de <word>" before matching
    return re.sub(r"\bsem (?:sinais? de |evidencia de )?\w+", " ", s)


def load(data):
    fila = pd.read_csv(data / "fila_cirurgica.csv",
                       parse_dates=["data_entrada_fila", "data_ultima_revisao_prioridade", "data_hba1c_ultima"])
    ev = pd.read_csv(data / "eventos_clinicos.csv", parse_dates=["data_evento"])
    procs = pd.read_csv(data / "procedimentos.csv")
    return fila, ev, procs


def clean(fila, ev):
    """Normalize fields, merge duplicate requests, drop bad events. Returns (fila, ev, removed)."""
    f = fila.copy()
    f["cid"] = f.cid_principal.str.upper().str.replace(".", "", regex=False).str.strip()
    f["prioridade_manual"] = (f.prioridade_regulacao.str.lower().str.strip()
                              .str.replace("é", "e", regex=False))
    f["municipio"] = f.municipio.str.strip().str.title()
    for c in ("justificativa_clinica", "observacoes"):
        f[c] = f[c].fillna("")

    # Duplicates: same patient + procedure. Keep the earliest entry, carry over the other rows' text and events.
    f = f.sort_values("data_entrada_fila")
    grp = f.groupby(["paciente_id", "procedimento_id"])
    keep_id = grp.solicitacao_id.transform("first")
    dup = f[f.solicitacao_id != keep_id]
    remap = dict(zip(dup.solicitacao_id, keep_id[dup.index]))
    for c in ("justificativa_clinica", "observacoes"):
        f[c] = grp[c].transform(lambda s: " | ".join(dict.fromkeys(x for x in s if x)))
    f = f[f.solicitacao_id == keep_id].copy()
    removed = [{"solicitacao_id": s, "motivo": "duplicada", "detalhe": f"mantida {k}"} for s, k in remap.items()]

    e = ev.copy()
    e["solicitacao_id"] = e.solicitacao_id.replace(remap)
    e = e[e.solicitacao_id.isin(f.solicitacao_id)]
    e = e.drop_duplicates(["solicitacao_id", "data_evento", "tipo_evento", "resultado", "descricao"])
    return f, e, removed


def exits(f, e, asof):
    """Requests that left the queue: exit event up to asof, or exit note in observacoes (undated)."""
    ev_out = e[e.resultado.isin(SAIDA_RESULTADOS) & (e.data_evento <= asof)]
    out = {s: r for s, r in zip(ev_out.solicitacao_id, ev_out.resultado)}
    obs = f.observacoes.map(norm_text)
    for s in f.solicitacao_id[obs.str.contains(OBS_SAIDA, regex=True)]:
        out.setdefault(s, "observacao")
    return out


def event_features(f, e, asof):
    e = e[e.data_evento <= asof].copy()
    e["dias_atras"] = (asof - e.data_evento).dt.days
    e["piora"] = e.tipo_evento.isin(PIORA_TIPOS) | e.resultado.isin(PIORA_RESULTADOS)
    w180 = e[e.dias_atras <= 180]

    def count(df, mask, name):
        return df[mask].groupby("solicitacao_id").size().rename(name)

    cols = [count(e, e.piora & (e.dias_atras <= d), f"piora_{d}d") for d in (30, 90, 180)]
    cols += [
        e[e.piora].groupby("solicitacao_id").dias_atras.min().rename("dias_desde_ultima_piora"),
        count(w180, w180.tipo_evento == "pronto_socorro", "ps_180d"),
        count(w180, w180.tipo_evento == "internacao", "internacao_180d"),
        w180[w180.tipo_evento == "internacao"].groupby("solicitacao_id").valor_numerico.sum().rename("dias_internado_180d"),
        count(w180, w180.resultado == "progressao", "progressao_imagem_180d"),
        count(w180, (w180.tipo_evento == "consulta_reavaliacao") & (w180.resultado == "piora"), "reaval_piora_180d"),
        count(w180, (w180.tipo_evento == "consulta_reavaliacao") & (w180.resultado == "melhora"), "reaval_melhora_180d"),
        count(w180, w180.resultado == "relata_piora", "relata_piora_180d"),
        count(w180, w180.resultado == "relata_melhora", "relata_melhora_180d"),
        count(w180, w180.tipo_evento == "falta", "faltas_180d"),
        count(e, (e.tipo_evento == "biopsia") & (e.resultado == "positivo"), "biopsia_positiva"),
    ]
    hb = e[e.tipo_evento == "hba1c"].sort_values("data_evento").groupby("solicitacao_id").valor_numerico
    cols += [hb.last().rename("hba1c_ultima_ev"), (hb.last() - hb.first()).rename("hba1c_delta"), hb.size().rename("n_hba1c")]

    out = pd.concat(cols, axis=1).reindex(f.solicitacao_id)
    counts = [c for c in out.columns if c not in ("dias_desde_ultima_piora", "hba1c_ultima_ev", "hba1c_delta")]
    out[counts] = out[counts].fillna(0).astype(int)
    out["biopsia_positiva"] = out.biopsia_positiva > 0
    out["dias_desde_ultima_piora"] = out.dias_desde_ultima_piora.fillna(9999).astype(int)
    out["hba1c_delta"] = out.hba1c_delta.fillna(0.0)
    return out.reset_index()


def build(fila, ev, procs, asof):
    """Feature table for every request active at `asof`, plus the list of removed requests."""
    f, e, removed = clean(fila[fila.data_entrada_fila <= asof], ev)
    out = exits(f, e, asof)
    removed += [{"solicitacao_id": s, "motivo": "saiu_da_fila", "detalhe": r} for s, r in out.items()]
    f = f[~f.solicitacao_id.isin(out)].merge(
        procs[["procedimento_id", "porte", "risco_cirurgico", "necessita_uti", "duracao_media_min"]], on="procedimento_id")

    x = f[["solicitacao_id", "paciente_id", "procedimento_id", "especialidade", "cid", "cid_descricao",
           "idade", "risco_cirurgico", "duracao_media_min", "prioridade_manual", "municipio", "distancia_hospital_km"]].copy()
    x["sexo_f"] = f.sexo.eq("F")
    x["asa_faltante"] = f.asa.isna()
    x["asa"] = f.asa.fillna(f.asa.median())
    x["porte"] = f.porte.map(PORTE)
    x["uti"] = f.necessita_uti.map(UTI)

    # Diagnosis, from the CID (never the manual flag)
    x["onco"] = f.cid.str.startswith("C")
    x["cid_incerto"] = f.cid.str.match(CID_INCERTO)
    x["cid_urgente"] = f.cid.isin(CID_URGENTE)
    x["cid_capitulo"] = f.cid.str[0]

    # Clinical status
    x["dor_faltante"] = f.intensidade_dor_eva.isna()
    x["dor_eva"] = f.intensidade_dor_eva.fillna(f.intensidade_dor_eva.median())
    lim = f.limitacao_funcional.map(LIMITACAO)
    x["limitacao_faltante"] = lim.isna()
    x["limitacao"] = lim.fillna(lim.median())

    # Comorbidities from the list + secondary CID + text
    tokens = f.comorbidades.fillna("").str.lower().str.split(";").map(lambda t: {s.strip() for s in t} - {"", "nenhuma"})
    x["n_comorbidades"] = tokens.map(len)
    for raw, name in COMORBIDADES.items():
        x[f"com_{name}"] = tokens.map(lambda t, raw=raw: raw in t)

    txt = f.justificativa_clinica.map(norm_text)
    obs = f.observacoes.map(norm_text)
    for name, pat in TXT_FLAGS.items():
        x[name] = txt.str.contains(pat, regex=True)
    x["txt_vaga"] = txt.str.strip().str.match(TXT_VAGA) | (txt.str.len() < 40)
    for name, pat in OBS_FLAGS.items():
        x[name] = obs.str.contains(pat, regex=True)

    x = x.merge(event_features(f, e, asof), on="solicitacao_id", how="left")
    x["sem_hba1c"] = x.n_hba1c == 0
    x["hba1c_modelo"] = x.hba1c_ultima_ev.fillna(x.hba1c_ultima_ev.median())

    # Rebuilt flags (evidence-based, ignoring the manual ones)
    x["diabetico"] = (x.com_dm | f.cid_secundario.fillna("").str.upper().str.match(r"^E1[0-4]").values
                      | txt.str.contains(r"\bdm\b|diabet", regex=True).values | (x.n_hba1c > 0))
    x["piora_clinica"] = (x.piora_180d > 0) | x.txt_piora | x.obs_piora | x.obs_internacao
    x["suspeita_malignidade"] = ~x.onco & (x.biopsia_positiva | (x.cid_incerto & x.txt_suspeita_malignidade))

    # Time
    x["dias_em_fila"] = (asof - f.data_entrada_fila).dt.days.values
    x["dias_desde_revisao"] = (asof - f.data_ultima_revisao_prioridade).dt.days.values

    # Readiness (not severity: never lowers priority)
    hba1c = x.hba1c_ultima_ev.fillna(f.hba1c_ultima)  # both indexed 0..n-1 after the merges
    x["pre_anestesica"] = f.avaliacao_pre_anestesica.values
    x["exames_pre_op_validos"] = f.exames_pre_op_validos.eq("sim").values
    x["hba1c_descontrolada"] = hba1c > 8.5
    x["pronto_para_agendar"] = x.pre_anestesica.eq("realizada") & x.exames_pre_op_validos & ~x.hba1c_descontrolada

    # Manual fields kept only to compare against (baseline), never as model inputs
    x["flag_oncologico_manual"] = f.flag_oncologico.eq("sim").values
    x["flag_piora_manual"] = f.flag_piora_clinica.eq("sim").values

    bools = x.select_dtypes(bool).columns
    x[bools] = x[bools].astype(int)
    return x, pd.DataFrame(removed)


def label(e, ids, asof, horizon):
    """1 if the request had a worsening event in (asof, asof + horizon]."""
    win = e[(e.data_evento > asof) & (e.data_evento <= asof + pd.Timedelta(days=horizon))]
    hit = win[win.tipo_evento.isin(PIORA_TIPOS) | win.resultado.isin(PIORA_RESULTADOS)].solicitacao_id
    return ids.isin(hit).astype(int)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path(__file__).resolve().parent / "dataset")
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--asof", type=pd.Timestamp, default=REF)
    ap.add_argument("--horizon", type=int, default=90, help="label horizon in days for the training table")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    fila, ev, procs = load(a.data)
    feats, removed = build(fila, ev, procs, a.asof)
    feats.to_csv(a.out / "features.csv", index=False)
    removed.to_csv(a.out / "removed.csv", index=False)

    t0 = a.asof - pd.Timedelta(days=a.horizon)
    train, _ = build(fila, ev, procs, t0)
    # events for duplicates were remapped inside build; redo the remap for the label window
    _, e_clean, _ = clean(fila, ev)
    train["label"] = label(e_clean, train.solicitacao_id, t0, a.horizon).values
    train[["solicitacao_id", *MODEL_FEATURES, "label"]].to_csv(a.out / f"train_h{a.horizon}.csv", index=False)

    print(f"as of {a.asof.date()}: {len(feats)} active requests, {len(removed)} removed "
          f"({dict(removed.motivo.value_counts())})")
    print(f"  onco {feats.onco.sum()} | suspected malignancy {feats.suspeita_malignidade.sum()} | "
          f"worsening (rebuilt) {feats.piora_clinica.sum()} | ready to schedule {feats.pronto_para_agendar.sum()}")
    print(f"training table as of {t0.date()}: {len(train)} rows, {train.label.sum()} positives "
          f"({train.label.mean():.0%}), {len(MODEL_FEATURES)} model features")
    nulls = feats[MODEL_FEATURES].isna().sum()
    if nulls.any():
        print("  nulls in model features:", dict(nulls[nulls > 0]))


if __name__ == "__main__":
    main()
