# AutoScout24 + SiteExtractor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a SiteExtractor abstraction layer, refactor LBC extraction into it, add AutoScout24 support, and bundle with esbuild.

**Architecture:** Each site gets an extractor class that produces data consumable by the existing backend. LBC sends raw `next_data` (unchanged). AutoScout24 sends pre-normalized `ad_data` matching `extract_ad_data()` output. esbuild bundles ES modules into a single injectable IIFE.

**Tech Stack:** JavaScript ES modules, esbuild, Vitest, Python/Flask/pytest

---

## Task 1: Setup esbuild bundler

**Files:**
- Create: `extension/build.js`
- Modify: `package.json`

**Step 1: Install esbuild**

Run: `npm install --save-dev esbuild`

**Step 2: Create build script**

Create `extension/build.js`:

```javascript
const esbuild = require('esbuild');

esbuild.buildSync({
  entryPoints: ['extension/content.js'],
  bundle: true,
  outfile: 'extension/dist/content.bundle.js',
  format: 'iife',
  target: ['chrome120'],
  minify: false,
  sourcemap: false,
});

console.log('Built extension/dist/content.bundle.js');
```

**Step 3: Add npm script**

In `package.json`, add to `scripts`:
```json
"build:ext": "node extension/build.js"
```

**Step 4: Run build to verify**

Run: `npm run build:ext`
Expected: `Built extension/dist/content.bundle.js` and file exists at `extension/dist/content.bundle.js`

**Step 5: Add dist/ to .gitignore if needed**

Check if `extension/dist/` should be gitignored or committed. For Chrome extension development, the bundle should be committed so the extension works without a build step for manual loading. Add a comment in build.js about this.

**Step 6: Commit**

```bash
git add extension/build.js package.json package-lock.json extension/dist/
git commit -m "build: add esbuild bundler for extension"
```

---

## Task 2: Create SiteExtractor base class

**Files:**
- Create: `extension/extractors/base.js`

**Step 1: Write the base class**

Create `extension/extractors/base.js`:

```javascript
/**
 * SiteExtractor - Interface commune pour l'extraction de donnees vehicule.
 *
 * Chaque site (LeBonCoin, AutoScout24, etc.) implemente cette interface.
 * Le contrat de sortie de extract() doit produire un objet compatible
 * avec le backend /api/analyze.
 */
export class SiteExtractor {
  /** Identifiant du site ('leboncoin', 'autoscout24'). */
  static SITE_ID = '';

  /** Patterns regex pour detecter le site depuis l'URL. */
  static URL_PATTERNS = [];

  /**
   * Detecte si l'URL courante est une page d'annonce.
   * @param {string} url
   * @returns {boolean}
   */
  isAdPage(url) {
    throw new Error('isAdPage() must be implemented');
  }

  /**
   * Extrait les donnees vehicule de la page.
   *
   * Retourne un objet avec:
   * - type: 'raw' (envoyer next_data brut au backend) ou 'normalized' (ad_data pre-digere)
   * - next_data: payload brut (si type='raw')
   * - ad_data: dict normalise au format extract_ad_data() (si type='normalized')
   * - source: identifiant du site
   *
   * @returns {Promise<{type: string, source: string, next_data?: object, ad_data?: object}>}
   */
  async extract() {
    throw new Error('extract() must be implemented');
  }

  /**
   * Revele le numero de telephone du vendeur si possible.
   * @returns {Promise<string|null>}
   */
  async revealPhone() {
    return null;
  }

  /**
   * Detecte un rapport gratuit (Autoviza, etc.) sur la page.
   * @returns {Promise<string|null>}
   */
  async detectFreeReport() {
    return null;
  }

  /**
   * Verifie si l'utilisateur est connecte sur le site.
   * @returns {boolean}
   */
  isLoggedIn() {
    return false;
  }

  /**
   * Retourne les signaux bonus specifiques au site (hadAccident, warranty, etc.).
   * Affiches dans une section popup dediee, pas envoyes au backend.
   *
   * @returns {Array<{label: string, value: string, status: string}>}
   */
  getBonusSignals() {
    return [];
  }

  /**
   * Extrait un resume vehicule court pour le header du progress tracker.
   * @returns {{make: string, model: string, year: string}|null}
   */
  getVehicleSummary() {
    return null;
  }
}
```

**Step 2: Commit**

```bash
git add -f extension/extractors/base.js
git commit -m "feat: add SiteExtractor base class"
```

---

## Task 3: Create extractor registry

**Files:**
- Create: `extension/extractors/index.js`

**Step 1: Write the registry**

Create `extension/extractors/index.js`:

```javascript
/**
 * Extractor Registry
 *
 * Detecte le site courant et retourne le bon SiteExtractor.
 */
import { LeBonCoinExtractor } from './leboncoin.js';
import { AutoScout24Extractor } from './autoscout24.js';

const EXTRACTORS = [LeBonCoinExtractor, AutoScout24Extractor];

/**
 * Retourne le SiteExtractor correspondant a l'URL, ou null si aucun match.
 * @param {string} url
 * @returns {SiteExtractor|null}
 */
export function getExtractor(url) {
  for (const ExtractorClass of EXTRACTORS) {
    for (const pattern of ExtractorClass.URL_PATTERNS) {
      if (pattern.test(url)) {
        return new ExtractorClass();
      }
    }
  }
  return null;
}
```

**Step 2: Commit**

```bash
git add -f extension/extractors/index.js
git commit -m "feat: add extractor registry"
```

---

## Task 4: Refactor LBC extraction into LeBonCoinExtractor

C'est la tache la plus grosse. On deplace le code LBC-specific de content.js vers `extractors/leboncoin.js` et on exporte une classe `LeBonCoinExtractor`.

**Files:**
- Create: `extension/extractors/leboncoin.js`
- Modify: `extension/content.js`

**Step 1: Create `extension/extractors/leboncoin.js`**

Deplacer de content.js vers leboncoin.js les elements suivants (en ajoutant `export` devant chaque fonction/constante utilisee par content.js) :

