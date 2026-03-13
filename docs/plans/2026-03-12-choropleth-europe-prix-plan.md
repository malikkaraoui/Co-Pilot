# Choropleth Europe — Prix par pays — Plan d'implémentation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ajouter une carte choropleth Plotly de l'Europe dans la page Argus admin, colorée par prix moyen pour un véhicule sélectionné (marque + modèle + année + carburant).

**Architecture:** Filtres dédiés (form GET) en bas de la page Argus → agrégation SQL par pays côté route Flask → `plotly.express.choropleth` serveur → `fig.to_json()` passé au template Jinja → `Plotly.react()` côté client. Rechargement page classique.

**Tech Stack:** Python 3.12 / Flask / SQLAlchemy / Plotly 6.0.1 (déjà installé) / Jinja2 / Bootstrap 5

**Design doc:** `docs/plans/2026-03-12-choropleth-europe-prix-design.md`

---

### Task 1: Test — La route argus accepte les query params carte et retourne map_json

**Files:**
- Modify: `tests/test_admin/test_admin.py`

**Step 1: Écrire le test**

```python
# À ajouter dans tests/test_admin/test_admin.py

from app.models.market_price import MarketPrice
from datetime import datetime, timezone, timedelta


class TestArgusMap:
    """Tests de la carte choropleth Europe dans la page Argus."""

    def test_argus_map_no_params_shows_placeholder(self, client, admin_user, app):
        """Sans filtres carte, on voit le placeholder 'Sélectionnez un véhicule'."""
        _login(client)
        resp = client.get("/admin/argus")
        assert resp.status_code == 200
        assert "Selectionnez un vehicule" in resp.data.decode()

    def test_argus_map_with_params_shows_chart(self, client, admin_user, app):
        """Avec les 4 filtres carte remplis et des données, on voit le chart Plotly."""
        from app.extensions import db

        with app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            mp = MarketPrice(
                make="Renault",
                model="Clio",
                year=2022,
                region="Ile-de-France",
                country="FR",
                fuel="diesel",
                price_min=8000,
                price_median=12000,
                price_mean=12500,
                price_max=18000,
                price_iqr_mean=12200,
                sample_count=15,
                collected_at=now,
                refresh_after=now + timedelta(hours=24),
            )
            db.session.add(mp)
            db.session.commit()

        _login(client)
        resp = client.get(
            "/admin/argus?map_make=Renault&map_model=Clio&map_year=2022&map_fuel=diesel"
        )
        assert resp.status_code == 200
        assert "chart-europe-prices" in resp.data.decode()

    def test_argus_map_no_data_shows_message(self, client, admin_user, app):
        """Avec les 4 filtres mais aucune donnée, message 'aucune donnée'."""
        _login(client)
        resp = client.get(
            "/admin/argus?map_make=Ferrari&map_model=F40&map_year=1990&map_fuel=essence"
        )
        assert resp.status_code == 200
        assert "Aucune donnee" in resp.data.decode() or "Selectionnez" in resp.data.decode()
```

**Step 2: Lancer le test, vérifier qu'il échoue**

Run: `python -m pytest tests/test_admin/test_admin.py::TestArgusMap -v`
Expected: FAIL — "Selectionnez un vehicule" pas trouvé (pas encore dans le template)

**Step 3: Commit le test**

```bash
git add tests/test_admin/test_admin.py
git commit -m "test(argus): add failing tests for Europe choropleth map"
```

---

### Task 2: Backend — Agrégation par pays + génération Plotly dans la route argus

**Files:**
- Modify: `app/admin/routes.py` (fonction `argus()`, lignes ~1407-1577)

**Step 1: Ajouter le mapping ISO-2 → ISO-3 et la logique carte en haut du fichier ou dans la fonction**

Ajouter dans la fonction `argus()`, juste avant le `return render_template(...)` (ligne ~1556) :

