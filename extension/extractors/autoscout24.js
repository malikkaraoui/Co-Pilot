/**
 * AutoScout24 Extractor
 *
 * Extrait les donnees vehicule depuis les pages d'annonces AutoScout24
 * (.ch, .de, .fr, .it, .at, .be, .nl, .es).
 *
 * Deux sources de donnees:
 * 1. RSC payload (React Server Components) -- richest data
 * 2. JSON-LD structured data -- fallback
 */

import { SiteExtractor } from './base.js';

// ── URL patterns ────────────────────────────────────────────────────

export const AS24_URL_PATTERNS = [
  /autoscout24\.\w+\/(?:fr|de|it|en|nl|es)?\/?d\//,
  /autoscout24\.\w+\/angebote\//,
  /autoscout24\.\w+\/offerte\//,
  /autoscout24\.\w+\/ofertas\//,
  /autoscout24\.\w+\/aanbod\//,
];

const AD_PAGE_PATTERN = /autoscout24\.\w+\/.*\/d\/.*-\d+/;

// TLD → country mapping for region field
const TLD_TO_COUNTRY = {
  ch: 'Suisse',
  de: 'Allemagne',
  fr: 'France',
  it: 'Italie',
  at: 'Autriche',
  be: 'Belgique',
  nl: 'Pays-Bas',
  es: 'Espagne',
};

// TLD → currency
const TLD_TO_CURRENCY = {
  ch: 'CHF',
};

// CHF → EUR rate (same as backend currency_service.py)
const CHF_TO_EUR = 0.94;

// TLD → ISO country code (for backend MarketPrice.country)
const TLD_TO_COUNTRY_CODE = {
  ch: 'CH', de: 'DE', fr: 'FR', it: 'IT',
  at: 'AT', be: 'BE', nl: 'NL', es: 'ES',
};

// Swiss ZIP prefix (2 digits) → canton name (French, matching backend SWISS_CANTONS)
const SWISS_ZIP_TO_CANTON = {
  '10': 'Vaud', '11': 'Vaud', '12': 'Geneve', '13': 'Vaud',
  '14': 'Vaud', '15': 'Vaud', '16': 'Fribourg', '17': 'Fribourg',
  '18': 'Vaud', '19': 'Valais',
  '20': 'Neuchatel', '21': 'Neuchatel', '22': 'Neuchatel', '23': 'Neuchatel',
  '24': 'Jura', '25': 'Berne', '26': 'Berne', '27': 'Jura',
  '28': 'Jura', '29': 'Jura',
  '30': 'Berne', '31': 'Berne', '32': 'Berne', '33': 'Berne',
  '34': 'Berne', '35': 'Berne', '36': 'Berne', '37': 'Berne',
  '38': 'Berne', '39': 'Valais',
  '40': 'Bale-Ville', '41': 'Bale-Campagne', '42': 'Bale-Campagne',
  '43': 'Argovie', '44': 'Bale-Campagne', '45': 'Soleure', '46': 'Soleure',
  '47': 'Soleure', '48': 'Argovie', '49': 'Berne',
  '50': 'Argovie', '51': 'Argovie', '52': 'Argovie', '53': 'Argovie',
  '54': 'Argovie', '55': 'Argovie', '56': 'Argovie', '57': 'Argovie',
  '58': 'Argovie', '59': 'Argovie',
  '60': 'Lucerne', '61': 'Lucerne', '62': 'Lucerne',
  '63': 'Zoug', '64': 'Schwyz', '65': 'Obwald',
  '66': 'Tessin', '67': 'Tessin', '68': 'Tessin', '69': 'Tessin',
  '70': 'Grisons', '71': 'Grisons', '72': 'Grisons', '73': 'Grisons',
  '74': 'Grisons', '75': 'Grisons', '76': 'Grisons', '77': 'Grisons',
  '78': 'Grisons', '79': 'Grisons',
  '80': 'Zurich', '81': 'Zurich', '82': 'Schaffhouse', '83': 'Zurich',
  '84': 'Zurich', '85': 'Thurgovie', '86': 'Zurich', '87': 'Saint-Gall',
  '88': 'Zurich', '89': 'Saint-Gall',
  '90': 'Saint-Gall', '91': 'Appenzell Rhodes-Exterieures', '92': 'Saint-Gall',
  '93': 'Saint-Gall', '94': 'Saint-Gall', '95': 'Thurgovie', '96': 'Saint-Gall',
  '97': 'Saint-Gall',
};

