"use strict";

/**
 * La Centrale — search URL builder and price extraction from listing pages.
 *
 * Reverse-engineered from lacentrale.fr/listing query parameters:
 *   ?makesModelsCommercialNames=PEUGEOT         (brand)
 *   ?makesModelsCommercialNames=PEUGEOT%3A308    (brand:model)
 *   ?energies=dies                               (fuel)
 *   ?gearbox=man                                 (gearbox)
 *   ?yearMin=2020&yearMax=2024                   (year range)
 *   ?mileageMin=10000&mileageMax=80000           (km range)
 */

import {
  LC_LISTING_BASE, LC_SEARCH_FUEL_CODES, LC_SEARCH_GEARBOX_CODES,
} from './constants.js';

// ── URL Builder ─────────────────────────────────────────────────

/**
 * Build a La Centrale listing search URL from vehicle criteria.
 *
 * @param {object} opts
 * @param {string} opts.make       - Brand name (e.g. "PEUGEOT")
 * @param {string} [opts.model]    - Model name (e.g. "308")
 * @param {number} [opts.yearMin]  - Min year
 * @param {number} [opts.yearMax]  - Max year
 * @param {number} [opts.mileageMin] - Min km
 * @param {number} [opts.mileageMax] - Max km
 * @param {string} [opts.fuel]     - Normalized fuel string (e.g. "diesel")
 * @param {string} [opts.gearbox]  - Normalized gearbox string (e.g. "manual")
 * @returns {string} Full listing URL
 */
export function buildLcSearchUrl(opts) {
  const params = new URLSearchParams();

  // Brand + optional model: "PEUGEOT" or "PEUGEOT:308"
  const make = (opts.make || '').toUpperCase();
  if (make) {
    const token = opts.model
      ? `${make}:${opts.model.toUpperCase()}`
      : make;
    params.set('makesModelsCommercialNames', token);
  }

  // Year range
  if (opts.yearMin) params.set('yearMin', String(opts.yearMin));
  if (opts.yearMax) params.set('yearMax', String(opts.yearMax));

  // Mileage range
  if (opts.mileageMin != null) params.set('mileageMin', String(opts.mileageMin));
  if (opts.mileageMax != null) params.set('mileageMax', String(opts.mileageMax));

  // Fuel
  if (opts.fuel) {
    const code = LC_SEARCH_FUEL_CODES[(opts.fuel || '').toLowerCase()];
    if (code) params.set('energies', code);
  }

  // Gearbox
  if (opts.gearbox) {
    const code = LC_SEARCH_GEARBOX_CODES[(opts.gearbox || '').toLowerCase()];
    if (code) params.set('gearbox', code);
  }

  return `${LC_LISTING_BASE}?${params.toString()}`;
}

/**
 * Compute mileage range brackets for LC search.
 * LC uses explicit min/max, so we compute a reasonable bracket
 * around the current vehicle's mileage.
 *
 * @param {number} km - Current vehicle mileage
 * @returns {{mileageMin: number, mileageMax: number}|null}
 */
export function getLcMileageRange(km) {
  if (!km || km <= 0) return null;
  if (km <= 10000)  return { mileageMin: 0,      mileageMax: 20000 };
  if (km <= 30000)  return { mileageMin: 0,      mileageMax: 50000 };
  if (km <= 60000)  return { mileageMin: 20000,  mileageMax: 80000 };
  if (km <= 120000) return { mileageMin: 50000,  mileageMax: 150000 };
  return              { mileageMin: 100000, mileageMax: 999999 };
}

// ── Price Extraction ────────────────────────────────────────────

/**
 * Fetch a La Centrale listing page and extract ad prices.
 *
 * LC is a Next.js app — prices live in the __NEXT_DATA__ JSON blob.
 * Fallback: regex scraping of price elements in HTML.
 *
 * @param {string} searchUrl - Full LC listing URL
 * @param {number} targetYear - Target year for filtering
 * @param {number} yearSpread - Tolerance around target year
 * @returns {Promise<Array<{price: number, year: number|null, km: number|null}>>}
 */
export async function fetchLcSearchPrices(searchUrl, targetYear, yearSpread) {
  let html;
  try {
    const resp = await fetch(searchUrl, {
      credentials: 'include',
      headers: { 'Accept': 'text/html' },
    });
    if (!resp.ok) {
      console.warn('[OKazCar] LC listing fetch HTTP %d for %s', resp.status, searchUrl.substring(0, 120));
      return [];
    }
    html = await resp.text();
  } catch (err) {
    console.warn('[OKazCar] LC listing fetch error:', err.message);
    return [];
  }

  // Strategy 1: __NEXT_DATA__ JSON
  let ads = _extractAdsFromNextData(html);

  // Strategy 2: inline JSON (window.__INITIAL_STATE__ or similar)
  if (!ads || ads.length === 0) {
    ads = _extractAdsFromInlineJson(html);
  }

  // Strategy 3: regex fallback (price tags in HTML)
  if (!ads || ads.length === 0) {
    ads = _extractPricesFromHtml(html);
  }

  if (!ads || ads.length === 0) {
    console.log('[OKazCar] LC listing: 0 ads extracted from %s', searchUrl.substring(0, 100));
    return [];
  }

  // Filter by year tolerance and minimum price
  return _filterAds(ads, targetYear, yearSpread);
}