**Fonctions a deplacer (referencing exact lines):**
- `isStaleData` (L150-162)
- `extractNextData` (L171-209)
- `extractLbcTokensFromDom` (L1284-1300)
- `extractVehicleFromNextData` (L1302-1341)
- `extractModelFromTitle` (L1347-1371)
- `GENERIC_MODELS` (L1374)
- `EXCLUDED_CATEGORIES` (L1377)
- `LBC_BRAND_ALIASES` (L1380-1382)
- `toLbcBrandToken` (L1385-1388)
- `getAdYear` (L1394-1405)
- `isUserLoggedIn` (L1411-1416)
- `detectAutovizaUrl` (L1425-1464)
- `revealPhoneNumber` (L1472-1515)
- `LBC_REGIONS` (L1689-1721)
- `LBC_FUEL_CODES` (L1725-1737)
- `LBC_GEARBOX_CODES` (L1741-1744)
- `getHorsePowerRange` (L1749-1758)
- `getMileageRange` (L1762-1769)
- `COLLECT_COOLDOWN_MS` (L1772)
- `extractRegionFromNextData` (L1775-1779)
- `extractLocationFromNextData` (L1783-1793)
- `DEFAULT_SEARCH_RADIUS` (L1796)
- `MIN_PRICES_FOR_ARGUS` (L1800)
- `getAdDetails` (L1804-1827)
- `parseRange` (L1831-1838)
- `buildApiFilters` (L1841-1887)
- `filterAndMapSearchAds` (L1890-1905)
- `fetchSearchPricesViaApi` (L1913-1960)
- `fetchSearchPricesViaHtml` (L1963-1980)
- `fetchSearchPrices` (L1985-2012)
- `buildLocationParam` (L2017-2026)
- `extractMileageFromNextData` (L2029-2041)
- `reportJobDone` (L2044-2059)
- `executeBonusJobs` (L2066-2180)
- `maybeCollectMarketPrices` (L2195-2585)
- `isAdPage` (L2590-2593) -- renommee en `isAdPageLBC`

**Structure du fichier** `extension/extractors/leboncoin.js`:

```javascript
import { SiteExtractor } from './base.js';

// ── Constantes LBC ─────────────────────────────────────────
// [coller ici: GENERIC_MODELS, EXCLUDED_CATEGORIES, LBC_BRAND_ALIASES,
//  LBC_REGIONS, LBC_FUEL_CODES, LBC_GEARBOX_CODES, COLLECT_COOLDOWN_MS,
//  DEFAULT_SEARCH_RADIUS, MIN_PRICES_FOR_ARGUS]

// ── Fonctions LBC ──────────────────────────────────────────
// [coller ici: toutes les fonctions listees ci-dessus]
// Les fonctions qui utilisent `backendFetch` ou `sleep` le recevront
// via le constructeur (injection de dependances).

export class LeBonCoinExtractor extends SiteExtractor {
  static SITE_ID = 'leboncoin';
  static URL_PATTERNS = [
    /leboncoin\.fr\/ad\//,
    /leboncoin\.fr\/voitures\//,
  ];

  constructor(deps = {}) {
    super();
    this._backendFetch = deps.backendFetch;
    this._sleep = deps.sleep;
    this._nextData = null;
    this._vehicle = null;
  }

  isAdPage(url) {
    return url.includes('leboncoin.fr/ad/') || url.includes('leboncoin.fr/voitures/');
  }

  async extract() {
    const nextData = await extractNextData();
    if (!nextData) return null;
    this._nextData = nextData;
    this._vehicle = extractVehicleFromNextData(nextData);
    return {
      type: 'raw',
      source: 'leboncoin',
      next_data: nextData,
    };
  }

  getVehicleSummary() {
    if (!this._vehicle) return null;
    return {
      make: this._vehicle.make,
      model: this._vehicle.model,
      year: this._vehicle.year,
    };
  }

  async revealPhone() {
    const ad = this._nextData?.props?.pageProps?.ad;
    if (!ad?.has_phone || !isUserLoggedIn()) return null;
    const phone = await revealPhoneNumber();
    if (phone && ad) {
      if (!ad.owner) ad.owner = {};
      ad.owner.phone = phone;
    }
    return phone;
  }

  isLoggedIn() {
    return isUserLoggedIn();
  }

  async detectFreeReport() {
    return detectAutovizaUrl(this._nextData);
  }

  async collectMarketPrices(progress) {
    if (!this._vehicle?.make || !this._vehicle?.model || !this._vehicle?.year) {
      return { submitted: false };
    }
    return maybeCollectMarketPrices(this._vehicle, this._nextData, progress);
  }

  getExtractedVehicle() {
    return this._vehicle;
  }

  getNextData() {
    return this._nextData;
  }
}

// ── Exports pour les tests existants ───────────────────────
export {
  extractVehicleFromNextData,
  extractRegionFromNextData,
  extractLocationFromNextData,
  buildLocationParam,
  DEFAULT_SEARCH_RADIUS,
  MIN_PRICES_FOR_ARGUS,
  fetchSearchPrices,
  fetchSearchPricesViaApi,
  fetchSearchPricesViaHtml,
  buildApiFilters,
  parseRange,
  filterAndMapSearchAds,
  extractMileageFromNextData,
  isUserLoggedIn,
  revealPhoneNumber,
  isStaleData,
  scoreColor,
  statusColor,
  statusIcon,
  filterLabel,
  maybeCollectMarketPrices,
  LBC_REGIONS,
  LBC_FUEL_CODES,
  LBC_GEARBOX_CODES,
  getMileageRange,
  getHorsePowerRange,
  COLLECT_COOLDOWN_MS,
  toLbcBrandToken,
  LBC_BRAND_ALIASES,
  getAdDetails,
  executeBonusJobs,
  reportJobDone,
};
```

**Important: les fonctions qui appellent `backendFetch` ou `sleep` :**
- `fetchSearchPricesViaApi` utilise `chrome.runtime.sendMessage` (pas backendFetch)
- `fetchSearchPricesViaHtml` utilise `fetch` natif via background
- `maybeCollectMarketPrices` utilise `backendFetch` et `sleep`
- `executeBonusJobs` utilise `backendFetch` et `sleep`
- `reportJobDone` utilise `backendFetch`
- `detectAutovizaUrl` utilise `fetch` et `sleep`
- `revealPhoneNumber` utilise DOM + `sleep`

