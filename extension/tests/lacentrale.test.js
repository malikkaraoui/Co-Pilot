"use strict";

import { describe, it, expect } from 'vitest';
import {
  LC_AD_PAGE_PATTERN, LC_FUEL_MAP, LC_GEARBOX_MAP,
} from '../extractors/lacentrale/constants.js';
import {
  extractGallery, extractTcVars, extractCoteFromDom, extractJsonLd, extractAutovizaUrl,
} from '../extractors/lacentrale/parser.js';
import {
  normalizeToAdData, buildBonusSignals,
} from '../extractors/lacentrale/normalize.js';
import { LaCentraleExtractor } from '../extractors/lacentrale/extractor.js';
import { getExtractor } from '../extractors/index.js';


// ═══════════════════════════════════════════════════════════════════
// 1. URL Detection
// ═══════════════════════════════════════════════════════════════════

describe('LC_AD_PAGE_PATTERN', () => {
  it('matches standard ad URL', () => {
    expect(LC_AD_PAGE_PATTERN.test('https://www.lacentrale.fr/auto-occasion-annonce-87103422544.html')).toBe(true);
  });

  it('rejects listing URL', () => {
    expect(LC_AD_PAGE_PATTERN.test('https://www.lacentrale.fr/listing?energies=dies')).toBe(false);
  });

  it('rejects home page', () => {
    expect(LC_AD_PAGE_PATTERN.test('https://www.lacentrale.fr/')).toBe(false);
  });

  it('rejects cote page', () => {
    expect(LC_AD_PAGE_PATTERN.test('https://www.lacentrale.fr/cote-auto-peugeot-208.html')).toBe(false);
  });
});


// ═══════════════════════════════════════════════════════════════════
// 2. Registry
// ═══════════════════════════════════════════════════════════════════

describe('getExtractor for La Centrale', () => {
  it('returns LaCentraleExtractor for ad URL', () => {
    const ext = getExtractor('https://www.lacentrale.fr/auto-occasion-annonce-87103422544.html');
    expect(ext).not.toBeNull();
    expect(ext.constructor.SITE_ID).toBe('lacentrale');
  });

  it('returns LaCentraleExtractor for lacentrale.fr (site-level match)', () => {
    const ext = getExtractor('https://www.lacentrale.fr/some-other-page');
    // URL_PATTERNS match the site, but isAdPage should reject non-ad pages
    expect(ext).not.toBeNull();
    expect(ext.isAdPage('https://www.lacentrale.fr/some-other-page')).toBe(false);
  });

  // Non-regression: other sites unchanged
  it('still returns LBC for leboncoin.fr', () => {
    const ext = getExtractor('https://www.leboncoin.fr/ad/voitures/123');
    expect(ext).not.toBeNull();
    expect(ext.constructor.SITE_ID).toBe('leboncoin');
  });

  it('still returns AS24 for autoscout24.ch', () => {
    const ext = getExtractor('https://www.autoscout24.ch/fr/d/audi-q5-20201676');
    expect(ext).not.toBeNull();
    expect(ext.constructor.SITE_ID).toBe('autoscout24');
  });
});


// ═══════════════════════════════════════════════════════════════════
// 3. isAdPage
// ═══════════════════════════════════════════════════════════════════

describe('LaCentraleExtractor.isAdPage', () => {
  const ext = new LaCentraleExtractor();

  it('accepts standard ad URL', () => {
    expect(ext.isAdPage('https://www.lacentrale.fr/auto-occasion-annonce-87103422544.html')).toBe(true);
  });

  it('rejects listing URL', () => {
    expect(ext.isAdPage('https://www.lacentrale.fr/listing?energies=dies')).toBe(false);
  });

  it('rejects cote URL', () => {
    expect(ext.isAdPage('https://www.lacentrale.fr/cote-auto-peugeot-208.html')).toBe(false);
  });

  it('rejects other domains', () => {
    expect(ext.isAdPage('https://www.leboncoin.fr/ad/voitures/123')).toBe(false);
  });
});


// ═══════════════════════════════════════════════════════════════════
// 4. Parser — extractGallery
// ═══════════════════════════════════════════════════════════════════

