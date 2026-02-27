# AutoScout24 + SiteExtractor Abstraction - Design

> Date : 2026-02-27
> Branche : `autoscout24`
> Statut : Approuve

---

## Contexte

Co-Pilot analyse les annonces LeBonCoin via une extension Chrome. L'objectif est d'etendre le support a AutoScout24 (tous domaines : .ch, .de, .fr, .it, .be, .nl, .at, .es) en introduisant une couche d'abstraction `SiteExtractor` qui rend l'extension multi-site.

Document de recherche prealable : `docs/autoscout24-data-analysis.md`

---

## Decisions prises

| Decision | Choix |
|----------|-------|
| Scope iteration 1 | Extraction seule (pas de collecte prix) |
| Devise | CHF tel quel (marche suisse separe) |
| Domaines | Tous les domaines AS24 (.ch, .de, .fr, .it, .be, .nl, .at, .es) |
| Bonus data | Section dediee dans le popup (hadAccident, warranty, listPrice, Google rating) |
| Parsing | RSC principal + JSON-LD fallback |
| Architecture | Approche C : abstraction SiteExtractor avec interface commune |

---

## Architecture

### Principe cle

Chaque SiteExtractor produit un payload que le backend sait deja consommer :
- **LBC** : envoie `next_data` brut -> le backend `extract_ad_data()` fait le travail (inchange)
- **AutoScout24** : le frontend extrait et normalise au format que `extract_ad_data()` retourne -> le backend le recoit comme `ad_data` pre-digere, skip l'extraction, passe direct aux filtres

### Structure fichiers

```
extension/
  extractors/
    base.js            <- Interface SiteExtractor (~50 lignes)
    leboncoin.js       <- Extraction LBC refactoree (~1400 lignes)
    autoscout24.js     <- Extraction AutoScout24 (~300 lignes)
    index.js           <- Registry : detecte le site -> bon extracteur (~30 lignes)
  content.js           <- Orchestrateur generique allege (~1000 lignes)
  build.js             <- esbuild : bundle -> dist/content.bundle.js
  dist/
    content.bundle.js  <- Fichier injecte par background.js
  background.js        <- Inchange (injecte dist/content.bundle.js)
  popup/               <- Inchange
```

### Interface SiteExtractor

```javascript
export class SiteExtractor {
  static SITE_ID = '';           // 'leboncoin' | 'autoscout24'
  static URL_PATTERNS = [];     // Regex pour detecter le site

  // Detection
  isAdPage(url) -> boolean

  // Extraction principale
  // LBC -> {type: 'raw', next_data: {...}}
  // AS24 -> {type: 'normalized', ad_data: {...format extract_ad_data()...}, extra_signals: [...]}
  async extract() -> { type, next_data?, ad_data?, extra_signals? }

  // Actions optionnelles
  async revealPhone() -> string|null
  async detectFreeReport() -> string|null
  isLoggedIn() -> boolean

  // Bonus data (affiches dans section popup dediee, pas envoyes au backend)
  getBonusSignals() -> []
}
```

### Contrat backend (`/api/analyze`)

Modification minimale -- un seul `if` dans `routes.py` :

```python
if 'ad_data' in request_json:
    # Pre-normalized (AutoScout24, La Centrale, etc.)
    data = request_json['ad_data']
    data['source'] = request_json.get('source', 'unknown')
else:
    # Legacy LBC path
    data = extract_ad_data(request_json['next_data'])
```

Les filtres ne changent pas. Ils recoivent le meme dict normalise.

---

## AutoScout24 : sources de donnees

### Source 1 : RSC Payload (principale)

Donnees vehicule embarquees dans les scripts `self.__next_f.push(...)` (React Server Components streaming Next.js). Objet vehicule complet avec : id, make, model, price, listPrice, previousPrice, mileage, firstRegistrationDate, fuelType, transmissionType, horsePower, hadAccident, inspected, directImport, warranty, seller, images, etc.

### Source 2 : JSON-LD (fallback)

Schema.org `@type: "Car"` dans `<script type="application/ld+json">`. Moins complet mais fiable : brand, model, year, price (CHF), mileage, HP, seller (AutoDealer avec rating).

### Mapping RSC -> format `extract_ad_data()`

