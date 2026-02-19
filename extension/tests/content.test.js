/**
 * Tests pour extension/content.js
 *
 * Vitest + jsdom -- couvre la logique navigateur (localStorage, cooldown,
 * extraction de donnees, collecte de prix) invisible aux tests Python.
 *
 * Run: npm run test:extension
 */

const {
  extractVehicleFromNextData,
  extractRegionFromNextData,
  extractLocationFromNextData,
  buildLocationParam,
  DEFAULT_SEARCH_RADIUS,
  MIN_PRICES_FOR_ARGUS,
  fetchSearchPrices,
  extractMileageFromNextData,
  isStaleData,
  isAdPage,
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
  SIMULATED_FILTERS,
  API_URL,
} = require('../content.js');


// ── Fixtures ────────────────────────────────────────────────────────

/** Construit un __NEXT_DATA__ minimal pour un vehicule LeBonCoin. */
function makeNextData(overrides = {}) {
  return {
    props: {
      pageProps: {
        ad: {
          list_id: overrides.list_id ?? 12345,
          attributes: overrides.attributes ?? [
            { key: 'brand', value: 'Peugeot' },
            { key: 'model', value: '3008' },
            { key: 'regdate', value: '2021' },
          ],
          location: {
            region_name: overrides.region ?? 'Île-de-France',
            ...(overrides.location || {}),
          },
          ...(overrides.ad || {}),
        },
      },
    },
  };
}

/** Construit une reponse next-job API. */
function makeJobResponse(target, collect = true, region = 'Île-de-France') {
  return {
    success: true,
    data: {
      collect,
      vehicle: target,
      region,
    },
  };
}

/** Construit un HTML de recherche LBC avec __NEXT_DATA__ contenant des prix. */
function makeSearchHTML(prices) {
  const ads = prices.map((p) => ({ price: [p], title: 'annonce test' }));
  const data = { props: { pageProps: { searchData: { ads } } } };
  return `<html><script id="__NEXT_DATA__" type="application/json">${JSON.stringify(data)}</script></html>`;
}


// ═══════════════════════════════════════════════════════════════════
// 1. Fonctions pures : couleurs, icones, labels
// ═══════════════════════════════════════════════════════════════════

describe('scoreColor', () => {
  it('retourne vert pour score >= 70', () => {
    expect(scoreColor(70)).toBe('#22c55e');
    expect(scoreColor(100)).toBe('#22c55e');
  });

  it('retourne orange pour score entre 40 et 69', () => {
    expect(scoreColor(40)).toBe('#f59e0b');
    expect(scoreColor(69)).toBe('#f59e0b');
  });

  it('retourne rouge pour score < 40', () => {
    expect(scoreColor(39)).toBe('#ef4444');
    expect(scoreColor(0)).toBe('#ef4444');
  });
});


describe('statusColor', () => {
  it('retourne la bonne couleur par statut', () => {
    expect(statusColor('pass')).toBe('#22c55e');
    expect(statusColor('warning')).toBe('#f59e0b');
    expect(statusColor('fail')).toBe('#ef4444');
    expect(statusColor('skip')).toBe('#9ca3af');
  });

  it('retourne gris pour statut inconnu', () => {
    expect(statusColor('unknown')).toBe('#6b7280');
  });
});


describe('statusIcon', () => {
  it('retourne la bonne icone par statut', () => {
    expect(statusIcon('pass')).toBe('\u2713');
    expect(statusIcon('warning')).toBe('\u26A0');
    expect(statusIcon('fail')).toBe('\u2717');
    expect(statusIcon('skip')).toBe('\u2014');
  });

  it('retourne ? pour statut inconnu', () => {
    expect(statusIcon('other')).toBe('?');
  });
});


describe('filterLabel', () => {
  it('retourne le label FR pour les filter IDs connus', () => {
    expect(filterLabel('L1')).toBe('Complétude des données');
    expect(filterLabel('L4')).toBe('Prix vs Argus');
    expect(filterLabel('L9')).toBe('Évaluation globale');
  });

  it('retourne le filter ID brut si inconnu', () => {
    expect(filterLabel('L99')).toBe('L99');
  });
});


// ═══════════════════════════════════════════════════════════════════
// 2. Detection de page annonce
// ═══════════════════════════════════════════════════════════════════

describe('isAdPage', () => {
  const originalLocation = window.location;

  afterEach(() => {
    // Restore original location
    Object.defineProperty(window, 'location', {
      value: originalLocation,
      writable: true,
    });
  });

  it('reconnait les URLs /ad/', () => {
    Object.defineProperty(window, 'location', {
      value: { href: 'https://www.leboncoin.fr/ad/voitures/2456789012' },
      writable: true,
    });
    expect(isAdPage()).toBe(true);
  });

  it('reconnait les URLs /voitures/', () => {
    Object.defineProperty(window, 'location', {
      value: { href: 'https://www.leboncoin.fr/voitures/2456789012' },
      writable: true,
    });
    expect(isAdPage()).toBe(true);
  });

  it('rejette les pages de recherche', () => {
    Object.defineProperty(window, 'location', {
      value: { href: 'https://www.leboncoin.fr/recherche?category=2' },
      writable: true,
    });
    expect(isAdPage()).toBe(false);
  });

  it('rejette les autres domaines', () => {
    Object.defineProperty(window, 'location', {
      value: { href: 'https://www.google.com' },
      writable: true,
    });
    expect(isAdPage()).toBe(false);
  });
});


