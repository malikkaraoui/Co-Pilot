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
  AS24_URL_PATTERNS,
} from '../extractors/autoscout24.js';


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