/**
 * Derives the Swiss canton from a postal code.
 * Uses 2-digit prefix mapping (covers ~95% accuracy).
 * @param {string|number} zipcode
 * @returns {string|null} Canton name or null if not mapped
 */
export function getCantonFromZip(zipcode) {
  const zip = String(zipcode || '').trim();
  if (zip.length < 4) return null;
  const prefix = zip.slice(0, 2);
  return SWISS_ZIP_TO_CANTON[prefix] || null;
}

// Minimum prices to submit
const MIN_PRICES = 5;

// ── Fuel type mapping ───────────────────────────────────────────────

const FUEL_MAP = {
  gasoline: 'Essence',
  diesel: 'Diesel',
  electric: 'Electrique',
  'mhev-diesel': 'Diesel',
  'mhev-gasoline': 'Essence',
  'phev-diesel': 'Hybride Rechargeable',
  'phev-gasoline': 'Hybride Rechargeable',
  cng: 'GNV',
  lpg: 'GPL',
  hydrogen: 'Hydrogene',
};

/**
 * Maps an AutoScout24 fuel type key to a French label.
 * Returns the original value if no mapping exists.
 * @param {string} fuelType
 * @returns {string}
 */
export function mapFuelType(fuelType) {
  const key = (fuelType || '').toLowerCase();
  return FUEL_MAP[key] || fuelType;
}

// ── Transmission mapping ────────────────────────────────────────────

const TRANSMISSION_MAP = {
  automatic: 'Automatique',
  manual: 'Manuelle',
  'semi-automatic': 'Automatique',
};

/**
 * Maps an AutoScout24 transmission key to a French label.
 * Returns the original value if no mapping exists.
 * @param {string} transmission
 * @returns {string}
 */
export function mapTransmission(transmission) {
  const key = (transmission || '').toLowerCase();
  return TRANSMISSION_MAP[key] || transmission;
}

// ── RSC payload parsing (DOM-dependent) ─────────────────────────────

/**
 * Extracts balanced JSON objects from a string starting at each '{'.
 * Uses a brace counter to handle nested objects correctly.
 * @param {string} text
 * @returns {Generator<string>}
 */
function* extractJsonObjects(text) {
  let i = 0;
  while (i < text.length) {
    if (text[i] !== '{') { i++; continue; }
    let depth = 0;
    let inString = false;
    let escape = false;
    const start = i;
    for (let j = i; j < text.length; j++) {
      const ch = text[j];
      if (escape) { escape = false; continue; }
      if (ch === '\\' && inString) { escape = true; continue; }
      if (ch === '"') { inString = !inString; continue; }
      if (inString) continue;
      if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        if (depth === 0) {
          yield text.slice(start, j + 1);
          i = j + 1;
          break;
        }
      }
      if (j === text.length - 1) i = j + 1; // unbalanced, skip
    }
    if (depth !== 0) break; // unbalanced remainder, stop
  }
}

/**
 * Recursively finds a vehicle-like node in nested payloads.
 * @param {unknown} input
 * @param {number} depth
 * @returns {object|null}
 */