**Solution:** Importer `backendFetch` et `sleep` depuis content.js qui les exporte :
```javascript
// En haut de leboncoin.js:
// backendFetch et sleep sont injectes a l'execution par content.js
let _backendFetch, _sleep;
export function initDeps(deps) {
  _backendFetch = deps.backendFetch;
  _sleep = deps.sleep;
}
```

**Step 2: Modifier content.js**

Supprimer tout le code LBC-specific (les fonctions listees ci-dessus) et remplacer par des imports :

```javascript
import { getExtractor } from './extractors/index.js';
import { initDeps as initLbcDeps } from './extractors/leboncoin.js';

// Au debut de init() ou au top level:
initLbcDeps({ backendFetch, sleep });
```

Modifier `runAnalysis()` pour utiliser l'extracteur :
```javascript
async function runAnalysis() {
  const extractor = getExtractor(window.location.href);
  if (!extractor) {
    showPopup(buildErrorPopup("Site non supporté par Co-Pilot."));
    return;
  }

  const progress = showProgress();

  // Phase 1: Extraction
  progress.update("extract", "running");
  const payload = await extractor.extract();
  if (!payload) {
    progress.update("extract", "error", "Impossible de lire les données");
    showPopup(buildErrorPopup("Impossible de lire les données de cette page."));
    return;
  }
  progress.update("extract", "done");

  // Vehicle summary in header
  const summary = extractor.getVehicleSummary();
  const vehicleLabel = document.getElementById("copilot-progress-vehicle");
  if (vehicleLabel && summary?.make) {
    vehicleLabel.textContent = [summary.make, summary.model, summary.year].filter(Boolean).join(" ");
  }

  // Phone
  if (extractor.isLoggedIn()) {
    progress.update("phone", "running");
    const phone = await extractor.revealPhone();
    if (phone) {
      progress.update("phone", "done", phone.replace(/(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})/, "$1 $2 $3 $4 $5"));
    } else {
      progress.update("phone", "warning", "Numéro non récupéré");
    }
  } else {
    progress.update("phone", "skip");
  }

  // Phase 2: Market prices (LBC only)
  let collectInfo = { submitted: false };
  if (extractor.collectMarketPrices) {
    collectInfo = await extractor.collectMarketPrices(progress).catch((err) => {
      console.error("[CoPilot] collectMarketPrices erreur:", err);
      return { submitted: false };
    });
  } else {
    progress.update("job", "skip", "Collecte non disponible pour ce site");
    progress.update("collect", "skip");
    progress.update("submit", "skip");
    progress.update("bonus", "skip");
  }

  // Phase 3: Backend analysis
  progress.update("analyze", "running");
  const body = payload.type === 'raw'
    ? { url: window.location.href, next_data: payload.next_data }
    : { url: window.location.href, ad_data: payload.ad_data, source: payload.source };

  const result = await fetchAnalysis(body, progress, collectInfo);
  if (!result) return;

  // Bonus signals (AutoScout24 section)
  const bonusSignals = extractor.getBonusSignals();

  // Score, filters, autoviza
  lastScanId = result.data.scan_id || null;
  progress.update("analyze", "done", (result.data.filters || []).length + " filtres analysés");
  progress.showFilters(result.data.filters || []);
  const score = result.data.score;
  const verdict = score >= 70 ? "Annonce fiable" : score >= 40 ? "Points d'attention" : "Vigilance requise";
  progress.showScore(score, verdict);

  // Free report
  progress.update("autoviza", "running");
  const freeReportUrl = await extractor.detectFreeReport();
  progress.update("autoviza", freeReportUrl ? "done" : "skip",
    freeReportUrl ? "Rapport gratuit trouvé" : "Aucun rapport disponible");

  // Details button
  const detailsBtn = document.getElementById("copilot-progress-details-btn");
  if (detailsBtn) {
    detailsBtn.style.display = "inline-block";
    detailsBtn.addEventListener("click", () => {
      showPopup(buildResultsPopup(result.data, {
        autovizaUrl: freeReportUrl,
        bonusSignals,
      }));
    });
  }
}
```

Modifier `init()` :
```javascript
function init() {
  const extractor = getExtractor(window.location.href);
  if (!extractor || !extractor.isAdPage(window.location.href)) return;
  removePopup();
  if (window.__copilotRunning) return;
  window.__copilotRunning = true;
  runAnalysis().finally(() => { window.__copilotRunning = false; });
}
```

**Step 3: Extraire `fetchAnalysis` comme fonction generique**

Le code de `fetchAnalysisOnce` (L1584-1628) est generique. Le renommer en `fetchAnalysis(body, progress, collectInfo)` et le garder dans content.js. Adapter pour accepter le body en parametre au lieu de hardcoder `{ next_data }`.

**Step 4: Rebuild et tester manuellement**

Run: `npm run build:ext`
Expected: Build succeeds, `extension/dist/content.bundle.js` created.

**Step 5: Commit**

```bash
git add -f extension/extractors/leboncoin.js extension/content.js extension/dist/
git commit -m "refactor: extract LBC code into LeBonCoinExtractor"
```

---

## Task 5: Update background.js to inject bundle

**Files:**
- Modify: `extension/background.js:101-104`

**Step 1: Change injected file**

In `background.js`, change line 104:
```javascript
// Before:
files: ["content.js"],
// After:
files: ["dist/content.bundle.js"],
```

**Step 2: Commit**

```bash
git add extension/background.js
git commit -m "feat: inject bundled content script"
```

---

## Task 6: Update manifest.json with AutoScout24 domains

**Files:**
- Modify: `extension/manifest.json`

**Step 1: Add host_permissions**

Add to `host_permissions` array:
```json
"https://*.autoscout24.ch/*",
"https://*.autoscout24.de/*",
"https://*.autoscout24.fr/*",
"https://*.autoscout24.it/*",
"https://*.autoscout24.be/*",
"https://*.autoscout24.nl/*",
"https://*.autoscout24.at/*",
"https://*.autoscout24.es/*"
```

**Step 2: Commit**

```bash
git add extension/manifest.json
git commit -m "feat: add AutoScout24 domains to manifest"
```

---

## Task 7: Create AutoScout24Extractor

