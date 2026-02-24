# Prospection CSV - Guide utilisateur

## Vue d'ensemble

La page **Prospection CSV** (`/admin/csv-prospection`) permet d'identifier proactivement les véhicules disponibles dans les CSV Kaggle mais absents du référentiel Co-Pilot.

## Workflow

1. **Consulter la liste** : Ouvrir `/admin/csv-prospection` depuis la sidebar admin
2. **Identifier un modèle intéressant** : Trier par nombre de fiches (déjà trié par défaut)
3. **Cliquer sur "🔍 Chercher sur LBC"** : Ouvre une recherche LBC dans un nouvel onglet
4. **Scanner avec l'extension** : Scanner quelques annonces pour ce modèle
5. **Ajouter au référentiel** : Via `/admin/car`, cliquer sur "Ajouter" dans la section "Modèles demandés"
6. **Bénéficier de l'auto-enrichissement** : Les X fiches CSV sont importées automatiquement

## Interface

### Stat Cards

- **Véhicules CSV non importés** : Nombre total de modèles disponibles
- **Fiches specs disponibles** : Nombre total de fiches techniques (tous modèles confondus)

### Tableau

| Colonne | Description |
|---------|-------------|
| **Marque** | Marque du véhicule (ex: Renault) |
| **Modèle** | Modèle du véhicule (ex: Clio) |
| **Plage années** | Années couvertes par les specs CSV (ex: 2012-2024) |
| **Fiches CSV** | Nombre de fiches qui seront importées (ex: 35) |
| **Action** | Lien direct vers recherche LBC |

### Pagination

- 50 véhicules par page
- Navigation "Précédent" / "Suivant"
- Indicateur "Page X / Y"

## Pourquoi cette feature ?

**Avant** : On découvrait les véhicules disponibles **par hasard** en scannant LBC.

**Maintenant** : On peut **choisir activement** les modèles à ajouter, en priorisant ceux avec le plus de données.

## Exemples

### Cas 1 : Ajouter la Renault Clio

1. Voir "Renault Clio" avec 35 fiches CSV
2. Cliquer "🔍 Chercher sur LBC" → Ouvre `https://www.leboncoin.fr/recherche?category=2&text=Renault+Clio`
3. Scanner 2-3 annonces avec l'extension
4. La Clio apparaît dans `/admin/car` "Modèles demandés"
5. Cliquer "Ajouter" → 35 fiches specs importées automatiquement

### Cas 2 : Référentiel déjà complet

Si la liste est vide avec message "🎉 Tous les véhicules CSV sont déjà importés !", c'est que :
- Tous les modèles CSV sont dans le référentiel
- Ou le CSV Kaggle ne contient que des modèles déjà ajoutés

## Notes techniques

- **Cache** : Le catalogue CSV est chargé en mémoire au démarrage de l'app
- **Performance** : Lookup O(1) après le 1er chargement
- **Tri** : Par `specs_count` descendant (modèles riches en données d'abord)
- **Compatibilité** : Fonctionne avec le CSV Kaggle existant sans modification

## Limites

- **Pas d'ajout automatique** : L'utilisateur doit scanner + ajouter manuellement (par design)
- **Pas de filtrage avancé** : Pas de filtre par marque/année (évolution future possible)
- **Données statiques** : Le catalogue se met à jour au restart de l'app uniquement
