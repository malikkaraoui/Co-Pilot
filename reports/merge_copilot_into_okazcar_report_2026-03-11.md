# Rapport de fusion copilot.db → okazcar.db

_Date_: 2026-03-11

## scan_logs

- Lus : 897
- Importés : 897
- Ignorés (doublon) : 0

## filter_results

- Lus : 8843
- Importés : 8843
- Ignorés (doublon) : 0

## market_prices

- Lus : 437
- Importés : 437
- Ignorés (doublon) : 0

## collection_jobs_as24

- Lus : 1397
- Importés : 1397
- Ignorés (doublon) : 0

## collection_jobs_lbc

- Lus : 1834
- Importés : 1834
- Ignorés (doublon) : 0

## youtube_videos

- Lus : 19
- Importés : 18
- Ignorés (doublon) : 0
- Ignorés (pas de véhicule cible) : 1
- Conflits : 1
  - video_id=gzJPcDrtsLc: vehicle_id=105 sans correspondance dans okazcar.db

## youtube_transcripts

- Lus : 19
- Importés : 18
- Ignorés (doublon) : 0
- Ignorés (pas de véhicule cible) : 1

## vehicle_syntheses

- Lus : 2
- Importés : 2
- Ignorés (doublon) : 0

## email_drafts

- Lus : 12
- Importés : 11
- Ignorés (doublon) : 1

## llm_usages

- Lus : 14
- Importés : 14
- Ignorés (doublon) : 0

## gemini_config

- Lus : 1
- Importés : 1
- Ignorés (doublon) : 0

## observed_motorizations

- Lus : 298
- Importés : 289
- Ignorés (doublon) : 0
- Ignorés (pas de véhicule cible) : 9

## vehicle_observed_specs

- Lus : 559
- Importés : 537
- Ignorés (doublon) : 8
- Ignorés (pas de véhicule cible) : 14

## failed_searches

- Lus : 9
- Importés : 8
- Ignorés (doublon) : 1

## Totaux

- Lus : 14341
- Importés : 14306
- Ignorés (doublon) : 10
- Ignorés (pas de mapping) : 25

## Note post-fusion validée

Ce rapport décrit les **flux importés** pendant l’opération de merge, pas le comptage final live de
toutes les tables après fusion.

Points à retenir après contrôle direct de `data/okazcar.db` :

- la table correcte est **`filter_results`** ;
- il n’existe pas de table `filter_results_db` dans la base canonique ;
- le compte final live de **`vehicle_syntheses` est 3**.

La ligne ci-dessus :

- `vehicle_syntheses` lus = 2
- `vehicle_syntheses` importés = 2

signifie uniquement que **2 synthèses ont été importées depuis `copilot.db`**. Le total présent en
base après fusion est **3**.
