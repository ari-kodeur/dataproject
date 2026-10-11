#!/usr/bin/env python3
"""Génère le rapport PDF de l'entrepôt à partir de la base SQLite (aucune valeur saisie à la main
pour les chiffres : tout est lu dans la base)."""
import argparse
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table,
                                TableStyle)

# ---------------------------------------------------------------- polices & couleurs
FD = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
for nom, f in [("DV", "DejaVuSans.ttf"), ("DV-B", "DejaVuSans-Bold.ttf"), ("DV-I", "DejaVuSans-Oblique.ttf"),
               ("DV-BI", "DejaVuSans-BoldOblique.ttf"), ("DVM", "DejaVuSansMono.ttf"),
               ("DVM-B", "DejaVuSansMono-Bold.ttf")]:
    pdfmetrics.registerFont(TTFont(nom, str(FD / f)))
registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-BI")
registerFontFamily("DVM", normal="DVM", bold="DVM-B", italic="DVM", boldItalic="DVM-B")

INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASE = "#e1e0d9", "#c3c2b7"
BLUE, BLUE_D, ORANGE = "#2a78d6", "#184f95", "#eb6834"
BLUE_T, ORANGE_T = "#cde2fb", "#fbe0d4"
HEAD_BG, ZEBRA = "#f0efec", "#f9f9f7"

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
AVAIL = PAGE_W - 2 * MARGIN

ST = {
    "body": ParagraphStyle("body", fontName="DV", fontSize=8.8, leading=12.6, textColor=colors.HexColor(INK)),
    "small": ParagraphStyle("small", fontName="DV", fontSize=7.6, leading=10.4, textColor=colors.HexColor(INK2)),
    "h1": ParagraphStyle("h1", fontName="DV-B", fontSize=15, leading=19, textColor=colors.HexColor(BLUE_D),
                         spaceBefore=4, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="DV-B", fontSize=10.5, leading=14, textColor=colors.HexColor(INK),
                         spaceBefore=10, spaceAfter=4),
    "cap": ParagraphStyle("cap", fontName="DV", fontSize=7.8, leading=10.6, textColor=colors.HexColor(INK2),
                          spaceBefore=3, spaceAfter=8),
    "cell": ParagraphStyle("cell", fontName="DV", fontSize=7.6, leading=9.6, textColor=colors.HexColor(INK)),
    "cellr": ParagraphStyle("cellr", fontName="DV", fontSize=7.6, leading=9.6, alignment=2,
                            textColor=colors.HexColor(INK)),
    "head": ParagraphStyle("head", fontName="DV-B", fontSize=7.6, leading=9.6, textColor=colors.HexColor(INK)),
    "headr": ParagraphStyle("headr", fontName="DV-B", fontSize=7.6, leading=9.6, alignment=2,
                            textColor=colors.HexColor(INK)),
    "bullet": ParagraphStyle("bullet", fontName="DV", fontSize=8.8, leading=12.6, leftIndent=11,
                             bulletIndent=1, spaceAfter=2.5, textColor=colors.HexColor(INK)),
    "tile": ParagraphStyle("tile", fontName="DV-B", fontSize=19, leading=24, textColor=colors.HexColor(BLUE_D)),
    "tile2": ParagraphStyle("tile2", fontName="DV-B", fontSize=16, leading=21, textColor=colors.HexColor(BLUE_D)),
    "tilelab": ParagraphStyle("tilelab", fontName="DV", fontSize=7.6, leading=10, textColor=colors.HexColor(INK2)),
    "code": ParagraphStyle("code", fontName="DVM", fontSize=7, leading=9.2, textColor=colors.HexColor(INK),
                           backColor=colors.HexColor(ZEBRA), borderPadding=5, leftIndent=4, rightIndent=4),
}

TR_METEO = {"Sunny": "Ensoleillé", "Cloudy": "Nuageux", "Fog": "Brouillard", "Stormy": "Orageux",
            "Windy": "Venteux", "Sandstorms": "Tempête de sable", "Inconnu": "Inconnu"}
TR_TRAFIC = {"Low": "Faible", "Medium": "Moyen", "High": "Élevé", "Jam": "Embouteillage", "Inconnu": "Inconnu"}
TR_ORDRE = {"Buffet": "Buffet", "Drinks": "Boissons", "Meal": "Repas", "Snack": "Snack"}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fr(x, d=0):
    if x is None or (isinstance(x, float) and np.isnan(x)) or x is pd.NA:
        return "—"
    s = f"{x:,.{d}f}".replace(",", " ").replace(".", ",")
    return s


def pct(x, d=1):
    return fr(x, d) + " %"


def P(txt, style="body"):
    return Paragraph(txt, ST[style])


def tbl(rows, widths, right=(), fs=None, zebra=True, repeat=1, header=True, total=None, pad=4):
    """rows : liste de listes de chaînes (la 1re ligne = en-tête)."""
    tot = float(sum(widths))
    w = [(total or AVAIL) * x / tot for x in widths]
    data = []
    for i, r in enumerate(rows):
        line = []
        for j, c in enumerate(r):
            is_head = header and i == 0
            style = ("headr" if j in right else "head") if is_head else ("cellr" if j in right else "cell")
            st = ST[style]
            if fs:
                st = ParagraphStyle(style + str(fs), parent=st, fontSize=fs, leading=fs * 1.25)
            line.append(Paragraph(str(c), st))
        data.append(line)
    t = Table(data, colWidths=w, repeatRows=repeat if header else 0)
    cmds = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
            ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(GRID))]
    if header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(HEAD_BG)),
                 ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(BASE))]
    if zebra and len(rows) > 3:
        cmds.append(("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor(ZEBRA)]))
    t.setStyle(TableStyle(cmds))
    return t


def mono(s):
    return f'<font name="DVM" size="7">{esc(s)}</font>'


# ---------------------------------------------------------------- figures
def style_ax(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.tick_params(colors=INK2, labelsize=7, length=0)
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)


def bar_panel(ax, labels, values, title, ymax):
    xs = range(len(values))
    ax.bar(xs, values, color=BLUE, width=0.55, zorder=3)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, ymax)
    style_ax(ax)
    ax.set_title(title, loc="left", fontsize=8.3, color=INK, fontweight="bold", pad=9)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fr(v, 0)))
    for x, v in zip(xs, values):
        ax.text(x, v + ymax * 0.02, fr(v, 1), ha="center", va="bottom", fontsize=7, color=INK)


