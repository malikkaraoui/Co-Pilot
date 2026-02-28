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

// Minimum prices to submit (raised from 5 for better statistical significance)
const MIN_PRICES = 10;

// Cooldown for collecting OTHER vehicles (24h), same as LBC
const COLLECT_COOLDOWN_MS = 24 * 60 * 60 * 1000;

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

// ── AS24 search parameter helpers ────────────────────────────────────

// AS24 gear codes for search URL
const AS24_GEAR_MAP = {
  automatic: 'A',
  automatique: 'A',
  'semi-automatic': 'A',
  manual: 'M',
  manuelle: 'M',
};

/**
 * Maps a gearbox string to AS24 search gear code ('A' or 'M').
 * @param {string} gearbox
 * @returns {string|null}
 */
export function getAs24GearCode(gearbox) {
  return AS24_GEAR_MAP[(gearbox || '').toLowerCase()] || null;
}

// AS24 search fuel codes (single-letter params accepted by search URLs)
const AS24_FUEL_CODE_MAP = {
  // RSC fuelType keys (English)
  gasoline: 'B', diesel: 'D', electric: 'E',
  cng: 'C', lpg: 'L', hydrogen: 'H',
  'mhev-diesel': 'D', 'mhev-gasoline': 'B',
  'phev-diesel': '2', 'phev-gasoline': '2',
  // French labels (from backend bonus jobs)
  essence: 'B', electrique: 'E',
  gnv: 'C', gpl: 'L', hydrogene: 'H',
  'hybride rechargeable': '2',
};

/**
 * Maps a fuel string (RSC key or French label) to AS24 search fuel code.
 * @param {string} fuel
 * @returns {string|null} e.g. 'D', 'B', 'E'
 */
export function getAs24FuelCode(fuel) {
  return AS24_FUEL_CODE_MAP[(fuel || '').toLowerCase()] || null;
}

/**
 * Returns AS24 power search params {powerfrom, powerto} based on hp.
 * Same bands as LBC getHorsePowerRange() for consistency.
 * @param {number} hp
 * @returns {object} e.g. {powerfrom: 170, powerto: 260}
 */
export function getAs24PowerParams(hp) {
  if (!hp || hp <= 0) return {};
  if (hp < 80)  return { powerto: 90 };
  if (hp < 110) return { powerfrom: 70, powerto: 120 };
  if (hp < 140) return { powerfrom: 100, powerto: 150 };
  if (hp < 180) return { powerfrom: 130, powerto: 190 };
  if (hp < 250) return { powerfrom: 170, powerto: 260 };
  if (hp < 350) return { powerfrom: 240, powerto: 360 };
  return { powerfrom: 340 };
}

/**
 * Returns AS24 mileage search params {kmfrom, kmto} based on km.
 * Same bands as LBC getMileageRange() for consistency.
 * @param {number} km
 * @returns {object} e.g. {kmfrom: 20000, kmto: 80000}
 */
export function getAs24KmParams(km) {
  if (!km || km <= 0) return {};
  if (km <= 10000) return { kmto: 20000 };
  if (km <= 30000) return { kmto: 50000 };
  if (km <= 60000) return { kmfrom: 20000, kmto: 80000 };
  if (km <= 120000) return { kmfrom: 50000, kmto: 150000 };
  return { kmfrom: 100000 };
}

/**
 * Returns hp_range string for the backend payload (same format as LBC).
 * @param {number} hp
 * @returns {string|null} e.g. '170-260'
 */
export function getHpRangeString(hp) {
  if (!hp || hp <= 0) return null;
  if (hp < 80)  return 'min-90';
  if (hp < 110) return '70-120';
  if (hp < 140) return '100-150';
  if (hp < 180) return '130-190';
  if (hp < 250) return '170-260';
  if (hp < 350) return '240-360';
  return '340-max';
}

/**
 * Parses an hp_range string (e.g. '170-260', 'min-90', '340-max')
 * into AS24 power search params {powerfrom, powerto}.
 * @param {string} hpRange
 * @returns {object} e.g. {powerfrom: 170, powerto: 260}
 */
