# Architecture base de données OKazCar — Synthèse

_Date : 13 mars 2026_

---

## 1. Pourquoi ces choix à la base

OKazCar est né comme un **projet d'étude** tourné en localhost. L'objectif initial était
simple : une extension Chrome qui analyse des annonces auto, un backend Flask qui score
les annonces, et une base SQLite locale comme support de données.

### Pourquoi SQLite

Le choix de SQLite était rationnel pour un projet à ce stade :

- **Zéro infrastructure** — pas de serveur de base de données à installer, configurer ou maintenir
- **Un seul fichier** — `data/okazcar.db`, facile à versionner, copier, sauvegarder
- **Performances excellentes en lecture** — le cas d'usage principal (scoring d'annonces) est majoritairement en lecture
- **Parfaitement adapté au single-user** — un développeur, une machine, un processus
- **Déploiement trivial** — pas de credentials, pas de connexion réseau, pas de pool

### Pourquoi le workflow "local = vérité"

La DB locale est devenue la source de vérité naturellement :

- Les **données de référence** (véhicules, specs, fiabilité moteur, seeds) sont préparées manuellement
- Le référentiel véhicule représente **1 962 véhicules** et **21 967 specs techniques** — tout curaté à la main
- Le développement se fait en local — tester, ajuster, valider, puis publier
- Le mécanisme de **snapshot vers GitHub Release** permettait de pousser une copie cohérente vers la prod

Ce workflow était adapté à un projet où la prod ne faisait que **servir** des données préparées en amont.

---

## 2. Ce que le projet est devenu

Le projet a dépassé le cadre initial. Il est devenu un **produit viable avec une boucle de valeur économique**.

### L'architecture actuelle en chiffres

| Composant | Détail |
|-----------|--------|
| Backend | Python 3.12 / Flask / SQLAlchemy 2.0 — **~16 700 lignes** de code applicatif |
| Base de données | SQLite WAL, 24 tables, **194 Mo** |
| Extension Chrome | Manifest v3, version 1.2.0, soumise au Chrome Web Store |
| Déploiement | Render Starter (Frankfurt, Docker, disque persistant 1 Go) — **7 EUR/mois** |
| Tests | **65 fichiers de tests**, suite complète ruff + pytest + vitest |
| Seeds | 5 scripts idempotents, 2 000+ lignes de données de référence |
| API | 57 routes (2 API REST publiques, ~30 admin, auth, gestion) |
| Filtres | Pipeline L1 à L10 (extraction, référentiel, cohérence, prix, visuel, téléphone, SIRET, réputation, scoring, ancienneté) |

### La boucle de valeur

```
Extension Chrome (gratuite, multi-sites)
    |
    v
Utilisateurs scannent des annonces
    |
    v
Chaque scan alimente la base (prix, régions, motorisations)
    |
    v
La base s'enrichit → l'argus maison devient plus précis
    |
    v
API REST exploite cette base enrichie (à développer)
    |
    v
Service payant possible grâce aux données crowdsourcées
```

L'extension couvre **LeBonCoin, LaCentrale et AutoScout24** (10 variantes régionales : FR, DE, CH, IT, BE, NL, AT, ES, PL, LU, SE). Chaque utilisateur qui scanne une annonce **enrichit la base de données** sans le savoir — c'est du crowdsourcing passif.

Le modèle économique émerge naturellement : les données collectées gratuitement par les utilisateurs deviennent une **base de prix marché** exploitable par une API REST pour des services tiers (estimation de valeur, détection de bonnes affaires, analyse de marché).

### Ce que ça implique

La prod n'est plus un simple miroir du local. Elle **génère de la donnée** :

- Scans utilisateurs
- Prix du marché collectés automatiquement
- Enrichissements runtime (pneus, motorisations observées)
- Historique métier (logs, jobs de collecte)

---

## 3. Le talon d'Achille : la gestion du schéma en production

### Le problème identifié

L'architecture DB n'a pas été repensée quand le projet est passé de "localhost" à "produit en prod".
Le workflow actuel repose sur un remplacement complet de la DB prod par un snapshot local :

