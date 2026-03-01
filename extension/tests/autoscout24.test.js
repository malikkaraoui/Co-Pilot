/**
 * Tests pour extension/extractors/autoscout24.js
 *
 * Couvre: URL detection, fuel/transmission mapping, normalizeToAdData,
 * buildBonusSignals.
 *
 * Run: npm run test:extension
 */

import {
  mapFuelType,
  mapTransmission,
  normalizeToAdData,
  buildBonusSignals,
  parseRSCPayload,
  parseJsonLd,
  extractTld,
  extractLang,
  buildSearchUrl,
  toAs24Slug,
  extractAs24SlugsFromSearchUrl,
  parseSearchPrices,
  getAs24GearCode,
  getAs24PowerParams,
  getAs24KmParams,
  getHpRangeString,
  getCantonCenterZip,
  getCantonFromZip,
  getAs24FuelCode,
  parseHpRange,
  AS24_URL_PATTERNS,
  AutoScout24Extractor,
} from '../extractors/autoscout24.js';
import { getExtractor } from '../extractors/index.js';
import { JSDOM } from 'jsdom';


// ── Fixtures ────────────────────────────────────────────────────────

const RSC_VEHICLE = {
  id: 20201676, status: 'activated', conditionType: 'used', vehicleCategory: 'car',
  versionFullName: 'Q5 Sportback 40 TDI S-Line quattro AHK 4x4',
  make: { id: 5, key: 'audi', name: 'AUDI' },
  model: { id: 23, key: 'q5', name: 'Q5' },
  price: 43900, previousPrice: null, listPrice: 87000,
  mileage: 29299, firstRegistrationDate: '2023-12-01', firstRegistrationYear: 2023,
  createdDate: '2026-02-11T09:00:20.284Z', lastModifiedDate: '2026-02-11T09:20:30.037Z',
  bodyType: 'suv', bodyColor: 'gray', interiorColor: 'black', metallic: true,
  doors: 5, seats: 5,
  fuelType: 'mhev-diesel', cubicCapacity: 1968, horsePower: 204, kiloWatts: 150,
  cylinders: 4, gears: 7,
  transmissionType: 'semi-automatic', transmissionTypeGroup: 'automatic',
  driveType: 'all', emissionStandard: 'euro-6d',
  directImport: true, hadAccident: false, inspected: true, tuned: false,
  warranty: { duration: 12, mileage: 20000, type: 'from-delivery' },
  sellerId: 24860,
  images: [{ key: '1.jpg' }, { key: '2.jpg' }, { key: '3.jpg' }],
  teaser: 'Fahrzeug mit Garantie...',
};

const JSON_LD = {
  '@type': 'Car', name: 'AUDI Q5 Sportback',
  brand: { name: 'AUDI' }, model: 'Q5', vehicleModelDate: 2023,
  color: 'gray', numberOfDoors: 5, vehicleSeatingCapacity: 5,
  vehicleTransmission: 'Automatique',
  mileageFromOdometer: { value: 29299, unitCode: 'KMT' },
  vehicleEngine: {
    enginePower: { value: 204, unitText: 'PS' },
    engineDisplacement: { value: 1968, unitCode: 'CMQ' },
    fuelType: 'Diesel',
  },
  offers: {
    price: 43900, priceCurrency: 'CHF',
    seller: {
      '@type': 'AutoDealer', name: 'I.B.A. Automobile AG',
      telephone: '+41628929454',
      address: { addressLocality: 'Niederlenz', postalCode: '5702' },
      aggregateRating: { ratingValue: 4.7, reviewCount: 151 },
    },
  },
};


// ── 1. URL detection ────────────────────────────────────────────────

describe('AS24_URL_PATTERNS', () => {
  function matchesAny(url) {
    return AS24_URL_PATTERNS.some((p) => p.test(url));
  }

  it('matches autoscout24.ch ad page', () => {
    expect(matchesAny('https://www.autoscout24.ch/fr/d/audi-q5-sportback-20201676')).toBe(true);
  });

  it('matches autoscout24.de ad page', () => {
    expect(matchesAny('https://www.autoscout24.de/angebote/bmw-320-12345')).toBe(true);
  });

  it('does NOT match leboncoin.fr', () => {
    expect(matchesAny('https://www.leboncoin.fr/ad/voitures/12345')).toBe(false);
  });

  it('does NOT match autoscout24 search page', () => {
    expect(matchesAny('https://www.autoscout24.ch/fr?makeModelVersions=123')).toBe(false);
  });
});


// ── 2. mapFuelType ──────────────────────────────────────────────────

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

  it('returns unknown values as-is', () => {
    expect(mapFuelType('banana')).toBe('banana');
  });
});


// ── 3. mapTransmission ──────────────────────────────────────────────

describe('mapTransmission', () => {
  it('maps automatic to Automatique', () => {
    expect(mapTransmission('automatic')).toBe('Automatique');
  });

  it('maps manual to Manuelle', () => {
    expect(mapTransmission('manual')).toBe('Manuelle');
  });

  it('maps semi-automatic to Automatique', () => {
    expect(mapTransmission('semi-automatic')).toBe('Automatique');
  });
});


// ── 4. normalizeToAdData ────────────────────────────────────────────