export function parseHpRange(hpRange) {
  if (!hpRange) return {};
  const parts = hpRange.split('-');
  if (parts.length !== 2) return {};
  const result = {};
  if (parts[0] !== 'min') result.powerfrom = parseInt(parts[0], 10);
  if (parts[1] !== 'max') result.powerto = parseInt(parts[1], 10);
  return result;
}

// Canton center ZIP codes for geo-targeted searches (chef-lieu)
const CANTON_CENTER_ZIP = {
  'Zurich': '8000', 'Berne': '3000', 'Lucerne': '6000', 'Uri': '6460',
  'Schwyz': '6430', 'Obwald': '6060', 'Nidwald': '6370', 'Glaris': '8750',
  'Zoug': '6300', 'Fribourg': '1700', 'Soleure': '4500', 'Bale-Ville': '4000',
  'Bale-Campagne': '4410', 'Schaffhouse': '8200',
  'Appenzell Rhodes-Exterieures': '9100', 'Appenzell Rhodes-Interieures': '9050',
  'Saint-Gall': '9000', 'Grisons': '7000', 'Argovie': '5000', 'Thurgovie': '8500',
  'Tessin': '6500', 'Vaud': '1000', 'Valais': '1950', 'Neuchatel': '2000',
  'Geneve': '1200', 'Jura': '2800',
};

/**
 * Returns the center ZIP for a canton (for geo-targeted AS24 searches).
 * @param {string} canton
 * @returns {string|null}
 */