```python
    # ── Carte choropleth Europe ──────────────────────────────────
    map_make = request.args.get("map_make", "").strip()
    map_model = request.args.get("map_model", "").strip()
    map_year = request.args.get("map_year", "", type=str).strip()
    map_fuel = request.args.get("map_fuel", "").strip()

    map_json = None
    map_models = []
    map_years = []
    map_fuels = []

    # Listes dynamiques pour les selects en cascade
    if map_make:
        map_models = [
            r.model
            for r in db.session.query(MarketPrice.model)
            .filter(MarketPrice.make == map_make)
            .distinct()
            .order_by(MarketPrice.model)
            .all()
        ]
    if map_make and map_model:
        map_years = [
            str(r.year)
            for r in db.session.query(MarketPrice.year)
            .filter(MarketPrice.make == map_make, MarketPrice.model == map_model)
            .distinct()
            .order_by(MarketPrice.year.desc())
            .all()
        ]
    if map_make and map_model and map_year:
        map_fuels = [
            r.fuel
            for r in db.session.query(MarketPrice.fuel)
            .filter(
                MarketPrice.make == map_make,
                MarketPrice.model == map_model,
                MarketPrice.year == int(map_year),
                MarketPrice.fuel.isnot(None),
            )
            .distinct()
            .order_by(MarketPrice.fuel)
            .all()
        ]

    # Générer la carte si les 4 filtres sont remplis
    if map_make and map_model and map_year and map_fuel:
        import plotly.express as px

        ISO2_TO_ISO3 = {
            "FR": "FRA", "DE": "DEU", "ES": "ESP", "IT": "ITA",
            "BE": "BEL", "NL": "NLD", "PT": "PRT", "AT": "AUT",
            "CH": "CHE", "GB": "GBR", "PL": "POL", "CZ": "CZE",
            "LU": "LUX", "IE": "IRL", "SE": "SWE", "DK": "DNK",
            "NO": "NOR", "FI": "FIN", "RO": "ROU", "HU": "HUN",
            "HR": "HRV", "SK": "SVK", "SI": "SVN", "BG": "BGR",
            "GR": "GRC", "LT": "LTU", "LV": "LVA", "EE": "EST",
        }
        ISO3_TO_NAME = {
            "FRA": "France", "DEU": "Allemagne", "ESP": "Espagne", "ITA": "Italie",
            "BEL": "Belgique", "NLD": "Pays-Bas", "PRT": "Portugal", "AUT": "Autriche",
            "CHE": "Suisse", "GBR": "Royaume-Uni", "POL": "Pologne", "CZE": "Tchequie",
            "LUX": "Luxembourg", "IRL": "Irlande", "SWE": "Suede", "DNK": "Danemark",
            "NOR": "Norvege", "FIN": "Finlande", "ROU": "Roumanie", "HUN": "Hongrie",
            "HRV": "Croatie", "SVK": "Slovaquie", "SVN": "Slovenie", "BGR": "Bulgarie",
            "GRC": "Grece", "LTU": "Lituanie", "LVA": "Lettonie", "EST": "Estonie",
        }

        country_stats = (
            db.session.query(
                MarketPrice.country,
                db.func.round(db.func.avg(MarketPrice.price_iqr_mean)).label("avg_price"),
                db.func.count(MarketPrice.id).label("ref_count"),
                db.func.sum(MarketPrice.sample_count).label("total_samples"),
            )
            .filter(
                MarketPrice.make == map_make,
                MarketPrice.model == map_model,
                MarketPrice.year == int(map_year),
                MarketPrice.fuel == map_fuel,
                MarketPrice.country.isnot(None),
                MarketPrice.price_iqr_mean.isnot(None),
            )
            .group_by(MarketPrice.country)
            .all()
        )

        if country_stats:
            data = []
            for row in country_stats:
                iso3 = ISO2_TO_ISO3.get(row.country)
                if iso3:
                    data.append({
                        "iso3": iso3,
                        "pays": ISO3_TO_NAME.get(iso3, row.country),
                        "prix_moyen": int(row.avg_price),
                        "references": row.ref_count,
                        "annonces": row.total_samples,
                    })

            if data:
                import pandas as pd

                df = pd.DataFrame(data)
                fig = px.choropleth(
                    df,
                    locations="iso3",
                    color="prix_moyen",
                    hover_name="pays",
                    hover_data={
                        "iso3": False,
                        "prix_moyen": ":,.0f",
                        "references": True,
                        "annonces": True,
                    },
                    scope="europe",
                    color_continuous_scale="RdYlGn_r",
                    labels={
                        "prix_moyen": "Prix moyen (€)",
                        "references": "References",
                        "annonces": "Annonces",
                    },
                    title=f"{map_make} {map_model} {map_year} — {map_fuel}",
                )
                fig.update_layout(
                    margin=dict(l=0, r=0, t=40, b=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                    geo=dict(
                        bgcolor="rgba(0,0,0,0)",
                        showframe=False,
                    ),
                    height=500,
                    coloraxis_colorbar=dict(
                        title="Prix (€)",
                        tickformat=",",
                    ),
                )
                map_json = fig.to_json()
```

**Step 2: Ajouter les nouvelles variables au `render_template`**

Dans le `return render_template(...)` existant (~ligne 1556), ajouter :

```python
        map_json=map_json,
        map_make=map_make,
        map_model=map_model,
        map_year=map_year,
        map_fuel=map_fuel,
        map_models=map_models,
        map_years=map_years,
        map_fuels=map_fuels,
        make_list=make_list,  # déjà présent, réutilisé pour le select carte
```

**Step 3: Lancer les tests existants pour vérifier qu'on n'a rien cassé**

Run: `python -m pytest tests/test_admin/test_admin.py -v`
Expected: Tests existants PASS

**Step 4: Commit**

```bash
git add app/admin/routes.py
git commit -m "feat(argus): add Europe choropleth map data aggregation by country"
```

---

### Task 3: Template — Section carte avec filtres et rendu Plotly

**Files:**
- Modify: `app/admin/templates/admin/argus.html` (après ligne ~614, avant les flash messages)

**Step 1: Ajouter la section carte**

