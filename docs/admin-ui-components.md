# Composants UI Admin — Guide de reutilisation

Reference des patterns UI du dashboard admin Vehicore.
Framework : **Bootstrap 5.3.3** + CSS inline dans `{% block extra_css %}`.

---

## 1. Layout (base.html)

```
+--sidebar (col-md-2)--+--content-area (col-md-10)--+
|  .sidebar             |  .content-area              |
|  bg: #1e293b          |  padding: 24px              |
|  min-height: 100vh    |  flash messages             |
|  nav-link + active    |  {% block content %}        |
+-----------------------+-----------------------------+
```

Responsive : sidebar `d-none d-md-block`, contenu `col-12 col-md-10`.

---

## 2. Stat Cards

Le composant le plus reutilise (50+ instances sur 19 templates).

```html
<div class="stat-card">
  <div class="stat-value" style="color: #22c55e">42</div>
  <div class="stat-label">Label descriptif</div>
</div>
```

```css
.stat-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.stat-value { font-size: 32px; font-weight: 800; color: #1e293b; }
.stat-label { font-size: 13px; color: #64748b; margin-top: 4px; }
```

**Couleurs valeur** : `#22c55e` (succes), `#ef4444` (danger), `#f59e0b` (warning), `#3b82f6` (primary), `#8b5cf6` (violet)

**Utilise dans** : dashboard, filters, car, argus, youtube, email, llm, failed_searches

---

## 3. KPI Grid (variante avancee)

Grille 6 colonnes avec icone en filigrane. Utilise dans failed_searches.

```html
<div class="kpi-grid">
  <div class="kpi-card">
    <span class="kpi-icon">&#128269;</span>
    <div class="kpi-value" style="color: #ef4444">12</div>
    <div class="kpi-label">CRITIQUES</div>
    <div class="kpi-sub">details optionnels</div>
  </div>
</div>
```

```css
.kpi-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
.kpi-card { background: #fff; border-radius: 10px; padding: 16px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); position: relative; }
.kpi-icon { position: absolute; top: 12px; right: 14px; font-size: 20px; opacity: 0.15; }
.kpi-value { font-size: 28px; font-weight: 800; }
.kpi-label { font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
.kpi-sub { font-size: 11px; color: #94a3b8; margin-top: 4px; }
@media (max-width: 992px) { .kpi-grid { grid-template-columns: repeat(3, 1fr); } }
```

---

## 4. Tables paginables

```html
<div class="table-responsive">
  <table class="table table-sm table-hover mb-0">
    <thead><tr><th>Col 1</th><th>Col 2</th></tr></thead>
    <tbody>
      <tr><td>data</td><td>data</td></tr>
    </tbody>
  </table>
</div>

<!-- Pagination -->
<nav class="mt-3">
  <ul class="pagination pagination-sm justify-content-center mb-0">
    {% for p in range(1, total_pages + 1) %}
    <li class="page-item {% if p == page %}active{% endif %}">
      <a class="page-link" href="?page={{ p }}">{{ p }}</a>
    </li>
    {% endfor %}
  </ul>
</nav>
```

**Variantes** : `table-striped`, `table-light` (thead), texte tronque (`max-width + text-overflow: ellipsis`)

---

## 5. Badges

### Bootstrap standard
```html
<span class="badge bg-success">pass</span>
<span class="badge bg-warning text-dark">warning</span>
<span class="badge bg-danger">fail</span>
<span class="badge bg-secondary">skip</span>
<span class="badge bg-primary">info</span>
<span class="badge bg-info">special</span>
```

### Custom (a definir dans extra_css)
| Classe | Background | Usage |
|--------|-----------|-------|
| `.badge-real` | #22c55e | Filtre operationnel |
| `.badge-simulated` | #8b5cf6 | Donnees simulees |
| `.badge-planned` | #d1d5db | Filtre prevu |
| `.badge-draft` | #f59e0b | Email brouillon |
| `.badge-approved` | #22c55e | Email approuve |
| `.badge-archived` | #64748b | Archive |
| `.badge-extracted` | #22c55e | YouTube transcript OK |
| `.badge-pending` | #f59e0b | En attente |
| `.badge-error` | #ef4444 | Erreur |

### Severity dots (failed_searches)
```html
<span class="severity-dot severity-critical"></span>
```
`.severity-critical` #ef4444, `.severity-high` #f97316, `.severity-medium` #eab308, `.severity-low` #22c55e

### Occurrence badges
```html
<span class="occ-badge occ-5">5</span>
```
`.occ-1` gris, `.occ-2` jaune, `.occ-3` orange, `.occ-5` rouge

---

## 6. Charts (Plotly 2.35.2)

CDN : `https://cdn.plot.ly/plotly-2.35.2.min.js`

### Options communes
```javascript
Plotly.newPlot('chart-id', traces, {
  margin: { t: 10, r: 20, b: 40, l: 40 },
  plot_bgcolor: 'transparent',
  paper_bgcolor: 'transparent',
}, { responsive: true, displayModeBar: false });
```