export function getCantonCenterZip(canton) {
  return CANTON_CENTER_ZIP[canton] || null;
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
 * Supports all AS24 search filters: fuel, gear, power, mileage, location.
 *
 * @param {string} makeKey - Lowercase make key (e.g. 'audi')
 * @param {string} modelKey - Lowercase model key (e.g. 'q5')
 * @param {number} year - Target year
 * @param {string} tld - TLD (e.g. 'ch', 'de')
 * @param {object} [options]
 * @param {number} [options.yearSpread=1] - Year range (+/-)
 * @param {string} [options.fuel] - AS24 fuel key (e.g. 'diesel')
 * @param {string} [options.gear] - 'A' or 'M'
 * @param {number} [options.powerfrom] - Min power in PS
 * @param {number} [options.powerto] - Max power in PS
 * @param {number} [options.kmfrom] - Min mileage
 * @param {number} [options.kmto] - Max mileage
 * @param {string} [options.zip] - ZIP code for geo search
 * @param {number} [options.radius] - Radius in km (requires zip)
 * @returns {string}
 */
export function buildSearchUrl(makeKey, modelKey, year, tld, options = {}) {
  const { yearSpread = 1, fuel, gear, powerfrom, powerto, kmfrom, kmto, zip, radius } = options;
  const base = `https://www.autoscout24.${tld}/lst/${makeKey}/${modelKey}`;
  const params = new URLSearchParams({
    fregfrom: String(year - yearSpread),
    fregto: String(year + yearSpread),
    sort: 'standard',
    desc: '0',
    atype: 'C',
    ustate: 'N,U',
  });
  if (fuel) params.set('fuel', fuel);
  if (gear) params.set('gear', gear);
  if (powerfrom) { params.set('powerfrom', String(powerfrom)); params.set('powertype', 'ps'); }
  if (powerto) { params.set('powerto', String(powerto)); params.set('powertype', 'ps'); }
  if (kmfrom) params.set('kmfrom', String(kmfrom));
  if (kmto) params.set('kmto', String(kmto));
  if (zip) { params.set('zip', String(zip)); params.set('zipr', String(radius || 50)); }
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
   * Collects market prices from AS24 search results.
   * Full next-job integration:
   *   1. Ask server which vehicle to collect (next-job API)
   *   2. Run 7-strategy cascade for the target vehicle
   *   3. Submit prices or report failure
   *   4. Execute bonus jobs from the collection queue
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
    const year = parseInt(this._adData.year_model, 10);
    const fuelKey = this._rsc?.fuelType || null;

    // Vehicle specs for search filters
    const hp = parseInt(this._adData.power_din_hp, 10) || 0;
    const km = parseInt(this._adData.mileage_km, 10) || 0;
    const gearRaw = this._rsc?.transmissionType || '';
    const gearCode = getAs24GearCode(gearRaw);
    const hpRangeStr = getHpRangeString(hp);

    // Region = canton for CH, country name for others
    const zipcode = this._adData?.location?.zipcode;
    const canton = (tld === 'ch' && zipcode) ? getCantonFromZip(zipcode) : null;
    const region = canton || countryName;

    // ── 1. Call next-job API ──────────────────────────────────────
    if (progress) progress.update('job', 'running');

    const fuelForJob = this._adData.fuel ? this._adData.fuel.toLowerCase() : '';
    const gearboxForJob = this._adData.gearbox ? this._adData.gearbox.toLowerCase() : '';
    const jobUrl = this._apiUrl.replace('/analyze', '/market-prices/next-job')
      + `?make=${encodeURIComponent(this._adData.make)}&model=${encodeURIComponent(this._adData.model)}`
      + `&year=${encodeURIComponent(year)}&region=${encodeURIComponent(region)}`
      + `&country=${encodeURIComponent(countryCode)}`
      + (fuelForJob ? `&fuel=${encodeURIComponent(fuelForJob)}` : '')
      + (gearboxForJob ? `&gearbox=${encodeURIComponent(gearboxForJob)}` : '')
      + (hpRangeStr ? `&hp_range=${encodeURIComponent(hpRangeStr)}` : '');

    let jobResp;
    try {
      console.log('[CoPilot] AS24 next-job →', jobUrl);
      jobResp = await this._fetch(jobUrl).then((r) => r.json());
      console.log('[CoPilot] AS24 next-job ←', JSON.stringify(jobResp));
    } catch (err) {
      console.warn('[CoPilot] AS24 next-job error:', err);
      if (progress) {
        progress.update('job', 'error', 'Serveur injoignable');
        progress.update('collect', 'skip');
        progress.update('submit', 'skip');
        progress.update('bonus', 'skip');
      }
      return { submitted: false, isCurrentVehicle: false };
    }

    // ── 2. Handle collect=false ───────────────────────────────────
    if (!jobResp?.data?.collect) {
      const queuedJobs = jobResp?.data?.bonus_jobs || [];
      if (queuedJobs.length === 0) {
        if (progress) {
          progress.update('job', 'done', 'Données déjà à jour');
          progress.update('collect', 'skip', 'Non nécessaire');
          progress.update('submit', 'skip');
          progress.update('bonus', 'skip');
        }
        return { submitted: false, isCurrentVehicle: false };
      }
      if (progress) {
        progress.update('job', 'done', `À jour — ${queuedJobs.length} jobs en attente`);
        progress.update('collect', 'skip', 'Véhicule déjà à jour');
        progress.update('submit', 'skip');
      }
      await this._executeBonusJobs(queuedJobs, tld, progress);
      return { submitted: false, isCurrentVehicle: false };
    }

    // ── 3. Determine target vehicle ───────────────────────────────
    const target = jobResp.data.vehicle;
    const targetRegion = jobResp.data.region;
    const isRedirect = !!jobResp.data.redirect;
    const bonusJobs = jobResp.data.bonus_jobs || [];

    const isCurrentVehicle =
      target.make.toLowerCase() === this._adData.make.toLowerCase()
      && target.model.toLowerCase() === this._adData.model.toLowerCase();

    // Cooldown 24h for OTHER vehicles only
    if (!isCurrentVehicle) {
      const lastCollect = parseInt(localStorage.getItem('copilot_last_collect') || '0', 10);
      if (Date.now() - lastCollect < COLLECT_COOLDOWN_MS) {
        if (progress) {
          progress.update('job', 'done', 'Cooldown actif (autre véhicule collecté récemment)');
          progress.update('collect', 'skip', 'Cooldown 24h');
          progress.update('submit', 'skip');
        }
        if (bonusJobs.length > 0) {
          await this._executeBonusJobs(bonusJobs, tld, progress);
        } else if (progress) {
          progress.update('bonus', 'skip');
        }
        return { submitted: false, isCurrentVehicle: false };
      }
    }

    const targetMakeKey = target.make.toLowerCase();
    const targetModelKey = target.model.toLowerCase();
    const targetYear = parseInt(target.year, 10);
    const targetLabel = `${target.make} ${target.model} ${targetYear}`;

    if (progress) {
      progress.update('job', 'done', targetLabel
        + (isCurrentVehicle ? ` (${targetRegion})` : ' (autre véhicule)'));
    }

    // ── 4. Build cascade strategies ───────────────────────────────
    const fuelCode = fuelKey ? getAs24FuelCode(fuelKey) : null;
    const targetCantonZip = getCantonCenterZip(targetRegion);
    const strategies = [];

    if (isCurrentVehicle) {
      // Full 7-strategy cascade with all vehicle-specific filters
      const powerParams = getAs24PowerParams(hp);
      const kmParams = getAs24KmParams(km);

      if (zipcode) {
        strategies.push({
          yearSpread: 1, fuel: fuelCode, gear: gearCode, ...powerParams, ...kmParams,
          zip: zipcode, radius: 30, precision: 5, label: `ZIP ${zipcode} +30km`,
        });
      }
      if (targetCantonZip) {
        strategies.push({
          yearSpread: 1, fuel: fuelCode, gear: gearCode, ...powerParams, ...kmParams,
          zip: targetCantonZip, radius: 50, precision: 4, label: `${targetRegion} ±1an`,
        });
        strategies.push({
          yearSpread: 2, fuel: fuelCode, gear: gearCode, ...powerParams,
          zip: targetCantonZip, radius: 50, precision: 4, label: `${targetRegion} ±2ans`,
        });
      }
      strategies.push({ yearSpread: 1, fuel: fuelCode, gear: gearCode, ...powerParams, precision: 3, label: 'National ±1an' });
      strategies.push({ yearSpread: 2, fuel: fuelCode, gear: gearCode, precision: 3, label: 'National ±2ans' });
      strategies.push({ yearSpread: 2, fuel: fuelCode, precision: 2, label: 'National fuel' });
      strategies.push({ yearSpread: 3, precision: 1, label: 'National large' });
    } else {
      // Simplified cascade for redirect (vehicle specs unknown)
      if (targetCantonZip) {
        strategies.push({
          yearSpread: 1, zip: targetCantonZip, radius: 50,
          precision: 3, label: `${targetRegion} ±1an`,
        });
      }
      strategies.push({ yearSpread: 1, precision: 2, label: 'National ±1an' });
      strategies.push({ yearSpread: 2, precision: 1, label: 'National ±2ans' });
    }

    // ── 5. Execute cascade ────────────────────────────────────────
    let prices = [];
    let usedPrecision = null;
    const searchLog = [];

    if (progress) progress.update('collect', 'running');

    for (let i = 0; i < strategies.length; i++) {
      if (i > 0) await new Promise((r) => setTimeout(r, 600 + Math.random() * 400));

      const { precision, label, ...searchOpts } = strategies[i];
      const searchUrl = buildSearchUrl(targetMakeKey, targetModelKey, targetYear, tld, searchOpts);

      try {
        const resp = await fetch(searchUrl, { credentials: 'same-origin' });
        if (!resp.ok) {
          searchLog.push({ step: i + 1, precision, label, ads_found: 0, url: searchUrl, was_selected: false, reason: `HTTP ${resp.status}` });
          if (progress) progress.addSubStep?.('collect', `Stratégie ${i + 1} · ${label}`, 'skip', `HTTP ${resp.status}`);
          continue;
        }

        const html = await resp.text();
        prices = parseSearchPrices(html);
        const enough = prices.length >= MIN_PRICES;

        console.log('[CoPilot] AS24 strategie %d (precision=%d): %d prix | %s', i + 1, precision, prices.length, searchUrl.substring(0, 150));

        searchLog.push({
          step: i + 1, precision, label, ads_found: prices.length,
          url: searchUrl, was_selected: enough,
          reason: enough ? `${prices.length} >= ${MIN_PRICES}` : `${prices.length} < ${MIN_PRICES}`,
        });

        if (progress) {
          progress.addSubStep?.('collect', `Stratégie ${i + 1} · ${label}`,
            enough ? 'done' : 'skip', `${prices.length} annonces`);
        }

        if (enough) { usedPrecision = precision; break; }
      } catch (err) {
        console.error('[CoPilot] AS24 search error:', err);
        searchLog.push({ step: i + 1, precision, label, ads_found: 0, url: searchUrl, was_selected: false, reason: err.message });
        if (progress) progress.addSubStep?.('collect', `Stratégie ${i + 1} · ${label}`, 'skip', 'Erreur');
      }
    }

    // ── 6. Submit or report failure ───────────────────────────────
    let submitted = false;

    if (prices.length >= MIN_PRICES) {
      let priceInts = prices.map((p) => p.price);
      let priceDetails = prices;
      if (currency === 'CHF') {
        priceInts = priceInts.map((p) => Math.round(p * CHF_TO_EUR));
        priceDetails = prices.map((p) => ({ ...p, price: Math.round(p.price * CHF_TO_EUR) }));
      }

      if (progress) {
        progress.update('collect', 'done', `${priceInts.length} prix (précision ${usedPrecision})`);
        progress.update('submit', 'running');
      }

      const marketUrl = this._apiUrl.replace('/analyze', '/market-prices');
      const payload = {
        make: target.make,
        model: target.model,
        year: targetYear,
        region: targetRegion,
        prices: priceInts,
        price_details: priceDetails,
        fuel: isCurrentVehicle && this._adData.fuel ? this._adData.fuel.toLowerCase() : null,
        precision: usedPrecision,
        country: countryCode,
        hp_range: isCurrentVehicle ? hpRangeStr : null,
        gearbox: isCurrentVehicle && this._adData.gearbox ? this._adData.gearbox.toLowerCase() : null,
        search_log: searchLog,
      };

      try {
        const resp = await this._fetch(marketUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (resp.ok) {
          if (progress) progress.update('submit', 'done', `${priceInts.length} prix envoyés (${targetRegion})`);
          submitted = true;
        } else {
          if (progress) progress.update('submit', 'error', 'Erreur serveur');
        }
      } catch (err) {
        console.error('[CoPilot] AS24 market-prices POST error:', err);
        if (progress) progress.update('submit', 'error', 'Erreur réseau');
      }
    } else {
      if (progress) {
        progress.update('collect', 'warning', `${prices.length} annonces (min ${MIN_PRICES})`);
        progress.update('submit', 'skip', 'Pas assez de données');
      }
      // Report failed search
      try {
        const failedUrl = this._apiUrl.replace('/analyze', '/market-prices/failed-search');
        await this._fetch(failedUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            make: target.make, model: target.model, year: targetYear,
            region: targetRegion,
            fuel: isCurrentVehicle ? (fuelKey || null) : null,
            hp_range: isCurrentVehicle ? hpRangeStr : null,
            country: countryCode, search_log: searchLog,
          }),
        });
      } catch { /* ignore */ }
    }

    // ── 7. Execute bonus jobs ─────────────────────────────────────
    if (bonusJobs.length > 0) {
      await this._executeBonusJobs(bonusJobs, tld, progress);
    } else if (progress) {
      progress.update('bonus', 'skip', 'Pas de jobs bonus');
    }

    // Update cooldown for redirected vehicles
    if (!isCurrentVehicle) {
      localStorage.setItem('copilot_last_collect', String(Date.now()));
    }

    return { submitted, isCurrentVehicle };
  }

  /**
   * Executes bonus collection jobs from the server queue.
   * Each job specifies a vehicle+region to collect prices for.
   * Only executes jobs matching the current site's country.
   *
   * @param {Array} bonusJobs - Jobs from next-job response
   * @param {string} tld - Current site TLD (ch, de, etc.)
   * @param {object} progress - Progress tracker
   */
  async _executeBonusJobs(bonusJobs, tld, progress) {
    const MIN_BONUS_PRICES = 5;
    const marketUrl = this._apiUrl.replace('/analyze', '/market-prices');
    const jobDoneUrl = this._apiUrl.replace('/analyze', '/market-prices/job-done');
    const currency = TLD_TO_CURRENCY[tld] || 'EUR';
    const countryCode = TLD_TO_COUNTRY_CODE[tld] || 'FR';

    if (progress) progress.update('bonus', 'running', `${bonusJobs.length} jobs`);

    for (const job of bonusJobs) {
      // Only execute jobs for the current country
      if ((job.country || 'FR') !== countryCode) {
        console.log('[CoPilot] AS24 bonus skip: country %s != %s', job.country, countryCode);
        await this._reportJobDone(jobDoneUrl, job.job_id, false);
        if (progress) progress.addSubStep?.('bonus', `${job.make} ${job.model}`, 'skip', 'Pays différent');
        continue;
      }

      try {
        await new Promise((r) => setTimeout(r, 800 + Math.random() * 600));

        const jobMakeKey = job.make.toLowerCase();
        const jobModelKey = job.model.toLowerCase();
        const jobYear = parseInt(job.year, 10);
        const cantonZip = getCantonCenterZip(job.region);

        // Build search options from job data
        const searchOpts = { yearSpread: 1 };
        if (job.fuel) {
          const fc = getAs24FuelCode(job.fuel);
          if (fc) searchOpts.fuel = fc;
        }
        if (job.gearbox) {
          const gc = getAs24GearCode(job.gearbox);
          if (gc) searchOpts.gear = gc;
        }
        if (job.hp_range) {
          const pp = parseHpRange(job.hp_range);
          Object.assign(searchOpts, pp);
        }
        if (cantonZip) {
          searchOpts.zip = cantonZip;
          searchOpts.radius = 50;
        }

        const searchUrl = buildSearchUrl(jobMakeKey, jobModelKey, jobYear, tld, searchOpts);
        const resp = await fetch(searchUrl, { credentials: 'same-origin' });

        if (!resp.ok) {
          await this._reportJobDone(jobDoneUrl, job.job_id, false);
          if (progress) progress.addSubStep?.('bonus', `${job.make} ${job.model} · ${job.region}`, 'skip', `HTTP ${resp.status}`);
          continue;
        }

        const html = await resp.text();
        const prices = parseSearchPrices(html);

        console.log('[CoPilot] AS24 bonus %s %s %d %s: %d prix', job.make, job.model, jobYear, job.region, prices.length);

        if (prices.length >= MIN_BONUS_PRICES) {
          let priceInts = prices.map((p) => p.price);
          let priceDetails = prices;
          if (currency === 'CHF') {
            priceInts = priceInts.map((p) => Math.round(p * CHF_TO_EUR));
            priceDetails = prices.map((p) => ({ ...p, price: Math.round(p.price * CHF_TO_EUR) }));
          }

          const bonusPrecision = prices.length >= 20 ? 4 : 2;
          const bonusPayload = {
            make: job.make, model: job.model, year: jobYear,
            region: job.region, prices: priceInts, price_details: priceDetails,
            fuel: job.fuel || null, hp_range: job.hp_range || null,
            precision: bonusPrecision, country: countryCode,
            search_log: [{
              step: 1, precision: bonusPrecision,
              location_type: cantonZip ? 'canton' : 'national',
              year_spread: 1,
              filters_applied: [
                ...(searchOpts.fuel ? ['fuel'] : []),
                ...(searchOpts.gear ? ['gearbox'] : []),
                ...(searchOpts.powerfrom || searchOpts.powerto ? ['hp'] : []),
              ],
              ads_found: prices.length, url: searchUrl,
              was_selected: true, reason: `bonus job: ${prices.length} annonces`,
            }],
          };

          const postResp = await this._fetch(marketUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bonusPayload),
          });
          await this._reportJobDone(jobDoneUrl, job.job_id, postResp.ok);
          if (progress) progress.addSubStep?.('bonus', `${job.make} ${job.model} · ${job.region}`, 'done', `${priceInts.length} prix`);
        } else {
          await this._reportJobDone(jobDoneUrl, job.job_id, false);
          if (progress) progress.addSubStep?.('bonus', `${job.make} ${job.model} · ${job.region}`, 'skip', `${prices.length} annonces`);
        }
      } catch (err) {
        console.warn('[CoPilot] AS24 bonus job error:', err);
        await this._reportJobDone(jobDoneUrl, job.job_id, false);
        if (progress) progress.addSubStep?.('bonus', `${job.make} ${job.model} · ${job.region}`, 'skip', 'Erreur');
      }
    }

    if (progress) progress.update('bonus', 'done');
  }

  /**
   * Reports a bonus job as done/failed to the server.
   * @param {string} jobDoneUrl
   * @param {number} jobId
   * @param {boolean} success
   */
  async _reportJobDone(jobDoneUrl, jobId, success) {
    if (!jobId) return;
    try {
      await this._fetch(jobDoneUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId, success }),
      });
    } catch { /* ignore */ }
  }
}