Insérer juste avant `{% if get_flashed_messages() %}` (ligne 616) :

```html
<!-- ── Carte Europe des prix par pays ────────────────────────── -->
<div class="stat-card mt-4">
  <h5 class="mb-3">
    Carte des prix par pays
    <small class="text-muted ms-2" style="font-size:12px">
      Selectionnez un vehicule pour visualiser les prix collectes en Europe.
    </small>
  </h5>

  <form method="get" class="row g-2 align-items-end mb-3">
    <!-- Conserver les filtres du tableau existant -->
    <input type="hidden" name="make" value="{{ make_filter }}">
    <input type="hidden" name="region" value="{{ region_filter }}">
    <input type="hidden" name="page" value="{{ page }}">

    <div class="col-md-2">
      <label class="form-label mb-1" style="font-size:13px">Marque</label>
      <select name="map_make" class="form-select form-select-sm" onchange="this.form.map_model.value='';this.form.map_year.value='';this.form.map_fuel.value='';this.form.submit()">
        <option value="">--</option>
        {% for m in make_list %}
        <option value="{{ m }}" {% if m == map_make %}selected{% endif %}>{{ m }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label mb-1" style="font-size:13px">Modele</label>
      <select name="map_model" class="form-select form-select-sm" {% if not map_make %}disabled{% endif %} onchange="this.form.map_year.value='';this.form.map_fuel.value='';this.form.submit()">
        <option value="">--</option>
        {% for m in map_models %}
        <option value="{{ m }}" {% if m == map_model %}selected{% endif %}>{{ m }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-2">
      <label class="form-label mb-1" style="font-size:13px">Annee</label>
      <select name="map_year" class="form-select form-select-sm" {% if not map_model %}disabled{% endif %} onchange="this.form.map_fuel.value='';this.form.submit()">
        <option value="">--</option>
        {% for y in map_years %}
        <option value="{{ y }}" {% if y == map_year %}selected{% endif %}>{{ y }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-2">
      <label class="form-label mb-1" style="font-size:13px">Carburant</label>
      <select name="map_fuel" class="form-select form-select-sm" {% if not map_year %}disabled{% endif %}>
        <option value="">--</option>
        {% for f in map_fuels %}
        <option value="{{ f }}" {% if f == map_fuel %}selected{% endif %}>{{ f }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-2">
      <button type="submit" class="btn btn-sm btn-primary" {% if not map_fuel %}disabled{% endif %}>
        Voir sur la carte
      </button>
    </div>
  </form>

  {% if map_json %}
  <div id="chart-europe-prices" style="height:500px"></div>
  {% elif map_make and map_model and map_year and map_fuel %}
  <p class="text-muted text-center py-4">
    Aucune donnee trouvee pour {{ map_make }} {{ map_model }} {{ map_year }} {{ map_fuel }}.
  </p>
  {% else %}
  <p class="text-muted text-center py-4">
    Selectionnez un vehicule ci-dessus pour afficher la carte des prix.
  </p>
  {% endif %}
</div>
```

**Step 2: Ajouter le JS de rendu Plotly dans le block extra_js**

Ajouter à la fin du template, dans un `{% block extra_js %}` ou juste avant `{% endblock %}` :

```html
{% if map_json %}
<script>
(function() {
  var figData = {{ map_json | safe }};
  Plotly.react("chart-europe-prices", figData.data, figData.layout, {responsive: true});
})();
</script>
{% endif %}
```

**Step 3: Lancer les tests**

Run: `python -m pytest tests/test_admin/test_admin.py::TestArgusMap -v`
Expected: PASS (les 3 tests)

**Step 4: Commit**

```bash
git add app/admin/templates/admin/argus.html
git commit -m "feat(argus): add Europe choropleth map section with vehicle filters"
```

---

### Task 4: Test manuel + vérification visuelle

**Step 1: Lancer le serveur local**

Run: `flask run` ou `python run.py`

**Step 2: Vérifier les scénarios**

1. Aller sur `/admin/argus` → la section carte apparaît en bas avec le placeholder
2. Sélectionner une marque → le dropdown modèle se peuple, la page recharge
3. Sélectionner marque + modèle + année + carburant → cliquer "Voir sur la carte"
4. La carte Europe s'affiche, colorée par prix moyen, hover fonctionnel
5. Vérifier que les filtres du tableau en haut ne sont pas cassés

**Step 3: Lancer la suite complète**

Run: `npm run verify`
Expected: ruff OK, pytest OK, vitest OK

**Step 4: Commit final si ajustements**

```bash
git add -A
git commit -m "fix(argus): polish choropleth map rendering"
```

---

### Récapitulatif

| Task | Description | Fichiers |
|------|-------------|----------|
| 1 | Tests failing pour la carte | `tests/test_admin/test_admin.py` |
| 2 | Backend : agrégation + Plotly serveur | `app/admin/routes.py` |
| 3 | Template : filtres + rendu carte | `app/admin/templates/admin/argus.html` |
| 4 | Vérification manuelle + `npm run verify` | — |
