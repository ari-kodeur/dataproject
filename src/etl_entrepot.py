#!/usr/bin/env python3
"""
ETL - Data warehouse "livraison de nourriture" (SQLite)

Sources :
  - train.csv / test.csv  : commandes de livraison (Food Delivery Dataset)
  - enquete CSV           : enquête clients de Bangalore (Online Food Delivery Preferences)

Usage :
  python3 etl_entrepot.py --train train.csv --test test.csv \
      --enquete "online food delivery dataset.csv" --out-dir sortie/

Étapes : Extract (lecture brute) -> Staging (copie telle quelle dans la base)
         -> Transform (nettoyage) -> Load (dimensions puis faits) -> Contrôles.
Le fichier Sample_Submission.csv n'est PAS chargé : ses valeurs sont des exemples,
pas des mesures.
"""
import argparse
import math
import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Schéma de l'entrepôt (constellation de faits : 2 faits, dimensions partagées)
# Règle : la clé -1 d'une dimension = valeur inconnue.
# --------------------------------------------------------------------------
SCHEMA = """
PRAGMA foreign_keys = ON;

-- ===== Dimensions partagées / livraisons =====
CREATE TABLE dim_temps (
    id_temps      INTEGER PRIMARY KEY,           -- AAAAMMJJ
    date_complete TEXT    NOT NULL,
    annee         INTEGER NOT NULL,
    mois          INTEGER NOT NULL,
    nom_mois      TEXT    NOT NULL,
    jour          INTEGER NOT NULL,
    jour_semaine  INTEGER NOT NULL,              -- 1 = lundi ... 7 = dimanche
    nom_jour      TEXT    NOT NULL,
    semaine_iso   INTEGER NOT NULL,
    est_weekend   INTEGER NOT NULL CHECK (est_weekend IN (0, 1))
);

CREATE TABLE dim_heure (
    id_heure INTEGER PRIMARY KEY,                -- 0..23, -1 = inconnue
    libelle  TEXT NOT NULL,
    tranche  TEXT NOT NULL
);

CREATE TABLE dim_ville (
    id_ville   INTEGER PRIMARY KEY,
    code_ville TEXT NOT NULL UNIQUE,             -- préfixe du code livreur
    nom_ville  TEXT NOT NULL                     -- nom déduit du code
);

CREATE TABLE dim_zone (
    id_zone   INTEGER PRIMARY KEY,               -- -1 = inconnue
    type_zone TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_livreur (
    id_livreur   INTEGER PRIMARY KEY,
    code_livreur TEXT NOT NULL UNIQUE,
    id_ville     INTEGER NOT NULL REFERENCES dim_ville(id_ville)
);

CREATE TABLE dim_conditions (
    id_conditions INTEGER PRIMARY KEY,
    meteo         TEXT NOT NULL,
    trafic        TEXT NOT NULL,
    festival      TEXT NOT NULL,
    UNIQUE (meteo, trafic, festival)
);

CREATE TABLE dim_type_commande (
    id_type_commande INTEGER PRIMARY KEY,
    type_commande    TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_vehicule (
    id_vehicule   INTEGER PRIMARY KEY,
    type_vehicule TEXT    NOT NULL,
    etat_vehicule INTEGER NOT NULL,              -- 0 (pire) .. 3 (meilleur) selon la source
    UNIQUE (type_vehicule, etat_vehicule)
);

-- ===== Fait 1 : une ligne = une commande livrée =====
CREATE TABLE fait_livraisons (
    id_livraison            INTEGER PRIMARY KEY,
    id_commande             TEXT    NOT NULL UNIQUE,
    jeu_donnees             TEXT    NOT NULL CHECK (jeu_donnees IN ('train', 'test')),
    id_temps                INTEGER NOT NULL REFERENCES dim_temps(id_temps),
    id_heure_commande       INTEGER NOT NULL REFERENCES dim_heure(id_heure),
    id_livreur              INTEGER NOT NULL REFERENCES dim_livreur(id_livreur),
    id_ville                INTEGER NOT NULL REFERENCES dim_ville(id_ville),
    id_zone                 INTEGER NOT NULL REFERENCES dim_zone(id_zone),
    id_conditions           INTEGER NOT NULL REFERENCES dim_conditions(id_conditions),
    id_type_commande        INTEGER NOT NULL REFERENCES dim_type_commande(id_type_commande),
    id_vehicule             INTEGER NOT NULL REFERENCES dim_vehicule(id_vehicule),
    heure_commande          TEXT,
    heure_ramassage         TEXT,
    age_livreur             INTEGER,
    note_livreur            REAL,
    livraisons_simultanees  INTEGER,
    coordonnees_valides     INTEGER NOT NULL CHECK (coordonnees_valides IN (0, 1)),
    lat_restaurant          REAL,
    lon_restaurant          REAL,
    lat_livraison           REAL,
    lon_livraison           REAL,
    distance_km             REAL,                -- mesure calculée (haversine)
    delai_preparation_min   INTEGER,             -- mesure calculée (ramassage - commande)
    temps_livraison_min     INTEGER              -- NULL pour le jeu 'test'
);
CREATE INDEX idx_fl_temps      ON fait_livraisons(id_temps);
CREATE INDEX idx_fl_ville      ON fait_livraisons(id_ville);
CREATE INDEX idx_fl_conditions ON fait_livraisons(id_conditions);
CREATE INDEX idx_fl_livreur    ON fait_livraisons(id_livreur);
CREATE INDEX idx_fl_heure      ON fait_livraisons(id_heure_commande);

-- ===== Fait 2 : une ligne = une réponse à l'enquête clients (Bangalore) =====
CREATE TABLE dim_profil_client (
    id_profil      INTEGER PRIMARY KEY,
    genre          TEXT NOT NULL,
    statut_marital TEXT NOT NULL,
    occupation     TEXT NOT NULL,
    niveau_etudes  TEXT NOT NULL,
    tranche_revenu TEXT NOT NULL,
    ordre_revenu   INTEGER NOT NULL,
    type_client    TEXT NOT NULL,
    UNIQUE (genre, statut_marital, occupation, niveau_etudes, tranche_revenu, type_client)
);

CREATE TABLE dim_localisation (
    id_localisation INTEGER PRIMARY KEY,
    code_postal     INTEGER NOT NULL UNIQUE,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL
);

CREATE TABLE fait_enquete (
    id_reponse       INTEGER PRIMARY KEY,
    id_profil        INTEGER NOT NULL REFERENCES dim_profil_client(id_profil),
    id_localisation  INTEGER NOT NULL REFERENCES dim_localisation(id_localisation),
    id_ville         INTEGER NOT NULL REFERENCES dim_ville(id_ville),
    age              INTEGER NOT NULL,
    taille_foyer     INTEGER NOT NULL,
    output_oui       INTEGER NOT NULL CHECK (output_oui IN (0, 1)),       -- colonne "Output" (sens non documenté)
    feedback_positif INTEGER NOT NULL CHECK (feedback_positif IN (0, 1))
);

-- ===== Journaux de contrôle =====
CREATE TABLE journal_anomalies (
    anomalie  TEXT NOT NULL,
    nb_lignes INTEGER NOT NULL,
    traitement TEXT NOT NULL
);
CREATE TABLE controle_qualite (
    controle TEXT NOT NULL,
    attendu  TEXT NOT NULL,
    obtenu   TEXT NOT NULL,
    statut   TEXT NOT NULL
);

-- ===== Vue à plat pour l'analyse =====
CREATE VIEW vue_livraisons AS
SELECT f.id_commande, f.jeu_donnees, t.date_complete, t.nom_jour, t.est_weekend,
       h.libelle AS heure_commande_h, h.tranche AS tranche_horaire,
       v.nom_ville, z.type_zone, l.code_livreur,
       c.meteo, c.trafic, c.festival,
       tc.type_commande, ve.type_vehicule, ve.etat_vehicule,
       f.age_livreur, f.note_livreur, f.livraisons_simultanees,
       f.distance_km, f.delai_preparation_min, f.temps_livraison_min
FROM fait_livraisons f
JOIN dim_temps t          ON t.id_temps = f.id_temps
JOIN dim_heure h          ON h.id_heure = f.id_heure_commande
JOIN dim_ville v          ON v.id_ville = f.id_ville
JOIN dim_zone z           ON z.id_zone = f.id_zone
JOIN dim_livreur l        ON l.id_livreur = f.id_livreur
JOIN dim_conditions c     ON c.id_conditions = f.id_conditions
JOIN dim_type_commande tc ON tc.id_type_commande = f.id_type_commande
JOIN dim_vehicule ve      ON ve.id_vehicule = f.id_vehicule;
"""