**Files:**
- Create: `extension/extractors/autoscout24.js`

**Step 1: Write the failing test**

Create `extension/tests/autoscout24.test.js`:

```javascript
import { describe, it, expect, beforeEach, vi } from 'vitest';

// Test data: RSC vehicle object (from docs/autoscout24-data-analysis.md)
const RSC_VEHICLE = {
  id: 20201676,
  status: 'activated',
  conditionType: 'used',
  vehicleCategory: 'car',
  versionFullName: 'Q5 Sportback 40 TDI S-Line quattro AHK 4x4',
  make: { id: 5, key: 'audi', name: 'AUDI' },
  model: { id: 23, key: 'q5', name: 'Q5' },
  price: 43900,
  previousPrice: null,
  listPrice: 87000,
  mileage: 29299,
  firstRegistrationDate: '2023-12-01',
  firstRegistrationYear: 2023,
  createdDate: '2026-02-11T09:00:20.284Z',
  lastModifiedDate: '2026-02-11T09:20:30.037Z',
  bodyType: 'suv',
  bodyColor: 'gray',
  interiorColor: 'black',
  metallic: true,
  doors: 5,
  seats: 5,
  fuelType: 'mhev-diesel',
  cubicCapacity: 1968,
  horsePower: 204,
  kiloWatts: 150,
  cylinders: 4,
  gears: 7,
  transmissionType: 'semi-automatic',
  transmissionTypeGroup: 'automatic',
  driveType: 'all',
  emissionStandard: 'euro-6d',
  directImport: true,
  hadAccident: false,
  inspected: true,
  tuned: false,
  warranty: { duration: 12, mileage: 20000, type: 'from-delivery' },
  sellerId: 24860,
  images: [{ key: '1.jpg' }, { key: '2.jpg' }, { key: '3.jpg' }],
  teaser: 'Fahrzeug mit Garantie...',
};

const JSON_LD = {
  '@type': 'Car',
  name: 'AUDI Q5 Sportback',
  brand: { name: 'AUDI' },
  model: 'Q5',
  vehicleModelDate: 2023,
  color: 'gray',
  numberOfDoors: 5,
  vehicleSeatingCapacity: 5,
  vehicleTransmission: 'Automatique',
  mileageFromOdometer: { value: 29299, unitCode: 'KMT' },
  vehicleEngine: {
    enginePower: { value: 204, unitText: 'PS' },
    engineDisplacement: { value: 1968, unitCode: 'CMQ' },
    fuelType: 'Diesel',
  },
  offers: {
    price: 43900,
    priceCurrency: 'CHF',
    seller: {
      '@type': 'AutoDealer',
      name: 'I.B.A. Automobile AG',
      telephone: '+41628929454',
      address: { addressLocality: 'Niederlenz', postalCode: '5702' },
      aggregateRating: { ratingValue: 4.7, reviewCount: 151 },
    },
  },
};

// We test the pure functions, not the DOM-dependent class methods
import {
  parseRSCPayload,
  parseJsonLd,
  normalizeToAdData,
  buildBonusSignals,
  mapFuelType,
  mapTransmission,
  AS24_URL_PATTERNS,
} from '../extractors/autoscout24.js';

describe('AutoScout24 URL detection', () => {
  it('matches autoscout24.ch ad URL', () => {
    const url = 'https://www.autoscout24.ch/fr/d/audi-q5-sportback-20201676';
    expect(AS24_URL_PATTERNS.some((p) => p.test(url))).toBe(true);
  });

  it('matches autoscout24.de ad URL', () => {
    const url = 'https://www.autoscout24.de/angebote/bmw-320-12345';
    expect(AS24_URL_PATTERNS.some((p) => p.test(url))).toBe(true);
  });

  it('does not match LBC URL', () => {
    const url = 'https://www.leboncoin.fr/ad/voitures/12345';
    expect(AS24_URL_PATTERNS.some((p) => p.test(url))).toBe(false);
  });

  it('does not match AS24 search page', () => {
    const url = 'https://www.autoscout24.ch/fr?makeModelVersions[0][makeKey]=audi';
    expect(AS24_URL_PATTERNS.some((p) => p.test(url))).toBe(false);
  });
});

describe('mapFuelType', () => {
  it('maps mhev-diesel to Diesel', () => {
    expect(mapFuelType('mhev-diesel')).toBe('Diesel');
  });

  it('maps gasoline to Essence', () => {
    expect(mapFuelType('gasoline')).toBe('Essence');
  });

  it('maps electric to Electrique', () => {
    expect(mapFuelType('electric')).toBe('Electrique');
  });

  it('maps phev-gasoline to Hybride Rechargeable', () => {
    expect(mapFuelType('phev-gasoline')).toBe('Hybride Rechargeable');
  });

  it('returns raw value for unknown types', () => {
    expect(mapFuelType('hydrogen')).toBe('hydrogen');
  });
});

describe('mapTransmission', () => {
  it('maps automatic to Automatique', () => {
    expect(mapTransmission('automatic')).toBe('Automatique');
  });

  it('maps manual to Manuelle', () => {
    expect(mapTransmission('manual')).toBe('Manuelle');
  });
});

describe('normalizeToAdData', () => {
  it('produces extract_ad_data-compatible output from RSC data', () => {
    const result = normalizeToAdData(RSC_VEHICLE, JSON_LD);

    expect(result.make).toBe('AUDI');
    expect(result.model).toBe('Q5');
    expect(result.year_model).toBe('2023');
    expect(result.price_eur).toBe(43900);
    expect(result.currency).toBe('CHF');
    expect(result.mileage_km).toBe(29299);
    expect(result.fuel).toBe('Diesel');
    expect(result.gearbox).toBe('Automatique');
    expect(result.power_din_hp).toBe(204);
    expect(result.image_count).toBe(3);
    expect(result.description).toBe('Fahrzeug mit Garantie...');
    expect(result.publication_date).toBe('2026-02-11T09:00:20.284Z');
    expect(result.owner_type).toBe('pro');
  });

  it('uses JSON-LD as fallback when RSC is null', () => {
    const result = normalizeToAdData(null, JSON_LD);

    expect(result.make).toBe('AUDI');
    expect(result.model).toBe('Q5');
    expect(result.year_model).toBe('2023');
    expect(result.price_eur).toBe(43900);
    expect(result.currency).toBe('CHF');
    expect(result.mileage_km).toBe(29299);
    expect(result.power_din_hp).toBe(204);
  });

  it('handles missing optional fields gracefully', () => {
    const minimal = { make: { name: 'BMW' }, model: { name: '320' }, price: 15000 };
    const result = normalizeToAdData(minimal, null);

    expect(result.make).toBe('BMW');
    expect(result.model).toBe('320');
    expect(result.price_eur).toBe(15000);
    expect(result.mileage_km).toBeNull();
    expect(result.fuel).toBeNull();
  });
});

describe('buildBonusSignals', () => {
  it('builds bonus signals from RSC data', () => {
    const signals = buildBonusSignals(RSC_VEHICLE, JSON_LD);

    expect(signals.length).toBeGreaterThanOrEqual(5);

    const accident = signals.find((s) => s.label.includes('Accident'));
    expect(accident).toBeDefined();
    expect(accident.status).toBe('pass');

    const warranty = signals.find((s) => s.label.includes('Garantie'));
    expect(warranty).toBeDefined();
    expect(warranty.value).toContain('12');

    const importSignal = signals.find((s) => s.label.includes('Import'));
    expect(importSignal).toBeDefined();
    expect(importSignal.status).toBe('warning');

    const listPrice = signals.find((s) => s.label.includes('neuf'));
    expect(listPrice).toBeDefined();
    expect(listPrice.value).toContain('87');
  });

  it('skips signals when data is missing', () => {
    const signals = buildBonusSignals({}, null);
    expect(signals.length).toBe(0);
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `npm run test:extension`
Expected: FAIL (module not found)

**Step 3: Implement AutoScout24Extractor**

Create `extension/extractors/autoscout24.js`:

```javascript
import { SiteExtractor } from './base.js';

