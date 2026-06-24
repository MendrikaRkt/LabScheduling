"""
lab_professor_assignment.py
===========================
Assignation des professeurs aux séances de laboratoire EN RESPECTANT
EXACTEMENT les crédits P de chaque professeur (convention : 1 crédit P = 5 séances).

CONTEXTE
--------
La feuille « Vista profesor » des fichiers `Distribucion_Practicas_*.xlsx`
affichait, jusqu'ici, un professeur choisi par simple ROTATION parmi tous les
professeurs « habilités » pour la matière (fichier subject_professors.csv).
Cette rotation répartit les séances de façon ~uniforme et IGNORE totalement :
  - le nombre de crédits P réel de chaque professeur,
  - le fait que certains noms listés ne font QUE de la théorie (T) pour la matière,
  - la répartition correcte entre plusieurs professeurs d'une même offre.

Ce module reconstruit l'assignation à partir de la SOURCE officielle
(feuille « Asignacion docente » de Asignacion_2025-2026_v5.xlsx) :

  * Une matière comporte une ou plusieurs OFFRES (lignes de la feuille).
  * Chaque offre déclare un nombre de « Grupos Prácticas » et jusqu'à 4
    professeurs avec (crédits, caractère T/P).
  * Convention métier : 1 crédit P = 5 séances = 1 groupe de pratiques complet
    (chaque groupe réalise 5 séances de labo).
    => un professeur avec k crédits P encadre k groupes de l'offre.
  * Les numéros de groupes sont attribués de façon cumulative, dans l'ordre des
    offres (ID croissant), ce qui reproduit la numérotation des fichiers générés
    (ex. Física : offres de 5+5+3+2 groupes -> groupes 1..15).

RÉSULTAT
--------
  - build_group_professor_map(fp) -> dict {(subject_clean, group_number): prof_name}
  - expected_sessions(fp)         -> DataFrame (subject, prof, credits_P, sessions)
  - write_subject_group_professors(fp, out) -> CSV consommable par le générateur

Les écarts de cohérence de la source (Σ crédits P d'une offre ≠ nb de groupes,
crédits fractionnaires) sont RÉPARTIS au plus juste (méthode du plus fort reste)
et SIGNALÉS, jamais bloqués — conformément à la philosophie du projet
(« l'affectation est une donnée ; le système la valide, il ne la décide pas »).
"""

from __future__ import annotations
import json
import math
import os
import unicodedata
import pandas as pd

CREDIT_TO_SESSIONS = 5
SESSIONS_PER_GROUP = 5  # chaque groupe de pratiques = 5 séances

# ---------------------------------------------------------------------------
# Committed cache (definitive N/D fix)
# ---------------------------------------------------------------------------
# The raw `Asignacion_*.xlsx` source is gitignored and is NOT present in the
# packaged / deployed application — so resolving it at runtime can fail and the
# Teacher View used to fall back to "N/A". To make the per-professor breakdown
# AVAILABLE EVERYWHERE, the source-derived data (which is stable) is persisted
# to a small committed JSON cache. When the xlsx cannot be located, the public
# functions below transparently read this cache instead, so professor names,
# P credits and expected sessions are always shown.
CACHE_BASENAME = "lab_professor_weights.json"
CACHE_CANDIDATES = [
    CACHE_BASENAME,
    os.path.join("data_clean", "optimizarion", CACHE_BASENAME),
    os.path.join("data_clean", CACHE_BASENAME),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), CACHE_BASENAME),
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "data_clean", "optimizarion", CACHE_BASENAME),
]