describe('extractGallery', () => {
  it('extracts from shape 1: gallery.data.{classified, vehicle}', () => {
    const win = {
      CLASSIFIED_GALLERY: {
        config: { source: 'LC' },
        data: {
          classified: { price: 9990, mileage: 95000 },
          vehicle: { make: 'PEUGEOT', model: '208' },
          images: { v1: { pictures: [{ id: '1' }, { id: '2' }] } },
        },
      },
    };
    const result = extractGallery(win);
    expect(result).not.toBeNull();
    expect(result.classified.price).toBe(9990);
    expect(result.vehicle.make).toBe('PEUGEOT');
    expect(result.images.v1.pictures).toHaveLength(2);
  });

  it('extracts from shape 2: gallery.{classified, vehicle} (no wrapper)', () => {
    const win = {
      CLASSIFIED_GALLERY: {
        classified: { price: 12000 },
        vehicle: { make: 'RENAULT', model: 'CLIO' },
        images: {},
      },
    };
    const result = extractGallery(win);
    expect(result).not.toBeNull();
    expect(result.classified.price).toBe(12000);
    expect(result.vehicle.make).toBe('RENAULT');
  });

  it('returns null if CLASSIFIED_GALLERY is missing', () => {
    expect(extractGallery({})).toBeNull();
    expect(extractGallery({ CLASSIFIED_GALLERY: null })).toBeNull();
  });

  it('returns null if CLASSIFIED_GALLERY has no classified/vehicle', () => {
    expect(extractGallery({ CLASSIFIED_GALLERY: { data: { something: 'else' } } })).toBeNull();
  });
});


// ═══════════════════════════════════════════════════════════════════
// 5. Parser — extractTcVars
// ═══════════════════════════════════════════════════════════════════

describe('extractTcVars', () => {
  it('extracts tc_vars when present', () => {
    const win = { tc_vars: { rating_count: 262, owner_category: 'professionnel' } };
    const result = extractTcVars(win);
    expect(result.rating_count).toBe(262);
  });

  it('returns empty object when tc_vars is absent', () => {
    expect(extractTcVars({})).toEqual({});
    expect(extractTcVars({ tc_vars: null })).toEqual({});
  });
});


// ═══════════════════════════════════════════════════════════════════
// 6. Parser — extractCoteFromDom
// ═══════════════════════════════════════════════════════════════════

describe('extractCoteFromDom', () => {
  function makeDoc(href) {
    const doc = { querySelector: () => null };
    if (href) {
      doc.querySelector = (sel) => {
        if (sel === 'a[href*="cote-auto"]') return { href };
        return null;
      };
    }
    return doc;
  }

  it('extracts quotation and trustIndex from cote link', () => {
    const doc = makeDoc('https://www.lacentrale.fr/cote-auto-peugeot-208.html?km=95000&price=9990&quotation=12380&trustIndex=2');
    const result = extractCoteFromDom(doc);
    expect(result.quotation).toBe(12380);
    expect(result.trustIndex).toBe(2);
  });

  it('returns nulls when no cote link', () => {
    const result = extractCoteFromDom(makeDoc(null));
    expect(result.quotation).toBeNull();
    expect(result.trustIndex).toBeNull();
  });

  it('returns nulls when quotation param missing', () => {
    const doc = makeDoc('https://www.lacentrale.fr/cote-auto-peugeot-208.html?km=95000');
    const result = extractCoteFromDom(doc);
    expect(result.quotation).toBeNull();
  });
});


// ═══════════════════════════════════════════════════════════════════
// 7. Parser — extractJsonLd
// ═══════════════════════════════════════════════════════════════════

describe('extractJsonLd', () => {
  function makeDoc(scripts) {
    return {
      querySelectorAll: () => scripts.map((content) => ({ textContent: content })),
    };
  }

  it('extracts Car JSON-LD', () => {
    const json = JSON.stringify({ '@type': 'Car', brand: 'Peugeot', model: '208' });
    const result = extractJsonLd(makeDoc([json]));
    expect(result).not.toBeNull();
    expect(result.brand).toBe('Peugeot');
  });

  it('returns null when no JSON-LD scripts', () => {
    expect(extractJsonLd(makeDoc([]))).toBeNull();
  });

  it('returns null when JSON-LD is not Car type', () => {
    const json = JSON.stringify({ '@type': 'Organization', name: 'Test' });
    expect(extractJsonLd(makeDoc([json]))).toBeNull();
  });

  it('handles malformed JSON gracefully', () => {
    expect(extractJsonLd(makeDoc(['not json']))).toBeNull();
  });
});


// ═══════════════════════════════════════════════════════════════════
// 8. Normalize — normalizeToAdData
// ═══════════════════════════════════════════════════════════════════

