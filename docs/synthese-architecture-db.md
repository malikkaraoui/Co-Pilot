# Architecture base de donnees OKazCar — Synthese

_Date : 13 mars 2026_

---

## 1. Pourquoi ces choix a la base

OKazCar est ne comme un **projet d'etude** tourne en localhost. L'objectif initial etait
simple : une extension Chrome qui analyse des annonces auto, un backend Flask qui score
les annonces, et une base SQLite locale comme support de donnees.

### Pourquoi SQLite

Le choix de SQLite etait rationnel pour un projet a ce stade :

- **Zero infrastructure** — pas de serveur de base de donnees a installer, configurer ou maintenir
- **Un seul fichier** — `data/okazcar.db`, facile a versionner, copier, sauvegarder
- **Performances excellentes en lecture** — le cas d'usage principal (scoring d'annonces) est majoritairement en lecture
- **Parfaitement adapte au single-user** — un developpeur, une machine, un processus
- **Deploiement trivial** — pas de credentials, pas de connexion reseau, pas de pool

### Pourquoi le workflow "local = verite"

La DB locale est devenue la source de verite naturellement :

- Les **donnees de reference** (vehicules, specs, fiabilite moteur, seeds) sont preparees manuellement
- Le referentiel vehicule represente **1 962 vehicules** et **21 967 specs techniques** — tout curate a la main
- Le developpement se fait en local — tester, ajuster, valider, puis publier
- Le mecanisme de **snapshot vers GitHub Release** permettait de pousser une copie coherente vers la prod

Ce workflow etait adapte a un projet ou la prod ne faisait que **servir** des donnees preparees en amont.

---

## 2. Ce que le projet est devenu

Le projet a depasse le cadre initial. Il est devenu un **produit viable avec une boucle de valeur economique**.

### L'architecture actuelle en chiffres

| Composant | Detail |
|-----------|--------|
| Backend | Python 3.12 / Flask / SQLAlchemy 2.0 — **~16 700 lignes** de code applicatif |
| Base de donnees | SQLite WAL, 24 tables, **194 Mo** |
| Extension Chrome | Manifest v3, version 1.2.0, soumise au Chrome Web Store |
| Deploiement | Render Starter (Frankfurt, Docker, disque persistant 1 Go) — **7 EUR/mois** |
| Tests | **65 fichiers de tests**, suite complete ruff + pytest + vitest |
| Seeds | 5 scripts idempotents, 2 000+ lignes de donnees de reference |
| API | 57 routes (2 API REST publiques, ~30 admin, auth, gestion) |
| Filtres | Pipeline L1 a L10 (extraction, referentiel, coherence, prix, visuel, telephone, SIRET, reputation, scoring, anciennete) |

### La boucle de valeur

```
Extension Chrome (gratuite, multi-sites)
    |
    v
Utilisateurs scannent des annonces
    |
    v
Chaque scan alimente la base (prix, regions, motorisations)
    |
    v
La base s'enrichit → l'argus maison devient plus precis
    |
    v
API REST exploite cette base enrichie (a developper)
    |
    v
Service payant possible grace aux donnees crowdsourcees
```

L'extension couvre **LeBonCoin, LaCentrale et AutoScout24** (10 variantes regionales : FR, DE, CH, IT, BE, NL, AT, ES, PL, LU, SE). Chaque utilisateur qui scanne une annonce **enrichit la base de donnees** sans le savoir — c'est du crowdsourcing passif.

Le modele economique emerge naturellement : les donnees collectees gratuitement par les utilisateurs deviennent une **base de prix marche** exploitable par une API REST pour des services tiers (estimation de valeur, detection de bonnes affaires, analyse de marche).

### Ce que ca implique

La prod n'est plus un simple miroir du local. Elle **genere de la donnee** :

- Scans utilisateurs
- Prix du marche collectes automatiquement
- Enrichissements runtime (pneus, motorisations observees)
- Historique metier (logs, jobs de collecte)

---

## 3. Le talon d'Achille : la gestion du schema en production

### Le probleme identifie