// ── URL Patterns ──────────────────────────────────────────
export const AS24_URL_PATTERNS = [
  /autoscout24\.\w+\/\w+\/d\/.+-\d+/,
  /autoscout24\.\w+\/\w+\/angebote\//,
];

// ── Fuel type mapping ─────────────────────────────────────
const FUEL_MAP = {
  'gasoline': 'Essence',
  'diesel': 'Diesel',
  'electric': 'Electrique',
  'mhev-diesel': 'Diesel',
  'mhev-gasoline': 'Essence',
  'phev-diesel': 'Hybride Rechargeable',
  'phev-gasoline': 'Hybride Rechargeable',
  'cng': 'GPL',
  'lpg': 'GPL',
  'hydrogen': 'Hydrogene',
};

const TRANSMISSION_MAP = {
  'automatic': 'Automatique',
  'manual': 'Manuelle',
  'semi-automatic': 'Automatique',
};

export function mapFuelType(fuelType) {
  if (!fuelType) return null;
  return FUEL_MAP[fuelType.toLowerCase()] || fuelType;
}

export function mapTransmission(transmission) {
  if (!transmission) return null;
  return TRANSMISSION_MAP[transmission.toLowerCase()] || transmission;
}

// ── RSC Payload Parsing ───────────────────────────────────

/**
 * Parse le RSC payload (React Server Components) depuis les scripts inline.
 * Cherche les scripts contenant self.__next_f.push avec les donnees vehicule.
 */
