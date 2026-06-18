"""
professor_credits.py
=====================
Feature "Lot 2 / #6" — Charge labo des professeurs et validation vs budget.

Ce que fait ce module (et ce qu'il NE fait PAS) :
  - Lit l'affectation OFFICIELLE (feuille "Asignacion docente").
  - Met les 4 blocs profs en forme longue : 1 ligne = (offre, prof, caractère T/P).
  - Calcule la charge labo par prof : Σ crédits P  ->  séances labo = crédits P x 5.
  - Joint le budget par prof depuis "Carga docente y de gestión"
    (colonne "Asignación recomendada"), avec repli explicite si absent.
  - SIGNALE les dépassements de budget. Ne bloque rien, ne ré-affecte rien.
    (L'affectation est une DONNÉE ; le système la valide, il ne la décide pas.)

Faits mesurés sur la donnée réelle (cf. exécution) à garder en tête :
  - Le budget "Asignación recomendada" est un budget TOTAL (T+P), pas un budget P.
    -> on signale donc la charge TOTALE vs budget, et on affiche la charge P à part.
  - ~17/127 profs dépassent déjà leur budget dans l'affectation officielle.
    -> un plafond DUR rendrait des données officielles "infaisables".
       Conclusion : signalement only.
  - Le co-encadrement (plusieurs profs P sur une même offre) est la norme.

Convention validée par le coordinateur : 1 crédit P = 5 séances de labo.
"""

import os
import sys
import unicodedata
import pandas as pd

CREDIT_TO_SESSIONS = 5
DEFAULT_FP = "Asignacion_2025-2026_v5.xlsx"