# Noms de villes DÉDUITS des préfixes des codes livreurs (ex. BANGRES15DEL01 -> BANG).
NOMS_VILLES = {
    "AGR": "Agra", "ALH": "Allahabad", "AURG": "Aurangabad", "BANG": "Bangalore",
    "BHP": "Bhopal", "CHEN": "Chennai", "COIMB": "Coimbatore", "DEH": "Dehradun",
    "GOA": "Goa", "HYD": "Hyderabad", "INDO": "Indore", "JAP": "Jaipur",
    "KNP": "Kanpur", "KOC": "Kochi", "KOL": "Kolkata", "LUDH": "Ludhiana",
    "MUM": "Mumbai", "MYS": "Mysore", "PUNE": "Pune", "RANCHI": "Ranchi",
    "SUR": "Surat", "VAD": "Vadodara",
}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
ORDRE_REVENU = {"No Income": 0, "Below Rs.10000": 1, "10001 to 25000": 2,
                "25001 to 50000": 3, "More than 50000": 4}


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------
def lire_brut(chemin):
    """EXTRACT : lecture sans aucune interprétation (tout en texte)."""
    return pd.read_csv(chemin, dtype=str, keep_default_na=False)


def compter_espaces(df):
    return int(sum((df[c] != df[c].str.strip()).sum() for c in df.columns))