// ═══════════════════════════════════════════════════════════════════
// 3. Extraction vehicule depuis __NEXT_DATA__
// ═══════════════════════════════════════════════════════════════════

describe('extractVehicleFromNextData', () => {
  it('extrait make/model/year depuis les attributs standards', () => {
    const result = extractVehicleFromNextData(makeNextData());
    expect(result).toEqual({
      make: 'Peugeot',
      model: '3008',
      year: '2021',
      fuel: '',
      gearbox: '',
      horse_power: '',
    });
  });

  it('gere les cles alternatives FR (key_label)', () => {
    const nextData = makeNextData({
      attributes: [
        { key_label: 'Marque', value: 'Renault' },
        { key_label: 'Modèle', value: 'Clio' },
        { key_label: 'Année modèle', value: '2020' },
      ],
    });
    const result = extractVehicleFromNextData(nextData);
    expect(result.make).toBe('Renault');
    expect(result.model).toBe('Clio');
    expect(result.year).toBe('2020');
  });

  it('utilise value_label en fallback si value est absent', () => {
    const nextData = makeNextData({
      attributes: [
        { key: 'brand', value_label: 'Bmw' },
        { key: 'model', value_label: 'X1' },
        { key: 'regdate', value_label: '2023' },
      ],
    });
    const result = extractVehicleFromNextData(nextData);
    expect(result.make).toBe('Bmw');
    expect(result.model).toBe('X1');
    expect(result.year).toBe('2023');
  });

  it('retourne des chaines vides quand les attributs manquent', () => {
    const nextData = makeNextData({ attributes: [] });
    const result = extractVehicleFromNextData(nextData);
    expect(result.make).toBe('');
    expect(result.model).toBe('');
    expect(result.year).toBe('');
  });

  it('extrait gearbox et horse_power depuis les attributs', () => {
    const nextData = makeNextData({
      attributes: [
        { key: 'brand', value: 'Renault' },
        { key: 'model', value: 'Clio' },
        { key: 'regdate', value: '2025' },
        { key: 'fuel', value: 'hybride' },
        { key: 'gearbox', value: 'Automatique' },
        { key: 'horse_power_din', value: '130' },
      ],
    });
    const result = extractVehicleFromNextData(nextData);
    expect(result.gearbox).toBe('Automatique');
    expect(result.horse_power).toBe('130');
  });

  it('extrait gearbox depuis cles FR alternatives', () => {
    const nextData = makeNextData({
      attributes: [
        { key: 'brand', value: 'Peugeot' },
        { key: 'model', value: '208' },
        { key: 'regdate', value: '2022' },
        { key: 'Boîte de vitesse', value: 'Manuelle' },
        { key: 'Puissance DIN', value: '75' },
      ],
    });
    const result = extractVehicleFromNextData(nextData);
    expect(result.gearbox).toBe('Manuelle');
    expect(result.horse_power).toBe('75');
  });

  it('retourne un objet vide quand ad est absent', () => {
    expect(extractVehicleFromNextData({})).toEqual({});
  });

  it('retourne un objet vide quand nextData est null', () => {
    expect(extractVehicleFromNextData(null)).toEqual({});
  });
});


// ═══════════════════════════════════════════════════════════════════
// 4. Extraction region depuis __NEXT_DATA__
// ═══════════════════════════════════════════════════════════════════

describe('extractRegionFromNextData', () => {
  it('extrait region_name depuis location', () => {
    const nextData = makeNextData({ region: 'Bretagne' });
    expect(extractRegionFromNextData(nextData)).toBe('Bretagne');
  });

  it('fallback sur region si region_name absent', () => {
    const nextData = {
      props: { pageProps: { ad: { location: { region: 'Corse' } } } },
    };
    expect(extractRegionFromNextData(nextData)).toBe('Corse');
  });

  it('retourne chaine vide quand nextData est null', () => {
    expect(extractRegionFromNextData(null)).toBe('');
  });

  it('retourne chaine vide quand location est vide', () => {
    const nextData = { props: { pageProps: { ad: { location: {} } } } };
    expect(extractRegionFromNextData(nextData)).toBe('');
  });
});


// ═══════════════════════════════════════════════════════════════════
// 4a-bis. Extraction localisation complete depuis __NEXT_DATA__
// ═══════════════════════════════════════════════════════════════════