```javascript
{
  make: rsc.make.name,                              // "AUDI"
  model: rsc.model.name,                            // "Q5"
  year_model: String(rsc.firstRegistrationYear),     // "2023"
  price_eur: rsc.price,                              // 43900 (CHF, meme champ)
  currency: "CHF",                                   // nouveau champ, ignore par filtres
  mileage_km: rsc.mileage,                          // 29299
  fuel: mapFuel(rsc.fuelType),                       // "Diesel"
  gearbox: mapGearbox(rsc.transmissionTypeGroup),    // "Automatique"
  power_din_hp: rsc.horsePower,                      // 204
  image_count: rsc.images.length,                    // 23
  owner_type: hasSellerFeatures ? "pro" : "private",
  description: rsc.teaser,
  location: { city: seller.city, region: null },
  publication_date: rsc.createdDate,                 // ISO 8601
  has_phone: !!seller.telephone,
  raw_attributes: {},                                // vide (pas d'attributs LBC)
}
```

### Bonus signals (section popup dediee)

```javascript
[
  { label: 'Accident declare',       value: 'Non',                    status: 'pass' },
  { label: 'Controle technique',     value: 'Fait',                   status: 'pass' },
  { label: 'Garantie',               value: '12 mois / 20000 km',    status: 'pass' },
  { label: 'Prix neuf catalogue',    value: '87000 CHF',              status: 'info' },
  { label: 'Decote',                 value: '-50%',                   status: 'info' },
  { label: 'Avis Google vendeur',    value: '4.7/5 (151 avis)',      status: 'pass' },
  { label: 'Import direct',          value: 'Oui',                    status: 'warning' },
]
```

---

## Manifest

### host_permissions (ajouts)

```json
"host_permissions": [
  "https://*.leboncoin.fr/*",
  "https://*.autoscout24.ch/*",
  "https://*.autoscout24.de/*",
  "https://*.autoscout24.fr/*",
  "https://*.autoscout24.it/*",
  "https://*.autoscout24.be/*",
  "https://*.autoscout24.nl/*",
  "https://*.autoscout24.at/*",
  "https://*.autoscout24.es/*",
  "http://localhost:5001/*"
]
```

### Background.js

Injecte `dist/content.bundle.js` au lieu de `content.js`.

---

## Decoupage de content.js (2660 lignes -> 3 fichiers)

| Destination | Contenu | ~Lignes |
|---|---|---|
| `extractors/leboncoin.js` | Toute l'extraction LBC : `extractNextData`, `extractVehicleFromNextData`, `extractLbcTokensFromDom`, `isStaleData`, `revealPhoneNumber`, `detectAutovizaUrl`, `isUserLoggedIn`, `isAdPage`, constantes LBC (`LBC_REGIONS`, `LBC_FUEL_CODES`, etc.), market price collection (`maybeCollectMarketPrices`, `fetchSearchPrices*`, `buildApiFilters`, `executeBonusJobs`, etc.) | ~1400 |
| `extractors/autoscout24.js` | Parsing RSC + JSON-LD, mapping fuel/gearbox, bonus signals, detection URL AS24 | ~300 |
| `content.js` (allege) | UI (popup builders, radar SVG, progress tracker), `backendFetch`, `runAnalysis` orchestrateur generique, `init` avec dispatch via registry, utilities (`escapeHTML`, `scoreColor`, etc.) | ~1000 |
| `extractors/base.js` | Classe `SiteExtractor` + helpers communs | ~50 |
| `extractors/index.js` | Registry `getExtractor(url)` | ~30 |

---

## Build (esbuild)

```javascript
// build.js
require('esbuild').buildSync({
  entryPoints: ['extension/content.js'],
  bundle: true,
  outfile: 'extension/dist/content.bundle.js',
  format: 'iife',
  target: 'chrome120',
});
```

Script npm : `"build:ext": "node extension/build.js"`

---

## Tests

- **JS (Vitest)** : tests unitaires pour chaque extracteur
  - `autoscout24.test.js` : parsing RSC, JSON-LD fallback, fuel mapping, bonus signals
  - `leboncoin.test.js` : tests existants migres
  - `registry.test.js` : detection de site
- **Python (pytest)** : test `POST /api/analyze` avec `ad_data` pre-normalise (bypass `extract_ad_data`)
- Tests existants LBC : inchanges (meme format)

---

## Hors scope iteration 1 (iteration 2 future)

- Collecte prix marche AutoScout24
- Conversion CHF -> EUR
- Email vendeur AS24
- YouTube AS24
- `maybeCollectMarketPrices` skip si `source !== 'leboncoin'`

---

## URLs de reference

- Annonce : `https://www.autoscout24.ch/fr/d/{slug}-{listing_id}`
- Listing : `https://www.autoscout24.ch/fr?makeModelVersions[0][makeKey]=audi&...`
- Detection regex : `/autoscout24\.\w+\/\w+\/d\/.+-(\d+)$/`
- Domaines : `.ch`, `.de`, `.fr`, `.it`, `.be`, `.nl`, `.at`, `.es`