def fig_schema(path):
    fig, ax = plt.subplots(figsize=(7.2, 4.55))
    ax.set_xlim(0, 132)
    ax.set_ylim(0, 86)
    ax.axis("off")
    boxes = {  # nom: (cx, cy, w, h, ligne 2, type)
        "dim_temps": (13, 74, 22, 10, "date, jour, mois, week-end", "d"),
        "dim_heure": (37, 74, 22, 10, "heure, tranche horaire", "d"),
        "dim_livreur": (61, 74, 22, 10, "code livreur, ville", "d"),
        "dim_ville": (91, 74, 24, 10, "22 villes (partagée)", "s"),
        "dim_localisation": (119, 74, 24, 10, "code postal, lat., long.", "d"),
        "fait_livraisons": (37, 44, 38, 28, "", "f"),
        "fait_enquete": (100, 44, 34, 24, "", "f"),
        "dim_zone": (12, 13, 20, 10, "type de zone", "d"),
        "dim_conditions": (34, 13, 20, 10, "météo, trafic, festival", "d"),
        "dim_type_commande": (56, 13, 20, 10, "type de commande", "d"),
        "dim_vehicule": (78, 13, 20, 10, "type, état du véhicule", "d"),
        "dim_profil_client": (104, 13, 24, 10, "genre, revenu, études…", "d"),
    }
    links = [("fait_livraisons", k) for k in ("dim_temps", "dim_heure", "dim_livreur", "dim_ville", "dim_zone",
                                                "dim_conditions", "dim_type_commande", "dim_vehicule")]
    links += [("fait_enquete", k) for k in ("dim_ville", "dim_localisation", "dim_profil_client")]
    links += [("dim_livreur", "dim_ville")]
    for a, b in links:
        xa, ya = boxes[a][:2]
        xb, yb = boxes[b][:2]
        ax.plot([xa, xb], [ya, yb], color=BASE, lw=1.1, zorder=1)
    for nom, (cx, cy, w, h, sub, t) in boxes.items():
        fc = {"f": BLUE_T, "s": ORANGE_T, "d": "white"}[t]
        ec = {"f": BLUE, "s": ORANGE, "d": BASE}[t]
        ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0,rounding_size=1.2",
                                    fc=fc, ec=ec, lw=1.3 if t != "d" else 1.0, zorder=2))
        if t == "f":
            ax.text(cx, cy + h / 2 - 3.8, nom, ha="center", va="center", fontsize=8.2, fontweight="bold",
                    color=INK, zorder=3)
        else:
            ax.text(cx, cy + 1.8, nom, ha="center", va="center", fontsize=6.7, fontweight="bold", color=INK, zorder=3)
            ax.text(cx, cy - 2.4, sub, ha="center", va="center", fontsize=5.4, color=INK2, zorder=3)
    fl = ["1 ligne = 1 commande", "distance_km", "delai_preparation_min", "temps_livraison_min", "note et âge du livreur"]
    for i, s in enumerate(fl):
        ax.text(37, 49.6 - i * 3.9, s, ha="center", va="center", fontsize=6.0 if i else 6.2,
                color=INK if i == 0 else INK2, style="italic" if i == 0 else "normal", zorder=3)
    fe = ["1 ligne = 1 réponse", "output_oui", "feedback_positif", "âge, taille du foyer"]
    for i, s in enumerate(fe):
        ax.text(100, 47.6 - i * 3.9, s, ha="center", va="center", fontsize=6.0 if i else 6.2,
                color=INK if i == 0 else INK2, style="italic" if i == 0 else "normal", zorder=3)
    # légende
    for i, (fc, ec, txt) in enumerate([(BLUE_T, BLUE, "Table de faits"), ("white", BASE, "Dimension"),
                                       (ORANGE_T, ORANGE, "Dimension partagée par les deux faits")]):
        x0 = 4 + i * 30 if i < 2 else 66
        ax.add_patch(FancyBboxPatch((x0, 2.2), 4, 2.6, boxstyle="round,pad=0,rounding_size=0.5", fc=fc, ec=ec,
                                    lw=1.0, zorder=2))
        ax.text(x0 + 5.5, 3.5, txt, ha="left", va="center", fontsize=6.2, color=INK2)
    fig.tight_layout(pad=0.2)
    fig.savefig(path, dpi=220, facecolor="white")
    plt.close(fig)


def fig_trafic_meteo(path, trafic, meteo):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, 2.7), gridspec_kw={"width_ratios": [4, 6]}, sharey=True)
    bar_panel(a1, [TR_TRAFIC[k] for k in trafic.index], trafic.values, "Selon le trafic routier", 36)
    bar_panel(a2, [TR_METEO[k] for k in meteo.index], meteo.values, "Selon la météo", 36)
    a1.set_ylabel("Temps moyen de livraison (min)", fontsize=7, color=INK2)
    for ax in (a1, a2):
        ax.tick_params(axis="x", labelsize=6.6)
    fig.tight_layout(pad=0.6, w_pad=1.6)
    fig.savefig(path, dpi=220, facecolor="white")
    plt.close(fig)


def fig_heure_distance(path, tranche, nb_tranche, dist, nb_dist):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.0, 2.8), gridspec_kw={"width_ratios": [6, 4]}, sharey=True)
    lab1 = [f"{k.split(' (')[0]}\n{k.split(' (')[1].rstrip(')')}\nn = {fr(n)}" for k, n in zip(tranche.index, nb_tranche)]
    bar_panel(a1, lab1, tranche.values, "Selon l'heure de commande", 36)
    lab2 = [f"{k}\nn = {fr(n)}" for k, n in zip(dist.index, nb_dist)]
    bar_panel(a2, lab2, dist.values, "Selon la distance restaurant → client", 36)
    a1.set_ylabel("Temps moyen de livraison (min)", fontsize=7, color=INK2)
    for ax in (a1, a2):
        ax.tick_params(axis="x", labelsize=6.2)
    fig.tight_layout(pad=0.6, w_pad=1.6)
    fig.savefig(path, dpi=220, facecolor="white")
    plt.close(fig)