function findVehicleNode(input, depth = 0) {
  if (!input || depth > 12) return null;

  if (Array.isArray(input)) {
    for (const item of input) {
      const found = findVehicleNode(item, depth + 1);
      if (found) return found;
    }
    return null;
  }

  if (typeof input !== 'object') return null;

  const obj = input;
  const hasMake = !!(typeof obj.make === 'string' || obj.make?.name);
  const hasModel = !!(typeof obj.model === 'string' || obj.model?.name);
  // Require at least one real vehicle field to avoid matching i18n translation
  // objects that also have make/model keys but as label strings like "Marque"/"Modèle".
  // Real vehicle nodes always have vehicleCategory as a string ("car"), price as a number,
  // or firstRegistrationDate as a string.
  const isRealVehicle = (
    typeof obj.vehicleCategory === 'string'
    || typeof obj.price === 'number'
    || typeof obj.firstRegistrationDate === 'string'
    || typeof obj.mileage === 'number'
  );
  if (hasMake && hasModel && isRealVehicle) return obj;

  for (const value of Object.values(obj)) {
    const found = findVehicleNode(value, depth + 1);
    if (found) return found;
  }
  return null;
}

function parseLooselyJsonLd(text) {
  const cleaned = String(text || '')
    .trim()
    .replace(/^<!--\s*/, '')
    .replace(/\s*-->$/, '')
    .trim();

  if (!cleaned) return null;
  try {
    return JSON.parse(cleaned);
  } catch {
    return null;
  }
}

function isVehicleLikeLdNode(node) {
  if (!node || typeof node !== 'object') return false;

  const type = String(node['@type'] || '').toLowerCase();
  if (type === 'car') return true;

  const hasMake = !!(node.brand?.name || node.brand);
  const hasModel = !!node.model;
  if (type === 'vehicle') return hasMake && hasModel;

  const hasSignals = !!(node.offers || node.vehicleModelDate || node.mileageFromOdometer || node.vehicleEngine);
  return hasMake && hasModel && hasSignals;
}

function findVehicleLikeLdNode(input, depth = 0) {
  if (!input || depth > 12) return null;

  if (Array.isArray(input)) {
    for (const item of input) {
      const found = findVehicleLikeLdNode(item, depth + 1);
      if (found) return found;
    }
    return null;
  }

  if (typeof input !== 'object') return null;
  if (isVehicleLikeLdNode(input)) return input;

  if (Array.isArray(input['@graph'])) {
    for (const item of input['@graph']) {
      const found = findVehicleLikeLdNode(item, depth + 1);
      if (found) return found;
    }
  }

  for (const value of Object.values(input)) {
    const found = findVehicleLikeLdNode(value, depth + 1);
    if (found) return found;
  }
  return null;
}

function extractMakeModelFromUrl(url) {
  try {
    const u = new URL(url);
    const match = u.pathname.match(/\/d\/([^/]+)-(\d+)(?:\/|$)/i);
    if (!match) return { make: null, model: null };

    const slug = decodeURIComponent(match[1] || '');
    const tokens = slug.split('-').filter(Boolean);
    if (!tokens.length) return { make: null, model: null };

    return {
      make: tokens[0] ? tokens[0].toUpperCase() : null,
      model: tokens[1] ? tokens[1].toUpperCase() : null,
    };
  } catch {
    return { make: null, model: null };
  }
}

function fallbackAdDataFromDom(doc, url) {
  const h1 = doc.querySelector('h1')?.textContent?.trim() || null;
  const title = h1 || doc.querySelector('meta[property="og:title"]')?.getAttribute('content') || doc.title || null;
  const priceMeta = doc.querySelector('meta[property="product:price:amount"]')?.getAttribute('content');
  const price = priceMeta ? Number(String(priceMeta).replace(/[^\d.]/g, '')) : null;
  const currency = doc.querySelector('meta[property="product:price:currency"]')?.getAttribute('content') || null;
  const fromUrl = extractMakeModelFromUrl(url);

  return {
    title,
    price_eur: Number.isFinite(price) ? price : null,
    currency,
    make: fromUrl.make,
    model: fromUrl.model,
    year_model: null,
    mileage_km: null,
    fuel: null,
    gearbox: null,
    doors: null,
    seats: null,
    first_registration: null,
    color: null,
    power_fiscal_cv: null,
    power_din_hp: null,
    location: {
      city: null,
      zipcode: null,
      department: null,
      region: null,
      lat: null,
      lng: null,
    },
    phone: null,
    description: null,
    owner_type: 'private',
    owner_name: null,
    siret: null,
    raw_attributes: {},
    image_count: 0,
    has_phone: false,
    has_urgent: false,
    has_highlight: false,
    has_boost: false,
    publication_date: null,
    days_online: null,
    index_date: null,
    days_since_refresh: null,
    republished: false,
    lbc_estimation: null,
  };
}