describe('extractLocationFromNextData', () => {
  it('extrait city/zipcode/lat/lng/region depuis location', () => {
    const nextData = makeNextData({
      location: {
        city: 'Vienne',
        zipcode: '38200',
        lat: 45.52172,
        lng: 4.87245,
        region_name: 'Auvergne-Rhône-Alpes',
      },
    });
    const loc = extractLocationFromNextData(nextData);
    expect(loc).toEqual({
      city: 'Vienne',
      zipcode: '38200',
      lat: 45.52172,
      lng: 4.87245,
      region: 'Auvergne-Rhône-Alpes',
    });
  });

  it('retourne null quand nextData est null', () => {
    expect(extractLocationFromNextData(null)).toBeNull();
  });

  it('retourne null quand location est absente', () => {
    expect(extractLocationFromNextData({ props: { pageProps: { ad: {} } } })).toBeNull();
  });

  it('retourne des valeurs vides quand les champs manquent', () => {
    const nextData = { props: { pageProps: { ad: { location: {} } } } };
    const loc = extractLocationFromNextData(nextData);
    expect(loc.city).toBe('');
    expect(loc.zipcode).toBe('');
    expect(loc.lat).toBeNull();
    expect(loc.lng).toBeNull();
    expect(loc.region).toBe('');
  });

  it('fallback sur region si region_name absent', () => {
    const nextData = { props: { pageProps: { ad: { location: { region: 'Corse' } } } } };
    const loc = extractLocationFromNextData(nextData);
    expect(loc.region).toBe('Corse');
  });
});


// ═══════════════════════════════════════════════════════════════════
// 4a-ter. buildLocationParam : geo-location > region fallback
// ═══════════════════════════════════════════════════════════════════

describe('buildLocationParam', () => {
  it('construit le format geo LBC avec lat/lng', () => {
    const loc = { city: 'Vienne', zipcode: '38200', lat: 45.52172, lng: 4.87245, region: 'Auvergne-Rhône-Alpes' };
    expect(buildLocationParam(loc)).toBe('Vienne_38200__45.52172_4.87245_5000_30000');
  });

  it('utilise un rayon custom si fourni', () => {
    const loc = { city: 'Lyon', zipcode: '69000', lat: 45.764, lng: 4.8357, region: 'Auvergne-Rhône-Alpes' };
    expect(buildLocationParam(loc, 50000)).toBe('Lyon_69000__45.764_4.8357_5000_50000');
  });

  it('fallback sur rn_XX quand lat/lng absents', () => {
    const loc = { city: '', zipcode: '', lat: null, lng: null, region: 'Bretagne' };
    expect(buildLocationParam(loc)).toBe(LBC_REGIONS['Bretagne']);
  });

  it('fallback sur rn_XX quand city absente', () => {
    const loc = { city: '', zipcode: '38200', lat: 45.52172, lng: 4.87245, region: 'Auvergne-Rhône-Alpes' };
    expect(buildLocationParam(loc)).toBe(LBC_REGIONS['Auvergne-Rhône-Alpes']);
  });

  it('retourne chaine vide quand location est null', () => {
    expect(buildLocationParam(null)).toBe('');
  });

  it('retourne chaine vide quand region inconnue et pas de geo', () => {
    const loc = { city: '', zipcode: '', lat: null, lng: null, region: 'Atlantide' };
    expect(buildLocationParam(loc)).toBe('');
  });

  it('DEFAULT_SEARCH_RADIUS vaut 30000 metres (30 km)', () => {
    expect(DEFAULT_SEARCH_RADIUS).toBe(30000);
  });
});


// ═══════════════════════════════════════════════════════════════════
// 4b. Extraction kilometrage depuis __NEXT_DATA__
// ═══════════════════════════════════════════════════════════════════

describe('extractMileageFromNextData', () => {
  it('extrait le kilometrage depuis l\'attribut mileage', () => {
    const nextData = makeNextData({
      attributes: [
        { key: 'brand', value: 'Renault' },
        { key: 'model', value: 'Clio' },
        { key: 'regdate', value: '2020' },
        { key: 'mileage', value: '45000' },
      ],
    });
    expect(extractMileageFromNextData(nextData)).toBe(45000);
  });

  it('retourne 0 quand nextData est null', () => {
    expect(extractMileageFromNextData(null)).toBe(0);
  });

  it('retourne 0 quand attribut mileage absent', () => {
    const nextData = makeNextData({ attributes: [{ key: 'brand', value: 'Peugeot' }] });
    expect(extractMileageFromNextData(nextData)).toBe(0);
  });

  it('parse des valeurs avec espaces (ex: "45 000")', () => {
    const nextData = makeNextData({
      attributes: [{ key: 'mileage', value: '45 000' }],
    });
    expect(extractMileageFromNextData(nextData)).toBe(45000);
  });
});


// ═══════════════════════════════════════════════════════════════════
// 4c. getMileageRange helper
// ═══════════════════════════════════════════════════════════════════