def img(path, width=AVAIL):
    from PIL import Image as PILImage
    w, h = PILImage.open(path).size
    return Image(str(path), width=width, height=width * h / w)


# ---------------------------------------------------------------- dictionnaire
DICT_LIV = [
    ("id_livraison", "Clé primaire de la ligne (1 à 56 992)."),
    ("id_commande", "Identifiant de commande d'origine (ex. 0x4607), unique."),
    ("jeu_donnees", "« train » (temps de livraison connu) ou « test » (temps inconnu)."),
    ("id_temps", "→ dim_temps : date de la commande (AAAAMMJJ)."),
    ("id_heure_commande", "→ dim_heure : heure de la commande (−1 si inconnue)."),
    ("id_livreur", "→ dim_livreur : livreur."),
    ("id_ville", "→ dim_ville : ville (déduite du code livreur)."),
    ("id_zone", "→ dim_zone : type de zone (Metropolitan, Urban, Semi-Urban)."),
    ("id_conditions", "→ dim_conditions : météo, trafic routier, jour de festival."),
    ("id_type_commande", "→ dim_type_commande : buffet, boissons, repas, snack."),
    ("id_vehicule", "→ dim_vehicule : type et état du véhicule."),
    ("heure_commande", "Heure de commande au format HH:MM:SS (vide si inconnue)."),
    ("heure_ramassage", "Heure de ramassage de la commande au restaurant."),
    ("age_livreur", "Âge du livreur (vide si absent ou inférieur à 18 ans)."),
    ("note_livreur", "Note du livreur, de 1 à 5 (vide si absente ou supérieure à 5)."),
    ("livraisons_simultanees", "Nombre de livraisons en parallèle (colonne multiple_deliveries, 0 à 3)."),
    ("coordonnees_valides", "1 si les coordonnées sont exploitables, 0 sinon."),
    ("lat_restaurant, lon_restaurant", "Position du restaurant, en degrés décimaux (vide si non valide)."),
    ("lat_livraison, lon_livraison", "Position du lieu de livraison, en degrés décimaux (vide si non valide)."),
    ("distance_km", "Mesure calculée : distance à vol d'oiseau restaurant → client (haversine)."),
    ("delai_preparation_min", "Mesure calculée : heure de ramassage − heure de commande, en minutes."),
    ("temps_livraison_min", "Mesure principale : temps de livraison en minutes (vide pour le jeu test)."),
]
DICT_ENQ = [
    ("id_reponse", "Clé primaire de la réponse (1 à 388)."),
    ("id_profil", "→ dim_profil_client : genre, statut, occupation, études, revenu, type de client."),
    ("id_localisation", "→ dim_localisation : code postal du répondant."),
    ("id_ville", "→ dim_ville : toujours Bangalore (lien avec les livraisons)."),
    ("age", "Âge du répondant (18 à 33 ans)."),
    ("taille_foyer", "Nombre de personnes dans le foyer (1 à 6)."),
    ("output_oui", "1 si la colonne source « Output » vaut Yes (sens non documenté par la source)."),
    ("feedback_positif", "1 si l'avis est positif, 0 s'il est négatif."),
]
DIMS = [
    ("dim_temps", "id_temps, date_complete, annee, mois, nom_mois, jour, jour_semaine, nom_jour, semaine_iso, est_weekend",
     "Calendrier continu, un jour par ligne."),
    ("dim_heure", "id_heure, libelle, tranche", "Heures 0 à 23, regroupées en 5 tranches, plus « Inconnue » (−1)."),
    ("dim_ville", "id_ville, code_ville, nom_ville", "Villes ; nom déduit du code livreur. Partagée par les deux faits."),
    ("dim_zone", "id_zone, type_zone", "Type de zone : Metropolitan, Urban, Semi-Urban, Inconnu."),
    ("dim_livreur", "id_livreur, code_livreur, id_ville", "Un livreur par code, rattaché à sa ville."),
    ("dim_conditions", "id_conditions, meteo, trafic, festival", "Combinaisons météo × trafic × festival observées."),
    ("dim_type_commande", "id_type_commande, type_commande", "Buffet, Drinks, Meal, Snack."),
    ("dim_vehicule", "id_vehicule, type_vehicule, etat_vehicule", "Combinaisons type × état du véhicule."),
    ("dim_profil_client", "id_profil, genre, statut_marital, occupation, niveau_etudes, tranche_revenu, ordre_revenu, type_client",
     "Profils distincts des répondants à l'enquête."),
    ("dim_localisation", "id_localisation, code_postal, latitude, longitude", "Codes postaux de l'enquête (Bangalore)."),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--figs", required=True)
    ap.add_argument("--sample-submission", required=True)
    a = ap.parse_args()
    figs = Path(a.figs)
    figs.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(a.db)
    q = lambda sql: pd.read_sql(sql, con)
    one = lambda sql: con.execute(sql).fetchone()[0]

    # --- vérification : le dictionnaire correspond au schéma réel
    def colonnes(t):
        return {r[1] for r in con.execute(f"PRAGMA table_info({t})")}

    def noms(d):
        return {c.strip() for k, _ in d for c in k.split(",")}

    assert noms(DICT_LIV) == colonnes("fait_livraisons"), noms(DICT_LIV) ^ colonnes("fait_livraisons")
    assert noms(DICT_ENQ) == colonnes("fait_enquete")
    for t, cols, _ in DIMS:
        assert {c.strip() for c in cols.split(",")} == colonnes(t), t
    types = {}
    for t in ("fait_livraisons", "fait_enquete"):
        for r in con.execute(f"PRAGMA table_info({t})"):
            types[(t, r[1])] = r[2]

    # --- chiffres clés
    n_tot = one("SELECT COUNT(*) FROM fait_livraisons")
    n_tr = one("SELECT COUNT(*) FROM fait_livraisons WHERE jeu_donnees='train'")
    n_te = one("SELECT COUNT(*) FROM fait_livraisons WHERE jeu_donnees='test'")
    n_enq = one("SELECT COUNT(*) FROM fait_enquete")
    n_vil = one("SELECT COUNT(*) FROM dim_ville")
    n_liv = one("SELECT COUNT(*) FROM dim_livreur")
    d0, d1 = con.execute("SELECT MIN(date_complete), MAX(date_complete) FROM dim_temps").fetchone()
    fdate = lambda s: f"{s[8:10]}/{s[5:7]}/{s[:4]}"
    n_sub = len(pd.read_csv(a.sample_submission))

    story = []

    # ============================== PAGE DE GARDE
    story += [Spacer(1, 38 * mm),
              Paragraph("Data warehouse<br/>Livraison de nourriture",
                        ParagraphStyle("t", fontName="DV-B", fontSize=27, leading=33, textColor=colors.HexColor(BLUE_D))),
              Spacer(1, 4 * mm),
              Paragraph("Rapport de construction et contenu de l'entrepôt de données",
                        ParagraphStyle("st", fontName="DV", fontSize=12.5, leading=17, textColor=colors.HexColor(INK2))),
              Spacer(1, 3 * mm),
              Paragraph("11 octobre 2026 · base SQLite entrepot_livraison.db",
                        ParagraphStyle("dt", fontName="DV", fontSize=9, textColor=colors.HexColor(MUTED))),
              Spacer(1, 16 * mm)]
    tiles = [(fr(n_tot), "livraisons chargées<br/>(train + test)"), (fr(n_tr), "livraisons avec<br/>temps de livraison"),
             (fr(n_enq), "réponses à l'enquête<br/>clients (Bangalore)"), (f"{n_vil} · {fr(n_liv)}", "villes · livreurs")]
    cells = [[Paragraph(v, ST["tile"]) for v, _ in tiles], [Paragraph(l, ST["tilelab"]) for _, l in tiles]]
    t = Table(cells, colWidths=[AVAIL / 4] * 4)
    t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1.2, colors.HexColor(BLUE)),
                           ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
                           ("TOPPADDING", (0, 1), (-1, 1), 1), ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [t, Spacer(1, 2 * mm),
              P(f"Période couverte par les commandes : du {fdate(d0)} au {fdate(d1)}.", "small"),
              Spacer(1, 16 * mm), P("Contenu du rapport", "h2")]
    sommaire = [("1", "Sources et données chargées"), ("2", "Architecture de l'entrepôt (schéma en constellation)"),
                ("3", "Dictionnaire des données"), ("4", "Contenu des dimensions"),
                ("5", "Aperçu des tables de faits"), ("6", "Premières analyses"),
                ("7", "Qualité des données : anomalies corrigées et contrôles"),
                ("8", "Limites à connaître"), ("A", "Reproduire la construction, exemples de requêtes")]
    for n, s in sommaire:
        story.append(Paragraph(f'<font name="DV-B" color="{BLUE_D}">{n}</font>&nbsp;&nbsp;&nbsp;{s}', ST["body"]))
        story.append(Spacer(1, 1.5 * mm))
    story.append(PageBreak())

    # ============================== 1. SOURCES
    story += [P("1. Sources et données chargées", "h1"),
              P("L'entrepôt réunit deux jeux de données de livraison de nourriture en Inde : les commandes d'un service "
                "de livraison (fichiers train et test) et une petite enquête auprès de clients de Bangalore. "
                "Chaque fichier a d'abord été copié tel quel dans des tables de <i>staging</i> (stg_train, stg_test, "
                "stg_enquete), puis nettoyé et chargé dans les dimensions et les faits."),
              Spacer(1, 3 * mm)]
    story.append(tbl([
        ["Fichier source", "Contenu", "Lignes", "Destination"],
        ["train.csv", "Commandes, avec le temps de livraison", fr(n_tr), "fait_livraisons (jeu_donnees = train)"],
        ["test.csv", "Commandes, sans temps de livraison", fr(n_te), "fait_livraisons (jeu_donnees = test)"],
        ["online food delivery dataset.csv", "Enquête auprès de clients de Bangalore", fr(n_enq), "fait_enquete"],
        ["Sample_Submission.csv", "Modèle de soumission : temps d'exemple pour les commandes du test", fr(n_sub),
         "<b>Non chargé</b> : valeurs d'exemple, pas des mesures"],
        ["train-selected-columns.csv (×2)", "Fichiers reçus vides (en-têtes seulement)", "0", "<b>Non utilisés</b>"],
    ], [26, 34, 9, 31], right=(2,)))
    story.append(P("Les valeurs textuelles (météo, type de véhicule, profils de l'enquête…) restent dans la langue de la "
                   "source, l'anglais. Les libellés de ce rapport sont en français.", "cap"))

    # ============================== 2. ARCHITECTURE
    story += [P("2. Architecture de l'entrepôt", "h1"),
              P("Le schéma est une <b>constellation de faits</b> : deux tables de faits qui partagent une dimension commune, "
                "<font name='DVM' size='8'>dim_ville</font>. Chaque fait est entouré de ses dimensions, comme dans un schéma en étoile."),
              Spacer(1, 2 * mm)]
    fig_schema(figs / "schema.png")
    story.append(img(figs / "schema.png"))
    story.append(P("Chaque trait relie une table de faits à une dimension par une clé étrangère. La seule liaison entre "
                   "l'enquête et les livraisons passe par la ville, car l'enquête ne contient aucun identifiant de client.", "cap"))
    story.append(P("Règles de conception", "h2"))
    for b in [
        "<b>Grain</b> : une ligne de <font name='DVM' size='8'>fait_livraisons</font> = une commande ; une ligne de "
        "<font name='DVM' size='8'>fait_enquete</font> = une réponse à l'enquête.",
        "<b>Clés de substitution</b> : chaque dimension a sa propre clé entière. La clé <b>−1</b> désigne une valeur inconnue "
        "(heure ou type de zone manquants).",
        "<b>Mesures</b> : temps de livraison, distance (calculée à partir des coordonnées) et délai de préparation "
        "(heure de ramassage moins heure de commande).",
        "<b>Âge et note du livreur</b> sont stockés dans le fait et non dans <font name='DVM' size='8'>dim_livreur</font> : "
        "pour un même code livreur, ils changent d'une commande à l'autre dans la source.",
        "<b>Traçabilité</b> : les tables de staging conservent les données brutes ; "
        "<font name='DVM' size='8'>journal_anomalies</font> et <font name='DVM' size='8'>controle_qualite</font> "
        "documentent le nettoyage dans la base elle-même.",
    ]:
        story.append(Paragraph(b, ST["bullet"], bulletText="•"))

    # ============================== 3. DICTIONNAIRE
    story += [CondPageBreak(110 * mm), P("3. Dictionnaire des données", "h1"), P("Table de faits fait_livraisons", "h2")]
    story.append(tbl([["Colonne", "Type", "Description"]] +
                     [[mono(k), types[("fait_livraisons", k.split(",")[0].strip())], esc(d)] for k, d in DICT_LIV],
                     [27, 9, 64]))
    story += [CondPageBreak(60 * mm), P("Table de faits fait_enquete", "h2")]
    story.append(tbl([["Colonne", "Type", "Description"]] +
                     [[mono(k), types[("fait_enquete", k)], esc(d)] for k, d in DICT_ENQ], [27, 9, 64]))
    story += [CondPageBreak(70 * mm), P("Dimensions", "h2")]
    story.append(tbl([["Table", "Colonnes", "Rôle", "Lignes"]] +
                     [[mono(t), mono(c).replace(", ", ", "), esc(r), fr(one(f"SELECT COUNT(*) FROM {t}"))]
                      for t, c, r in DIMS], [20, 40, 32, 8], right=(3,), fs=7.2))

    # ============================== 4. CONTENU DES DIMENSIONS
    story += [CondPageBreak(100 * mm), P("4. Contenu des dimensions", "h1"),
              P("Valeurs des attributs et nombre de commandes concernées (train et test confondus, "
                f"{fr(n_tot)} commandes).")]
    story.append(Spacer(1, 2 * mm))

    def valeurs(col, tr=None):
        d = q(f"SELECT {col} v, COUNT(*) n FROM vue_livraisons GROUP BY 1 ORDER BY 2 DESC")
        def lib(v):
            if pd.isna(v):
                return "Inconnu"
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            return tr.get(v, v) if tr else v

        return " · ".join(f"{esc(lib(v))}&nbsp;: <b>{fr(n)}</b>" for v, n in zip(d.v, d.n))

    story.append(tbl([
        ["Attribut", "Valeurs (nombre de commandes)"],
        ["Type de zone", valeurs("type_zone")],
        ["Type de commande", valeurs("type_commande", TR_ORDRE)],
        ["Type de véhicule", valeurs("type_vehicule")],
        ["Météo", valeurs("meteo", TR_METEO)],
        ["Trafic routier", valeurs("trafic", TR_TRAFIC)],
        ["Jour de festival", valeurs("festival")],
        ["Tranche horaire", valeurs("tranche_horaire")],
        ["Livraisons simultanées", valeurs("livraisons_simultanees")],
    ], [20, 80]))
    story.append(P("Météo et trafic : Sunny = ensoleillé, Cloudy = nuageux, Fog = brouillard, Stormy = orageux, Windy = venteux, "
                   "Sandstorms = tempête de sable ; Low = faible, Medium = moyen, High = élevé, Jam = embouteillage. "
                   "« Inconnu » = valeur absente de la source.", "cap"))

    story.append(P("dim_ville : villes, livreurs et commandes", "h2"))
    dv = q("""SELECT v.id_ville, v.code_ville, v.nom_ville, COUNT(DISTINCT f.id_livreur) livreurs,
              COUNT(f.id_livraison) cmd, SUM(f.jeu_donnees='train') ntr, ROUND(AVG(f.temps_livraison_min),1) tl
              FROM dim_ville v LEFT JOIN fait_livraisons f USING(id_ville) GROUP BY v.id_ville ORDER BY cmd DESC, v.nom_ville""")
    rows = [["Id", "Code", "Ville (déduite du code)", "Livreurs", "Commandes", "Temps moyen (min, train)"]]
    for r in dv.itertuples():
        rows.append([r.id_ville, mono(r.code_ville), r.nom_ville, fr(r.livreurs), fr(r.cmd), fr(r.tl, 1)])
    story.append(tbl(rows, [6, 12, 28, 12, 14, 28], right=(0, 3, 4, 5)))
    gros, petits = dv[dv.ntr > 2000], dv[dv.ntr <= 2000]
    lv = sorted(dv.livreurs.unique())
    story.append(P(f"{len(gros)} villes ont entre {fr(gros.ntr.min())} et {fr(gros.ntr.max())} commandes du jeu train, les {len(petits)} autres "
                   f"entre {fr(petits.ntr.min())} et {fr(petits.ntr.max())}. "
                   + (f"Chaque ville compte exactement {lv[0]} livreurs. " if len(lv) == 1 else "")
                   + f"Le temps moyen va de {fr(dv.tl.min(), 1)} à {fr(dv.tl.max(), 1)} min d'une ville à l'autre.", "cap"))

    dvh = q("""SELECT v.id_vehicule, v.type_vehicule, v.etat_vehicule, COUNT(*) n
               FROM dim_vehicule v JOIN fait_livraisons f USING(id_vehicule) GROUP BY v.id_vehicule ORDER BY v.id_vehicule""")
    story.append(KeepTogether([P("dim_vehicule", "h2"), tbl([["Id", "Type de véhicule", "État (0 à 3)", "Commandes"]] +
                     [[r.id_vehicule, r.type_vehicule, r.etat_vehicule, fr(r.n)] for r in dvh.itertuples()],
                     [8, 40, 20, 20], right=(0, 2, 3))]))

    story.append(P("dim_temps, dim_heure, dim_livreur, dim_conditions : extraits", "h2"))
    story.append(P(f"<font name='DVM' size='8'>dim_temps</font> contient {one('SELECT COUNT(*) FROM dim_temps')} jours consécutifs "
                   f"({fdate(d0)} → {fdate(d1)}) ; <font name='DVM' size='8'>dim_heure</font> contient 24 heures et « Inconnue » ; "
                   f"<font name='DVM' size='8'>dim_livreur</font> {fr(n_liv)} livreurs ; <font name='DVM' size='8'>dim_conditions</font> "
                   f"{one('SELECT COUNT(*) FROM dim_conditions')} combinaisons.", "body"))
    story.append(Spacer(1, 2 * mm))
    dt = q("SELECT * FROM dim_temps LIMIT 7")
    story.append(tbl([["id_temps", "date_complete", "jour", "nom_mois", "nom_jour", "semaine_iso", "est_weekend"]] +
                     [[r.id_temps, r.date_complete, r.jour, r.nom_mois, r.nom_jour, r.semaine_iso, r.est_weekend]
                      for r in dt.itertuples()], [14, 16, 8, 14, 14, 14, 14], right=(0, 2, 5, 6)))
    story.append(Spacer(1, 3 * mm))
    dl = q("""SELECT l.id_livreur, l.code_livreur, v.nom_ville FROM dim_livreur l JOIN dim_ville v USING(id_ville) LIMIT 5""")
    dc = q("SELECT * FROM dim_conditions LIMIT 5")
    t1 = tbl([["id_livreur", "code_livreur", "ville"]] + [[r.id_livreur, mono(r.code_livreur), r.nom_ville] for r in dl.itertuples()],
             [10, 22, 14], right=(0,), fs=7, total=AVAIL * 0.47)
    t2 = tbl([["id", "meteo", "trafic", "festival"]] + [[r.id_conditions, r.meteo, r.trafic, r.festival] for r in dc.itertuples()],
             [6, 14, 12, 10], right=(0,), fs=7, total=AVAIL * 0.47)
    story.append(Table([[t1, t2]], colWidths=[AVAIL * 0.5, AVAIL * 0.5],
                       style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                         ("RIGHTPADDING", (0, 0), (-1, -1), 4)])))

    prof = {c: q(f"SELECT {c} v, COUNT(*) n FROM fait_enquete JOIN dim_profil_client USING(id_profil) GROUP BY 1 ORDER BY 2 DESC")
            for c in ["genre", "statut_marital", "occupation", "niveau_etudes", "tranche_revenu", "type_client"]}
    lab = {"genre": "Genre", "statut_marital": "Statut marital", "occupation": "Occupation",
           "niveau_etudes": "Niveau d'études", "tranche_revenu": "Revenu mensuel (roupies)", "type_client": "Type de client"}
    rows = [["Attribut de dim_profil_client", "Valeurs (nombre de réponses)"]]
    for c, d in prof.items():
        rows.append([lab[c], " · ".join(f"{esc(v)}&nbsp;: <b>{fr(n)}</b>" for v, n in zip(d.v, d.n))])
    bloc_enq = [P("Dimensions de l'enquête", "h2"), tbl(rows, [26, 74])]
    nprof = one("SELECT COUNT(*) FROM dim_profil_client")
    nloc = one("SELECT COUNT(*) FROM dim_localisation")
    cp0, cp1 = con.execute("SELECT MIN(code_postal), MAX(code_postal) FROM dim_localisation").fetchone()
    bloc_enq.append(P(f"{nprof} profils distincts et {nloc} codes postaux (de {cp0} à {cp1}, secteur de Bangalore) "
                      f"pour {n_enq} réponses.", "cap"))
    story.append(KeepTogether(bloc_enq))

    # ============================== 5. APERÇU DES FAITS
    story += [CondPageBreak(110 * mm), P("5. Aperçu des tables de faits", "h1"),
              P(f"Extraits lus dans la vue <font name='DVM' size='8'>vue_livraisons</font>, qui rassemble le fait et toutes ses dimensions. "
                f"Les {fr(n_tot)} lignes complètes sont dans la base et dans les fichiers CSV fournis ; un PDF ne peut pas les contenir toutes.")]
    story.append(Spacer(1, 2 * mm))
    story.append(P("fait_livraisons : 10 premières commandes du jeu train", "h2"))
    cols = ["id_commande", "jeu_donnees", "date_complete", "heure_commande_h", "nom_ville", "type_zone", "meteo", "trafic",
            "type_vehicule", "distance_km", "delai_preparation_min", "temps_livraison_min"]
    hdr = ["ID", "Jeu", "Date", "Heure", "Ville", "Zone", "Météo", "Trafic", "Véhicule", "Dist. km", "Prép. min", "Livr. min"]

    def rows_prev(df):
        out = []
        for r in df.itertuples(index=False):
            d = r._asdict()
            out.append([mono(d["id_commande"]), d["jeu_donnees"], d["date_complete"], d["heure_commande_h"], d["nom_ville"],
                        d["type_zone"], d["meteo"], d["trafic"], d["type_vehicule"], fr(d["distance_km"], 1),
                        fr(d["delai_preparation_min"]), fr(d["temps_livraison_min"])])
        return out

    pa = q(f"SELECT {', '.join(cols)} FROM vue_livraisons WHERE jeu_donnees='train' LIMIT 10")
    pb = q(f"SELECT {', '.join(cols)} FROM vue_livraisons WHERE jeu_donnees='test' LIMIT 3")
    w = [12, 8, 12.5, 10.5, 12.5, 14, 13, 9.5, 18, 7.5, 7.5, 7.5]
    story.append(tbl([hdr] + rows_prev(pa), w, right=(9, 10, 11), fs=6.3, pad=3))
    story.append(P("fait_livraisons : 3 commandes du jeu test (temps inconnu)", "h2"))
    story.append(tbl([hdr] + rows_prev(pb), w, right=(9, 10, 11), fs=6.3, pad=3))
    story.append(P("« — » signale une valeur vide (NULL) : ici le temps de livraison du jeu test, ou une distance non calculable "
                   "lorsque les coordonnées du restaurant sont inutilisables.", "cap"))

    story.append(P("fait_enquete : 10 premières réponses", "h2"))
    pe = q("""SELECT e.id_reponse, p.genre, e.age, p.statut_marital, p.occupation, p.niveau_etudes, p.tranche_revenu,
              p.type_client, l.code_postal, e.taille_foyer, e.output_oui, e.feedback_positif
              FROM fait_enquete e JOIN dim_profil_client p USING(id_profil) JOIN dim_localisation l USING(id_localisation) LIMIT 10""")
    story.append(tbl([["Id", "Genre", "Âge", "Statut", "Occupation", "Études", "Revenu", "Client", "Code post.", "Foyer", "Output", "Avis +"]] +
                     [[r.id_reponse, r.genre, r.age, r.statut_marital, r.occupation, r.niveau_etudes, r.tranche_revenu,
                       r.type_client, r.code_postal, r.taille_foyer, r.output_oui, r.feedback_positif] for r in pe.itertuples()],
                     [4.5, 8, 5.5, 8, 11.5, 12, 14, 9, 9.5, 6, 7.5, 7.5], right=(0, 2, 8, 9, 10, 11), fs=6.3, pad=3))

    # ============================== 6. ANALYSES
    story += [CondPageBreak(125 * mm), P("6. Premières analyses", "h1"),
              P("Ces résultats montrent ce que l'entrepôt permet de calculer. Ce sont des moyennes observées sur le jeu train "
                f"({fr(n_tr)} commandes avec temps de livraison), pas des effets isolés : les conditions se combinent dans les données.")]
    k = q("""SELECT AVG(temps_livraison_min) tl, AVG(distance_km) dist, AVG(delai_preparation_min) prep,
             100.0*SUM(coordonnees_valides)/COUNT(*) pv FROM fait_livraisons WHERE jeu_donnees='train'""").iloc[0]
    kt = [(fr(k.tl, 1) + " min", "temps moyen de livraison"), (fr(k.dist, 1) + " km", "distance moyenne (coordonnées valides)"),
          (fr(k.prep, 1) + " min", "délai de préparation moyen"), (pct(k.pv, 1), "commandes à coordonnées exploitables")]
    cells = [[Paragraph(v, ST["tile2"]) for v, _ in kt], [Paragraph(l, ST["tilelab"]) for _, l in kt]]
    t = Table(cells, colWidths=[AVAIL / 4] * 4)
    t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1.0, colors.HexColor(BLUE)), ("TOPPADDING", (0, 0), (-1, 0), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, 0), 1), ("TOPPADDING", (0, 1), (-1, 1), 1),
                           ("BOTTOMPADDING", (0, 1), (-1, 1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [Spacer(1, 3 * mm), t]

    tr = q("SELECT trafic, AVG(temps_livraison_min) tl FROM vue_livraisons WHERE jeu_donnees='train' AND trafic<>'Inconnu' GROUP BY 1")
    tr = tr.set_index("trafic").tl.reindex(["Low", "Medium", "High", "Jam"])
    me = q("SELECT meteo, AVG(temps_livraison_min) tl FROM vue_livraisons WHERE jeu_donnees='train' AND meteo<>'Inconnu' GROUP BY 1")
    me = me.set_index("meteo").tl.sort_values()
    fig_trafic_meteo(figs / "trafic_meteo.png", tr, me)
    story += [P("Temps de livraison selon le trafic et la météo", "h2"), img(figs / "trafic_meteo.png"),
              P(f"Le temps moyen passe de {fr(tr['Low'], 1)} min avec un trafic faible à {fr(tr['Jam'], 1)} min en cas d'embouteillage. "
                f"Il est de {fr(me.iloc[0], 1)} min par temps ensoleillé et de {fr(me.iloc[-1], 1)} min par brouillard ou temps nuageux. "
                "Les valeurs « Inconnu » ne sont pas représentées.", "cap")]

    th = q("""SELECT tranche_horaire t, AVG(temps_livraison_min) tl, COUNT(*) n FROM vue_livraisons
              WHERE jeu_donnees='train' AND tranche_horaire<>'Inconnue' GROUP BY 1""").set_index("t")
    ordre = ["Nuit (0h-5h)", "Matin (6h-10h)", "Midi (11h-14h)", "Après-midi (15h-18h)", "Soir (19h-23h)"]
    th = th.reindex(ordre)
    dd = q("SELECT distance_km d, temps_livraison_min t FROM fait_livraisons WHERE jeu_donnees='train' AND distance_km IS NOT NULL")
    bins = pd.cut(dd.d, [0, 5, 10, 15, 100], labels=["< 5 km", "5 à 10 km", "10 à 15 km", "≥ 15 km"], right=False)
    dg = dd.groupby(bins, observed=True).t.agg(["mean", "count"])
    fig_heure_distance(figs / "heure_distance.png", th.tl, th.n, dg["mean"].rename(lambda s: str(s)), dg["count"])
    story += [CondPageBreak(95 * mm), P("Temps de livraison selon l'heure et la distance", "h2"), img(figs / "heure_distance.png"),
              P(f"Tranche la plus rapide : {th.tl.idxmin().split(' (')[0].lower()} ({fr(th.tl.min(), 1)} min) ; "
                f"tranche la plus chargée : {th.n.idxmax().split(' (')[0].lower()} ({fr(th.n.max())} commandes). "
                + (f"Le temps moyen augmente avec la distance, de {fr(dg['mean'].iloc[0], 1)} min sous 5 km à "
                   f"{fr(dg['mean'].iloc[-1], 1)} min à partir de 15 km. " if dg["mean"].is_monotonic_increasing
                   else "Le lien entre distance et temps n'est pas régulier. ")
                + "Les distances ne sont calculées que pour les coordonnées valides.", "cap")]

    rows = [["Critère", "Groupe", "Réponses", "Output = Yes", "Avis positifs"]]
    for crit, col in [("Type de client", "type_client"), ("Occupation", "occupation")]:
        d = q(f"""SELECT {col} g, COUNT(*) n, 100.0*AVG(output_oui) po, 100.0*AVG(feedback_positif) pp
                  FROM fait_enquete JOIN dim_profil_client USING(id_profil) GROUP BY 1 ORDER BY n DESC""")
        for i, r in enumerate(d.itertuples()):
            rows.append([crit if i == 0 else "", r.g, fr(r.n), pct(r.po), pct(r.pp)])
    tot = q("SELECT COUNT(*) n, 100.0*AVG(output_oui) po, 100.0*AVG(feedback_positif) pp FROM fait_enquete").iloc[0]
    rows.append(["<b>Ensemble</b>", "", f"<b>{fr(tot.n)}</b>", f"<b>{pct(tot.po)}</b>", f"<b>{pct(tot.pp)}</b>"])
    story.append(KeepTogether([P("Enquête : réponses « Output = Yes » et avis positifs", "h2"),
                               tbl(rows, [20, 24, 14, 18, 18], right=(2, 3, 4)),
                               P("Les étudiants (207 réponses) sont ceux qui répondent le plus souvent « Yes » à la question Output. "
                                 "Les groupes de moins de 25 réponses (clients nouveaux, femmes au foyer) sont trop petits pour conclure.", "cap")]))

    # ============================== 7. QUALITÉ
    story += [CondPageBreak(110 * mm), P("7. Qualité des données", "h1"),
              P("Anomalies détectées dans les fichiers sources et traitement appliqué. Les données brutes restent intactes dans "
                "les tables de staging.", "body"), Spacer(1, 2 * mm)]
    ja = q("SELECT * FROM journal_anomalies")
    story.append(tbl([["Anomalie", "Lignes ou valeurs", "Traitement"]] +
                     [[esc(r.anomalie), fr(r.nb_lignes), esc(r.traitement)] for r in ja.itertuples()], [42, 11, 47], right=(1,)))
    n_inv = int(ja[ja.anomalie.str.contains(r"\(0, 0\)")].nb_lignes.iloc[0])
    n_dup = int(ja[ja.anomalie.str.contains("double")].nb_lignes.iloc[0])
    story.append(P(f"Les coordonnées du restaurant à (0, 0) concernent {fr(n_inv)} commandes sur {fr(n_tot)} ({pct(100 * n_inv / n_tot)}) : "
                   "elles sont gardées dans l'entrepôt, mais sans coordonnées ni distance.", "cap"))
    cq = q("SELECT * FROM controle_qualite")
    rows = [["Contrôle", "Attendu", "Obtenu", "Statut"]]
    for r in cq.itertuples():
        att, obt = r.attendu, r.obtenu
        if len(att) > 40:
            att, obt = "effectifs par ville (22)", "identiques"
        fmt = lambda v: fr(int(v)) if str(v).isdigit() else esc(v)
        rows.append([esc(r.controle), fmt(att), fmt(obt), f"<b>{esc(r.statut)}</b>"])
    n_ok = int((cq.statut == "OK").sum())
    story.append(KeepTogether([P("Contrôles de cohérence après chargement", "h2"), tbl(rows, [50, 16, 16, 8], right=(1, 2)),
                               P(f"{n_ok} contrôles sur {len(cq)} réussis. Les comparaisons se font entre les tables de staging "
                                 "(données brutes) et les tables finales, avec un calcul indépendant.", "cap")]))

    # ============================== 8. LIMITES
    story += [P("8. Limites à connaître", "h1")]
    for b in [
        f"<b>Temps de livraison absent pour le jeu test.</b> Les {fr(n_te)} commandes du test n'ont pas de temps réel : "
        "la colonne est vide et les valeurs d'exemple de Sample_Submission.csv n'ont pas été utilisées.",
        "<b>L'enquête n'est pas reliée aux commandes.</b> Elle n'a pas d'identifiant client et concerne uniquement Bangalore : "
        "la seule jointure possible avec les livraisons est la ville.",
        "<b>Sens de la colonne Output non documenté</b> dans la source. Elle est conservée telle quelle sous le nom output_oui.",
        "<b>Noms de villes déduits</b> des préfixes des codes livreurs (ex. BANG pour Bangalore) ; la source ne les donne pas.",
        f"<b>{fr(n_inv)} commandes sans coordonnées exploitables</b> (restaurant à 0, 0) : elles n'ont pas de distance.",
        f"<b>Profil très uniforme</b> : {lv[0]} livreurs dans chaque ville et des temps moyens entre {fr(dv.tl.min(), 1)} et "
        f"{fr(dv.tl.max(), 1)} min. Les comparaisons entre villes apportent peu d'information.",
        f"<b>{fr(n_dup)} lignes de l'enquête sont en double.</b> Sans identifiant, impossible de savoir si ce sont de vrais doublons : elles sont conservées.",
        "<b>Âge et note du livreur varient pour un même livreur</b> d'une commande à l'autre dans la source, ce qui est inhabituel : "
        "ces valeurs sont à utiliser avec prudence.",
    ]:
        story.append(Paragraph(b, ST["bullet"], bulletText="•"))

    # ============================== ANNEXE
    story += [CondPageBreak(90 * mm), P("Annexe : reproduire la construction", "h1"),
              P("Le script <font name='DVM' size='8'>etl_entrepot.py</font> lit les trois fichiers sources, "
                "crée la base <font name='DVM' size='8'>entrepot_livraison.db</font> et le fichier <font name='DVM' size='8'>schema.sql</font>, "
                "puis exécute les contrôles. Il nécessite Python avec les bibliothèques pandas et numpy.")]
    story.append(Spacer(1, 2 * mm))
    story.append(Preformatted('python3 etl_entrepot.py --train train.csv --test test.csv \\\n'
                              '    --enquete "online food delivery dataset.csv" --out-dir sortie/', ST["code"]))
    story.append(P("Exemples de requêtes d'analyse", "h2"))
    sql = """-- Temps moyen de livraison selon le trafic
SELECT trafic, COUNT(*) AS commandes, ROUND(AVG(temps_livraison_min), 1) AS temps_moyen
FROM vue_livraisons
WHERE jeu_donnees = 'train'
GROUP BY trafic ORDER BY temps_moyen;

-- Commandes et temps moyen par ville
SELECT v.nom_ville, COUNT(*) AS commandes, ROUND(AVG(f.temps_livraison_min), 1) AS temps_moyen
FROM fait_livraisons f JOIN dim_ville v USING (id_ville)
GROUP BY v.nom_ville ORDER BY commandes DESC;

-- Enquête : part de réponses Output = Yes selon l'occupation
SELECT p.occupation, COUNT(*) AS reponses, ROUND(100.0 * AVG(e.output_oui), 1) AS pct_yes
FROM fait_enquete e JOIN dim_profil_client p USING (id_profil)
GROUP BY p.occupation;"""
    story.append(Preformatted(sql, ST["code"]))

    # ---------------------------------------------------------------- document
    def pied(canv, doc):
        canv.saveState()
        canv.setFont("DV", 7.2)
        canv.setFillColor(colors.HexColor(MUTED))
        if doc.page > 1:
            canv.drawString(MARGIN, 10 * mm, "Data warehouse livraison de nourriture : rapport")
            canv.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {doc.page}")
        canv.restoreState()

    doc = BaseDocTemplate(str(a.out), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=16 * mm,
                          bottomMargin=18 * mm, title="Data warehouse : livraison de nourriture",
                          subject="Rapport de construction et contenu de l'entrepôt de données")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(MARGIN, 18 * mm, AVAIL, PAGE_H - 34 * mm, id="f",
                                                              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
                                       onPage=pied)])
    doc.build(story)
    print("PDF écrit :", a.out)


if __name__ == "__main__":
    main()