const SAMPLE_GALLERY = {
  classified: {
    reference: 'W103422544',
    price: 9990,
    mileage: 95000,
    year: '2021',
    firstHand: true,
    averageMileage: 65208,
    mileageBadge: 'OVER_MILEAGE',
    goodDealBadge: 'VERY_GOOD_DEAL',
    customerType: 'PRO',
    visitPlace: '88',
    title: 'PEUGEOT 208 II',
    description: { content: 'Superbe vehicule...', status: 'ACCEPTED' },
    priceVariation: {
      prices: { initial: 9990, current: 9990, isDropping: false },
      displayedAge: 5,
    },
  },
  vehicle: {
    make: 'PEUGEOT',
    model: '208',
    commercialModel: '208',
    label: 'II 1.5 BLUEHDI 100 S&S ACTIVE BUSINESS',
    energy: 'DIESEL',
    gearbox: 'MECANIQUE',
    powerDin: 102,
    fiscalHorsePower: 5,
    nbOfDoors: 5,
    externalColor: 'blanc',
    nbOfOwners: 1,
    firstTrafficDate: '2021-07-23',
    international: false,
    critair: { critairLevel: '2', standardMet: 'EURO6' },
    seatingCapacity: 5,
  },
  images: { v1: { pictures: [{ id: '1' }, { id: '2' }, { id: '3' }] } },
};

const SAMPLE_TC_VARS = {
  owner_category: 'professionnel',
  warranty_duration: '6',
  rating_count: 262,
  rating_satisfaction: 5,
  badge_maintenance: ['entretienAVerifier'],
};

const SAMPLE_COTE = { quotation: 12380, trustIndex: 2 };

describe('normalizeToAdData', () => {
  it('produces correct core fields from gallery data', () => {
    const ad = normalizeToAdData(SAMPLE_GALLERY, SAMPLE_TC_VARS, SAMPLE_COTE, null);

    expect(ad.make).toBe('PEUGEOT');
    expect(ad.model).toBe('208');
    expect(ad.price_eur).toBe(9990);
    expect(ad.year_model).toBe('2021');
    expect(ad.mileage_km).toBe(95000);
    expect(ad.fuel).toBe('diesel');
    expect(ad.gearbox).toBe('manual');
    expect(ad.owner_type).toBe('pro');
    expect(ad.country).toBe('FR');
    expect(ad.currency).toBe('EUR');
    expect(ad.image_count).toBe(3);
    expect(ad.description).toBe('Superbe vehicule...');
    expect(ad.power_din_hp).toBe(102);
    expect(ad.power_fiscal_cv).toBe(5);
    expect(ad.doors).toBe(5);
    expect(ad.color).toBe('blanc');
    expect(ad.days_online).toBe(5);
    expect(ad.first_registration).toBe('2021-07-23');
  });

  it('includes LC-specific fields', () => {
    const ad = normalizeToAdData(SAMPLE_GALLERY, SAMPLE_TC_VARS, SAMPLE_COTE, null);

    expect(ad.lc_quotation).toBe(12380);
    expect(ad.lc_trust_index).toBe(2);
    expect(ad.lc_good_deal_badge).toBe('VERY_GOOD_DEAL');
    expect(ad.lc_mileage_badge).toBe('OVER_MILEAGE');
    expect(ad.lc_average_mileage).toBe(65208);
    expect(ad.lc_nb_owners).toBe(1);
    expect(ad.lc_is_international).toBe(false);
    expect(ad.lc_first_hand).toBe(true);
    expect(ad.lc_warranty_duration).toBe('6');
    expect(ad.lc_badge_maintenance).toEqual(['entretienAVerifier']);
  });

  it('handles private seller', () => {
    const gallery = {
      ...SAMPLE_GALLERY,
      classified: { ...SAMPLE_GALLERY.classified, customerType: 'PART' },
    };
    const ad = normalizeToAdData(gallery, {}, null, null);
    expect(ad.owner_type).toBe('private');
  });

  it('normalizes fuel types correctly', () => {
    const fuels = [
      ['DIESEL', 'diesel'],
      ['ESSENCE', 'essence'],
      ['ELECTRIQUE', 'electric'],
      ['HYBRIDE', 'hybrid'],
      ['GPL', 'lpg'],
    ];
    for (const [input, expected] of fuels) {
      const gallery = {
        ...SAMPLE_GALLERY,
        vehicle: { ...SAMPLE_GALLERY.vehicle, energy: input },
      };
      const ad = normalizeToAdData(gallery, {}, null, null);
      expect(ad.fuel).toBe(expected);
    }
  });

  it('normalizes gearbox types correctly', () => {
    const gearboxes = [
      ['MECANIQUE', 'manual'],
      ['AUTOMATIQUE', 'automatic'],
    ];
    for (const [input, expected] of gearboxes) {
      const gallery = {
        ...SAMPLE_GALLERY,
        vehicle: { ...SAMPLE_GALLERY.vehicle, gearbox: input },
      };
      const ad = normalizeToAdData(gallery, {}, null, null);
      expect(ad.gearbox).toBe(expected);
    }
  });

  it('handles missing gallery gracefully (JSON-LD fallback)', () => {
    const jsonLd = {
      '@type': 'Car',
      name: 'Peugeot 208',
      brand: 'Peugeot',
      model: '208',
      color: 'Blanc',
      offers: { price: 9990 },
      mileageFromOdometer: { value: 95000 },
      dateVehicleFirstRegistered: '2021',
    };
    const ad = normalizeToAdData(null, {}, null, jsonLd);
    expect(ad.make).toBe('Peugeot');
    expect(ad.model).toBe('208');
    expect(ad.price_eur).toBe(9990);
    expect(ad.year_model).toBe('2021');
  });

  it('handles missing tc_vars', () => {
    const ad = normalizeToAdData(SAMPLE_GALLERY, null, null, null);
    expect(ad.dealer_rating).toBeNull();
    expect(ad.dealer_review_count).toBeNull();
    expect(ad.lc_warranty_duration).toBeNull();
  });

  it('handles missing cote', () => {
    const ad = normalizeToAdData(SAMPLE_GALLERY, {}, null, null);
    expect(ad.lc_quotation).toBeNull();
    expect(ad.lc_trust_index).toBeNull();
  });

  it('handles missing images', () => {
    const gallery = { ...SAMPLE_GALLERY, images: {} };
    const ad = normalizeToAdData(gallery, {}, null, null);
    expect(ad.image_count).toBe(0);
  });

  it('collectMarketPrices returns no-op', async () => {
    const ext = new LaCentraleExtractor();
    const result = await ext.collectMarketPrices({});
    expect(result).toEqual({ submitted: false, isCurrentVehicle: false });
  });
});