```
DB locale → snapshot → GitHub Release → Render télécharge au démarrage
```

**Le risque** : publier un snapshot local **écrase les données générées en prod** (scans, prix, enrichissements).
Ces données n'existent nulle part ailleurs.

De plus, il n'y a **aucun système de migration** versionnée. Si un modèle Python évolue (nouvelle colonne, nouvelle table),
la DB prod ne le voit pas — sauf si on écrase tout avec un nouveau snapshot.

### Ce qui fonctionne déjà bien

Avant de paniquer, constatons ce qui est déjà en place :

1. **Backup automatique robuste** — `sync_render_sqlite.py` crée une sauvegarde horodatée de l'ancienne DB
   avant chaque remplacement, avec vérification SHA256 et integrity check
2. **`db.create_all()` au démarrage** — les nouvelles tables sont créées automatiquement si elles n'existent pas
3. **SQLite = un fichier** — le rollback c'est `cp backup.db okazcar.db`, rien de plus
4. **Snapshots versionnés** — chaque publication génère un manifeste JSON avec hash, version, timestamp
5. **Disque persistant Render** — la DB survit aux redémarrages du container

Le système actuel est **robuste pour ce qu'il fait**. Il n'est simplement pas conçu pour un produit qui génère de la donnée en prod.

---

## 4. Les solutions qui s'offrent à nous

### Option A — Statu quo amélioré

Garder le workflow actuel avec des garde-fous supplémentaires :
- Alerter avant chaque `render:publish-db` si la prod contient des données non sauvegardées
- Ajouter un `pull-db` pour récupérer la DB prod en local avant publication

**Quand c'est adapté** : tant que la prod collecte peu de données critiques.

### Option B — Flask-Migrate (recommandée)

Introduire un vrai système de migrations avec Flask-Migrate (Alembic) :

- **Batch mode** pour SQLite — mature et bien documenté, contourne les limites `ALTER TABLE`
- Chaque évolution de schéma est un script versionné, testable, réversible
- La prod n'est plus jamais écrasée — elle évolue par migrations incrémentales
- Backup fichier automatique avant chaque migration (filet de sécurité)

**Estimation** : 2-3 jours de mise en place initiale, puis le workflow devient naturel.

### Option C — Hybride transitoire

Distinguer les tables de référence (gérées localement) des tables vivantes (jamais écrasées) :
- Publier uniquement les seeds de référence vers la prod
- Ne jamais écraser les tables runtime

**Limite** : complexité conceptuelle, risque de confusion sur qui possède quoi.

### Recommandation

**Option B avec la stratégie backup-first** :

1. Installer Flask-Migrate, configurer le batch mode SQLite
2. Générer la migration initiale (représente le schéma actuel)
3. `flask db stamp head` sur la prod (marquer comme "à jour" sans ré-exécuter)
4. Intégrer `backup .db + flask db upgrade` dans `docker-entrypoint.sh`
5. Chaque changement de modèle → `flask db migrate` → relire → tester → déployer

Le risque est **faible** car :
- Le rollback ultime reste `cp backup.db okazcar.db`
- Les migrations sont testées localement avant déploiement
- Le batch mode Alembic est éprouvé pour SQLite

---

## 5. Conclusion

L'architecture DB actuelle était le bon choix au bon moment. SQLite local, seeds manuels,
snapshot vers prod — c'était pragmatique et adapté à un projet d'étude.

Le projet a grandi au-delà de cette architecture. L'extension Chrome sur le Web Store,
le déploiement Render, la collecte de données crowdsourcées — tout ça transforme OKazCar
en un produit qui **génère de la valeur en production**.

Le talon d'Achille n'est pas un défaut de conception initial — c'est la conséquence naturelle
d'un projet qui a réussi au-delà de son cadre prévu. La solution est identifiée, le chemin
est tracé, et les fondations existantes (backups, seeds, `create_all`) facilitent la transition.

> Un projet qui n'a jamais eu ce problème est un projet qui n'a jamais dépassé le stade du prototype.