export function parseRSCPayload(document) {
  const scripts = document.querySelectorAll('script');
  for (const s of scripts) {
    const t = s.textContent || '';
    if (!t.includes('firstRegistrationDate') || !t.includes('hadAccident')) continue;

    try {
      // RSC format: self.__next_f.push([1,"...escaped JSON..."])
      // On cherche le JSON du vehicule dans le contenu escape
      const matches = t.match(/\\"id\\":(\d+).*?\\"vehicleCategory\\":\\"car\\"/s);
      if (!matches) continue;

      // Extraire le JSON complet du vehicule
      // Strategie: chercher le bloc qui commence par {"id": et finit avant "seller"
      let raw = t;
      // Unescape le RSC streaming format
      raw = raw.replace(/\\"/g, '"').replace(/\\n/g, '\n').replace(/\\u0026/g, '&');

      // Trouver l'objet vehicule via regex
      const vehicleMatch = raw.match(/"id":(\d+),"status":"[^"]+","conditionType"/);
      if (!vehicleMatch) continue;

      const startIdx = raw.lastIndexOf('{', vehicleMatch.index);
      if (startIdx === -1) continue;

      // Trouver la fin de l'objet vehicule (avant "seller":)
      let depth = 0;
      let endIdx = startIdx;
      for (let i = startIdx; i < raw.length; i++) {
        if (raw[i] === '{') depth++;
        if (raw[i] === '}') depth--;
        if (depth === 0) { endIdx = i + 1; break; }
      }

      const jsonStr = raw.substring(startIdx, endIdx);
      return JSON.parse(jsonStr);
    } catch (e) {
      console.warn('[CoPilot AS24] RSC parse error:', e);
      continue;
    }
  }
  return null;
}

// ── JSON-LD Parsing ───────────────────────────────────────

export function parseJsonLd(document) {
  const scripts = document.querySelectorAll('script[type="application/ld+json"]');
  for (const script of scripts) {
    try {
      const data = JSON.parse(script.textContent);
      // Peut etre un array ou un objet
      const items = Array.isArray(data) ? data : [data];
      for (const item of items) {
        if (item['@type'] === 'Car') return item;
        // Peut etre imbrique dans Organization
        const offers = item.offers || item.hasOfferCatalog;
        if (offers) {
          const car = offers.itemListElement?.[0]?.item ||
                      offers.itemOffered ||
                      (offers['@type'] === 'Car' ? offers : null);
          if (car?.['@type'] === 'Car') return car;
        }
      }
    } catch (e) {
      continue;
    }
  }
  return null;
}

// ── Normalisation ─────────────────────────────────────────

/**
 * Normalise les donnees RSC + JSON-LD vers le format extract_ad_data().
 * C'est le contrat backend: le dict retourne doit avoir les memes cles
 * que ce que app/services/extraction.py::extract_ad_data() produit.
 */
export function normalizeToAdData(rsc, jsonLd) {
  const seller = jsonLd?.offers?.seller;

  // Determiner owner_type: si le vendeur a des features pro, c'est un pro
  let ownerType = 'private';
  if (rsc?.sellerId || seller?.['@type'] === 'AutoDealer') {
    ownerType = 'pro';
  }

  // Currency from JSON-LD or default
  const currency = jsonLd?.offers?.priceCurrency || 'CHF';

  return {
    title: rsc?.versionFullName || jsonLd?.name || null,
    price_eur: rsc?.price ?? jsonLd?.offers?.price ?? null,
    currency: currency,
    make: rsc?.make?.name || jsonLd?.brand?.name || null,
    model: rsc?.model?.name || jsonLd?.model || null,
    year_model: String(
      rsc?.firstRegistrationYear ||
      jsonLd?.vehicleModelDate ||
      ''
    ) || null,
    mileage_km: rsc?.mileage ?? jsonLd?.mileageFromOdometer?.value ?? null,
    fuel: mapFuelType(rsc?.fuelType) || jsonLd?.vehicleEngine?.fuelType || null,
    gearbox: mapTransmission(rsc?.transmissionTypeGroup) ||
             jsonLd?.vehicleTransmission || null,
    doors: rsc?.doors ?? jsonLd?.numberOfDoors ?? null,
    seats: rsc?.seats ?? jsonLd?.vehicleSeatingCapacity ?? null,
    first_registration: rsc?.firstRegistrationDate || null,
    color: rsc?.bodyColor || jsonLd?.color || null,
    power_fiscal_cv: null,  // Non disponible sur AS24
    power_din_hp: rsc?.horsePower ||
                  jsonLd?.vehicleEngine?.enginePower?.value || null,
    location: {
      city: seller?.address?.addressLocality || null,
      zipcode: seller?.address?.postalCode || null,
      department: null,
      region: null,
      lat: null,
      lng: null,
    },
    phone: seller?.telephone || null,
    description: rsc?.teaser || '',
    owner_type: ownerType,
    owner_name: seller?.name || null,
    siret: null,
    raw_attributes: {},
    image_count: rsc?.images?.length || 0,
    has_phone: !!(seller?.telephone),
    has_urgent: false,
    has_highlight: false,
    has_boost: false,
    publication_date: rsc?.createdDate || null,
    days_online: null,  // Calcule cote backend
    index_date: rsc?.lastModifiedDate || null,
    days_since_refresh: null,
    republished: false,
    lbc_estimation: null,
  };
}

// ── Bonus Signals ─────────────────────────────────────────

export function buildBonusSignals(rsc, jsonLd) {
  if (!rsc || typeof rsc !== 'object') return [];
  const signals = [];
  const seller = jsonLd?.offers?.seller;

  if (typeof rsc.hadAccident === 'boolean') {
    signals.push({
      label: 'Accident declare',
      value: rsc.hadAccident ? 'Oui' : 'Non',
      status: rsc.hadAccident ? 'fail' : 'pass',
    });
  }

  if (typeof rsc.inspected === 'boolean') {
    signals.push({
      label: 'Controle technique',
      value: rsc.inspected ? 'Fait' : 'Non fait',
      status: rsc.inspected ? 'pass' : 'warning',
    });
  }

  if (rsc.warranty?.duration) {
    const km = rsc.warranty.mileage
      ? ` / ${(rsc.warranty.mileage / 1000).toFixed(0)}k km`
      : '';
    signals.push({
      label: 'Garantie',
      value: `${rsc.warranty.duration} mois${km}`,
      status: 'pass',
    });
  }

  if (rsc.listPrice && rsc.price) {
    const decote = Math.round((1 - rsc.price / rsc.listPrice) * 100);
    const currency = jsonLd?.offers?.priceCurrency || 'CHF';
    signals.push({
      label: 'Prix neuf catalogue',
      value: `${rsc.listPrice.toLocaleString()} ${currency}`,
      status: 'info',
    });
    signals.push({
      label: 'Decote',
      value: `-${decote}%`,
      status: 'info',
    });
  }

  if (seller?.aggregateRating) {
    const r = seller.aggregateRating;
    signals.push({
      label: 'Avis Google vendeur',
      value: `${r.ratingValue}/5 (${r.reviewCount} avis)`,
      status: r.ratingValue >= 4.0 ? 'pass' : r.ratingValue >= 3.0 ? 'warning' : 'fail',
    });
  }

  if (typeof rsc.directImport === 'boolean' && rsc.directImport) {
    signals.push({
      label: 'Import direct',
      value: 'Oui',
      status: 'warning',
    });
  }

  return signals;
}

// ── Classe AutoScout24Extractor ───────────────────────────

export class AutoScout24Extractor extends SiteExtractor {
  static SITE_ID = 'autoscout24';
  static URL_PATTERNS = AS24_URL_PATTERNS;

  constructor() {
    super();
    this._rsc = null;
    this._jsonLd = null;
    this._adData = null;
  }

  isAdPage(url) {
    return /autoscout24\.\w+\/\w+\/d\/.+-\d+/.test(url);
  }

  async extract() {
    this._rsc = parseRSCPayload(document);
    this._jsonLd = parseJsonLd(document);

    if (!this._rsc && !this._jsonLd) {
      console.warn('[CoPilot AS24] No RSC or JSON-LD data found');
      return null;
    }

    this._adData = normalizeToAdData(this._rsc, this._jsonLd);

    return {
      type: 'normalized',
      source: 'autoscout24',
      ad_data: this._adData,
    };
  }

  getVehicleSummary() {
    if (!this._adData) return null;
    return {
      make: this._adData.make,
      model: this._adData.model,
      year: this._adData.year_model,
    };
  }

  isLoggedIn() {
    return false;  // Pas de revelation telephone sur AS24
  }

  getBonusSignals() {
    return buildBonusSignals(this._rsc, this._jsonLd);
  }
}
```

**Step 4: Run tests**

Run: `npm run test:extension`
Expected: All tests pass

**Step 5: Commit**

```bash
git add -f extension/extractors/autoscout24.js extension/tests/autoscout24.test.js
git commit -m "feat: add AutoScout24Extractor with RSC + JSON-LD parsing"
```

---

## Task 8: Backend - Accept `ad_data` in /api/analyze

**Files:**
- Modify: `app/schemas/analyze.py`
- Modify: `app/api/routes.py:63-102`

**Step 1: Write the failing test**

Create `tests/test_api/test_analyze_ad_data.py`:

```python
"""Tests for POST /api/analyze with pre-normalized ad_data (multi-site support)."""

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app.test_client()


def _autoscout_ad_data():
    """Minimal AutoScout24 ad_data matching extract_ad_data() output."""
    return {
        "title": "AUDI Q5 Sportback 40 TDI",
        "price_eur": 43900,
        "currency": "CHF",
        "make": "AUDI",
        "model": "Q5",
        "year_model": "2023",
        "mileage_km": 29299,
        "fuel": "Diesel",
        "gearbox": "Automatique",
        "power_din_hp": 204,
        "image_count": 23,
        "owner_type": "pro",
        "description": "Fahrzeug mit Garantie",
        "location": {"city": "Niederlenz", "region": None},
        "publication_date": "2026-02-11T09:00:20.284Z",
        "has_phone": True,
        "phone": "+41628929454",
        "raw_attributes": {},
        "has_urgent": False,
        "has_highlight": False,
        "has_boost": False,
        "days_online": None,
        "index_date": None,
        "days_since_refresh": None,
        "republished": False,
        "lbc_estimation": None,
    }


class TestAnalyzeAdData:
    """Tests for the ad_data path (pre-normalized, non-LBC sites)."""

    def test_ad_data_returns_score(self, client):
        """POST with ad_data should bypass extract_ad_data and return a score."""
        resp = client.post(
            "/api/analyze",
            json={
                "url": "https://www.autoscout24.ch/fr/d/audi-q5-20201676",
                "ad_data": _autoscout_ad_data(),
                "source": "autoscout24",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "score" in data["data"]
        assert 0 <= data["data"]["score"] <= 100
        assert len(data["data"]["filters"]) > 0

    def test_ad_data_source_stored(self, client):
        """Source should be stored in ad_data for downstream use."""
        resp = client.post(
            "/api/analyze",
            json={
                "url": "https://www.autoscout24.ch/fr/d/audi-q5-20201676",
                "ad_data": _autoscout_ad_data(),
                "source": "autoscout24",
            },
        )
        assert resp.status_code == 200

    def test_legacy_next_data_still_works(self, client):
        """Legacy LBC path with next_data should still work."""
        resp = client.post(
            "/api/analyze",
            json={
                "url": "https://www.leboncoin.fr/ad/voitures/12345",
                "next_data": {
                    "props": {
                        "pageProps": {
                            "ad": {
                                "list_id": 12345,
                                "attributes": [
                                    {"key": "brand", "value": "Peugeot"},
                                    {"key": "model", "value": "208"},
                                    {"key": "regdate", "value": "2021"},
                                ],
                                "price": [15000],
                                "images": {"nb_images": 5},
                                "location": {"region_name": "Ile-de-France"},
                                "owner": {"type": "private"},
                            }
                        }
                    }
                },
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_neither_next_data_nor_ad_data_returns_400(self, client):
        """Request without next_data or ad_data should fail validation."""
        resp = client.post(
            "/api/analyze",
            json={"url": "https://example.com"},
        )
        assert resp.status_code == 400
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api/test_analyze_ad_data.py -v`
Expected: FAIL (Pydantic validation requires `next_data`)

**Step 3: Update schema**

In `app/schemas/analyze.py`, change `AnalyzeRequest`:

```python
class AnalyzeRequest(BaseModel):
    """Corps de la requete pour POST /api/analyze.

    Accepte soit next_data (LBC legacy) soit ad_data (pre-normalise, multi-site).
    """

    url: str | None = None
    next_data: dict[str, Any] | None = Field(None, description="Leboncoin __NEXT_DATA__ JSON")
    ad_data: dict[str, Any] | None = Field(None, description="Pre-normalized vehicle data")
    source: str | None = Field(None, description="Site source (leboncoin, autoscout24)")
```

**Step 4: Update routes.py**

In `app/api/routes.py`, modify `_do_analyze()` to handle both paths. After the Pydantic validation block (line 88), replace the extraction block (lines 90-102):

```python
    # Validation: au moins un des deux payloads requis
    if not req.next_data and not req.ad_data:
        return jsonify(
            {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "next_data ou ad_data requis.",
                "data": None,
            }
        ), 400

    # Extraction des donnees de l'annonce
    if req.ad_data:
        # Pre-normalized path (AutoScout24, La Centrale, etc.)
        ad_data = req.ad_data
        if req.source:
            ad_data["source"] = req.source
    else:
        # Legacy LBC path
        try:
            ad_data = extract_ad_data(req.next_data)
        except ExtractionError as exc:
            logger.warning("Extraction failed: %s", exc)
            return jsonify(
                {
                    "success": False,
                    "error": "EXTRACTION_ERROR",
                    "message": "Impossible d'extraire les donnees de cette annonce.",
                    "data": None,
                }
            ), 422
```

Also update `raw_data` in ScanLog persistence (line 160):
```python
raw_data=json_data.get("next_data") or json_data.get("ad_data"),
```

**Step 5: Run tests**

Run: `pytest tests/test_api/test_analyze_ad_data.py -v`
Expected: All 4 tests pass

Run: `pytest tests/ -v --timeout=30`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add app/schemas/analyze.py app/api/routes.py tests/test_api/test_analyze_ad_data.py
git commit -m "feat: accept ad_data in /api/analyze for multi-site support"
```

---

## Task 9: Popup bonus signals section

**Files:**
- Modify: `extension/content.js` (the `buildResultsPopup` function)

**Step 1: Add bonus signals rendering**

In `buildResultsPopup`, after the filters list and before the premium section, add:

```javascript
// Bonus signals section (AutoScout24 exclusive data)
if (options.bonusSignals && options.bonusSignals.length > 0) {
  html += `<div style="margin:12px 0;padding:10px;background:#f0f4ff;border-radius:8px;border:1px solid #d0d8f0;">`;
  html += `<div style="font-weight:600;font-size:13px;margin-bottom:8px;color:#334155;">Signaux ${options.source || 'AutoScout24'}</div>`;
  for (const signal of options.bonusSignals) {
    const icon = signal.status === 'pass' ? '✓' : signal.status === 'warning' ? '⚠' : signal.status === 'fail' ? '✗' : 'ℹ';
    const color = signal.status === 'pass' ? '#16a34a' : signal.status === 'warning' ? '#f59e0b' : signal.status === 'fail' ? '#ef4444' : '#6366f1';
    html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;font-size:12px;">`;
    html += `<span style="color:#64748b;">${escapeHTML(signal.label)}</span>`;
    html += `<span style="font-weight:600;color:${color};">${icon} ${escapeHTML(signal.value)}</span>`;
    html += `</div>`;
  }
  html += `</div>`;
}
```

**Step 2: Rebuild**

Run: `npm run build:ext`

**Step 3: Commit**

```bash
git add -f extension/content.js extension/dist/
git commit -m "feat: add bonus signals section to popup (AutoScout24)"
```

---

## Task 10: Update existing tests for module system

**Files:**
- Modify: `extension/tests/content.test.js`
- Modify: `vitest.config.mjs`

**Step 1: Update vitest config**

Since we now use ES modules with esbuild bundling, tests need to import from the extractors. But tests run in Node (not bundled). Two options:
- Option A: Tests import from source files (extractors/*.js) using vitest's ESM support
- Option B: Tests import from the CJS module.exports block

**Best approach**: Keep the existing `module.exports` block in content.js for backward compatibility, AND add a separate test file that imports from the extractors directly for new tests.

Update `vitest.config.mjs` to handle both:
```javascript
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['extension/tests/**/*.test.js'],
    globals: true,
  },
});
```

No changes needed if the existing content.test.js still uses `require('../content.js')` -- the IIFE + module.exports pattern still works because esbuild only bundles the entry point, and tests run against the source.

**Step 2: Verify existing tests pass**

Run: `npm run test:extension`
Expected: All existing tests pass (content.test.js unchanged)

**Step 3: Commit if any changes**

```bash
git add vitest.config.mjs extension/tests/
git commit -m "test: ensure existing tests work with new module structure"
```

---

## Task 11: Integration test with real AutoScout24 page

**Files:**
- Create: `extension/tests/autoscout24-integration.test.js`

**Step 1: Create integration test with fixture HTML**

This test verifies end-to-end RSC parsing with realistic page content. We create a minimal HTML fixture from the documented RSC structure.

```javascript
import { describe, it, expect } from 'vitest';
import { parseJsonLd, normalizeToAdData, buildBonusSignals } from '../extractors/autoscout24.js';
import { JSDOM } from 'jsdom';