describe('normalizeToAdData', () => {
  it('normalizes full RSC data', () => {
    const ad = normalizeToAdData(RSC_VEHICLE, JSON_LD);

    expect(ad.make).toBe('AUDI');
    expect(ad.model).toBe('Q5');
    expect(ad.year_model).toBe(2023);
    expect(ad.price_eur).toBe(43900);
    expect(ad.currency).toBe('CHF');
    expect(ad.mileage_km).toBe(29299);
    expect(ad.fuel).toBe('Diesel');
    expect(ad.gearbox).toBe('Automatique');
    expect(ad.power_din_hp).toBe(204);
    expect(ad.image_count).toBe(3);
    expect(ad.description).toBe('Fahrzeug mit Garantie...');
    expect(ad.publication_date).toBe('2026-02-11T09:00:20.284Z');
    expect(ad.owner_type).toBe('pro');
  });

  it('falls back to JSON-LD when RSC is null', () => {
    const ad = normalizeToAdData(null, JSON_LD);

    expect(ad.make).toBe('AUDI');
    expect(ad.model).toBe('Q5');
    expect(ad.year_model).toBe(2023);
    expect(ad.price_eur).toBe(43900);
    expect(ad.currency).toBe('CHF');
    expect(ad.mileage_km).toBe(29299);
    expect(ad.fuel).toBe('Diesel');
    expect(ad.gearbox).toBe('Automatique');
    expect(ad.power_din_hp).toBe(204);
    expect(ad.owner_type).toBe('pro');
    expect(ad.phone).toBe('+41628929454');
  });

  it('counts images from JSON-LD when RSC is null', () => {
    const ldWithImages = {
      ...JSON_LD,
      image: ['img1.jpg', 'img2.jpg', 'img3.jpg', 'img4.jpg', 'img5.jpg'],
    };
    const ad = normalizeToAdData(null, ldWithImages);
    expect(ad.image_count).toBe(5);
  });

  it('extracts dealer_rating from JSON-LD when RSC is null', () => {
    const ad = normalizeToAdData(null, JSON_LD);
    expect(ad.dealer_rating).toBe(4.7);
    expect(ad.dealer_review_count).toBe(151);
  });

  it('falls back to JSON-LD images when RSC images is empty', () => {
    const rscNoImages = { ...RSC_VEHICLE, images: [] };
    const ldWithImages = {
      ...JSON_LD,
      image: Array.from({ length: 23 }, (_, i) => `img${i}.jpg`),
    };
    const ad = normalizeToAdData(rscNoImages, ldWithImages);
    expect(ad.image_count).toBe(23);
  });

  it('handles minimal RSC data with null optional fields', () => {
    const minimal = {
      make: { name: 'BMW' },
      model: { name: '320' },
      price: 15000,
    };
    const ad = normalizeToAdData(minimal, null);

    expect(ad.make).toBe('BMW');
    expect(ad.model).toBe('320');
    expect(ad.price_eur).toBe(15000);
    expect(ad.year_model).toBeNull();
    expect(ad.mileage_km).toBeNull();
    expect(ad.fuel).toBeNull();
    expect(ad.gearbox).toBeNull();
    expect(ad.power_din_hp).toBeNull();
    expect(ad.image_count).toBe(0);
    expect(ad.description).toBeNull();
    expect(ad.publication_date).toBeNull();
    expect(ad.phone).toBeNull();
  });
});


// ── 5. buildBonusSignals ────────────────────────────────────────────

describe('buildBonusSignals', () => {
  it('produces signals from full RSC data', () => {
    const signals = buildBonusSignals(RSC_VEHICLE, JSON_LD);

    const accident = signals.find((s) => s.label === 'Accident');
    expect(accident).toBeDefined();
    expect(accident.value).toContain('Non');
    expect(accident.status).toBe('pass');

    const ct = signals.find((s) => s.label === 'CT');
    expect(ct).toBeDefined();
    expect(ct.status).toBe('pass');

    const warranty = signals.find((s) => s.label === 'Garantie');
    expect(warranty).toBeDefined();
    expect(warranty.value).toContain('12');
    expect(warranty.value).toContain('20000');

    const listPrice = signals.find((s) => s.label === 'Prix catalogue');
    expect(listPrice).toBeDefined();
    expect(listPrice.value).toContain('87000');

    const decote = signals.find((s) => s.label === 'Decote');
    expect(decote).toBeDefined();
    expect(decote.value).toContain('%');

    const rating = signals.find((s) => s.label === 'Note Google');
    expect(rating).toBeDefined();
    expect(rating.value).toContain('4.7');
    expect(rating.value).toContain('151');

    const importSignal = signals.find((s) => s.label === 'Import');
    expect(importSignal).toBeDefined();
    expect(importSignal.status).toBe('warning');
  });

  it('returns empty array for empty RSC', () => {
    const signals = buildBonusSignals({}, {});
    expect(signals).toEqual([]);
  });
});


// ── 6. getExtractor registry (T1) ────────────────────────────────

describe('getExtractor', () => {
  it('returns extractor for AutoScout24 URL', () => {
    const ext = getExtractor('https://www.autoscout24.ch/fr/d/audi-q5-20201676');
    expect(ext).not.toBeNull();
    expect(ext.constructor.SITE_ID).toBe('autoscout24');
  });

  it('returns extractor for LeBonCoin URL', () => {
    const ext = getExtractor('https://www.leboncoin.fr/ad/voitures/12345');
    expect(ext).not.toBeNull();
    expect(ext.constructor.SITE_ID).toBe('leboncoin');
  });

  it('returns null for unknown URL', () => {
    expect(getExtractor('https://www.lacentrale.fr/auto-occasion-123.html')).toBeNull();
    expect(getExtractor('https://www.google.com')).toBeNull();
    expect(getExtractor('')).toBeNull();
  });
});


// ── 7. parseRSCPayload with realistic DOM (T2) ─────────────────