/**
 * Parses the RSC (React Server Components) payload from the page.
 * Searches all script tags for JSON containing vehicle data.
 * Uses balanced brace extraction for robust nested JSON handling.
 * @param {Document} doc
 * @returns {object|null}
 */
export function parseRSCPayload(doc) {
  const scripts = doc.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    // Pre-filter: check keywords without quotes to handle both raw JSON
    // and RSC Flight format where quotes are escaped as \"
    if (!text.includes('vehicleCategory') && !text.includes('firstRegistrationDate')) {
      continue;
    }

    // Next.js RSC Flight payloads wrap data in self.__next_f.push([1,"..."])
    // where JSON quotes are double-escaped as \\" (or sometimes \") in textContent.
    // Strip all backslashes preceding a quote so extractJsonObjects can properly
    // track string boundaries and extract balanced JSON objects.
    const searchText = text.includes('self.__next_f')
      ? text.replace(/\\+"/g, '"')
      : text;

    for (const candidate of extractJsonObjects(searchText)) {
      if (!candidate.includes('"vehicleCategory"') && !candidate.includes('"firstRegistrationDate"')) {
        continue;
      }
      try {
        const parsed = JSON.parse(candidate);
        const vehicle = findVehicleNode(parsed);
        if (vehicle) return vehicle;
      } catch {
        // Not valid JSON, try next candidate
      }
    }
  }
  return null;
}

// ── JSON-LD parsing (DOM-dependent) ─────────────────────────────────

/**
 * Parses JSON-LD structured data from the page.
 * @param {Document} doc
 * @returns {object|null}
 */
export function parseJsonLd(doc) {
  const scripts = doc.querySelectorAll('script[type="application/ld+json"]');
  for (const script of scripts) {
    const data = parseLooselyJsonLd(script.textContent || '');
    if (!data) continue;
    const vehicle = findVehicleLikeLdNode(data);
    if (vehicle) return vehicle;
  }
  return null;
}

// ── Normalize to ad_data ────────────────────────────────────────────

/**
 * Normalizes RSC and/or JSON-LD data into the extract_ad_data() format
 * expected by the backend /api/analyze endpoint.
 *
 * @param {object|null} rsc - RSC vehicle payload
 * @param {object|null} jsonLd - JSON-LD structured data
 * @returns {object}
 */