// ── Internal extraction helpers ─────────────────────────────────

function _extractAdsFromNextData(html) {
  const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (!match) return null;

  try {
    const data = JSON.parse(match[1]);
    const pp = data?.props?.pageProps || {};

    // Try multiple known paths for LC listing data
    const classifieds =
      pp?.searchData?.classifieds ||
      pp?.classifieds ||
      pp?.initialProps?.searchData?.classifieds ||
      pp?.searchData?.listings ||
      pp?.listings ||
      null;

    if (Array.isArray(classifieds) && classifieds.length > 0) {
      return _mapLcClassifieds(classifieds);
    }

    // Try to find ads nested in a results wrapper
    const results = pp?.searchData?.results || pp?.results || [];
    if (Array.isArray(results) && results.length > 0) {
      return _mapLcClassifieds(results);
    }

    console.debug('[OKazCar] LC __NEXT_DATA__: no classifieds array found');
    return null;
  } catch (err) {
    console.warn('[OKazCar] LC __NEXT_DATA__ parse error:', err.message);
    return null;
  }
}

function _extractAdsFromInlineJson(html) {
  // Some LC pages embed data in a window.__INITIAL_STATE__ or similar
  const patterns = [
    /window\.__INITIAL_STATE__\s*=\s*(\{[\s\S]*?\});?\s*<\/script>/,
    /window\.__DATA__\s*=\s*(\{[\s\S]*?\});?\s*<\/script>/,
  ];

  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (!match) continue;
    try {
      const data = JSON.parse(match[1]);
      const classifieds = data?.search?.classifieds || data?.classifieds || data?.listings || [];
      if (Array.isArray(classifieds) && classifieds.length > 0) {
        return _mapLcClassifieds(classifieds);
      }
    } catch { /* continue to next pattern */ }
  }
  return null;
}

function _extractPricesFromHtml(html) {
  // Last resort: extract prices from HTML via regex
  // LC listing cards typically have price in structured elements
  const pricePattern = /(\d{1,3}(?:[\s\u00a0]\d{3})*)\s*\u20ac/g;
  const prices = [];
  let m;
  while ((m = pricePattern.exec(html)) !== null) {
    const raw = m[1].replace(/[\s\u00a0]/g, '');
    const price = parseInt(raw, 10);
    // Only car-range prices
    if (price >= 500 && price <= 200000) {
      prices.push({ price, year: null, km: null });
    }
  }
  // Deduplicate (same price = likely same element rendered twice)
  const seen = new Set();
  return prices.filter((p) => {
    if (seen.has(p.price)) return false;
    seen.add(p.price);
    return true;
  });
}

/**
 * Map LC classified objects to our internal {price, year, km} format.
 */
function _mapLcClassifieds(classifieds) {
  return classifieds
    .map((c) => {
      // LC classifieds have various shapes. Try known fields:
      const price = c.price ?? c.priceListing ?? c.priceLabel ?? null;
      const priceInt = typeof price === 'number' ? price
        : typeof price === 'string' ? parseInt(price.replace(/[^\d]/g, ''), 10)
        : null;

      // Year: from vehicle.year, year, or firstTrafficDate
      let year = c.year ?? c.vehicle?.year ?? null;
      if (!year && c.vehicle?.firstTrafficDate) {
        const ym = String(c.vehicle.firstTrafficDate).match(/^(\d{4})/);
        if (ym) year = parseInt(ym[1], 10);
      }
      if (!year && c.firstTrafficDate) {
        const ym = String(c.firstTrafficDate).match(/^(\d{4})/);
        if (ym) year = parseInt(ym[1], 10);
      }

      // Mileage
      const km = c.mileage ?? c.vehicle?.mileage ?? c.km ?? null;

      return { price: priceInt, year, km };
    })
    .filter((a) => a.price && Number.isFinite(a.price) && a.price >= 500);
}

/**
 * Filter ads by year tolerance and minimum price.
 */
function _filterAds(ads, targetYear, yearSpread) {
  return ads.filter((a) => {
    if (a.price < 500) return false;
    if (targetYear >= 1990 && a.year) {
      if (Math.abs(a.year - targetYear) > yearSpread) return false;
    }
    return true;
  });
}