describe('getMileageRange', () => {
  it('retourne null pour km <= 0 ou absent', () => {
    expect(getMileageRange(0)).toBeNull();
    expect(getMileageRange(null)).toBeNull();
    expect(getMileageRange(undefined)).toBeNull();
  });

  it('quasi-neuf: min-20000 pour km <= 10000', () => {
    expect(getMileageRange(3310)).toBe('min-20000');
    expect(getMileageRange(10000)).toBe('min-20000');
  });

  it('faible km: min-50000 pour 10001-30000', () => {
    expect(getMileageRange(10001)).toBe('min-50000');
    expect(getMileageRange(25000)).toBe('min-50000');
    expect(getMileageRange(30000)).toBe('min-50000');
  });

  it('usage normal: 20000-80000 pour 30001-60000', () => {
    expect(getMileageRange(30001)).toBe('20000-80000');
    expect(getMileageRange(50000)).toBe('20000-80000');
    expect(getMileageRange(60000)).toBe('20000-80000');
  });

  it('usage intensif: 50000-150000 pour 60001-120000', () => {
    expect(getMileageRange(60001)).toBe('50000-150000');
    expect(getMileageRange(100000)).toBe('50000-150000');
    expect(getMileageRange(120000)).toBe('50000-150000');
  });

  it('haute frequentation: 100000-max pour > 120000', () => {
    expect(getMileageRange(120001)).toBe('100000-max');
    expect(getMileageRange(250000)).toBe('100000-max');
  });
});


// ═══════════════════════════════════════════════════════════════════
// 4d. getHorsePowerRange helper
// ═══════════════════════════════════════════════════════════════════

describe('getHorsePowerRange', () => {
  it('retourne null pour hp <= 0 ou absent', () => {
    expect(getHorsePowerRange(0)).toBeNull();
    expect(getHorsePowerRange(null)).toBeNull();
    expect(getHorsePowerRange(undefined)).toBeNull();
    expect(getHorsePowerRange(-10)).toBeNull();
  });

  it('arrondit a la dizaine inferieure: 130ch -> "130-max"', () => {
    expect(getHorsePowerRange(130)).toBe('130-max');
  });

  it('arrondit a la dizaine inferieure: 136ch -> "130-max"', () => {
    expect(getHorsePowerRange(136)).toBe('130-max');
  });

  it('arrondit a la dizaine inferieure: 75ch -> "70-max"', () => {
    expect(getHorsePowerRange(75)).toBe('70-max');
  });

  it('gere les puissances exactes sur dizaine: 100ch -> "100-max"', () => {
    expect(getHorsePowerRange(100)).toBe('100-max');
  });

  it('gere les petites puissances: 45ch -> "40-max"', () => {
    expect(getHorsePowerRange(45)).toBe('40-max');
  });
});


// ═══════════════════════════════════════════════════════════════════
// 5. Detection de donnees SPA perimees
// ═══════════════════════════════════════════════════════════════════

describe('isStaleData', () => {
  const originalLocation = window.location;

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      value: originalLocation,
      writable: true,
    });
  });

  it('retourne false quand ad ID correspond au URL ID', () => {
    Object.defineProperty(window, 'location', {
      value: { href: 'https://www.leboncoin.fr/ad/voitures/12345' },
      writable: true,
    });
    expect(isStaleData(makeNextData({ list_id: 12345 }))).toBe(false);
  });

  it('retourne true quand ad ID ne correspond pas', () => {
    Object.defineProperty(window, 'location', {
      value: { href: 'https://www.leboncoin.fr/ad/voitures/12345' },
      writable: true,
    });
    expect(isStaleData(makeNextData({ list_id: 99999 }))).toBe(true);
  });

  it('retourne true quand ad est absent des donnees', () => {
    Object.defineProperty(window, 'location', {
      value: { href: 'https://www.leboncoin.fr/ad/voitures/12345' },
      writable: true,
    });
    expect(isStaleData({ props: { pageProps: {} } })).toBe(true);
  });

  it('retourne false quand URL na pas de numeric ID', () => {
    Object.defineProperty(window, 'location', {
      value: { href: 'https://www.leboncoin.fr/recherche' },
      writable: true,
    });
    expect(isStaleData(makeNextData())).toBe(false);
  });
});


// ═══════════════════════════════════════════════════════════════════
// 6. Constantes : regions, cooldown, filtres simules
// ═══════════════════════════════════════════════════════════════════

