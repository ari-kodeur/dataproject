# Entrepôt de données – livraison de nourriture

Projet d'apprentissage : construction d'un data warehouse (SQLite) à partir de données publiques Kaggle, avec ETL Python reproductible et rapport PDF.

## Contenu
- `src/etl_entrepot.py` : ETL (staging → dimensions → faits), nettoyage, journal d'anomalies, 12 contrôles qualité
- `src/build_pdf.py` : génération du rapport depuis la base
- `docs/schema.sql` : schéma de l'entrepôt
- `docs/Rapport_Data_Warehouse.pdf` : rapport (modèle, dictionnaire, résultats)

## Modèle
Schéma en **constellation** : `fait_livraisons` (56 992 lignes) et `fait_enquete` (388 lignes) partagent la dimension `dim_ville`. L'enquête n'ayant pas d'identifiant client, elle ne se relie aux livraisons que par la ville.

## Résultats (jeu d'entraînement)
- Temps moyen de livraison : 26,3 min ; trafic faible 21,3 min contre embouteillage 31,2 min ; < 5 km 22,2 min contre ≥ 15 km 29,9 min
- 4 510 commandes avec coordonnées restaurant inutilisables (distance NULL)
- Ce sont des moyennes observées, pas des effets isolés.

## Limites
Données publiques très uniformes (60 livreurs par ville, temps moyens quasi identiques entre villes) ; noms de villes déduits des préfixes de codes ; enquête limitée à Bangalore ; sens de la colonne « Output » non confirmé.

## Utilisation
```bash
pip install pandas reportlab matplotlib
python src/etl_entrepot.py --train train.csv --test test.csv --enquete "online food delivery dataset.csv" --out-dir out
python src/build_pdf.py --db out/entrepot_livraison.db --out out/Rapport.pdf --figs out/figs
```
Les CSV ne sont pas inclus : à télécharger sur Kaggle.

## Sources (vérifier les licences avant réutilisation)
- *Food Delivery Dataset* – gauravmalik26 (Kaggle)
- *Online Food Delivery Preferences – Bangalore region* – Benroshan007 (Kaggle)