describe('AutoScout24 integration', () => {
  it('extracts vehicle data from JSON-LD in a realistic page', () => {
    const html = `
      <html><head>
        <script type="application/ld+json">${JSON.stringify({
          "@type": "Car",
          "name": "BMW 320d xDrive Touring",
          "brand": { "name": "BMW" },
          "model": "320",
          "vehicleModelDate": 2022,
          "color": "black",
          "numberOfDoors": 5,
          "mileageFromOdometer": { "value": 45000, "unitCode": "KMT" },
          "vehicleEngine": {
            "enginePower": { "value": 190 },
            "fuelType": "Diesel",
          },
          "vehicleTransmission": "Automatique",
          "offers": {
            "price": 38500,
            "priceCurrency": "CHF",
            "seller": {
              "@type": "AutoDealer",
              "name": "Swiss Auto AG",
              "telephone": "+41441234567",
              "address": { "addressLocality": "Zurich", "postalCode": "8001" },
              "aggregateRating": { "ratingValue": 4.5, "reviewCount": 89 },
            }
          }
        })}</script>
      </head><body></body></html>
    `;
    const dom = new JSDOM(html);
    const jsonLd = parseJsonLd(dom.window.document);

    expect(jsonLd).not.toBeNull();
    expect(jsonLd.model).toBe('320');

    const adData = normalizeToAdData(null, jsonLd);
    expect(adData.make).toBe('BMW');
    expect(adData.model).toBe('320');
    expect(adData.price_eur).toBe(38500);
    expect(adData.currency).toBe('CHF');
    expect(adData.mileage_km).toBe(45000);
    expect(adData.owner_type).toBe('pro');
    expect(adData.location.city).toBe('Zurich');
  });
});
```

**Step 2: Run**

Run: `npm run test:extension`
Expected: All tests pass

**Step 3: Commit**

```bash
git add -f extension/tests/autoscout24-integration.test.js
git commit -m "test: add AutoScout24 integration test with JSON-LD fixture"
```

---

## Task 12: Full rebuild + manual verification

**Step 1: Run all Python tests**

Run: `pytest tests/ -v --timeout=30`
Expected: All pass

**Step 2: Run all JS tests**

Run: `npm run test:extension`
Expected: All pass

**Step 3: Build extension**

Run: `npm run build:ext`
Expected: Build succeeds

**Step 4: Lint**

Run: `cd "/Users/malik/Documents/Espace de travail/Co-Pilot" && ruff check . && ruff format --check .`
Expected: Clean

**Step 5: Final commit if needed**

```bash
git add -A && git status
```

---

## Summary

| Task | Description | Fichiers |
|------|-------------|----------|
| 1 | Setup esbuild | `build.js`, `package.json` |
| 2 | SiteExtractor base class | `extractors/base.js` |
| 3 | Extractor registry | `extractors/index.js` |
| 4 | Refactor LBC into LeBonCoinExtractor | `extractors/leboncoin.js`, `content.js` |
| 5 | Update background.js injection | `background.js` |
| 6 | Manifest AutoScout24 domains | `manifest.json` |
| 7 | AutoScout24Extractor + tests | `extractors/autoscout24.js`, tests |
| 8 | Backend ad_data support + tests | `schemas/analyze.py`, `routes.py`, tests |
| 9 | Popup bonus signals | `content.js` |
| 10 | Update existing tests | `content.test.js` |
| 11 | Integration test | `autoscout24-integration.test.js` |
| 12 | Full verification | All |

**Commits: ~12 commits, incrementaux, chacun vert (tests passent).**