def nettoyer(df):
    """Supprime les espaces superflus et transforme 'NaN' / '' en vraie valeur vide."""
    out = df.apply(lambda s: s.str.strip())
    return out.mask(out.isin(["NaN", ""]))


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def minutes(serie):
    """'HH:MM:SS' -> minutes depuis minuit (NaN si vide)."""
    p = serie.str.extract(r"^(\d{1,2}):(\d{2})")
    return pd.to_numeric(p[0]) * 60 + pd.to_numeric(p[1])


def ajouter_dim(df, cols, id_col):
    d = df[cols].drop_duplicates().sort_values(cols).reset_index(drop=True)
    d.insert(0, id_col, range(1, len(d) + 1))
    return d


def tranche(h):
    if h < 6:
        return "Nuit (0h-5h)"
    if h < 11:
        return "Matin (6h-10h)"
    if h < 15:
        return "Midi (11h-14h)"
    if h < 19:
        return "Après-midi (15h-18h)"
    return "Soir (19h-23h)"


# --------------------------------------------------------------------------
# TRANSFORM - livraisons
# --------------------------------------------------------------------------
def transformer_livraisons(raw_train, raw_test, journal):
    n_espaces = compter_espaces(raw_train) + compter_espaces(raw_test)
    tr, te = nettoyer(raw_train), nettoyer(raw_test)
    tr["jeu_donnees"], te["jeu_donnees"] = "train", "test"
    te["Time_taken(min)"] = np.nan
    df = pd.concat([tr, te], ignore_index=True)

    journal.append(("Espaces superflus en début/fin de valeur (toutes colonnes)", n_espaces,
                    "Supprimés"))
    vides = ["NaN", "conditions NaN"]
    nb_nan = int(sum(raw[c].str.strip().isin(vides).sum() for raw in (raw_train, raw_test) for c in raw.columns))
    journal.append(('Valeurs manquantes écrites "NaN" (texte) au lieu de vide', nb_nan,
                    'Converties en NULL ; "Inconnu" dans les dimensions'))

    # --- identifiants / ville
    df["id_commande"] = df["ID"]
    df["code_livreur"] = df["Delivery_person_ID"]
    df["code_ville"] = df["code_livreur"].str.extract(r"^([A-Z]+?)RES\d+DEL\d+$")[0]
    assert df["code_ville"].notna().all(), "code livreur de format inattendu"
    assert set(df["code_ville"]) <= set(NOMS_VILLES), "préfixe de ville inconnu"

    # --- âge / note : valeurs impossibles -> NULL
    age = pd.to_numeric(df["Delivery_person_Age"])
    note = pd.to_numeric(df["Delivery_person_Ratings"])
    n_age, n_note = int((age < 18).sum()), int((note > 5).sum())
    journal.append(("Âge du livreur < 18 ans", n_age, "Mis à NULL (valeur de la source conservée en staging)"))
    journal.append(("Note du livreur > 5 (échelle 1 à 5)", n_note, "Mise à NULL"))
    df["age_livreur"] = age.mask(age < 18)
    df["note_livreur"] = note.mask(note > 5)
    df["livraisons_simultanees"] = pd.to_numeric(df["multiple_deliveries"])

    # --- dimensions descriptives
    df["meteo"] = df["Weatherconditions"].str.replace(r"^conditions\s*", "", regex=True)
    df["meteo"] = df["meteo"].replace("NaN", np.nan)
    journal.append(('Préfixe "conditions " devant la météo', int(df["Weatherconditions"].str.startswith("conditions").sum()),
                    'Retiré (ex. "conditions Sunny" -> "Sunny")'))
    df["trafic"], df["festival"] = df["Road_traffic_density"], df["Festival"]
    df["type_zone"] = df["City"].replace({"Metropolitian": "Metropolitan"})
    journal.append(('Faute de frappe "Metropolitian"', int((df["City"] == "Metropolitian").sum()),
                    'Corrigée en "Metropolitan"'))
    df["type_commande"], df["type_vehicule"] = df["Type_of_order"], df["Type_of_vehicle"]
    df["etat_vehicule"] = pd.to_numeric(df["Vehicle_condition"]).astype(int)

    # --- temps
    d = pd.to_datetime(df["Order_Date"], format="%d-%m-%Y")
    df["date"] = d
    df["id_temps"] = d.dt.strftime("%Y%m%d").astype(int)
    m_cmd, m_ram = minutes(df["Time_Orderd"]), minutes(df["Time_Order_picked"])
    df["heure_h"] = (m_cmd // 60)
    n_h = int(df["heure_h"].isna().sum())
    journal.append(("Heure de commande manquante", n_h,
                    "Heure = Inconnue (clé -1) ; délai de préparation NULL"))
    df["heure_commande"] = df["Time_Orderd"]
    df["heure_ramassage"] = df["Time_Order_picked"]
    delai = (m_ram - m_cmd) % 1440
    df["delai_preparation_min"] = delai

    # --- temps de livraison "(min) 24" -> 24
    tt = pd.to_numeric(df["Time_taken(min)"].str.extract(r"(\d+)")[0])
    df["temps_livraison_min"] = tt
    journal.append(('Temps de livraison au format "(min) 24"', int(tt.notna().sum()),
                    "Converti en entier (24)"))
    journal.append(("Commandes du jeu test sans temps de livraison", int((df["jeu_donnees"] == "test").sum()),
                    "Temps = NULL (non inventé)"))

    # --- coordonnées
    rl, rg = pd.to_numeric(df["Restaurant_latitude"]), pd.to_numeric(df["Restaurant_longitude"])
    dl, dg = pd.to_numeric(df["Delivery_location_latitude"]), pd.to_numeric(df["Delivery_location_longitude"])
    n_neg = int(((rl < 0) | (rg < 0)).sum())
    journal.append(("Coordonnées du restaurant négatives", n_neg,
                    "Valeur absolue (l'écart restaurant-livraison devient cohérent, au plus 0,14 degré)"))
    rl, rg = rl.abs(), rg.abs()
    valide = rl.between(6, 38) & rg.between(68, 98)
    n_inv = int((~valide).sum())
    journal.append(("Coordonnées du restaurant à (0, 0) / hors Inde", n_inv,
                    "Coordonnées et distance mises à NULL, coordonnees_valides = 0"))
    df["coordonnees_valides"] = valide.astype(int)
    df["lat_restaurant"], df["lon_restaurant"] = rl.where(valide), rg.where(valide)
    df["lat_livraison"], df["lon_livraison"] = dl.where(valide), dg.where(valide)
    df["distance_km"] = haversine_km(df["lat_restaurant"], df["lon_restaurant"],
                                     df["lat_livraison"], df["lon_livraison"]).round(3)
    return df


# --------------------------------------------------------------------------
# TRANSFORM - enquête
# --------------------------------------------------------------------------
def transformer_enquete(raw, journal):
    n_espaces = compter_espaces(raw)
    df = raw.apply(lambda s: s.str.strip())
    identique = bool((df["Output"] == df["Unnamed: 13"]).all())
    journal.append(('Enquête : colonne "Unnamed: 13" identique à "Output"', len(df) if identique else 0,
                    "Colonne supprimée"))
    journal.append(("Enquête : espaces superflus", n_espaces, "Supprimés"))
    n_dup = int(df.duplicated().sum())
    journal.append(("Enquête : lignes en double (aucun identifiant client)", n_dup,
                    "Conservées (impossible de savoir si ce sont de vrais doublons)"))
    n_typo = int((df["Occupation"] == "Self Employeed").sum())
    df["Occupation"] = df["Occupation"].replace("Self Employeed", "Self Employed")
    journal.append(('Enquête : faute "Self Employeed"', n_typo, 'Corrigée en "Self Employed"'))
    return df


# --------------------------------------------------------------------------
# LOAD
# --------------------------------------------------------------------------
def charger(con, nom, df):
    df.to_sql(nom, con, if_exists="append", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--enquete", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / "entrepot_livraison.db"
    if db_path.exists():
        db_path.unlink()
    (out / "schema.sql").write_text(SCHEMA.strip() + "\n", encoding="utf-8")
    journal = []

    # ---- EXTRACT
    raw_train, raw_test, raw_enq = lire_brut(a.train), lire_brut(a.test), lire_brut(a.enquete)
    print(f"Extract : train={len(raw_train)}  test={len(raw_test)}  enquête={len(raw_enq)}")

    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)

    # ---- STAGING (copie brute, telle que dans les fichiers)
    raw_train.to_sql("stg_train", con, index=False)
    raw_test.to_sql("stg_test", con, index=False)
    raw_enq.to_sql("stg_enquete", con, index=False)

    # ---- TRANSFORM
    liv = transformer_livraisons(raw_train, raw_test, journal)
    enq = transformer_enquete(raw_enq, journal)

    # ---- LOAD : dimensions
    d0, d1 = liv["date"].min(), liv["date"].max()
    cal = pd.DataFrame({"date": pd.date_range(d0, d1, freq="D")})
    dim_temps = pd.DataFrame({
        "id_temps": cal["date"].dt.strftime("%Y%m%d").astype(int),
        "date_complete": cal["date"].dt.strftime("%Y-%m-%d"),
        "annee": cal["date"].dt.year, "mois": cal["date"].dt.month,
        "nom_mois": cal["date"].dt.month.map(lambda m: MOIS[m - 1]),
        "jour": cal["date"].dt.day,
        "jour_semaine": cal["date"].dt.dayofweek + 1,
        "nom_jour": cal["date"].dt.dayofweek.map(lambda i: JOURS[i]),
        "semaine_iso": cal["date"].dt.isocalendar().week.astype(int),
        "est_weekend": (cal["date"].dt.dayofweek >= 5).astype(int),
    })
    dim_heure = pd.DataFrame({"id_heure": list(range(24)) + [-1]})
    dim_heure["libelle"] = dim_heure["id_heure"].map(lambda h: f"{h:02d}h" if h >= 0 else "Inconnue")
    dim_heure["tranche"] = dim_heure["id_heure"].map(lambda h: tranche(h) if h >= 0 else "Inconnue")

    villes = sorted(set(liv["code_ville"]) | {"BANG"})
    dim_ville = pd.DataFrame({"id_ville": range(1, len(villes) + 1), "code_ville": villes})
    dim_ville["nom_ville"] = dim_ville["code_ville"].map(NOMS_VILLES)
    id_ville = dict(zip(dim_ville["code_ville"], dim_ville["id_ville"]))

    zones = sorted(liv["type_zone"].dropna().unique())
    dim_zone = pd.DataFrame({"id_zone": list(range(1, len(zones) + 1)) + [-1],
                             "type_zone": zones + ["Inconnu"]})
    id_zone = dict(zip(dim_zone["type_zone"], dim_zone["id_zone"]))

    livreurs = liv[["code_livreur", "code_ville"]].drop_duplicates().sort_values("code_livreur").reset_index(drop=True)
    dim_livreur = livreurs.assign(id_livreur=range(1, len(livreurs) + 1),
                                  id_ville=livreurs["code_ville"].map(id_ville))[["id_livreur", "code_livreur", "id_ville"]]
    id_livreur = dict(zip(dim_livreur["code_livreur"], dim_livreur["id_livreur"]))

    cond = liv[["meteo", "trafic", "festival"]].fillna("Inconnu")
    dim_cond = ajouter_dim(cond, ["meteo", "trafic", "festival"], "id_conditions")
    dim_tc = ajouter_dim(liv[["type_commande"]], ["type_commande"], "id_type_commande")
    dim_veh = ajouter_dim(liv[["type_vehicule", "etat_vehicule"]], ["type_vehicule", "etat_vehicule"], "id_vehicule")

    for nom, d in [("dim_temps", dim_temps), ("dim_heure", dim_heure), ("dim_ville", dim_ville),
                   ("dim_zone", dim_zone), ("dim_livreur", dim_livreur), ("dim_conditions", dim_cond),
                   ("dim_type_commande", dim_tc), ("dim_vehicule", dim_veh)]:
        charger(con, nom, d)

    # ---- LOAD : fait_livraisons
    f = pd.DataFrame({"id_livraison": range(1, len(liv) + 1)})
    f["id_commande"], f["jeu_donnees"] = liv["id_commande"], liv["jeu_donnees"]
    f["id_temps"] = liv["id_temps"]
    f["id_heure_commande"] = liv["heure_h"].fillna(-1).astype(int)
    f["id_livreur"] = liv["code_livreur"].map(id_livreur)
    f["id_ville"] = liv["code_ville"].map(id_ville)
    f["id_zone"] = liv["type_zone"].fillna("Inconnu").map(id_zone)
    c = liv[["meteo", "trafic", "festival"]].fillna("Inconnu")
    key_c = dim_cond.set_index(["meteo", "trafic", "festival"])["id_conditions"].to_dict()
    f["id_conditions"] = [key_c[k] for k in zip(c["meteo"], c["trafic"], c["festival"])]
    f["id_type_commande"] = liv["type_commande"].map(dict(zip(dim_tc["type_commande"], dim_tc["id_type_commande"])))
    key_v = dim_veh.set_index(["type_vehicule", "etat_vehicule"])["id_vehicule"].to_dict()
    f["id_vehicule"] = [key_v[(t, e)] for t, e in zip(liv["type_vehicule"], liv["etat_vehicule"])]
    for col in ["heure_commande", "heure_ramassage", "coordonnees_valides", "lat_restaurant", "lon_restaurant",
                "lat_livraison", "lon_livraison", "distance_km"]:
        f[col] = liv[col]
    for col in ["age_livreur", "livraisons_simultanees", "delai_preparation_min", "temps_livraison_min"]:
        f[col] = liv[col].astype("Int64")
    f["note_livreur"] = liv["note_livreur"]
    charger(con, "fait_livraisons", f)

    # ---- LOAD : enquête
    enq["ordre_revenu"] = enq["Monthly Income"].map(ORDRE_REVENU)
    assert enq["ordre_revenu"].notna().all()
    prof = enq.rename(columns={"Gender": "genre", "Marital Status": "statut_marital",
                               "Occupation": "occupation", "Educational Qualifications": "niveau_etudes",
                               "Monthly Income": "tranche_revenu", "Customer Type": "type_client"})
    cols_p = ["genre", "statut_marital", "occupation", "niveau_etudes", "tranche_revenu", "ordre_revenu", "type_client"]
    dim_prof = ajouter_dim(prof[cols_p], cols_p, "id_profil")
    dim_loc = enq[["Pin code", "latitude", "longitude"]].drop_duplicates().sort_values("Pin code").reset_index(drop=True)
    dim_loc.columns = ["code_postal", "latitude", "longitude"]
    dim_loc["code_postal"] = dim_loc["code_postal"].astype(int)
    dim_loc[["latitude", "longitude"]] = dim_loc[["latitude", "longitude"]].astype(float)
    dim_loc.insert(0, "id_localisation", range(1, len(dim_loc) + 1))
    charger(con, "dim_profil_client", dim_prof)
    charger(con, "dim_localisation", dim_loc)

    m_prof = prof.merge(dim_prof, on=cols_p, how="left")
    m_loc = enq[["Pin code"]].astype(int).rename(columns={"Pin code": "code_postal"}).merge(
        dim_loc[["code_postal", "id_localisation"]], on="code_postal", how="left")
    fe = pd.DataFrame({"id_reponse": range(1, len(enq) + 1)})
    fe["id_profil"] = m_prof["id_profil"].values
    fe["id_localisation"] = m_loc["id_localisation"].values
    fe["id_ville"] = id_ville["BANG"]
    fe["age"] = enq["Age"].astype(int).values
    fe["taille_foyer"] = enq["Family size"].astype(int).values
    fe["output_oui"] = (enq["Output"] == "Yes").astype(int).values
    fe["feedback_positif"] = (enq["Feedback"] == "Positive").astype(int).values
    assert enq["Feedback"].isin(["Positive", "Negative"]).all()
    journal.append(('Enquête : "Negative " avec espace final', int(len(enq) - fe["feedback_positif"].sum()),
                    "Normalisé en Negative puis codé 0/1"))
    charger(con, "fait_enquete", fe)

    # ---- Journal des anomalies
    con.executemany("INSERT INTO journal_anomalies VALUES (?,?,?)", journal)

    # ---- CONTRÔLES (comparaison indépendante avec le staging brut)
    ctl = []

    def verifier(nom, attendu, obtenu):
        ctl.append((nom, str(attendu), str(obtenu), "OK" if str(attendu) == str(obtenu) else "ÉCHEC"))

    q = lambda sql: con.execute(sql).fetchone()[0]
    verifier("Lignes fait_livraisons = lignes train + test (staging)",
             q("SELECT (SELECT COUNT(*) FROM stg_train) + (SELECT COUNT(*) FROM stg_test)"),
             q("SELECT COUNT(*) FROM fait_livraisons"))
    verifier("Commandes train chargées", q("SELECT COUNT(*) FROM stg_train"),
             q("SELECT COUNT(*) FROM fait_livraisons WHERE jeu_donnees='train'"))
    verifier("Commandes test chargées", q("SELECT COUNT(*) FROM stg_test"),
             q("SELECT COUNT(*) FROM fait_livraisons WHERE jeu_donnees='test'"))
    verifier("Identifiants de commande uniques",
             q("SELECT COUNT(*) FROM fait_livraisons"), q("SELECT COUNT(DISTINCT id_commande) FROM fait_livraisons"))
    verifier("Somme des temps de livraison : staging brut = fait",
             q("SELECT SUM(CAST(substr(trim(\"Time_taken(min)\"), 7) AS INTEGER)) FROM stg_train"),
             q("SELECT SUM(temps_livraison_min) FROM fait_livraisons"))
    verifier("Lignes fait_enquete = lignes enquête (staging)", q("SELECT COUNT(*) FROM stg_enquete"),
             q("SELECT COUNT(*) FROM fait_enquete"))
    verifier("Réponses 'Output = Yes' : staging = fait",
             q("SELECT COUNT(*) FROM stg_enquete WHERE trim(Output)='Yes'"),
             q("SELECT SUM(output_oui) FROM fait_enquete"))
    verifier("Clés étrangères orphelines", 0, len(con.execute("PRAGMA foreign_key_check").fetchall()))
    verifier("Commandes sans temps de livraison (hors jeu test)", 0,
             q("SELECT COUNT(*) FROM fait_livraisons WHERE jeu_donnees='train' AND temps_livraison_min IS NULL"))
    verifier("Distances négatives ou > 100 km", 0,
             q("SELECT COUNT(*) FROM fait_livraisons WHERE distance_km < 0 OR distance_km > 100"))
    verifier("Délais de préparation négatifs", 0,
             q("SELECT COUNT(*) FROM fait_livraisons WHERE delai_preparation_min < 0"))
    # recomptage par ville fait indépendamment avec pandas sur le brut
    brut = pd.concat([raw_train["Delivery_person_ID"], raw_test["Delivery_person_ID"]]).str.strip()
    attendu_v = {k: int(v) for k, v in brut.str.extract(r"^([A-Z]+?)RES")[0].value_counts().sort_index().items()}
    obtenu_v = dict(con.execute("SELECT v.code_ville, COUNT(*) FROM fait_livraisons f JOIN dim_ville v USING(id_ville) GROUP BY 1 ORDER BY 1").fetchall())
    verifier("Commandes par ville : brut = fait", attendu_v, obtenu_v)
    con.executemany("INSERT INTO controle_qualite VALUES (?,?,?,?)", ctl)
    con.commit()

    # ---- Résumé
    for nom, att, obt, st in ctl:
        print(f"[{st}] {nom}" + ("" if st == "OK" else f"  attendu={att} obtenu={obt}"))
    for t in ["dim_temps", "dim_heure", "dim_ville", "dim_zone", "dim_livreur", "dim_conditions",
              "dim_type_commande", "dim_vehicule", "fait_livraisons", "dim_profil_client",
              "dim_localisation", "fait_enquete"]:
        print(f"{t:20s} {q(f'SELECT COUNT(*) FROM {t}'):>7d} lignes")
    con.close()
    echecs = [c for c in ctl if c[3] != "OK"]
    if echecs:
        raise SystemExit(f"{len(echecs)} contrôle(s) en échec")


if __name__ == "__main__":
    main()