# Correspondance « nom de matière généré (nettoyé) » -> « nom de matière source ».
# Les fichiers générés utilisent un libellé court ; la source utilise le libellé
# administratif complet. Cette table fait le pont (clés normalisées sans accents).
SUBJECT_ALIASES = {
    "fisica": "Física I",
    "fisica ii": "Física II",
    "quimica": "Química General",
    "electrotecnia": "Electrotecnia",
    "mecanismos": "Mecanismos y Elementos de Máquinas",
    "termodinamica": "Termodinámica y Transferencia de Calor",
    "tecnologias de fabricacion": "Tecnologías de Fabricación",
    "robotica y automatizacion": "Robótica y Automatización Industrial",
    "automatizacion industrial": "Automatización de sistemas de producción",
    "tecnologia medio ambiente": "Tecnología del Medio Ambiente",
    "resistencia de materiales": "Resistencia de Materiales",
    "mecanica de fluidos": "Mecánica y máquinas de Fluidos",
    "regulacion automatica": "Regulación Automática",
    "tecnologia electronica": "Tecnología Electrónica",
    "electronica y automatica": "Electrónica y Automática",
    "informatica y com. industriales": "Informática y Comunicaciones Industriales",
    "informatica y comunicaciones industriales": "Informática y Comunicaciones Industriales",
    "metodos numericos": "Métodos Numéricos en Ingeniería",
    "modelado de sistemas": "Modelado de Sistemas Físicos II",
    "automatic control": "Automatic Control",
    "ingenieria de control": "Ingeniería de Control",
    "control de maquinas": "Control de Máquinas y Accionamientos Eléctricos",
    "estructuras": "Estructuras",
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


# Cache interne : clé d'alias normalisée -> nom de matière SOURCE normalisé.
_ALIAS_TO_SOURCE = None


def _alias_to_source():
    """Construit {alias_normalisé: source_normalisée} à partir de SUBJECT_ALIASES."""
    global _ALIAS_TO_SOURCE
    if _ALIAS_TO_SOURCE is None:
        _ALIAS_TO_SOURCE = {_norm(k): _norm(v) for k, v in SUBJECT_ALIASES.items()}
    return _ALIAS_TO_SOURCE


def canonical_subject_key(name):
    """Clé canonique STABLE et robuste aux variantes de libellé d'une matière.

    Les fichiers générés emploient parfois un libellé court (« Informática y
    Com. Industriales ») là où la source utilise le libellé complet
    (« Informática y Comunicaciones Industriales »). Plusieurs alias peuvent
    donc désigner la même matière. Cette fonction renvoie une clé UNIQUE par
    matière (le nom source normalisé) quelle que soit l'orthographe d'entrée,
    de sorte que la « Teacher View » et le cache concordent toujours.

    Pour une matière hors SUBJECT_ALIASES, renvoie simplement son nom normalisé.
    """
    n = _norm(name)
    return _alias_to_source().get(n, n)


def _to_num(x):
    if x is None:
        return 0.0
    v = pd.to_numeric(str(x).strip().replace(",", "."), errors="coerce")
    return 0.0 if pd.isna(v) else float(v)


def _find_sheet(xls, *keywords):
    for name in xls.sheet_names:
        n = _norm(name)
        if all(_norm(k) in n for k in keywords):
            return name
    raise KeyError(f"Feuille introuvable pour {keywords} parmi {xls.sheet_names}")


def _find_weights_cache():
    """Renvoie le chemin du cache JSON committé, ou None s'il est introuvable."""
    for c in CACHE_CANDIDATES:
        if c and os.path.exists(c):
            return c
    # via app_paths si disponible (déploiement / workspace)
    try:
        import app_paths as _ap
        for rel in (CACHE_BASENAME,
                    os.path.join("data_clean", "optimizarion", CACHE_BASENAME)):
            r = _ap.resolve_existing(rel)
            if r and os.path.exists(r):
                return r
    except Exception:
        pass
    return None


def load_weights_cache():
    """Charge le cache committé des poids/séances dérivés de la source.

    Structure attendue :
        {
          "weights":  {subject_clean: [[prof_name, eff_credits], ...]},
          "expected": {subject_clean: [[prof_name, groups, sessions], ...]}
        }
    Renvoie le dict, ou None si le cache est absent ou illisible.
    """
    fp = _find_weights_cache()
    if not fp:
        return None
    try:
        with open(fp, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data.get("weights"):
            return data
    except Exception:
        pass
    return None


def write_weights_cache(fp, out_path=None):
    """Génère le cache committé à partir de la source Asignación (fp).

    Persiste les poids effectifs par matière ET les séances attendues idéales
    (carte source agrégée par professeur), de sorte que la Teacher View puisse
    être produite SANS le fichier xlsx (correction définitive du « N/D »).
    """
    if out_path is None:
        out_path = os.path.join("data_clean", "optimizarion", CACHE_BASENAME)
    weights = subject_professor_weights(fp)
    exp = expected_sessions(fp)
    expected = {}
    for _, r in exp.iterrows():
        expected.setdefault(r["subject_clean"], []).append(
            [r["prof_name"], int(r["groups"]), int(r["sessions_expected"])])
    payload = {
        "generated_from": os.path.basename(str(fp)),
        "convention": "1 P credit = 5 sessions",
        "weights": {s: [[n, round(float(v), 6)] for n, v in lst]
                    for s, lst in weights.items()},
        "expected": expected,
        # Repli prof de théorie pour les matières sans aucun crédit P (ex.
        # « Estructuras ») : évite « N/A » quand un labo a malgré tout été planifié.
        "theory": theory_professors(fp),
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return out_path


def _load_code_to_name(fp):
    """Abréviation de professeur -> nom complet, depuis 'Carga docente'."""
    xls = pd.ExcelFile(fp)
    sheet = _find_sheet(xls, "carga", "docente")
    cg = pd.read_excel(fp, sheet_name=sheet, header=0, dtype=str)
    cg.columns = [str(c).strip() for c in cg.columns]
    out = {}
    for _, r in cg.iterrows():
        code = str(r.get("Abreviatura") or "").strip()
        name = str(r.get("Profesor") or "").strip()
        if code and code.lower() != "nan":
            out[code] = name if name and name.lower() != "nan" else code
    return out


# --------------------------------------------------------------------------- #
# 1) Extraction des offres de labo par matière (une ligne par bloc professeur
#    impliqué dans les pratiques : caractère 'P' ou 'TP')
# --------------------------------------------------------------------------- #
def parse_lab_offerings(fp):
    """
    Retourne un DataFrame, une ligne par (offre, bloc-professeur de pratiques) :
      subject_src, subject_clean, curso, semestre, offering_id,
      grupos_practicas, cred_P_offering, prof_code, prof_name,
      char ('P' ou 'TP'), credits_block
    `cred_P_offering` est la colonne OFFICIELLE « Créditos P » de l'offre : c'est
    le BUDGET P faisant autorité (Σ sur les offres × 5 = nb total de séances,
    ce qui correspond au total produit par l'optimiseur).
    `credits_block` est la valeur « Cr. Prof. » brute du bloc (pour un bloc TP
    elle inclut la théorie ; elle est donc retraitée plus loin).
    Seules les matières présentes dans SUBJECT_ALIASES sont retenues.
    """
    xls = pd.ExcelFile(fp)
    sheet = _find_sheet(xls, "asignaci", "docente")
    raw = pd.read_excel(fp, sheet_name=sheet, header=0, dtype=str)
    raw.columns = [str(c).strip() for c in raw.columns]
    code2name = _load_code_to_name(fp)

    src_to_clean = {_norm(v): k for k, v in SUBJECT_ALIASES.items()}

    blocks = [(f"Prof. {i}", f"Cr. Prof. {i}", f"Tipo Asig. {i}") for i in (1, 2, 3, 4)]
    rows = []
    for _, r in raw.iterrows():
        subj = str(r.get("Asignatura") or "").strip()
        if not subj or subj.lower() == "nan":
            continue
        if _norm(subj) not in src_to_clean:
            continue
        clean = src_to_clean[_norm(subj)]
        for pcol, ccol, kcol in blocks:
            name = r.get(pcol)
            if not name or str(name).strip().lower() in ("", "nan", "0", "none"):
                continue
            char = str(r.get(kcol)).strip().upper()
            if "P" not in char:          # garde P et TP, ignore T pur
                continue
            cr = _to_num(r.get(ccol))
            if cr <= 0:
                continue
            code = str(name).strip()
            rows.append({
                "subject_src":      subj,
                "subject_clean":    clean,
                "curso":            str(r.get("Curso")).strip(),
                "semestre":         str(r.get("Semestre")).strip(),
                "offering_id":      str(r.get("ID")).strip(),
                "grupos_practicas": _to_num(r.get("Grupos Prácticas")),
                "cred_P_offering":  _to_num(r.get("Créditos P")),
                "prof_code":        code,
                "prof_name":        code2name.get(code, code),
                "char":             "TP" if char == "TP" else "P",
                "credits_block":    cr,
            })
    df = pd.DataFrame(rows)
    if len(df):
        df["_oid"] = pd.to_numeric(df["offering_id"], errors="coerce")
        df = df.sort_values(["subject_clean", "_oid"]).drop(columns="_oid")
    return df.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 2) Crédits P EFFECTIFS par professeur dans une offre
# --------------------------------------------------------------------------- #
def effective_p_credits(group_rows, budget):
    """
    Calcule les crédits P effectifs de chaque bloc d'une offre, de sorte que
    leur somme vaille EXACTEMENT `budget` (= Créditos P officiel de l'offre, ou,
    à défaut, le nombre de groupes de pratiques).

    Règles (conçues pour être EXACTES sur les offres cohérentes et raisonnables
    sur les cas ambigus, conformément à « signaler, ne pas re-décider ») :
      - bloc P pur  -> poids de base = Cr. Prof. (crédits déjà purement P) ;
      - bloc TP     -> poids de base = 0 (la part P n'est pas explicite) ;
      - résidu = budget − Σ(base P pur) :
          * résidu > 0 et blocs TP présents
                -> le résidu est réparti entre les blocs TP au prorata de leur
                   « Cr. Prof. » (estimation de leur part de pratiques) ;
          * résidu > 0 sans bloc TP
                -> réparti entre les blocs P au prorata de leur base ;
          * résidu < 0 (sur-assignation : Σ P pur > budget)
                -> les bases P sont réduites au prorata pour sommer au budget.
    Retourne une liste de crédits effectifs (même ordre que group_rows) ;
    Σ = budget (à l'arrondi flottant près).
    """
    chars = [r["char"] for r in group_rows]
    blocks = [r["credits_block"] for r in group_rows]
    base = [b if c == "P" else 0.0 for b, c in zip(blocks, chars)]
    sum_pure = sum(base)
    residual = budget - sum_pure

    tp_idx = [i for i, c in enumerate(chars) if c == "TP"]
    eff = list(base)

    if abs(residual) < 1e-9:
        return eff
    if residual > 0:
        if tp_idx:
            tp_total = sum(blocks[i] for i in tp_idx) or float(len(tp_idx))
            for i in tp_idx:
                w = blocks[i] / tp_total if tp_total else 1.0 / len(tp_idx)
                eff[i] = residual * w
        elif sum_pure > 0:
            eff = [b * budget / sum_pure for b in base]
        else:
            # aucun bloc exploitable : répartition uniforme
            eff = [budget / len(group_rows)] * len(group_rows)
    else:  # residual < 0 : sur-assignation -> réduire les blocs P purs
        if sum_pure > 0:
            eff = [b * budget / sum_pure for b in base]
    return eff


# --------------------------------------------------------------------------- #
# 3) Répartition de crédits effectifs -> groupes entiers (plus fort reste)
# --------------------------------------------------------------------------- #
def _allocate_groups(weights, n_groups):
    """
    Répartit `n_groups` groupes entiers proportionnellement aux poids fournis.
    Cas nominal : poids entiers sommant à n_groups -> chacun reçoit son poids.
    Sinon : méthode du plus fort reste pour garantir Σ groupes == n_groups.
    """
    total = sum(weights)
    if n_groups <= 0 or total <= 0:
        return [0] * len(weights)
    raw = [w / total * n_groups for w in weights]
    floors = [int(math.floor(x)) for x in raw]
    deficit = n_groups - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in range(max(0, deficit)):
        floors[order[i % len(order)]] += 1
    return floors


# --------------------------------------------------------------------------- #
# 4) Carte (matière, groupe) -> professeur + diagnostics
# --------------------------------------------------------------------------- #
def build_group_professor_map(fp, return_diagnostics=False):
    """
    Retourne dict {(subject_clean, group_number): prof_name}.
    Les numéros de groupes sont attribués cumulativement par matière dans
    l'ordre des offres (ID croissant), reproduisant la numérotation des fichiers
    générés (ex. Física : offres 5+5+3+2 -> groupes 1..15).
    Si return_diagnostics=True, retourne aussi la liste des diagnostics par offre.
    """
    off = parse_lab_offerings(fp)
    gmap = {}
    diags = []
    for clean, sub in off.groupby("subject_clean"):
        next_group = 1
        for oid, grp in sub.groupby("offering_id", sort=False):
            grp = grp.reset_index(drop=True)
            n_groups = int(round(grp["grupos_practicas"].iloc[0]))
            budget = grp["cred_P_offering"].iloc[0]
            # budget faisant autorité : Créditos P de l'offre ; repli = nb groupes
            if budget <= 0:
                budget = float(n_groups)
            rows = grp.to_dict("records")
            names = [r["prof_name"] for r in rows]
            sum_pure_p = sum(r["credits_block"] for r in rows if r["char"] == "P")
            has_tp = any(r["char"] == "TP" for r in rows)

            eff = effective_p_credits(rows, budget)
            alloc = _allocate_groups(eff, n_groups)

            g = next_group
            for name, k in zip(names, alloc):
                for _ in range(k):
                    gmap[(clean, g)] = name
                    g += 1
            next_group += n_groups

            # cohérence : crédits P purs == budget officiel, sans bloc TP
            coherent = (not has_tp) and abs(sum_pure_p - budget) < 1e-6
            if has_tp:
                status = "TP_estimé"
            elif abs(sum_pure_p - budget) < 1e-6:
                status = "cohérent"
            elif sum_pure_p > budget:
                status = "sur-assignation_source"
            else:
                status = "sous-assignation_source"
            diags.append({
                "subject_clean": clean,
                "offering_id": oid,
                "n_groups": n_groups,
                "cred_P_offering": round(budget, 3),
                "sum_pure_P": round(sum_pure_p, 3),
                "has_TP": has_tp,
                "groups_assigned": {n: a for n, a in zip(names, alloc)},
                "eff_credits": {n: round(e, 3) for n, e in zip(names, eff)},
                "status": status,
                "coherent": coherent,
            })
    if return_diagnostics:
        return gmap, diags
    return gmap


# --------------------------------------------------------------------------- #
# 5) Séances attendues par (matière, professeur) — selon la carte effective
# --------------------------------------------------------------------------- #
def expected_sessions(fp=None):
    """
    DataFrame : subject_clean, prof_name, groups, sessions_expected
    (sessions_expected = groupes attribués × 5), c.-à-d. la cible exacte que la
    feuille « Teacher View » corrigée doit reproduire.

    Si `fp` (Asignación xlsx) est absent/introuvable, reconstruit le DataFrame
    depuis le cache committé (correction définitive du « N/D »).
    """
    if not fp or not os.path.exists(str(fp)):
        cache = load_weights_cache()
        if cache and cache.get("expected"):
            rows = [{"subject_clean": canonical_subject_key(s), "prof_name": p,
                     "groups": int(g), "sessions_expected": int(sess)}
                    for s, lst in cache["expected"].items()
                    for p, g, sess in lst]
            df = pd.DataFrame(rows, columns=["subject_clean", "prof_name",
                                             "groups", "sessions_expected"])
            return df.sort_values(["subject_clean", "sessions_expected"],
                                  ascending=[True, False]).reset_index(drop=True)
        return pd.DataFrame(columns=["subject_clean", "prof_name",
                                     "groups", "sessions_expected"])
    gmap = build_group_professor_map(fp)
    agg = {}
    for (subj, _g), prof in gmap.items():
        agg[(canonical_subject_key(subj), prof)] = \
            agg.get((canonical_subject_key(subj), prof), 0) + 1
    rows = [{"subject_clean": s, "prof_name": p, "groups": n,
             "sessions_expected": n * SESSIONS_PER_GROUP}
            for (s, p), n in agg.items()]
    df = pd.DataFrame(rows)
    return df.sort_values(["subject_clean", "sessions_expected"],
                          ascending=[True, False]).reset_index(drop=True)


def subject_professor_weights(fp=None):
    """
    Poids de pratiques EFFECTIFS par professeur, agrégés au niveau matière :
      {subject_clean: [(prof_name, eff_credits), ...]} (ordre décroissant).
    Ces poids servent à répartir, AU PRORATA des crédits P, les groupes
    RÉELLEMENT planifiés par l'optimiseur — dont le nombre peut différer du
    nombre administratif « Grupos Prácticas » de la source.

    Si `fp` (Asignación xlsx) est absent/introuvable, lit le cache committé
    (correction définitive du « N/D »).
    """
    if not fp or not os.path.exists(str(fp)):
        cache = load_weights_cache()
        if cache and cache.get("weights"):
            # Re-clé par clé canonique : robustesse aux variantes de libellé.
            return {canonical_subject_key(s): [(n, float(v)) for n, v in lst]
                    for s, lst in cache["weights"].items()}
        return {}
    off = parse_lab_offerings(fp)
    weights = {}
    for clean, sub in off.groupby("subject_clean"):
        acc = {}
        for _oid, grp in sub.groupby("offering_id", sort=False):
            grp = grp.reset_index(drop=True)
            n_groups = int(round(grp["grupos_practicas"].iloc[0]))
            budget = grp["cred_P_offering"].iloc[0]
            if budget <= 0:
                budget = float(n_groups)
            rows = grp.to_dict("records")
            eff = effective_p_credits(rows, budget)
            for r, e in zip(rows, eff):
                acc[r["prof_name"]] = acc.get(r["prof_name"], 0.0) + e
        weights[canonical_subject_key(clean)] = \
            sorted(acc.items(), key=lambda kv: kv[1], reverse=True)
    return weights


def assign_schedule_groups(fp, subject_to_groups):  # fp peut être None -> cache
    """
    Affecte les groupes RÉELLEMENT planifiés aux professeurs, au prorata des
    crédits P effectifs.

    subject_to_groups : {subject_clean: [liste des numéros de groupes planifiés]}
    Retourne {(subject_clean, group_number): prof_name}.

    Là où le volume planifié == volume source (ex. Física, Química), le nombre de
    séances par professeur égale EXACTEMENT crédits P × 5. Là où il diffère, la
    PROPORTION des crédits P est respectée et l'écart de volume est signalé par
    le rapport de validation.
    """
    weights = subject_professor_weights(fp)  # déjà re-clé en canonique
    gmap = {}
    for subj, groups in subject_to_groups.items():
        groups = sorted(set(groups))
        # `subj` peut être un libellé court ; on le canonicalise pour retrouver
        # les poids (et on conserve `subj` comme clé de sortie, attendue par
        # l'appelant de la Teacher View).
        w = weights.get(subj) or weights.get(canonical_subject_key(subj))
        if not w or not groups:
            continue
        names = [n for n, _ in w]
        vals = [max(0.0, v) for _, v in w]
        alloc = _allocate_groups(vals, len(groups))
        idx = 0
        for name, k in zip(names, alloc):
            for _ in range(k):
                gmap[(subj, groups[idx])] = name
                idx += 1
    return gmap


def theory_professors(fp=None):
    """Professeurs de THÉORIE par matière, en REPLI pour les matières dont la
    source n'attribue AUCUN crédit P/TP (ex. « Estructuras » : seul un bloc « T »
    existe). Permet à la Teacher View d'afficher un responsable plausible au lieu
    de « N/A » lorsqu'un planning de labo a malgré tout été produit.

    Renvoie {clé_canonique: [noms de professeurs]} et ne contient QUE les
    matières sans aucun bloc de pratiques (sinon les crédits P font autorité).
    Lit le cache committé si le xlsx source est absent (correction « N/D »).
    """
    if not fp or not os.path.exists(str(fp)):
        cache = load_weights_cache()
        if cache and cache.get("theory"):
            return {canonical_subject_key(s): list(v)
                    for s, v in cache["theory"].items()}
        return {}
    xls = pd.ExcelFile(fp)
    sheet = _find_sheet(xls, "asignaci", "docente")
    raw = pd.read_excel(fp, sheet_name=sheet, header=0, dtype=str)
    raw.columns = [str(c).strip() for c in raw.columns]
    code2name = _load_code_to_name(fp)
    src_to_clean = {_norm(v): k for k, v in SUBJECT_ALIASES.items()}
    blocks = [(f"Prof. {i}", f"Tipo Asig. {i}") for i in (1, 2, 3, 4)]
    out = {}
    has_practice = {}
    for _, r in raw.iterrows():
        subj = str(r.get("Asignatura") or "").strip()
        if not subj or _norm(subj) not in src_to_clean:
            continue
        key = canonical_subject_key(src_to_clean[_norm(subj)])
        for pcol, kcol in blocks:
            name = r.get(pcol)
            if not name or str(name).strip().lower() in ("", "nan", "0", "none"):
                continue
            char = str(r.get(kcol)).strip().upper()
            if "P" in char:
                has_practice[key] = True
            else:
                nm = code2name.get(str(name).strip(), str(name).strip())
                out.setdefault(key, [])
                if nm not in out[key]:
                    out[key].append(nm)
    return {k: v for k, v in out.items() if not has_practice.get(k)}


def declared_p_credits(fp):
    """
    DataFrame des crédits P DÉCLARÉS bruts par (matière, professeur) à partir des
    blocs P purs (transparence / comparaison avec la cible effective). Les blocs
    TP n'y figurent pas (leur part P n'est pas explicite dans la source)."""
    off = parse_lab_offerings(fp)
    pure = off[off["char"] == "P"]
    if not len(pure):
        return pd.DataFrame(columns=["subject_clean", "prof_name",
                                     "credits_P_declared", "sessions_declared"])
    g = (pure.groupby(["subject_clean", "prof_name"], as_index=False)["credits_block"]
             .sum().rename(columns={"credits_block": "credits_P_declared"}))
    g["sessions_declared"] = g["credits_P_declared"] * CREDIT_TO_SESSIONS
    return g.sort_values(["subject_clean", "credits_P_declared"],
                         ascending=[True, False]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 5) Export CSV consommable par le générateur Excel
# --------------------------------------------------------------------------- #
def write_subject_group_professors(fp, out_path="subject_group_professors.csv"):
    """
    Écrit un CSV : subject, group, professor  (une ligne par groupe de labo),
    que build_vista_profesor_sheet peut charger pour afficher le professeur
    réellement responsable de chaque groupe, dans le respect des crédits P.
    """
    gmap = build_group_professor_map(fp)
    rows = [{"subject": s, "group": g, "professor": p}
            for (s, g), p in sorted(gmap.items())]
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    return out_path


if __name__ == "__main__":
    import sys
    fp = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/ubuntu/Shared/Uploads/Asignacion_2025-2026_v5 - 2026-06-17 12:34:55.xlsx"
    exp = expected_sessions(fp)
    print(exp.to_string())
    gmap, diags = build_group_professor_map(fp, return_diagnostics=True)
    print(f"\n{len(gmap)} couples (matière, groupe) assignés (modèle source idéal).")
    by_status = {}
    for d in diags:
        by_status.setdefault(d["status"], 0)
        by_status[d["status"]] += 1
    print("Statut des offres :", by_status)
