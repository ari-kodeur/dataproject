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

CREATE TABLE "stg_train" (
"ID" TEXT,
  "Delivery_person_ID" TEXT,
  "Delivery_person_Age" TEXT,
  "Delivery_person_Ratings" TEXT,
  "Restaurant_latitude" TEXT,
  "Restaurant_longitude" TEXT,
  "Delivery_location_latitude" TEXT,
  "Delivery_location_longitude" TEXT,
  "Order_Date" TEXT,
  "Time_Orderd" TEXT,
  "Time_Order_picked" TEXT,
  "Weatherconditions" TEXT,
  "Road_traffic_density" TEXT,
  "Vehicle_condition" TEXT,
  "Type_of_order" TEXT,
  "Type_of_vehicle" TEXT,
  "multiple_deliveries" TEXT,
  "Festival" TEXT,
  "City" TEXT,
  "Time_taken(min)" TEXT
);

CREATE TABLE "stg_test" (
"ID" TEXT,
  "Delivery_person_ID" TEXT,
  "Delivery_person_Age" TEXT,
  "Delivery_person_Ratings" TEXT,
  "Restaurant_latitude" TEXT,
  "Restaurant_longitude" TEXT,
  "Delivery_location_latitude" TEXT,
  "Delivery_location_longitude" TEXT,
  "Order_Date" TEXT,
  "Time_Orderd" TEXT,
  "Time_Order_picked" TEXT,
  "Weatherconditions" TEXT,
  "Road_traffic_density" TEXT,
  "Vehicle_condition" TEXT,
  "Type_of_order" TEXT,
  "Type_of_vehicle" TEXT,
  "multiple_deliveries" TEXT,
  "Festival" TEXT,
  "City" TEXT
);

CREATE TABLE "stg_enquete" (
"Age" TEXT,
  "Gender" TEXT,
  "Marital Status" TEXT,
  "Occupation" TEXT,
  "Monthly Income" TEXT,
  "Educational Qualifications" TEXT,
  "Family size" TEXT,
  "Customer Type" TEXT,
  "latitude" TEXT,
  "longitude" TEXT,
  "Pin code" TEXT,
  "Output" TEXT,
  "Feedback" TEXT,
  "Unnamed: 13" TEXT
);