describe('parseRSCPayload', () => {
  it('extracts vehicle from raw JSON in script tag', () => {
    const vehicleJson = JSON.stringify({
      vehicleCategory: 'car',
      make: { name: 'AUDI' },
      model: { name: 'Q5' },
      price: 43900,
      mileage: 29299,
      warranty: { duration: 12, mileage: 20000 },
    });
    const html = `<html><head>
      <script>var data = ${vehicleJson};</script>
    </head><body></body></html>`;
    const dom = new JSDOM(html);
    const result = parseRSCPayload(dom.window.document);
    expect(result).not.toBeNull();
    expect(result.make.name).toBe('AUDI');
    expect(result.model.name).toBe('Q5');
    expect(result.warranty.duration).toBe(12);
  });

  it('extracts vehicle from Next.js RSC Flight payload (self.__next_f.push)', () => {
    const vehicle = {
      vehicleCategory: 'car',
      make: { name: 'ALFA ROMEO', key: 'alfa-romeo' },
      model: { name: 'Giulia', key: 'giulia' },
      price: 34500,
      mileage: 45000,
      firstRegistrationDate: '2020-06-01',
      firstRegistrationYear: 2020,
      fuelType: 'gasoline',
    };
    // In real AS24 pages, RSC Flight textContent has DOUBLE-escaped JSON:
    // self.__next_f.push([1,"...{\\"key\\":\\"val\\"}..."])
    // where \\" are two literal \ chars + " in the textContent
    const rawJson = JSON.stringify(vehicle);
    const doubleEscaped = rawJson.replace(/"/g, '\\\\"');
    const scriptText = 'self.__next_f.push([1,"6:' + doubleEscaped + '"])';

    // Build DOM programmatically to control exact textContent
    const dom = new JSDOM('<html><head></head><body></body></html>');
    const doc = dom.window.document;
    const script = doc.createElement('script');
    script.textContent = scriptText;
    doc.head.appendChild(script);

    const result = parseRSCPayload(doc);
    expect(result).not.toBeNull();
    expect(result.make.name).toBe('ALFA ROMEO');
    expect(result.model.name).toBe('Giulia');
    expect(result.price).toBe(34500);
    expect(result.firstRegistrationYear).toBe(2020);
  });

  it('ignores i18n translation objects with make/model label keys', () => {
    // AS24 pages have an i18n script with labels like {make: "Marque", model: "Modèle"}
    // and vehicleCategory as an object (translations), NOT a string.
    // The parser must skip these and find the real vehicle data.
    const i18n = JSON.stringify({
      make: 'Marque',
      model: 'Modèle',
      vehicleCategory: { car: 'Voitures', motorcycle: 'Motos' },
      year: 'Année',
    });
    const real = JSON.stringify({
      vehicleCategory: 'car',
      make: { name: 'VW' },
      model: { name: 'GOLF' },
      price: 37890,
      mileage: 24700,
      firstRegistrationDate: '2024-11-04',
      firstRegistrationYear: 2024,
    });
    // i18n script comes BEFORE the real data script (like on real AS24 pages)
    const html = `<html><head>
      <script>var labels = ${i18n};</script>
      <script>var listing = ${real};</script>
    </head><body></body></html>`;
    const dom = new JSDOM(html);
    const result = parseRSCPayload(dom.window.document);
    expect(result).not.toBeNull();
    expect(result.make.name).toBe('VW');
    expect(result.model.name).toBe('GOLF');
    expect(result.price).toBe(37890);
  });

  it('returns null when no vehicle data in scripts', () => {
    const html = '<html><head><script>var x = 1;</script></head><body></body></html>';
    const dom = new JSDOM(html);
    expect(parseRSCPayload(dom.window.document)).toBeNull();
  });

  it('handles deeply nested JSON with balanced braces', () => {
    const vehicleJson = JSON.stringify({
      vehicleCategory: 'car',
      make: { id: 5, name: 'BMW' },
      model: { id: 23, name: '320' },
      price: 35000,
      warranty: { duration: 6, mileage: 10000, type: 'from-delivery' },
      images: [{ key: '1.jpg' }, { key: '2.jpg' }],
    });
    const html = `<html><head><script>window.__data = ${vehicleJson};</script></head><body></body></html>`;
    const dom = new JSDOM(html);
    const result = parseRSCPayload(dom.window.document);
    expect(result).not.toBeNull();
    expect(result.make.name).toBe('BMW');
    expect(result.warranty.duration).toBe(6);
    expect(result.images).toHaveLength(2);
  });
});


// ── 8. normalizeToAdData with make as string (T3) ──────────────

describe('normalizeToAdData edge cases', () => {
  it('handles RSC make/model as strings instead of objects', () => {
    const rsc = {
      make: 'AUDI',
      model: 'A3',
      price: 25000,
      mileage: 50000,
    };
    const ad = normalizeToAdData(rsc, null);
    expect(ad.make).toBe('AUDI');
    expect(ad.model).toBe('A3');
    expect(ad.price_eur).toBe(25000);
  });

  it('handles mixed: make as object, model as string', () => {
    const rsc = {
      make: { name: 'BMW' },
      model: '320',
      price: 30000,
    };
    const ad = normalizeToAdData(rsc, null);
    expect(ad.make).toBe('BMW');
    expect(ad.model).toBe('320');
  });

  it('falls back to JSON-LD brand when RSC make is null', () => {
    const rsc = { make: null, model: { name: 'Golf' }, price: 20000 };
    const jsonLd = { brand: { name: 'Volkswagen' }, model: 'Golf' };
    const ad = normalizeToAdData(rsc, jsonLd);
    expect(ad.make).toBe('Volkswagen');
    expect(ad.model).toBe('Golf');
  });
});


// ── 9. parseJsonLd edge cases (T7) ─────────────────────────────

describe('parseJsonLd edge cases', () => {
  it('ignores JSON-LD with @type Product (not Car)', () => {
    const html = `<html><head>
      <script type="application/ld+json">${JSON.stringify({
        "@type": "Product",
        "name": "Some product",
      })}</script>
    </head><body></body></html>`;
    const dom = new JSDOM(html);
    expect(parseJsonLd(dom.window.document)).toBeNull();
  });

  it('ignores JSON-LD with @type Vehicle (not Car)', () => {
    const html = `<html><head>
      <script type="application/ld+json">${JSON.stringify({
        "@type": "Vehicle",
        "name": "Some vehicle",
      })}</script>
    </head><body></body></html>`;
    const dom = new JSDOM(html);
    expect(parseJsonLd(dom.window.document)).toBeNull();
  });

  it('handles malformed JSON-LD gracefully', () => {
    const html = '<html><head><script type="application/ld+json">{invalid json</script></head><body></body></html>';
    const dom = new JSDOM(html);
    expect(parseJsonLd(dom.window.document)).toBeNull();
  });
});


// ── 10. Case-insensitive mapping (NIT-5) ────────────────────────

describe('case-insensitive mapping', () => {
  it('mapFuelType handles uppercase', () => {
    expect(mapFuelType('GASOLINE')).toBe('Essence');
    expect(mapFuelType('Diesel')).toBe('Diesel');
    expect(mapFuelType('ELECTRIC')).toBe('Electrique');
  });

  it('mapTransmission handles uppercase', () => {
    expect(mapTransmission('AUTOMATIC')).toBe('Automatique');
    expect(mapTransmission('Manual')).toBe('Manuelle');
  });

  it('mapFuelType maps cng to GNV (not GPL)', () => {
    expect(mapFuelType('cng')).toBe('GNV');
    expect(mapFuelType('CNG')).toBe('GNV');
    expect(mapFuelType('lpg')).toBe('GPL');
  });
});


// ── 11. extractTld ──────────────────────────────────────────────────

describe('extractTld', () => {
  it('extracts .ch TLD', () => {
    expect(extractTld('https://www.autoscout24.ch/fr/d/audi-q5-20201676')).toBe('ch');
  });

  it('extracts .de TLD', () => {
    expect(extractTld('https://www.autoscout24.de/angebote/bmw-320-12345')).toBe('de');
  });

  it('extracts .fr TLD', () => {
    expect(extractTld('https://www.autoscout24.fr/offres/renault-clio-999')).toBe('fr');
  });

  it('defaults to de for unknown', () => {
    expect(extractTld('https://www.example.com')).toBe('de');
  });
});


// ── 11b. toAs24Slug ──────────────────────────────────────────────────

describe('toAs24Slug', () => {
  it('lowercases and replaces spaces with hyphens', () => {
    expect(toAs24Slug('A 35 AMG')).toBe('a-35-amg');
  });

  it('handles already slugified input', () => {
    expect(toAs24Slug('mercedes-benz')).toBe('mercedes-benz');
  });

  it('removes special characters', () => {
    expect(toAs24Slug('Série 3')).toBe('srie-3');
  });

  it('handles empty/null input', () => {
    expect(toAs24Slug('')).toBe('');
    expect(toAs24Slug(null)).toBe('');
  });

  it('collapses multiple spaces', () => {
    expect(toAs24Slug('Classe  A')).toBe('classe-a');
  });
});

// ── 12. buildSearchUrl ──────────────────────────────────────────────

describe('buildSearchUrl', () => {
  it('builds basic search URL for .ch (SMG format)', () => {
    const url = buildSearchUrl('audi', 'q5', 2023, 'ch');
    expect(url).toContain('autoscout24.ch/fr/s/mo-q5/mk-audi');
    expect(url).toContain('fregfrom=2022');
    expect(url).toContain('fregto=2024');
  });

  it('builds basic search URL for .de (GmbH format)', () => {
    const url = buildSearchUrl('audi', 'q5', 2023, 'de');
    expect(url).toContain('autoscout24.de/lst/audi/q5');
    expect(url).toContain('fregfrom=2022');
    expect(url).toContain('fregto=2024');
  });

  it('includes fuel filter when provided', () => {
    const url = buildSearchUrl('bmw', '320', 2021, 'de', { fuel: 'diesel' });
    expect(url).toContain('fuel=diesel');
  });

  it('applies yearSpread correctly', () => {
    const url = buildSearchUrl('audi', 'a3', 2020, 'fr', { yearSpread: 2 });
    expect(url).toContain('fregfrom=2018');
    expect(url).toContain('fregto=2022');
  });

  it('uses correct TLD domain', () => {
    expect(buildSearchUrl('vw', 'golf', 2022, 'it')).toContain('autoscout24.it');
    expect(buildSearchUrl('vw', 'golf', 2022, 'at')).toContain('autoscout24.at');
  });

  it('includes gear param', () => {
    const url = buildSearchUrl('bmw', '320', 2021, 'ch', { gear: 'A' });
    expect(url).toContain('gear=A');
  });

  it('includes power params with powertype=ps', () => {
    const url = buildSearchUrl('vw', 'golf', 2021, 'ch', { powerfrom: 170, powerto: 260 });
    expect(url).toContain('powerfrom=170');
    expect(url).toContain('powerto=260');
    expect(url).toContain('powertype=ps');
  });

  it('includes km range params', () => {
    const url = buildSearchUrl('audi', 'a3', 2020, 'de', { kmfrom: 20000, kmto: 80000 });
    expect(url).toContain('kmfrom=20000');
    expect(url).toContain('kmto=80000');
  });

  it('includes zip and radius for geo search', () => {
    const url = buildSearchUrl('audi', 'q5', 2023, 'ch', { zip: '1200', radius: 30 });
    expect(url).toContain('zip=1200');
    expect(url).toContain('zipr=30');
  });

  it('includes all params together', () => {
    const url = buildSearchUrl('vw', 'golf', 2021, 'ch', {
      yearSpread: 1, fuel: 'gasoline', gear: 'M',
      powerfrom: 100, powerto: 150, kmfrom: 20000, kmto: 80000,
      zip: '8000', radius: 50,
    });
    expect(url).toContain('fuel=gasoline');
    expect(url).toContain('gear=M');
    expect(url).toContain('powerfrom=100');
    expect(url).toContain('powerto=150');
    expect(url).toContain('kmfrom=20000');
    expect(url).toContain('kmto=80000');
    expect(url).toContain('zip=8000');
    expect(url).toContain('zipr=50');
  });

  it('omits empty params', () => {
    const url = buildSearchUrl('bmw', '320', 2021, 'de', { fuel: null, gear: null });
    expect(url).not.toContain('fuel=');
    expect(url).not.toContain('gear=');
  });

  it('uses SMG /s/mo-/mk- format for .ch with lang', () => {
    const url = buildSearchUrl('vw', 'tiguan', 2016, 'ch', { lang: 'fr' });
    expect(url).toContain('autoscout24.ch/fr/s/mo-tiguan/mk-vw');
  });

  it('uses SMG /s/ format for .ch with de lang', () => {
    const url = buildSearchUrl('audi', 'q5', 2023, 'ch', { lang: 'de' });
    expect(url).toContain('autoscout24.ch/de/s/mo-q5/mk-audi');
  });

  it('uses /lst/ format for .de without lang prefix', () => {
    const url = buildSearchUrl('vw', 'golf', 2022, 'de', { lang: null });
    expect(url).toContain('autoscout24.de/lst/vw/golf');
    expect(url).not.toMatch(/autoscout24\.de\/\w+\/lst/);
  });

  it('defaults to /fr/ for .ch when no lang provided', () => {
    const url = buildSearchUrl('bmw', 'x3', 2020, 'ch');
    expect(url).toContain('autoscout24.ch/fr/s/mo-x3/mk-bmw');
  });

  it('supports brandOnly option (no model in path)', () => {
    const url = buildSearchUrl('mercedes-benz', 'a-35-amg', 2019, 'de', { brandOnly: true });
    expect(url).toContain('autoscout24.de/lst/mercedes-benz?');
    expect(url).not.toContain('a-35-amg');
  });

  it('slugifies make/model with spaces', () => {
    const url = buildSearchUrl('Mercedes-Benz', 'A 35 AMG', 2019, 'de');
    expect(url).toContain('/lst/mercedes-benz/a-35-amg');
  });
});


// ── 12a. extractAs24SlugsFromSearchUrl ─────────────────────────────

describe('extractAs24SlugsFromSearchUrl', () => {
  it('extracts make/model on .ch SMG URLs', () => {
    const parsed = extractAs24SlugsFromSearchUrl(
      'https://www.autoscout24.ch/fr/s/mo-a-35-amg/mk-mercedes-benz?fregfrom=2018'
    );
    expect(parsed).toEqual({ makeSlug: 'mercedes-benz', modelSlug: 'a-35-amg' });
  });

  it('extracts make only on brand-only .ch URL', () => {
    const parsed = extractAs24SlugsFromSearchUrl(
      'https://www.autoscout24.ch/fr/s/mk-mercedes-benz?fregfrom=2018'
    );
    expect(parsed).toEqual({ makeSlug: 'mercedes-benz', modelSlug: null });
  });

  it('extracts make/model on GmbH /lst URLs with lang prefix', () => {
    const parsed = extractAs24SlugsFromSearchUrl(
      'https://www.autoscout24.de/de/lst/bmw/320?fregfrom=2020'
    );
    expect(parsed).toEqual({ makeSlug: 'bmw', modelSlug: '320' });
  });

  it('returns null slugs for unsupported URL', () => {
    const parsed = extractAs24SlugsFromSearchUrl('https://www.example.com/search?q=car');
    expect(parsed).toEqual({ makeSlug: null, modelSlug: null });
  });
});


// ── 12b. extractLang ─────────────────────────────────────────────────

describe('extractLang', () => {
  it('extracts fr from Swiss French URL', () => {
    expect(extractLang('https://www.autoscout24.ch/fr/d/vw-tiguan-123')).toBe('fr');
  });

  it('extracts de from Swiss German URL', () => {
    expect(extractLang('https://www.autoscout24.ch/de/d/bmw-320-456')).toBe('de');
  });

  it('extracts it from Swiss Italian URL', () => {
    expect(extractLang('https://www.autoscout24.ch/it/d/audi-a3-789')).toBe('it');
  });

  it('returns null for URL without lang prefix', () => {
    expect(extractLang('https://www.autoscout24.de/angebote/vw-golf-123')).toBeNull();
  });

  it('extracts nl from Belgian Dutch URL', () => {
    expect(extractLang('https://www.autoscout24.be/nl/d/vw-polo-123')).toBe('nl');
  });
});


// ── 13. parseSearchPrices ───────────────────────────────────────────

describe('parseSearchPrices', () => {
  it('extracts prices from HTML with price+mileage patterns', () => {
    const html = `
      <script>{"price":25000,"mileage":45000,"make":"BMW"}</script>
      <script>{"price":27500,"mileage":38000,"make":"BMW"}</script>
      <script>{"price":23000,"mileage":62000,"make":"BMW"}</script>
    `;
    const results = parseSearchPrices(html);
    expect(results).toHaveLength(3);
    expect(results[0].price).toBe(25000);
    expect(results[0].km).toBe(45000);
    expect(results[1].price).toBe(27500);
  });

  it('filters out prices below 500', () => {
    const html = '<script>{"price":100,"mileage":5000}</script><script>{"price":15000,"mileage":30000}</script>';
    const results = parseSearchPrices(html);
    expect(results).toHaveLength(1);
    expect(results[0].price).toBe(15000);
  });

  it('filters out prices above 500000', () => {
    const html = '<script>{"price":999999,"mileage":5000}</script><script>{"price":15000,"mileage":30000}</script>';
    const results = parseSearchPrices(html);
    expect(results).toHaveLength(1);
  });

  it('deduplicates by price+km', () => {
    const html = `
      <script>{"price":25000,"mileage":45000}</script>
      <script>{"price":25000,"mileage":45000}</script>
      <script>{"price":26000,"mileage":45000}</script>
    `;
    const results = parseSearchPrices(html);
    expect(results).toHaveLength(2);
  });

  it('returns empty array for HTML without listings', () => {
    const html = '<html><body>No results</body></html>';
    expect(parseSearchPrices(html)).toEqual([]);
  });

  // ── JSON-LD OfferCatalog (AS24 SMG / .ch) ──

  it('extracts prices from JSON-LD OfferCatalog (AS24.ch format)', () => {
    const html = `<html><head>
      <script type="application/ld+json">{
        "@type": "Organization",
        "mainEntity": {
          "@type": "WebPageElement",
          "offers": {
            "@type": "OfferCatalog",
            "itemListElement": [
              {
                "@type": "Product",
                "offers": {
                  "@type": "Offer",
                  "price": 53900,
                  "priceCurrency": "CHF",
                  "itemOffered": {
                    "@type": "Car",
                    "mileageFromOdometer": {"@type": "QuantitativeValue", "value": 19845},
                    "vehicleEngine": {"fuelType": "Diesel"},
                    "vehicleModelDate": "2018"
                  }
                }
              },
              {
                "@type": "Product",
                "offers": {
                  "@type": "Offer",
                  "price": 48500,
                  "priceCurrency": "CHF",
                  "itemOffered": {
                    "@type": "Car",
                    "mileageFromOdometer": {"@type": "QuantitativeValue", "value": 85000},
                    "vehicleEngine": {"fuelType": "Diesel"},
                    "vehicleModelDate": "2017"
                  }
                }
              }
            ]
          }
        }
      }</script></head></html>`;
    const results = parseSearchPrices(html);
    expect(results).toHaveLength(2);
    expect(results[0]).toEqual({ price: 53900, year: 2018, km: 19845, fuel: 'Diesel' });
    expect(results[1]).toEqual({ price: 48500, year: 2017, km: 85000, fuel: 'Diesel' });
  });

  it('JSON-LD: filters prices below 500 and above 500000', () => {
    const html = `<html><head><script type="application/ld+json">{
      "@type": "Organization",
      "mainEntity": {"offers": {"@type": "OfferCatalog", "itemListElement": [
        {"@type": "Product", "offers": {"price": 200, "itemOffered": {"mileageFromOdometer": {"value": 1000}}}},
        {"@type": "Product", "offers": {"price": 600000, "itemOffered": {"mileageFromOdometer": {"value": 5000}}}},
        {"@type": "Product", "offers": {"price": 30000, "itemOffered": {"mileageFromOdometer": {"value": 50000}}}}
      ]}}
    }</script></head></html>`;
    const results = parseSearchPrices(html);
    expect(results).toHaveLength(1);
    expect(results[0].price).toBe(30000);
  });

  it('JSON-LD: deduplicates by price+km', () => {
    const html = `<html><head><script type="application/ld+json">{
      "@type": "Organization",
      "mainEntity": {"offers": {"@type": "OfferCatalog", "itemListElement": [
        {"@type": "Product", "offers": {"price": 25000, "itemOffered": {"mileageFromOdometer": {"value": 40000}}}},
        {"@type": "Product", "offers": {"price": 25000, "itemOffered": {"mileageFromOdometer": {"value": 40000}}}},
        {"@type": "Product", "offers": {"price": 26000, "itemOffered": {"mileageFromOdometer": {"value": 40000}}}}
      ]}}
    }</script></head></html>`;
    const results = parseSearchPrices(html);
    expect(results).toHaveLength(2);
  });

  it('JSON-LD: handles missing mileage and fuel gracefully', () => {
    const html = `<html><head><script type="application/ld+json">{
      "@type": "Organization",
      "mainEntity": {"offers": {"@type": "OfferCatalog", "itemListElement": [
        {"@type": "Product", "offers": {"price": 15000, "itemOffered": {}}}
      ]}}
    }</script></head></html>`;
    const results = parseSearchPrices(html);
    expect(results).toHaveLength(1);
    expect(results[0]).toEqual({ price: 15000, year: null, km: null, fuel: null });
  });

  it('prefers RSC results over JSON-LD when RSC has data', () => {
    const html = `
      <script>{"price":20000,"mileage":30000}</script>
      <script type="application/ld+json">{"@type":"Organization","mainEntity":{"offers":{"@type":"OfferCatalog","itemListElement":[{"@type":"Product","offers":{"price":21000,"itemOffered":{"mileageFromOdometer":{"value":31000}}}}]}}}</script>
    `;
    const results = parseSearchPrices(html);
    // RSC found 1 result, so JSON-LD is NOT used
    expect(results).toHaveLength(1);
    expect(results[0].price).toBe(20000);
    expect(results[0].km).toBe(30000);
  });
});


// ── 14. AutoScout24Extractor phone & login ──────────────────────────

describe('AutoScout24Extractor phone & login', () => {
  it('isLoggedIn always returns true (public data)', () => {
    const ext = new AutoScout24Extractor();
    expect(ext.isLoggedIn()).toBe(true);
  });

  it('hasPhone returns true when phone is in ad_data', () => {
    const ext = new AutoScout24Extractor();
    ext._adData = { phone: '+41628929454', make: 'AUDI', model: 'Q5' };
    expect(ext.hasPhone()).toBe(true);
  });

  it('hasPhone returns false when no phone', () => {
    const ext = new AutoScout24Extractor();
    ext._adData = { make: 'AUDI', model: 'Q5' };
    expect(ext.hasPhone()).toBe(false);
  });

  it('hasPhone returns false when adData is null', () => {
    const ext = new AutoScout24Extractor();
    expect(ext.hasPhone()).toBe(false);
  });

  it('revealPhone returns phone from ad_data', async () => {
    const ext = new AutoScout24Extractor();
    ext._adData = { phone: '+41628929454' };
    const phone = await ext.revealPhone();
    expect(phone).toBe('+41628929454');
  });

  it('revealPhone returns null when no phone', async () => {
    const ext = new AutoScout24Extractor();
    ext._adData = {};
    const phone = await ext.revealPhone();
    expect(phone).toBeNull();
  });
});


// ── 15. getAs24GearCode ──────────────────────────────────────────────

describe('getAs24GearCode', () => {
  it('maps automatic to A', () => {
    expect(getAs24GearCode('automatic')).toBe('A');
    expect(getAs24GearCode('Automatique')).toBe('A');
    expect(getAs24GearCode('semi-automatic')).toBe('A');
  });

  it('maps manual to M', () => {
    expect(getAs24GearCode('manual')).toBe('M');
    expect(getAs24GearCode('Manuelle')).toBe('M');
  });

  it('returns null for unknown', () => {
    expect(getAs24GearCode('banana')).toBeNull();
    expect(getAs24GearCode(null)).toBeNull();
    expect(getAs24GearCode('')).toBeNull();
  });
});


// ── 16. getAs24PowerParams ───────────────────────────────────────────

describe('getAs24PowerParams', () => {
  it('returns empty for no hp', () => {
    expect(getAs24PowerParams(0)).toEqual({});
    expect(getAs24PowerParams(null)).toEqual({});
    expect(getAs24PowerParams(-10)).toEqual({});
  });

  it('returns {powerto: 90} for low hp', () => {
    expect(getAs24PowerParams(75)).toEqual({ powerto: 90 });
  });

  it('returns correct range for mid hp', () => {
    expect(getAs24PowerParams(100)).toEqual({ powerfrom: 70, powerto: 120 });
    expect(getAs24PowerParams(136)).toEqual({ powerfrom: 100, powerto: 150 });
  });

  it('returns correct range for GTI hp (245)', () => {
    expect(getAs24PowerParams(245)).toEqual({ powerfrom: 170, powerto: 260 });
  });

  it('returns {powerfrom: 340} for high hp', () => {
    expect(getAs24PowerParams(400)).toEqual({ powerfrom: 340 });
  });
});


// ── 17. getAs24KmParams ──────────────────────────────────────────────

describe('getAs24KmParams', () => {
  it('returns empty for no km', () => {
    expect(getAs24KmParams(0)).toEqual({});
    expect(getAs24KmParams(null)).toEqual({});
  });

  it('returns {kmto: 20000} for low km', () => {
    expect(getAs24KmParams(5000)).toEqual({ kmto: 20000 });
  });

  it('returns correct range for 30k km', () => {
    expect(getAs24KmParams(30000)).toEqual({ kmto: 50000 });
  });

  it('returns full range for mid km', () => {
    expect(getAs24KmParams(50000)).toEqual({ kmfrom: 20000, kmto: 80000 });
  });

  it('returns {kmfrom: 100000} for high km', () => {
    expect(getAs24KmParams(200000)).toEqual({ kmfrom: 100000 });
  });
});


// ── 18. getHpRangeString ─────────────────────────────────────────────

describe('getHpRangeString', () => {
  it('returns null for no hp', () => {
    expect(getHpRangeString(0)).toBeNull();
    expect(getHpRangeString(null)).toBeNull();
  });

  it('returns min-90 for low hp', () => {
    expect(getHpRangeString(75)).toBe('min-90');
  });

  it('returns 100-150 for 136hp', () => {
    expect(getHpRangeString(136)).toBe('100-150');
  });

  it('returns 170-260 for GTI (245hp)', () => {
    expect(getHpRangeString(245)).toBe('170-260');
  });

  it('returns 340-max for high hp', () => {
    expect(getHpRangeString(400)).toBe('340-max');
  });
});


// ── 19. getCantonCenterZip ───────────────────────────────────────────

describe('getCantonCenterZip', () => {
  it('returns 1200 for Geneve', () => {
    expect(getCantonCenterZip('Geneve')).toBe('1200');
  });

  it('returns 8000 for Zurich', () => {
    expect(getCantonCenterZip('Zurich')).toBe('8000');
  });

  it('returns 3000 for Berne', () => {
    expect(getCantonCenterZip('Berne')).toBe('3000');
  });

  it('returns null for unknown canton', () => {
    expect(getCantonCenterZip('Paris')).toBeNull();
    expect(getCantonCenterZip(null)).toBeNull();
  });
});


// ── 20. getCantonFromZip ─────────────────────────────────────────────

describe('getCantonFromZip', () => {
  it('returns Geneve for 1200', () => {
    expect(getCantonFromZip('1200')).toBe('Geneve');
  });

  it('returns Zurich for 8000', () => {
    expect(getCantonFromZip('8000')).toBe('Zurich');
  });

  it('returns Vaud for 1000', () => {
    expect(getCantonFromZip('1000')).toBe('Vaud');
  });

  it('returns null for short zip', () => {
    expect(getCantonFromZip('12')).toBeNull();
  });

  it('returns null for empty', () => {
    expect(getCantonFromZip('')).toBeNull();
    expect(getCantonFromZip(null)).toBeNull();
  });
});


// ─── getAs24FuelCode ─────────────────────────────────────────────────

describe('getAs24FuelCode', () => {
  it('maps RSC diesel to D', () => {
    expect(getAs24FuelCode('diesel')).toBe('D');
  });

  it('maps RSC gasoline to B', () => {
    expect(getAs24FuelCode('gasoline')).toBe('B');
  });

  it('maps RSC electric to E', () => {
    expect(getAs24FuelCode('electric')).toBe('E');
  });

  it('maps French essence to B', () => {
    expect(getAs24FuelCode('essence')).toBe('B');
  });

  it('maps French electrique to E', () => {
    expect(getAs24FuelCode('electrique')).toBe('E');
  });

  it('maps phev-gasoline to 2 (hybrid)', () => {
    expect(getAs24FuelCode('phev-gasoline')).toBe('2');
  });

  it('maps mhev-diesel to D', () => {
    expect(getAs24FuelCode('mhev-diesel')).toBe('D');
  });

  it('is case insensitive', () => {
    expect(getAs24FuelCode('Diesel')).toBe('D');
    expect(getAs24FuelCode('ESSENCE')).toBe('B');
  });

  it('returns null for unknown', () => {
    expect(getAs24FuelCode('unknown')).toBeNull();
    expect(getAs24FuelCode(null)).toBeNull();
    expect(getAs24FuelCode('')).toBeNull();
  });
});


// ─── parseHpRange ────────────────────────────────────────────────────

describe('parseHpRange', () => {
  it('parses 170-260 into powerfrom/powerto', () => {
    expect(parseHpRange('170-260')).toEqual({ powerfrom: 170, powerto: 260 });
  });

  it('parses min-90 into powerto only', () => {
    expect(parseHpRange('min-90')).toEqual({ powerto: 90 });
  });

  it('parses 340-max into powerfrom only', () => {
    expect(parseHpRange('340-max')).toEqual({ powerfrom: 340 });
  });

  it('returns empty for null/empty', () => {
    expect(parseHpRange(null)).toEqual({});
    expect(parseHpRange('')).toEqual({});
  });

  it('returns empty for invalid format', () => {
    expect(parseHpRange('200')).toEqual({});
  });
});


// ─── collectMarketPrices next-job integration ────────────────────────

describe('collectMarketPrices next-job integration', () => {
  function createExtractor(adData, rsc) {
    const ext = new AutoScout24Extractor();
    ext._adData = adData;
    ext._rsc = rsc || null;
    return ext;
  }

  const baseAdData = {
    make: 'AUDI', model: 'Q5', year_model: '2023',
    power_din_hp: 204, mileage_km: 29000,
    fuel: 'Diesel', gearbox: 'Automatique',
    location: { zipcode: '1201', region: 'Geneve' },
    phone: '+41628929454',
  };

  const baseRsc = {
    fuelType: 'diesel', transmissionType: 'automatic',
    make: { key: 'audi', name: 'AUDI' },
    model: { key: 'q5', name: 'Q5' },
  };

  it('returns {submitted: false} when no make/model', async () => {
    const ext = createExtractor({ make: null, model: null, year_model: '2023' });
    ext.initDeps({ fetch: vi.fn(), apiUrl: 'http://localhost:5001/api/analyze' });
    const result = await ext.collectMarketPrices(null);
    expect(result.submitted).toBe(false);
  });

  it('returns {submitted: false} when deps not injected', async () => {
    const ext = createExtractor(baseAdData, baseRsc);
    const result = await ext.collectMarketPrices(null);
    expect(result.submitted).toBe(false);
  });

  it('calls next-job API with correct params', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { collect: false, bonus_jobs: [] } }),
    });

    // Mock window.location for extractTld
    const origLocation = globalThis.window;
    globalThis.window = { location: { href: 'https://www.autoscout24.ch/fr/d/audi-q5-123' } };

    const ext = createExtractor(baseAdData, baseRsc);
    ext.initDeps({ fetch: mockFetch, apiUrl: 'http://localhost:5001/api/analyze' });

    await ext.collectMarketPrices(null);

    // Verify next-job was called
    expect(mockFetch).toHaveBeenCalled();
    const firstCallUrl = mockFetch.mock.calls[0][0];
    expect(firstCallUrl).toContain('/market-prices/next-job');
    expect(firstCallUrl).toContain('make=AUDI');
    expect(firstCallUrl).toContain('model=Q5');
    expect(firstCallUrl).toContain('country=CH');
    expect(firstCallUrl).toContain('region=Geneve');

    globalThis.window = origLocation;
  });

  it('skips cascade when collect=false with no bonus', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { collect: false, bonus_jobs: [] } }),
    });

    globalThis.window = { location: { href: 'https://www.autoscout24.ch/fr/d/audi-q5-123' } };

    const ext = createExtractor(baseAdData, baseRsc);
    ext.initDeps({ fetch: mockFetch, apiUrl: 'http://localhost:5001/api/analyze' });

    const progress = {
      update: vi.fn(),
      addSubStep: vi.fn(),
    };

    const result = await ext.collectMarketPrices(progress);

    expect(result.submitted).toBe(false);
    // Should update job to done, collect/submit/bonus to skip
    expect(progress.update).toHaveBeenCalledWith('job', 'done', expect.any(String));
    expect(progress.update).toHaveBeenCalledWith('collect', 'skip', expect.any(String));
    expect(progress.update).toHaveBeenCalledWith('bonus', 'skip');

    globalThis.window = undefined;
  });

  it('handles next-job error gracefully', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error('Network error'));

    globalThis.window = { location: { href: 'https://www.autoscout24.ch/fr/d/audi-q5-123' } };

    const ext = createExtractor(baseAdData, baseRsc);
    ext.initDeps({ fetch: mockFetch, apiUrl: 'http://localhost:5001/api/analyze' });

    const result = await ext.collectMarketPrices(null);
    expect(result.submitted).toBe(false);

    globalThis.window = undefined;
  });
});


// ─── buildSearchUrl fuel code integration ────────────────────────────

describe('buildSearchUrl with fuel codes', () => {
  it('uses AS24 fuel code D for diesel', () => {
    const url = buildSearchUrl('audi', 'q5', 2023, 'ch', { fuel: 'D' });
    expect(url).toContain('fuel=D');
  });

  it('uses AS24 fuel code B for gasoline', () => {
    const url = buildSearchUrl('bmw', '320', 2022, 'de', { fuel: 'B' });
    expect(url).toContain('fuel=B');
  });
});