L'architecture DB n'a pas ete repensee quand le projet est passe de "localhost" a "produit en prod".
Le workflow actuel repose sur un remplacement complet de la DB prod par un snapshot local :

```
DB locale → snapshot → GitHub Release → Render telecharge au demarrage
```

**Le risque** : publier un snapshot local **ecrase les donnees generees en prod** (scans, prix, enrichissements).
Ces donnees n'existent nulle part ailleurs.

De plus, il n'y a **aucun systeme de migration** versionnee. Si un modele Python evolue (nouvelle colonne, nouvelle table),
la DB prod ne le voit pas — sauf si on ecrase tout avec un nouveau snapshot.

### Ce qui fonctionne deja bien

Avant de paniquer, constatons ce qui est deja en place :

1. **Backup automatique robuste** — `sync_render_sqlite.py` cree une sauvegarde horodatee de l'ancienne DB
   avant chaque remplacement, avec verification SHA256 et integrity check
2. **`db.create_all()` au demarrage** — les nouvelles tables sont creees automatiquement si elles n'existent pas
3. **SQLite = un fichier** — le rollback c'est `cp backup.db okazcar.db`, rien de plus
4. **Snapshots versionnes** — chaque publication genere un manifeste JSON avec hash, version, timestamp
5. **Disque persistant Render** — la DB survit aux redemarrages du container

Le systeme actuel est **robuste pour ce qu'il fait**. Il n'est simplement pas concu pour un produit qui genere de la donnee en prod.

---

## 4. Les solutions qui s'offrent a nous

### Option A — Statu quo ameliore

Garder le workflow actuel avec des garde-fous supplementaires :
- Alerter avant chaque `render:publish-db` si la prod contient des donnees non sauvegardees
- Ajouter un `pull-db` pour recuperer la DB prod en local avant publication

**Quand c'est adapte** : tant que la prod collecte peu de donnees critiques.

### Option B — Flask-Migrate (recommandee)

Introduire un vrai systeme de migrations avec Flask-Migrate (Alembic) :

- **Batch mode** pour SQLite — mature et bien documente, contourne les limites `ALTER TABLE`
- Chaque evolution de schema est un script versionne, testable, reversible
- La prod n'est plus jamais ecrasee — elle evolue par migrations incrementales
- Backup fichier automatique avant chaque migration (filet de securite)

**Estimation** : 2-3 jours de mise en place initiale, puis le workflow devient naturel.

### Option C — Hybride transitoire

Distinguer les tables de reference (gerees localement) des tables vivantes (jamais ecrasees) :
- Publier uniquement les seeds de reference vers la prod
- Ne jamais ecraser les tables runtime

**Limite** : complexite conceptuelle, risque de confusion sur qui possede quoi.

### Recommandation

**Option B avec la strategie backup-first** :

1. Installer Flask-Migrate, configurer le batch mode SQLite
2. Generer la migration initiale (represente le schema actuel)
3. `flask db stamp head` sur la prod (marquer comme "a jour" sans re-executer)
4. Integrer `backup .db + flask db upgrade` dans `docker-entrypoint.sh`
5. Chaque changement de modele → `flask db migrate` → relire → tester → deployer

Le risque est **faible** car :
- Le rollback ultime reste `cp backup.db okazcar.db`
- Les migrations sont testees localement avant deploiement
- Le batch mode Alembic est eprouve pour SQLite

---

## 5. Conclusion

L'architecture DB actuelle etait le bon choix au bon moment. SQLite local, seeds manuels,
snapshot vers prod — c'etait pragmatique et adapte a un projet d'etude.

Le projet a grandi au-dela de cette architecture. L'extension Chrome sur le Web Store,
le deploiement Render, la collecte de donnees crowdsourcees — tout ca transforme OKazCar
en un produit qui **genere de la valeur en production**.

Le talon d'Achille n'est pas un defaut de conception initial — c'est la consequence naturelle
d'un projet qui a reussi au-dela de son cadre prevu. La solution est identifiee, le chemin
est trace, et les fondations existantes (backups, seeds, `create_all`) facilitent la transition.

> Un projet qui n'a jamais eu ce probleme est un projet qui n'a jamais depasse le stade du prototype.