export function normalizeToAdData(rsc, jsonLd) {
  const ld = jsonLd || {};
  const offers = ld.offers || {};
  const seller = offers.seller || {};
  const sellerAddress = seller.address || {};
  const engine = ld.vehicleEngine || {};

  // Determine owner_type: pro if sellerId exists (RSC) or seller is AutoDealer (JSON-LD)
  function resolveOwnerType() {
    if (rsc && rsc.sellerId) return 'pro';
    if (seller['@type'] === 'AutoDealer') return 'pro';
    return 'private';
  }

  // Resolve make/model: RSC can return string ("AUDI") or object ({name: "AUDI"})
  function resolveMake() {
    if (rsc) {
      const m = typeof rsc.make === 'string' ? rsc.make : rsc.make?.name;
      if (m) return m;
    }
    return ld.brand?.name || (typeof ld.brand === 'string' ? ld.brand : null) || null;
  }
  function resolveModel() {
    if (rsc) {
      const m = typeof rsc.model === 'string' ? rsc.model : rsc.model?.name;
      if (m) return m;
    }
    return ld.model || null;
  }

  // Dealer rating from JSON-LD aggregateRating
  const rating = seller.aggregateRating || {};
  const dealerRating = rating.ratingValue ?? null;
  const dealerReviewCount = rating.reviewCount ?? null;

  // Derive region from ZIP for Swiss ads (canton = region equivalent)
  const zipcode = sellerAddress.postalCode || null;
  const tld = typeof window !== 'undefined' ? extractTld(window.location.href) : null;
  const countryCode = tld ? (TLD_TO_COUNTRY_CODE[tld] || null) : null;
  const derivedRegion = (tld === 'ch' && zipcode) ? getCantonFromZip(zipcode) : null;

  // RSC-first extraction with JSON-LD fallback
  if (rsc) {
    return {
      title: rsc.versionFullName || ld.name || null,
      price_eur: rsc.price ?? offers.price ?? null,
      currency: offers.priceCurrency || null,
      make: resolveMake(),
      model: resolveModel(),
      year_model: rsc.firstRegistrationYear || ld.vehicleModelDate || null,
      mileage_km: rsc.mileage ?? ld.mileageFromOdometer?.value ?? null,
      fuel: rsc.fuelType ? mapFuelType(rsc.fuelType) : (engine.fuelType || null),
      gearbox: rsc.transmissionType
        ? mapTransmission(rsc.transmissionType)
        : (ld.vehicleTransmission || null),
      doors: rsc.doors ?? ld.numberOfDoors ?? null,
      seats: rsc.seats ?? ld.vehicleSeatingCapacity ?? null,
      first_registration: rsc.firstRegistrationDate || null,
      color: rsc.bodyColor || ld.color || null,
      power_fiscal_cv: null,
      power_din_hp: rsc.horsePower ?? engine.enginePower?.value ?? null,
      country: countryCode,
      location: {
        city: sellerAddress.addressLocality || null,
        zipcode,
        department: null,
        region: derivedRegion,
        lat: null,
        lng: null,
      },
      phone: seller.telephone || null,
      description: rsc.teaser || null,
      owner_type: resolveOwnerType(),
      owner_name: seller.name || null,
      siret: null,
      dealer_rating: dealerRating,
      dealer_review_count: dealerReviewCount,
      raw_attributes: {},
      image_count: Array.isArray(rsc.images) && rsc.images.length > 0
        ? rsc.images.length
        : (Array.isArray(ld.image) ? ld.image.length : 0),
      has_phone: Boolean(seller.telephone),
      has_urgent: false,
      has_highlight: false,
      has_boost: false,
      publication_date: rsc.createdDate || null,
      days_online: null,
      index_date: rsc.lastModifiedDate || null,
      days_since_refresh: null,
      republished: false,
      lbc_estimation: null,
    };
  }

  // JSON-LD only (no RSC)
  return {
    title: ld.name || null,
    price_eur: offers.price ?? null,
    currency: offers.priceCurrency || null,
    make: ld.brand?.name || null,
    model: ld.model || null,
    year_model: ld.vehicleModelDate || null,
    mileage_km: ld.mileageFromOdometer?.value ?? null,
    fuel: engine.fuelType || null,
    gearbox: ld.vehicleTransmission || null,
    doors: ld.numberOfDoors ?? null,
    seats: ld.vehicleSeatingCapacity ?? null,
    first_registration: null,
    color: ld.color || null,
    power_fiscal_cv: null,
    power_din_hp: engine.enginePower?.value ?? null,
    country: countryCode,
    location: {
      city: sellerAddress.addressLocality || null,
      zipcode,
      department: null,
      region: derivedRegion,
      lat: null,
      lng: null,
    },
    phone: seller.telephone || null,
    description: null,
    owner_type: resolveOwnerType(),
    owner_name: seller.name || null,
    siret: null,
    dealer_rating: dealerRating,
    dealer_review_count: dealerReviewCount,
    raw_attributes: {},
    image_count: Array.isArray(ld.image) ? ld.image.length : 0,
    has_phone: Boolean(seller.telephone),
    has_urgent: false,
    has_highlight: false,
    has_boost: false,
    publication_date: null,
    days_online: null,
    index_date: null,
    days_since_refresh: null,
    republished: false,
    lbc_estimation: null,
  };
}

// ── Bonus signals ───────────────────────────────────────────────────