### Types utilises
| Type | Usage | Couleurs |
|------|-------|----------|
| Bar vertical | Scans/jour (30j) | #3b82f6 |
| Bar horizontal | Top marques | #3b82f6 |
| Histogramme | Distribution scores | #22c55e |
| Stacked bar | Filtres pass/warn/fail/skip | #22c55e / #f59e0b / #ef4444 / #9ca3af |
| Line + markers | Tendances 30j | Par severite |

---

## 7. Onglets / Tabs

### Bootstrap nav-tabs (issues.html)
```html
<ul class="nav nav-tabs mb-4">
  <li class="nav-item">
    <a class="nav-link {% if site == 'lbc' %}active{% endif %}" href="...">LeBonCoin</a>
  </li>
  <li class="nav-item">
    <a class="nav-link {% if site == 'as24' %}active{% endif %}" href="...">AutoScout24</a>
  </li>
</ul>
```

### Custom status-tabs (failed_searches.html)
```css
.status-tabs { display: flex; border-bottom: 2px solid #e2e8f0; }
.status-tab { padding: 8px 16px; font-size: 13px; font-weight: 600; color: #64748b; border-bottom: 2px solid transparent; }
.status-tab.active { color: #1e293b; border-bottom-color: #3b82f6; }
.tab-count { background: #e2e8f0; border-radius: 10px; padding: 1px 7px; font-size: 11px; }
.status-tab.active .tab-count { background: #3b82f6; color: #fff; }
```

---

## 8. Modals (Bootstrap)

```html
<div class="modal fade" id="myModal" tabindex="-1">
  <div class="modal-dialog modal-lg">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Titre</h5>
        <button class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body"><!-- contenu --></div>
      <div class="modal-footer">
        <button class="btn btn-sm btn-secondary" data-bs-dismiss="modal">Fermer</button>
      </div>
    </div>
  </div>
</div>
```

---

## 9. Formulaires / Filtres

```html
<form method="GET" class="filter-bar">
  <select name="status" class="form-select form-select-sm" style="width:120px" onchange="this.form.submit()">
    <option value="">Tous</option>
    <option value="new" {% if status_filter == 'new' %}selected{% endif %}>Nouveau</option>
  </select>
  <input type="text" name="search" class="form-control form-control-sm" style="width:200px" placeholder="Rechercher...">
</form>
```

```css
.filter-bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 12px 0; }
```

---

## 10. Bulk Action Bar

Barre sticky en bas de page pour actions groupees (failed_searches).

```css
.bulk-bar { display: none; position: sticky; bottom: 0; background: #1e293b; color: #fff; padding: 10px 20px; border-radius: 8px 8px 0 0; z-index: 100; }
.bulk-bar.show { display: flex; align-items: center; gap: 12px; }
```

---

## 11. Sections pliables (Collapse)

```html
<a class="btn btn-sm btn-outline-secondary" data-bs-toggle="collapse" href="#section1">+ Afficher</a>
<div class="collapse" id="section1">
  <!-- contenu masque par defaut -->
</div>
```

---

## 12. Formatage donnees (Jinja)

| Pattern | Exemple | Resultat |
|---------|---------|----------|
| Milliers | `"{:,}".format(n).replace(",", " ")` | `12 345` |
| Date courte | `\|localdatetime('%d/%m/%Y')` | `02/03/2026` |
| Date + heure | `\|localdatetime('%d/%m %H:%M:%S')` | `02/03 14:30:15` |
| Troncature | `style="max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"` | `Peugeot 308 SW...` |
| Etoiles | `{{ '\u2605' * n }}{{ '\u2606' * (5-n) }}` | `★★★☆☆` |

---

## Palette de couleurs

| Token | Hex | Usage |
|-------|-----|-------|
| success | `#22c55e` | pass, ok, vert |
| warning | `#f59e0b` | warning, attention |
| danger | `#ef4444` | fail, erreur, critique |
| primary | `#3b82f6` | liens, actions, selection |
| secondary | `#6b7280` | texte secondaire |
| muted | `#9ca3af` | skip, inactif |
| info | `#06b6d4` | info cyan |
| violet | `#8b5cf6` | simule, special |
| dark | `#1e293b` | sidebar, texte principal |
| subtle | `#64748b` | labels, sous-texte |
| bg-light | `#f8f9fa` | fonds clairs |
| border | `#e5e7eb` | bordures, separateurs |

---

## Fichiers de reference

| Fichier | Role |
|---------|------|
| `app/admin/templates/admin/base.html` | Layout + sidebar + flash messages |
| `app/admin/templates/admin/dashboard.html` | Stat cards + Plotly charts + tables |
| `app/admin/templates/admin/failed_searches.html` | KPI grid + status tabs + bulk bar |
| `app/admin/templates/admin/filters.html` | Filter cards + maturity bars |
| `app/admin/templates/admin/argus.html` | Tables complexes + modals |
| `app/admin/templates/admin/llm.html` | Config cards + collapse forms |
| `app/admin/routes.py` | Routes + donnees passees aux templates |