// ═══════════════════════════════════════════════════════════════════
// 9. Bonus Signals
// ═══════════════════════════════════════════════════════════════════

describe('buildBonusSignals', () => {
  it('includes good deal badge', () => {
    const signals = buildBonusSignals(SAMPLE_GALLERY, SAMPLE_TC_VARS, SAMPLE_COTE);
    const badge = signals.find((s) => s.label === 'Badge La Centrale');
    expect(badge).toBeDefined();
    expect(badge.value).toBe('Très bonne affaire');
    expect(badge.status).toBe('pass');
  });

  it('includes mileage badge', () => {
    const signals = buildBonusSignals(SAMPLE_GALLERY, {}, {});
    const km = signals.find((s) => s.label === 'Kilométrage');
    expect(km).toBeDefined();
    expect(km.status).toBe('warning');
  });

  it('includes owners count', () => {
    const signals = buildBonusSignals(SAMPLE_GALLERY, {}, {});
    const owners = signals.find((s) => s.label === 'Propriétaires');
    expect(owners).toBeDefined();
    expect(owners.value).toBe('1');
    expect(owners.status).toBe('pass');
  });

  it('includes quotation', () => {
    const signals = buildBonusSignals(SAMPLE_GALLERY, {}, SAMPLE_COTE);
    const cote = signals.find((s) => s.label === 'Cote La Centrale');
    expect(cote).toBeDefined();
    expect(cote.value).toContain('12');
  });

  it('includes warranty', () => {
    const signals = buildBonusSignals(SAMPLE_GALLERY, SAMPLE_TC_VARS, {});
    const warranty = signals.find((s) => s.label === 'Garantie');
    expect(warranty).toBeDefined();
    expect(warranty.value).toBe('6 mois');
  });

  it('includes maintenance badge', () => {
    const signals = buildBonusSignals(SAMPLE_GALLERY, SAMPLE_TC_VARS, {});
    const maint = signals.find((s) => s.label === 'Entretien');
    expect(maint).toBeDefined();
    expect(maint.status).toBe('warning');
  });

  it('includes seller rating', () => {
    const signals = buildBonusSignals(SAMPLE_GALLERY, SAMPLE_TC_VARS, {});
    const rating = signals.find((s) => s.label === 'Avis vendeur');
    expect(rating).toBeDefined();
    expect(rating.value).toContain('262');
  });

  it('returns empty array with null inputs', () => {
    expect(buildBonusSignals(null, null, null)).toEqual([]);
  });
});