describe('Constants', () => {
  it('COLLECT_COOLDOWN_MS vaut exactement 24 heures', () => {
    expect(COLLECT_COOLDOWN_MS).toBe(24 * 60 * 60 * 1000);
  });

  it('SIMULATED_FILTERS contient L4 et L5 uniquement', () => {
    expect(SIMULATED_FILTERS).toContain('L4');
    expect(SIMULATED_FILTERS).toContain('L5');
    expect(SIMULATED_FILTERS).toHaveLength(2);
  });

  it('API_URL pointe vers /api/analyze sur localhost:5001', () => {
    expect(API_URL).toBe('http://localhost:5001/api/analyze');
  });

  it('LBC_REGIONS contient 13 regions metropolitaines', () => {
    expect(Object.keys(LBC_REGIONS)).toHaveLength(13);
  });

  it('LBC_REGIONS a les accents francais corrects', () => {
    expect(LBC_REGIONS).toHaveProperty('Île-de-France');
    expect(LBC_REGIONS).toHaveProperty('Auvergne-Rhône-Alpes');
    expect(LBC_REGIONS).toHaveProperty("Provence-Alpes-Côte d'Azur");
    expect(LBC_REGIONS).toHaveProperty('Bourgogne-Franche-Comté');
  });

  it('LBC_REGIONS a des noms sans accents pour les autres', () => {
    expect(LBC_REGIONS).toHaveProperty('Bretagne');
    expect(LBC_REGIONS).toHaveProperty('Normandie');
    expect(LBC_REGIONS).toHaveProperty('Corse');
  });

  it('LBC_REGIONS values suivent le pattern rn_N (region + voisines)', () => {
    Object.values(LBC_REGIONS).forEach((v) => {
      expect(v).toMatch(/^rn_\d+$/);
    });
  });

  it('LBC_GEARBOX_CODES mappe manuelle et automatique', () => {
    expect(LBC_GEARBOX_CODES['manuelle']).toBe(1);
    expect(LBC_GEARBOX_CODES['automatique']).toBe(2);
  });

  it('MIN_PRICES_FOR_ARGUS vaut 3', () => {
    expect(MIN_PRICES_FOR_ARGUS).toBe(3);
  });

  it('LBC_FUEL_CODES mappe les 4 energies principales', () => {
    expect(LBC_FUEL_CODES['essence']).toBe(1);
    expect(LBC_FUEL_CODES['diesel']).toBe(2);
    expect(LBC_FUEL_CODES['electrique']).toBe(4);
    expect(LBC_FUEL_CODES['électrique']).toBe(4);
    expect(LBC_FUEL_CODES['hybride']).toBe(6);
  });
});


// ═══════════════════════════════════════════════════════════════════
// 7. Collecte crowdsourcee : cooldown, localStorage, fetch
// ═══════════════════════════════════════════════════════════════════

