# Design — Carte choropleth Europe des prix par pays

**Date** : 2026-03-12
**Critere** : 06 Maps/GPS
**Effort** : faible — donnees existantes, Plotly deja en place

## Objectif

Ajouter une carte choropleth interactive de l'Europe dans la page Argus admin,
coloree par prix moyen pour un vehicule specifique (marque + modele + annee + carburant).

Exemple : "Clio 2022 diesel" → la carte colore chaque pays selon le prix moyen collecte.

## Architecture

### Approche retenue

`plotly.express.choropleth` cote serveur (Approche A).

- Zero dependance nouvelle — Plotly 6.0.1 backend + Plotly.js 2.35.2 frontend deja present
- Geometries pays integrees dans Plotly (`locationmode="ISO-3"`)
- Pattern identique aux 3 charts Plotly existants du dashboard

### Emplacement

Page Argus (`/admin/argus`), nouvelle section en bas apres "Seuils argus par vehicule",
avant les flash messages (ligne ~614 de `argus.html`).

### Filtres dedicates a la carte

4 dropdowns en cascade au-dessus de la carte :

1. **Marque** (select) — toutes les marques presentes dans MarketPrice
2. **Modele** (select) — filtre par marque selectionnee
3. **Annee** (select) — filtre par marque+modele
4. **Carburant** (select) — filtre par marque+modele+annee

Bouton **"Voir sur la carte"** → rechargement page classique (form GET),
coherent avec les filtres existants du tableau.

La carte n'apparait que quand les 4 filtres sont remplis et soumis.

### Backend — Route `argus()`

Nouveaux query params : `map_make`, `map_model`, `map_year`, `map_fuel`.

Quand les 4 sont fournis :

```python
# Agregation par pays
country_stats = (
    db.session.query(
        MarketPrice.country,
        db.func.avg(MarketPrice.price_iqr_mean).label("avg_price"),
        db.func.count(MarketPrice.id).label("ref_count"),
        db.func.sum(MarketPrice.sample_count).label("total_samples"),
    )
    .filter(
        MarketPrice.make == map_make,
        MarketPrice.model == map_model,
        MarketPrice.year == map_year,
        MarketPrice.fuel == map_fuel,
        MarketPrice.country.isnot(None),
        MarketPrice.price_iqr_mean.isnot(None),
    )
    .group_by(MarketPrice.country)
    .all()
)
```

Construction du fig avec `plotly.express.choropleth` :

```python
import plotly.express as px

ISO2_TO_ISO3 = {"FR": "FRA", "DE": "DEU", "ES": "ESP", "IT": "ITA", "BE": "BEL", ...}

fig = px.choropleth(
    df,
    locations="iso3",
    color="avg_price",
    hover_name="country",
    hover_data={"avg_price": ":,.0f", "ref_count": True, "total_samples": True},
    scope="europe",
    color_continuous_scale="RdYlGn_r",  # rouge=cher, vert=bon marche
    labels={"avg_price": "Prix moyen (€)", "ref_count": "References", "total_samples": "Annonces"},
)
fig.update_layout(
    margin=dict(l=0, r=0, t=30, b=0),
    paper_bgcolor="rgba(0,0,0,0)",
    geo=dict(bgcolor="rgba(0,0,0,0)"),
)
map_json = fig.to_json()
```

Passe `map_json` au template (ou `None` si filtres incomplets).

### Template — Section carte

```html
<!-- Carte Europe des prix -->
<div class="stat-card mt-4">
  <h5 class="mb-3">Carte des prix par pays</h5>
  <form method="get" class="row g-2 align-items-end mb-3">
    <!-- Conserver les filtres du tableau -->
    <input type="hidden" name="make" value="{{ make_filter }}">
    <input type="hidden" name="region" value="{{ region_filter }}">
    <input type="hidden" name="page" value="{{ page }}">

    <div class="col-md-2">
      <label class="form-label mb-1">Marque</label>
      <select name="map_make" class="form-select form-select-sm">...</select>
    </div>
    <div class="col-md-3">
      <label class="form-label mb-1">Modele</label>
      <select name="map_model" class="form-select form-select-sm">...</select>
    </div>
    <div class="col-md-2">
      <label class="form-label mb-1">Annee</label>
      <select name="map_year" class="form-select form-select-sm">...</select>
    </div>
    <div class="col-md-2">
      <label class="form-label mb-1">Carburant</label>
      <select name="map_fuel" class="form-select form-select-sm">...</select>
    </div>
    <div class="col-md-2">
      <button type="submit" class="btn btn-sm btn-primary">Voir sur la carte</button>
    </div>
  </form>

  {% if map_json %}
  <div id="chart-europe-prices" style="height:500px"></div>
  <script>Plotly.react("chart-europe-prices", ...{{ map_json | safe }});</script>
  {% else %}
  <p class="text-muted text-center py-4">
    Selectionnez un vehicule ci-dessus pour afficher la carte des prix.
  </p>
  {% endif %}
</div>
```

### Mapping ISO-2 → ISO-3

Dict Python statique couvrant les pays europeens courants :

```python
ISO2_TO_ISO3 = {
    "FR": "FRA", "DE": "DEU", "ES": "ESP", "IT": "ITA",
    "BE": "BEL", "NL": "NLD", "PT": "PRT", "AT": "AUT",
    "CH": "CHE", "GB": "GBR", "PL": "POL", "CZ": "CZE",
    "LU": "LUX", "IE": "IRL", "SE": "SWE", "DK": "DNK",
}
```

Extensible : nouveaux pays ajoutes au dict au besoin.

### Peuplement des dropdowns

Les selects Modele/Annee/Carburant doivent etre dynamiques selon la selection.
Avec le rechargement page, c'est simple : cote serveur on query les valeurs
distinctes filtrees par les params deja choisis.

- `map_make` choisi → query modeles distincts pour cette marque
- `map_make` + `map_model` → query annees distinctes
- les 3 → query carburants distincts

### Ce qu'on ne fait PAS

- Pas de zoom sub-national (regions francaises)
- Pas de GeoJSON externe
- Pas de nouvelle dependance
- Pas d'AJAX — rechargement page classique
- Pas d'endpoint API separe