/**
 * Builds bonus signals from RSC and JSON-LD data.
 * Each signal has {label, value, status}.
 *
 * @param {object|null} rsc
 * @param {object|null} jsonLd
 * @returns {Array<{label: string, value: string, status: string}>}
 */
export function buildBonusSignals(rsc, jsonLd) {
  const signals = [];
  if (!rsc) return signals;

  // Accident
  if (typeof rsc.hadAccident === 'boolean') {
    signals.push({
      label: 'Accident',
      value: rsc.hadAccident ? 'Oui' : 'Non',
      status: rsc.hadAccident ? 'fail' : 'pass',
    });
  }

  // CT (inspected)
  if (typeof rsc.inspected === 'boolean') {
    signals.push({
      label: 'CT',
      value: rsc.inspected ? 'Passe' : 'Non communique',
      status: rsc.inspected ? 'pass' : 'warning',
    });
  }

  // Warranty
  if (rsc.warranty && rsc.warranty.duration) {
    signals.push({
      label: 'Garantie',
      value: `${rsc.warranty.duration} mois / ${rsc.warranty.mileage || '?'} km`,
      status: 'pass',
    });
  }

  // List price + decote
  if (rsc.listPrice && rsc.price) {
    signals.push({
      label: 'Prix catalogue',
      value: `${rsc.listPrice} EUR`,
      status: 'info',
    });
    const decote = Math.round((1 - rsc.price / rsc.listPrice) * 100);
    signals.push({
      label: 'Decote',
      value: `${decote}%`,
      status: 'info',
    });
  }

  // Google rating from seller
  const ld = jsonLd || {};
  const seller = ld.offers?.seller || {};
  const rating = seller.aggregateRating;
  if (rating && rating.ratingValue) {
    signals.push({
      label: 'Note Google',
      value: `${rating.ratingValue}/5 (${rating.reviewCount} avis)`,
      status: 'info',
    });
  }

  // Direct import
  if (rsc.directImport === true) {
    signals.push({
      label: 'Import',
      value: 'Import direct',
      status: 'warning',
    });
  }

  return signals;
}

// ── Search helpers for market price collection ──────────────────────

/**
 * Extracts the TLD from an AutoScout24 URL.
 * @param {string} url
 * @returns {string} e.g. 'ch', 'de', 'fr'
 */
export function extractTld(url) {
  const match = url.match(/autoscout24\.(\w+)/);
  return match ? match[1] : 'de';
}

/**
 * Builds an AutoScout24 search URL for similar vehicles.
 * @param {string} makeKey - Lowercase make key (e.g. 'audi')
 * @param {string} modelKey - Lowercase model key (e.g. 'q5')
 * @param {number} year - Target year
 * @param {string} tld - TLD (e.g. 'ch', 'de')
 * @param {object} [options]
 * @param {number} [options.yearSpread=1] - Year range (+/-)
 * @param {string} [options.fuel] - AS24 fuel key (e.g. 'diesel')
 * @returns {string}
 */
export function buildSearchUrl(makeKey, modelKey, year, tld, options = {}) {
  const { yearSpread = 1, fuel } = options;
  const base = `https://www.autoscout24.${tld}/lst/${makeKey}/${modelKey}`;
  const params = new URLSearchParams({
    fregfrom: String(year - yearSpread),
    fregto: String(year + yearSpread),
    sort: 'standard',
    desc: '0',
    atype: 'C',
    'ustate': 'N,U',
  });
  if (fuel) params.set('fuel', fuel);
  return `${base}?${params}`;
}

/**
 * Parses AS24 search result page to extract vehicle prices.
 * Looks for listing data in script tags (RSC/Next.js chunks).
 * @param {string} html - Raw HTML of search page
 * @returns {Array<{price: number, year: number|null, km: number|null, fuel: string|null}>}
 */