describe('maybeCollectMarketPrices', () => {
  const currentVehicle = { make: 'Peugeot', model: '3008', year: '2021', fuel: 'diesel', gearbox: 'Automatique', horse_power: '180' };

  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  /**
   * Mock global.fetch avec des reponses sequentielles.
   *
   * Avec l'escalade progressive, maybeCollectMarketPrices fait :
   *   1. GET  /market-prices/next-job  -> jobResponse (json)
   *   2. GET  leboncoin.fr/recherche   -> searchHTML (text)  [1 a 3 strategies]
   *   3. POST /market-prices           -> { ok: submitOk }
   *
   * @param {object} opts
   * @param {object} opts.jobResponse - Reponse next-job
   * @param {string} opts.searchHTML - HTML pour UNE recherche (si assez de prix, pas d'escalade)
   * @param {string[]} opts.searchHTMLs - HTML pour CHAQUE strategie d'escalade (prioritaire sur searchHTML)
   * @param {boolean} opts.submitOk - Reponse du POST market-prices
   */
  function mockFetchSequence({ jobResponse, searchHTML, searchHTMLs, submitOk = true }) {
    const fetchMock = vi.fn();

    // Appel 1 : next-job
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(jobResponse),
    });

    // Appels search : 1 par strategie d'escalade tentee
    const htmls = searchHTMLs || (searchHTML !== undefined ? [searchHTML] : []);
    for (const html of htmls) {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(html),
      });
    }

    // POST market-prices (seulement si >= 3 prix)
    if (submitOk !== undefined) {
      fetchMock.mockResolvedValueOnce({ ok: submitOk });
    }

    global.fetch = fetchMock;
    return fetchMock;
  }


  // ── Sorties anticipees ──────────────────────────────────────────

  describe('sorties anticipees', () => {
    it('retourne submitted=false quand make est vide', async () => {
      const result = await maybeCollectMarketPrices(
        { make: '', model: '3008', year: '2021' },
        makeNextData(),
      );
      expect(result.submitted).toBe(false);
    });

    it('retourne submitted=false quand model est vide', async () => {
      const result = await maybeCollectMarketPrices(
        { make: 'Peugeot', model: '', year: '2021' },
        makeNextData(),
      );
      expect(result.submitted).toBe(false);
    });

    it('retourne submitted=false quand year est vide', async () => {
      const result = await maybeCollectMarketPrices(
        { make: 'Peugeot', model: '3008', year: '' },
        makeNextData(),
      );
      expect(result.submitted).toBe(false);
    });

    it('retourne submitted=false quand region absente du nextData', async () => {
      const nextData = { props: { pageProps: { ad: { location: {} } } } };
      const result = await maybeCollectMarketPrices(currentVehicle, nextData);
      expect(result.submitted).toBe(false);
    });

    it('retourne submitted=false quand le serveur dit collect=false', async () => {
      mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle, false),
      });
      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());
      expect(result.submitted).toBe(false);
    });

    it('retourne submitted=false quand next-job est injoignable', async () => {
      global.fetch = vi.fn().mockRejectedValueOnce(new Error('network'));
      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());
      expect(result.submitted).toBe(false);
    });
  });


  // ── Logique de cooldown (le coeur du bug corrige) ───────────────

  describe('logique de cooldown', () => {
    it('bypass le cooldown pour le vehicule COURANT', async () => {
      // Cooldown actif (5 min ago)
      localStorage.setItem('copilot_last_collect', String(Date.now() - 5 * 60 * 1000));

      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(
          { make: 'Peugeot', model: '3008', year: '2021' },
        ),
        searchHTML: makeSearchHTML([12000, 13000, 14000]),
        submitOk: true,
      });

      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());

      // NE DOIT PAS etre bloque par le cooldown
      expect(result.submitted).toBe(true);
      expect(result.isCurrentVehicle).toBe(true);
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it('bloque la collecte pour un AUTRE vehicule quand cooldown actif', async () => {
      // Cooldown actif (1h ago, bien dans les 24h)
      localStorage.setItem('copilot_last_collect', String(Date.now() - 1 * 60 * 60 * 1000));

      mockFetchSequence({
        jobResponse: makeJobResponse(
          { make: 'Renault', model: 'Clio', year: '2020' },
        ),
      });

      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());

      // DOIT etre bloque
      expect(result.submitted).toBe(false);
    });

    it('autorise la collecte pour un AUTRE vehicule quand cooldown expire', async () => {
      // Cooldown expire (25h ago)
      localStorage.setItem('copilot_last_collect', String(Date.now() - 25 * 60 * 60 * 1000));

      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(
          { make: 'Renault', model: 'Clio', year: '2020' },
        ),
        searchHTML: makeSearchHTML([10000, 11000, 12000]),
        submitOk: true,
      });

      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());

      expect(result.submitted).toBe(true);
      expect(result.isCurrentVehicle).toBe(false);
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it('traite absence de localStorage comme cooldown expire', async () => {
      // Pas de copilot_last_collect du tout
      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(
          { make: 'Renault', model: 'Clio', year: '2020' },
        ),
        searchHTML: makeSearchHTML([10000, 11000, 12000]),
        submitOk: true,
      });

      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());

      expect(result.submitted).toBe(true);
      expect(result.isCurrentVehicle).toBe(false);
    });
  });


  // ── Detection isCurrentVehicle (case-insensitive) ───────────────

  describe('detection isCurrentVehicle', () => {
    it('matche case-insensitive (PEUGEOT == Peugeot)', async () => {
      mockFetchSequence({
        jobResponse: makeJobResponse(
          { make: 'PEUGEOT', model: '3008', year: '2021' },
        ),
        searchHTML: makeSearchHTML([12000, 13000, 14000]),
        submitOk: true,
      });

      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());
      expect(result.isCurrentVehicle).toBe(true);
    });

    it('modele different = pas vehicule courant', async () => {
      // Cooldown expire pour permettre la collecte d'un autre vehicule
      localStorage.setItem('copilot_last_collect', String(Date.now() - 25 * 60 * 60 * 1000));

      mockFetchSequence({
        jobResponse: makeJobResponse(
          { make: 'Peugeot', model: '208', year: '2021' },
        ),
        searchHTML: makeSearchHTML([8000, 9000, 10000]),
        submitOk: true,
      });

      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());
      expect(result.isCurrentVehicle).toBe(false);
    });
  });


  // ── Persistence localStorage ────────────────────────────────────

  describe('persistence localStorage', () => {
    it('sauvegarde copilot_last_collect apres collecte reussie', async () => {
      const before = Date.now();

      mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle),
        searchHTML: makeSearchHTML([12000, 13000, 14000]),
        submitOk: true,
      });

      await maybeCollectMarketPrices(currentVehicle, makeNextData());

      const stored = parseInt(localStorage.getItem('copilot_last_collect'), 10);
      expect(stored).toBeGreaterThanOrEqual(before);
      expect(stored).toBeLessThanOrEqual(Date.now());
    });

    it('sauvegarde le timestamp meme avec moins de 3 prix', async () => {
      const tooFew = makeSearchHTML([12000, 13000]); // seulement 2
      mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle),
        searchHTMLs: [tooFew, tooFew], // 2 strategies, aucune suffisante
      });

      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());

      expect(result.submitted).toBe(false);
      expect(localStorage.getItem('copilot_last_collect')).not.toBeNull();
    });

    it('sauvegarde le timestamp meme quand le POST echoue', async () => {
      mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle),
        searchHTML: makeSearchHTML([12000, 13000, 14000]),
        submitOk: false,
      });

      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());

      expect(result.submitted).toBe(false);
      expect(localStorage.getItem('copilot_last_collect')).not.toBeNull();
    });
  });


  // ── Verification des appels fetch ───────────────────────────────

  describe('appels fetch', () => {
    it('construit URL next-job avec parametres encodes', async () => {
      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle, false),
      });

      await maybeCollectMarketPrices(currentVehicle, makeNextData());

      const url = fetchMock.mock.calls[0][0];
      expect(url).toContain('/market-prices/next-job');
      expect(url).toContain('make=Peugeot');
      expect(url).toContain('model=3008');
      expect(url).toContain('year=2021');
    });

    it('envoie POST /market-prices avec le bon body', async () => {
      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle),
        searchHTML: makeSearchHTML([12000, 13000, 14000, 15000]),
        submitOk: true,
      });

      await maybeCollectMarketPrices(currentVehicle, makeNextData());

      // 3eme appel = POST
      expect(fetchMock).toHaveBeenCalledTimes(3);
      const postCall = fetchMock.mock.calls[2];
      expect(postCall[1].method).toBe('POST');

      const body = JSON.parse(postCall[1].body);
      expect(body.make).toBe('Peugeot');
      expect(body.model).toBe('3008');
      expect(body.year).toBe(2021); // parseInt applique
      expect(body.prices).toEqual([12000, 13000, 14000, 15000]);
      expect(body.fuel).toBe('diesel');
    });

    it('filtre les prix <= 500 de la recherche LBC', async () => {
      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle),
        searchHTML: makeSearchHTML([100, 500, 12000, 13000, 14000]),
        submitOk: true,
      });

      await maybeCollectMarketPrices(currentVehicle, makeNextData());

      const body = JSON.parse(fetchMock.mock.calls[2][1].body);
      expect(body.prices).toEqual([12000, 13000, 14000]);
      expect(body.prices).not.toContain(100);
      expect(body.prices).not.toContain(500);
    });

    it('ne POST pas quand moins de 3 prix valides (toutes strategies epuisees)', async () => {
      const tooFew = makeSearchHTML([12000, 13000]);
      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle),
        searchHTMLs: [tooFew, tooFew], // 2 strategies (rn ±1, rn ±2), aucune suffisante
      });

      await maybeCollectMarketPrices(currentVehicle, makeNextData());

      // next-job + 2 recherches (escalade), pas de POST
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it('utilise u_car_brand et u_car_model dans URL de recherche LBC', async () => {
      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle),
        searchHTML: makeSearchHTML([12000, 13000, 14000]),
        submitOk: true,
      });

      await maybeCollectMarketPrices(currentVehicle, makeNextData());

      const searchUrl = fetchMock.mock.calls[1][0];
      expect(searchUrl).toContain('u_car_brand=PEUGEOT');
      expect(searchUrl).toContain('u_car_model=PEUGEOT_3008');
      expect(searchUrl).not.toContain('text=');
    });

    it('ajoute fuel= a URL de recherche LBC', async () => {
      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle),
        searchHTML: makeSearchHTML([12000, 13000, 14000]),
        submitOk: true,
      });

      await maybeCollectMarketPrices(currentVehicle, makeNextData());

      const searchUrl = fetchMock.mock.calls[1][0];
      expect(searchUrl).toContain('fuel=2'); // diesel = 2
    });

    it('ajoute gearbox= a URL de recherche LBC', async () => {
      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle),
        searchHTML: makeSearchHTML([12000, 13000, 14000]),
        submitOk: true,
      });

      await maybeCollectMarketPrices(currentVehicle, makeNextData());

      const searchUrl = fetchMock.mock.calls[1][0];
      expect(searchUrl).toContain('gearbox=2'); // automatique = 2
    });

    it('ajoute horse_power_din= a URL de recherche LBC', async () => {
      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle),
        searchHTML: makeSearchHTML([12000, 13000, 14000]),
        submitOk: true,
      });

      await maybeCollectMarketPrices(currentVehicle, makeNextData());

      const searchUrl = fetchMock.mock.calls[1][0];
      expect(searchUrl).toContain('horse_power_din=180-max'); // 180ch -> 180-max
    });

    it('ajoute le parametre region rn_XX a URL quand pas de geo-location', async () => {
      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle, true, 'Île-de-France'),
        searchHTML: makeSearchHTML([12000, 13000, 14000]),
        submitOk: true,
      });

      await maybeCollectMarketPrices(currentVehicle, makeNextData());

      const searchUrl = fetchMock.mock.calls[1][0];
      expect(searchUrl).toContain('locations=rn_12');
    });

    it('utilise geo-location city+rayon quand lat/lng disponibles', async () => {
      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle, true, 'Auvergne-Rhône-Alpes'),
        searchHTML: makeSearchHTML([12000, 13000, 14000]),
        submitOk: true,
      });

      const nextData = makeNextData({
        location: {
          city: 'Vienne',
          zipcode: '38200',
          lat: 45.52172,
          lng: 4.87245,
          region_name: 'Auvergne-Rhône-Alpes',
        },
      });

      await maybeCollectMarketPrices(currentVehicle, nextData);

      const searchUrl = fetchMock.mock.calls[1][0];
      expect(searchUrl).toContain('locations=Vienne_38200__45.52172_4.87245_5000_30000');
      expect(searchUrl).not.toContain('rn_');
    });
  });


  // ── Test de regression : le bug exact corrige aujourd'hui ───────

  describe('regression: cooldown ne bloque pas le vehicule courant', () => {
    it('collecte meme avec cooldown recent pour le vehicule en cours', async () => {
      // Scenario : l'utilisateur a vu une autre annonce il y a 30 min
      // (cooldown active), maintenant il visite une Peugeot 3008.
      // La collecte NE DOIT PAS etre bloquee.
      const thirtyMinAgo = Date.now() - 30 * 60 * 1000;
      localStorage.setItem('copilot_last_collect', String(thirtyMinAgo));

      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle),
        searchHTML: makeSearchHTML([14000, 15000, 16000, 17000]),
        submitOk: true,
      });

      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());

      // Assertions critiques pour le fix
      expect(result.submitted).toBe(true);
      expect(result.isCurrentVehicle).toBe(true);
      expect(fetchMock).toHaveBeenCalledTimes(3);

      // Le timestamp doit etre rafraichi
      const newTs = parseInt(localStorage.getItem('copilot_last_collect'), 10);
      expect(newTs).toBeGreaterThan(thirtyMinAgo);
    });
  });


  // ── Escalade progressive : geo → region → region+annee elargie ──

  describe('escalade progressive', () => {
    it('utilise geo-location en strategie 1, puis rn_XX si pas assez', async () => {
      const tooFew = makeSearchHTML([12000, 13000]); // 2 prix = pas assez
      const enough = makeSearchHTML([12000, 13000, 14000]); // 3 prix = OK

      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle, true, 'Auvergne-Rhône-Alpes'),
        searchHTMLs: [tooFew, enough], // strategie 1 echoue, strategie 2 reussit
        submitOk: true,
      });

      const nextData = makeNextData({
        region: 'Auvergne-Rhône-Alpes',
        location: {
          city: 'Vienne',
          zipcode: '38200',
          lat: 45.52172,
          lng: 4.87245,
          region_name: 'Auvergne-Rhône-Alpes',
        },
      });

      const result = await maybeCollectMarketPrices(currentVehicle, nextData);

      expect(result.submitted).toBe(true);
      // 4 appels : next-job + search geo + search rn + POST
      expect(fetchMock).toHaveBeenCalledTimes(4);

      // Strategie 1 : geo-location
      const url1 = fetchMock.mock.calls[1][0];
      expect(url1).toContain('locations=Vienne_38200__45.52172_4.87245_5000_30000');

      // Strategie 2 : region rn_XX (fallback)
      const url2 = fetchMock.mock.calls[2][0];
      expect(url2).toContain('locations=rn_');
    });

    it('elargit les annees en strategie 3 (±2 au lieu de ±1)', async () => {
      const tooFew = makeSearchHTML([12000, 13000]); // pas assez
      const enough = makeSearchHTML([11000, 12000, 13000, 14000]); // OK

      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle, true, 'Île-de-France'),
        searchHTMLs: [tooFew, tooFew, enough], // strategies 1+2 echouent, 3 reussit
        submitOk: true,
      });

      const nextData = makeNextData({
        location: {
          city: 'Paris',
          zipcode: '75001',
          lat: 48.8566,
          lng: 2.3522,
          region_name: 'Île-de-France',
        },
      });

      const result = await maybeCollectMarketPrices(currentVehicle, nextData);

      expect(result.submitted).toBe(true);
      // 5 appels : next-job + 3 recherches + POST
      expect(fetchMock).toHaveBeenCalledTimes(5);

      // Strategie 3 : regdate elargi ±2 (2021 → 2019-2023)
      const url3 = fetchMock.mock.calls[3][0];
      expect(url3).toContain('regdate=2019-2023');
      expect(url3).toContain('locations=rn_12');
    });

    it('stoppe des que la premiere strategie a assez de prix', async () => {
      const enough = makeSearchHTML([12000, 13000, 14000, 15000]);

      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle, true, 'Île-de-France'),
        searchHTML: enough, // strategie 1 suffit
        submitOk: true,
      });

      const result = await maybeCollectMarketPrices(currentVehicle, makeNextData());

      expect(result.submitted).toBe(true);
      // 3 appels seulement : next-job + 1 search + POST (pas d'escalade)
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it('sans geo-location, 2 strategies seulement (rn ±1, rn ±2)', async () => {
      const tooFew = makeSearchHTML([12000, 13000]);

      const fetchMock = mockFetchSequence({
        jobResponse: makeJobResponse(currentVehicle, true, 'Île-de-France'),
        searchHTMLs: [tooFew, tooFew], // 2 strategies, aucune suffisante
      });

      // makeNextData() n'a PAS de lat/lng → pas de strategie geo
      await maybeCollectMarketPrices(currentVehicle, makeNextData());

      // 3 appels : next-job + 2 recherches (pas de POST)
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });
  });
});