def _find_asignacion_file():
    """Localise le fichier Asignacion avec plusieurs chemins possibles."""
    candidates = [
        DEFAULT_FP,
        '/home/ubuntu/Uploads/Asignacion_2025-2026_v5.xlsx',
        '/home/ubuntu/Shared/Uploads/Asignacion_2025-2026_v5.xlsx',
        '/home/ubuntu/lab_project/Asignacion_2025-2026_v5.xlsx',
        'data/Asignacion_2025-2026_v5.xlsx',
        'data_clean/Asignacion_2025-2026_v5.xlsx',
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # Recherche récursive en dernier recours
    for root_dir in ['/home/ubuntu', os.getcwd()]:
        for dirpath, _, files in os.walk(root_dir):
            for f in files:
                if f.lower().startswith('asignacion') and f.endswith('.xlsx'):
                    return os.path.join(dirpath, f)
    return DEFAULT_FP


# --------------------------------------------------------------------------- #
# Helpers robustes (accents / décimales espagnoles / recherche de feuille)
# --------------------------------------------------------------------------- #
def _norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _to_num(x):
    if x is None:
        return 0.0
    s = str(x).strip().replace(",", ".")
    v = pd.to_numeric(s, errors="coerce")
    return 0.0 if pd.isna(v) else float(v)


def _find_sheet(xls, *keywords):
    """Trouve une feuille dont le nom normalisé contient TOUS les mots-clés."""
    for name in xls.sheet_names:
        n = _norm(name)
        if all(_norm(k) in n for k in keywords):
            return name
    raise KeyError(f"Feuille introuvable pour {keywords} parmi {xls.sheet_names}")


# --------------------------------------------------------------------------- #
# 1) Parser l'affectation -> forme longue
# --------------------------------------------------------------------------- #
def parse_assignment(fp=None):
    """
    Retourne un DataFrame en forme longue :
      offering_id, mixto_id, actividad_id, subject, curso, semestre,
      prof_code, credits, char  ('T' ou 'P')
    Une ligne par (offre de groupe, professeur non vide).
    """
    if fp is None:
        fp = _find_asignacion_file()
    xls = pd.ExcelFile(fp)
    sheet = _find_sheet(xls, "asignaci", "docente")
    raw = pd.read_excel(fp, sheet_name=sheet, header=0, dtype=str)
    raw.columns = [str(c).strip() for c in raw.columns]

    blocks = [
        (f"Prof. {i}", f"Cr. Prof. {i}", f"Tipo Asig. {i}")
        for i in (1, 2, 3, 4)
    ]
    rows = []
    for _, r in raw.iterrows():
        subj = r.get("Asignatura")
        if not subj or _norm(subj) in ("", "nan"):
            continue
        for pcol, ccol, kcol in blocks:
            name = r.get(pcol)
            if not name or _norm(name) in ("", "nan", "0"):
                continue
            char = str(r.get(kcol)).strip().upper()[:1]
            if char not in ("T", "P"):
                continue
            rows.append({
                "offering_id":  str(r.get("ID")).strip(),
                "mixto_id":     str(r.get("mixto ID")).strip(),
                "actividad_id": str(r.get("actividad ID")).strip(),
                "subject":      str(subj).strip(),
                "curso":        str(r.get("Curso")).strip(),
                "semestre":     str(r.get("Semestre")).strip(),
                "prof_code":    str(name).strip(),
                "credits":      _to_num(r.get(ccol)),
                "char":         char,
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 2) Crosswalk code -> (nom, budget) depuis "Carga docente y de gestión"
# --------------------------------------------------------------------------- #
def load_budgets(fp=None):
    """
    Retourne un DataFrame : prof_code, prof_name, budget, src_total_credits
      - budget = "Asignación recomendada" (budget TOTAL ; NaN si absent)
      - src_total_credits = "Total créditos" de la source (charge déjà imputée)
    """
    if fp is None:
        fp = _find_asignacion_file()
    xls = pd.ExcelFile(fp)
    sheet = _find_sheet(xls, "carga", "docente")
    cg = pd.read_excel(fp, sheet_name=sheet, header=0, dtype=str)
    cg.columns = [str(c).strip() for c in cg.columns]
    out = pd.DataFrame({
        "prof_code":         cg["Abreviatura"].astype(str).str.strip(),
        "prof_name":         cg["Profesor"].astype(str).str.strip(),
        "budget":            cg["Asignación recomendada"].map(
                                 lambda x: pd.to_numeric(str(x).replace(",", "."),
                                                         errors="coerce")),
        "src_total_credits": cg["Total créditos"].map(
                                 lambda x: pd.to_numeric(str(x).replace(",", "."),
                                                         errors="coerce")),
    })
    out = out[out["prof_code"].map(_norm).isin(["", "nan"]) == False]
    return out.drop_duplicates(subset="prof_code", keep="first")


# --------------------------------------------------------------------------- #
# 3) Charge labo par prof + validation budget
# --------------------------------------------------------------------------- #
def professor_lab_load(assign_df, budgets_df, default_budget=None):
    """
    Agrège par prof :
      lab_credits (Σ P), lab_sessions (= lab_credits x 5),
      theory_credits (Σ T), total_assigned (Σ T+P),
      prof_name, budget, margin, over_budget, budget_source
    default_budget : repli si le prof n'a pas de budget dans le fichier
                     (None = on laisse NaN et on ne juge pas le dépassement).
    """
    # totaux T / P / global par code
    piv = (assign_df.pivot_table(index="prof_code", columns="char",
                                 values="credits", aggfunc="sum", fill_value=0.0)
           .reset_index())
    for col in ("T", "P"):
        if col not in piv.columns:
            piv[col] = 0.0
    piv = piv.rename(columns={"P": "lab_credits", "T": "theory_credits"})
    piv["total_assigned"] = piv["lab_credits"] + piv["theory_credits"]
    piv["lab_sessions"] = piv["lab_credits"] * CREDIT_TO_SESSIONS

    # jointure budget / nom
    m = piv.merge(budgets_df, on="prof_code", how="left")
    m["prof_name"] = m["prof_name"].fillna(m["prof_code"])
    m["budget_source"] = m["budget"].map(
        lambda b: "fichier" if pd.notna(b) else
                  ("défaut" if default_budget is not None else "absent"))
    if default_budget is not None:
        m["budget"] = m["budget"].fillna(float(default_budget))

    m["margin"] = m["budget"] - m["total_assigned"]
    m["over_budget"] = m["total_assigned"] > m["budget"]   # NaN budget -> False

    cols = ["prof_code", "prof_name", "lab_credits", "lab_sessions",
            "theory_credits", "total_assigned", "budget", "budget_source",
            "margin", "over_budget", "src_total_credits"]
    return (m[cols]
            .sort_values(["lab_credits", "total_assigned"], ascending=False)
            .reset_index(drop=True))


# --------------------------------------------------------------------------- #
# Exécution / rapport
# --------------------------------------------------------------------------- #
def _report(fp):
    print(f"# Fichier : {fp}\n")
    assign = parse_assignment(fp)
    budgets = load_budgets(fp)

    # --- sanity check : reproduire l'exemple Física I du coordinateur ---
    #   (match EXACT "Física I" ; tri entier de l'offering_id, pas alpha)
    fis = assign[(assign.subject == "Física I") & (assign.char == "P")].copy()
    print("## Contrôle parser — 1re offre de Física I (séances = crédits x5)")
    first = fis.iloc[0:0]
    if len(fis):
        fis["_oid"] = pd.to_numeric(fis.offering_id, errors="coerce")
        first = fis[fis._oid == fis._oid.min()]
    for _, r in first.iterrows():
        print(f"   {r.prof_code:<6} {r.credits:>4g} cr P  ->  "
              f"{r.credits*CREDIT_TO_SESSIONS:>4g} séances")
    print()

    # --- portée labo ---
    labP = assign[assign.char == "P"]
    print("## Portée labo (caractère P)")
    print(f"   offres avec labo : {labP.offering_id.nunique()}")
    print(f"   lignes (prof x offre) P : {len(labP)}")
    print(f"   profs distincts en P : {labP.prof_code.nunique()}")
    print(f"   Σ crédits P : {labP.credits.sum():.1f}  "
          f"->  Σ séances labo : {labP.credits.sum()*CREDIT_TO_SESSIONS:.0f}")
    co = (labP.groupby('offering_id').prof_code.nunique() > 1).sum()
    print(f"   offres en co-encadrement (>1 prof P) : {co}")
    frac = labP[(labP.credits*CREDIT_TO_SESSIONS % 1) != 0]
    print(f"   lignes donnant un nb de séances NON entier : {len(frac)}")
    print()

    load = professor_lab_load(assign, budgets, default_budget=None)

    print("## Charge labo par prof — top 15")
    top = load[load.lab_credits > 0].head(15)
    hdr = f"{'Prof':<34}{'cr P':>6}{'séan.':>7}{'cr tot':>8}{'budget':>8}{'marge':>8}  flag"
    print(hdr)
    print("-" * len(hdr))
    for _, r in top.iterrows():
        b = "—" if pd.isna(r.budget) else f"{r.budget:g}"
        mg = "—" if pd.isna(r.margin) else f"{r.margin:+g}"
        flag = "⚠ DÉPASSE" if r.over_budget else ""
        print(f"{r.prof_name[:33]:<34}{r.lab_credits:>6g}{r.lab_sessions:>7g}"
              f"{r.total_assigned:>8g}{b:>8}{mg:>8}  {flag}")
    print()

    # --- validation budget (signalement, pas blocage) ---
    judged = load[load.budget.notna()]
    over = judged[judged.over_budget]
    print("## Validation budget (charge TOTALE T+P vs budget recommandé)")
    print(f"   profs avec budget connu : {len(judged)} / {len(load)} "
          f"(sans budget : {len(load)-len(judged)})")
    print(f"   profs en dépassement : {len(over)}  -> SIGNALÉS (jamais bloqués)")
    if len(over):
        for _, r in over.sort_values("margin").head(12).iterrows():
            print(f"      {r.prof_name[:33]:<34} "
                  f"{r.total_assigned:g} cr  >  budget {r.budget:g}  "
                  f"({r.margin:+g})")
    print()

    # --- contrôle croisé "Tabla Din Profes" ---
    try:
        xls = pd.ExcelFile(fp)
        tdp = pd.read_excel(fp, sheet_name=_find_sheet(xls, "tabla", "din", "profes"),
                            header=None, dtype=str)
        # somme des crédits "(P)" telle que tabulée dans le pivot officiel
        mask_p = tdp[1].astype(str).str.contains(r"\(P\)", na=False)
        tdp_P = pd.to_numeric(tdp.loc[mask_p, 2].astype(str).str.replace(",", "."),
                              errors="coerce").sum()
        print("## Contrôle croisé vs 'Tabla Din Profes'")
        print(f"   Σ crédits P (pivot officiel) : {tdp_P:.1f}   "
              f"| Σ crédits P (parser) : {labP.credits.sum():.1f}   "
              f"| écart : {abs(tdp_P - labP.credits.sum()):.1f}")
    except Exception as e:
        print(f"## Contrôle croisé indisponible : {e}")
    print()

    # --- export ---
    assign.to_csv("professor_assignment.csv", index=False)
    load.to_csv("professor_lab_load.csv", index=False)
    print("Écrit : professor_assignment.csv  |  professor_lab_load.csv")
    return assign, load


if __name__ == "__main__":
    fp = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FP
    _report(fp)