export function parseSearchPrices(html) {
  const results = [];
  // AS24 search results embed listing JSON in script tags.
  // Each listing has "price" and "mileage" keys.
  const listingPattern = /"price"\s*:\s*(\d+).*?"mileage"\s*:\s*(\d+)/g;
  let match;
  while ((match = listingPattern.exec(html)) !== null) {
    const price = parseInt(match[1], 10);
    const mileage = parseInt(match[2], 10);
    if (price > 500 && price < 500000) {
      results.push({ price, year: null, km: mileage, fuel: null });
    }
  }

  // Deduplicate by price+km (same listing can appear in multiple RSC chunks)
  const seen = new Set();
  return results.filter((r) => {
    const key = `${r.price}-${r.km}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// ── AutoScout24Extractor class ──────────────────────────────────────

export class AutoScout24Extractor extends SiteExtractor {
  static SITE_ID = 'autoscout24';
  static URL_PATTERNS = AS24_URL_PATTERNS;

  /** @type {object|null} Cached RSC data */
  _rsc = null;
  /** @type {object|null} Cached JSON-LD data */
  _jsonLd = null;
  /** @type {object|null} Cached ad_data */
  _adData = null;

  /**
   * @param {string} url
   * @returns {boolean}
   */
  isAdPage(url) {
    return AD_PAGE_PATTERN.test(url);
  }

  /**
   * Extracts vehicle data from the current page.
   * @returns {Promise<{type: string, source: string, ad_data: object}|null>}
   */
  async extract() {
    this._rsc = parseRSCPayload(document);
    this._jsonLd = parseJsonLd(document);

    if (!this._rsc && !this._jsonLd) {
      this._adData = fallbackAdDataFromDom(document, window.location.href);
      const hasSomeData = Boolean(this._adData.title || this._adData.make || this._adData.model);
      if (!hasSomeData) return null;
      return {
        type: 'normalized',
        source: 'autoscout24',
        ad_data: this._adData,
      };
    }

    this._adData = normalizeToAdData(this._rsc, this._jsonLd);

    return {
      type: 'normalized',
      source: 'autoscout24',
      ad_data: this._adData,
    };
  }

  /**
   * @returns {{make: string, model: string, year: string}|null}
   */
  getVehicleSummary() {
    if (!this._adData) return null;
    return {
      make: this._adData.make || '',
      model: this._adData.model || '',
      year: String(this._adData.year_model || ''),
    };
  }

  /**
   * AS24 phone data is public (JSON-LD), no login needed.
   * @returns {boolean}
   */
  isLoggedIn() {
    return true;
  }

  /**
   * Returns the phone number already extracted from JSON-LD.
   * No DOM interaction needed (unlike LBC where a button click reveals it).
   * @returns {Promise<string|null>}
   */
  async revealPhone() {
    return this._adData?.phone || null;
  }

  /**
   * AS24 ads include the phone in JSON-LD (seller.telephone).
   * @returns {boolean}
   */
  hasPhone() {
    return Boolean(this._adData?.phone);
  }

  /**
   * @returns {Array<{label: string, value: string, status: string}>}
   */
  getBonusSignals() {
    return buildBonusSignals(this._rsc, this._jsonLd);
  }

  /**
   * Collects market prices from AS24 search results for the current vehicle.
   * Fetches a search page, parses prices, converts CHF→EUR if needed,
   * and submits to the backend /api/market-prices endpoint.
   *
   * @param {object} progress - Progress tracker for UI updates
   * @returns {Promise<{submitted: boolean, isCurrentVehicle: boolean}>}
   */
  async collectMarketPrices(progress) {
    if (!this._adData?.make || !this._adData?.model || !this._adData?.year_model) {
      return { submitted: false, isCurrentVehicle: false };
    }
    if (!this._fetch || !this._apiUrl) {
      console.warn('[CoPilot] AS24 collectMarketPrices: deps not injected');
      return { submitted: false, isCurrentVehicle: false };
    }

    const tld = extractTld(window.location.href);
    const countryName = TLD_TO_COUNTRY[tld] || 'Europe';
    const countryCode = TLD_TO_COUNTRY_CODE[tld] || 'FR';
    const currency = TLD_TO_CURRENCY[tld] || 'EUR';
    const makeKey = (this._rsc?.make?.key || this._adData.make).toLowerCase();
    const modelKey = (this._rsc?.model?.key || this._adData.model).toLowerCase();
    const year = parseInt(this._adData.year_model, 10);
    const fuelKey = this._rsc?.fuelType || null;

    // Region = canton for CH, country name for others
    const zipcode = this._adData?.location?.zipcode;
    const canton = (tld === 'ch' && zipcode) ? getCantonFromZip(zipcode) : null;
    const region = canton || countryName;

    if (progress) progress.update('job', 'done', `${this._adData.make} ${this._adData.model} ${year} (${region})`);

    // Strategy 1: precise (same TLD, ±1 year, with fuel)
    // Strategy 2: wider (same TLD, ±2 years, no fuel filter)
    const strategies = [
      { yearSpread: 1, fuel: fuelKey, precision: 4, label: 'précise' },
      { yearSpread: 2, fuel: null, precision: 3, label: 'élargie' },
    ];

    let prices = [];
    let usedPrecision = 3;

    for (const strat of strategies) {
      const searchUrl = buildSearchUrl(makeKey, modelKey, year, tld, {
        yearSpread: strat.yearSpread,
        fuel: strat.fuel,
      });

      if (progress) progress.update('collect', 'running', `Recherche ${strat.label}...`);

      try {
        const resp = await fetch(searchUrl, { credentials: 'same-origin' });
        if (!resp.ok) {
          console.warn(`[CoPilot] AS24 search HTTP ${resp.status}: ${searchUrl}`);
          continue;
        }
        const html = await resp.text();
        prices = parseSearchPrices(html);
        usedPrecision = strat.precision;

        if (prices.length >= MIN_PRICES) {
          if (progress) progress.update('collect', 'done', `${prices.length} annonces trouvées`);
          break;
        }
      } catch (err) {
        console.error('[CoPilot] AS24 search error:', err);
      }
    }

    if (prices.length < MIN_PRICES) {
      if (progress) {
        progress.update('collect', 'warning', `${prices.length} annonces (min ${MIN_PRICES})`);
        progress.update('submit', 'skip', 'Pas assez de données');
        progress.update('bonus', 'skip');
      }
      return { submitted: false, isCurrentVehicle: true };
    }

    // Convert CHF to EUR if needed (market prices must be EUR in backend)
    let priceInts = prices.map((p) => p.price);
    let priceDetails = prices;
    if (currency === 'CHF') {
      priceInts = priceInts.map((p) => Math.round(p * CHF_TO_EUR));
      priceDetails = prices.map((p) => ({
        ...p,
        price: Math.round(p.price * CHF_TO_EUR),
      }));
    }

    // Submit to backend
    if (progress) progress.update('submit', 'running');
    const marketUrl = this._apiUrl.replace('/analyze', '/market-prices');
    const payload = {
      make: this._adData.make,
      model: this._adData.model,
      year,
      region,
      prices: priceInts,
      price_details: priceDetails,
      fuel: this._adData.fuel ? this._adData.fuel.toLowerCase() : null,
      precision: usedPrecision,
      country: countryCode,
    };

    try {
      const resp = await this._fetch(marketUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (resp.ok) {
        if (progress) progress.update('submit', 'done', `${priceInts.length} prix envoyés (${region})`);
        if (progress) progress.update('bonus', 'skip', 'Pas de jobs bonus');
        return { submitted: true, isCurrentVehicle: true };
      }

      const errBody = await resp.json().catch(() => null);
      console.warn('[CoPilot] AS24 market-prices POST failed:', resp.status, errBody);
      if (progress) progress.update('submit', 'error', `Erreur serveur (${resp.status})`);
    } catch (err) {
      console.error('[CoPilot] AS24 market-prices POST error:', err);
      if (progress) progress.update('submit', 'error', 'Erreur réseau');
    }

    if (progress) progress.update('bonus', 'skip');
    return { submitted: false, isCurrentVehicle: true };
  }
}
