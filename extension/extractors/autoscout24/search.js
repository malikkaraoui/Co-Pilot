"use strict";

import { brandsMatch } from '../../shared/brand.js';
import { SMG_TLDS } from './constants.js';

// ── URL & slug helpers ──────────────────────────────────────────────

export function extractTld(url) {
  const match = url.match(/autoscout24\.(\w+)/);
  return match ? match[1] : 'de';
}

export function extractLang(url) {
  const match = url.match(/autoscout24\.\w+\/(fr|de|it|en|nl|es|pl|sv)\//);
  return match ? match[1] : null;
}

export function toAs24Slug(name) {
  return String(name || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9\-]/g, '');
}

export function extractAs24SlugsFromSearchUrl(url, tldHint = null) {
  try {
    const u = new URL(url);
    const hostMatch = u.hostname.match(/autoscout24\.(\w+)$/i);
    const tld = (tldHint || (hostMatch ? hostMatch[1] : '') || '').toLowerCase();
    const path = decodeURIComponent(u.pathname || '');

    if (SMG_TLDS.has(tld)) {
      const smg = path.match(/\/s\/(?:mo-([^/]+)\/)?mk-([^/?#]+)/i);
      if (!smg) return { makeSlug: null, modelSlug: null };
      const modelSlug = smg[1] ? toAs24Slug(smg[1]) : null;
      const makeSlug = smg[2] ? toAs24Slug(smg[2]) : null;
      return { makeSlug, modelSlug };
    }

    const normalizedPath = path.replace(/^\/(fr|de|it|en|nl|es|pl|sv)(?=\/|$)/i, '');
    const gmbh = normalizedPath.match(/^\/lst\/([^/]+)(?:\/([^/?#]+))?/i);
    if (!gmbh) return { makeSlug: null, modelSlug: null };
    const makeSlug = gmbh[1] ? toAs24Slug(gmbh[1]) : null;
    const modelSlug = gmbh[2] ? toAs24Slug(gmbh[2]) : null;
    return { makeSlug, modelSlug };
  } catch {
    return { makeSlug: null, modelSlug: null };
  }
}

export function buildSearchUrl(makeKey, modelKey, year, tld, options = {}) {
  const { yearSpread = 1, fuel, gear, powerfrom, powerto, kmfrom, kmto, zip, radius, lang, brandOnly } = options;

  const makeSlug = toAs24Slug(makeKey);
  const modelSlug = brandOnly ? '' : toAs24Slug(modelKey);

  let base;

  if (SMG_TLDS.has(tld)) {
    const langPrefix = lang ? `/${lang}` : '/fr';
    if (modelSlug) {
      base = `https://www.autoscout24.${tld}${langPrefix}/s/mo-${modelSlug}/mk-${makeSlug}`;
    } else {
      base = `https://www.autoscout24.${tld}${langPrefix}/s/mk-${makeSlug}`;
    }
  } else {
    const langSegment = lang ? `/${lang}` : '';
    if (modelSlug) {
      base = `https://www.autoscout24.${tld}${langSegment}/lst/${makeSlug}/${modelSlug}`;
    } else {
      base = `https://www.autoscout24.${tld}${langSegment}/lst/${makeSlug}`;
    }
  }

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

/** @see shared/brand.js — re-export for backward compatibility. */
export const brandMatchesAs24 = brandsMatch;

// ── Price parsing from search results ───────────────────────────────

function _extractJsonLdBrand(item) {
  return item?.brand?.name
    || item?.offers?.itemOffered?.brand?.name
    || item?.manufacturer
    || item?.offers?.itemOffered?.manufacturer
    || null;
}

export function parseSearchPrices(html, targetMake = null) {
  const results = _parseSearchPricesRSC(html);

  if (results.length === 0) {
    const nextDataResults = _parseSearchPricesNextData(html, targetMake);
    if (nextDataResults.length > 0) return nextDataResults;
  }

  if (results.length === 0) {
    const jsonLdResults = _parseSearchPricesJsonLd(html, targetMake);
    if (jsonLdResults.length > 0) return jsonLdResults;
  }

  return results;
}

function _parseSearchPricesRSC(html) {
  const results = [];
  const listingPattern = /"price"\s*:\s*(\d+).*?"mileage"\s*:\s*(\d+)/g;
  let match;
  while ((match = listingPattern.exec(html)) !== null) {
    const price = parseInt(match[1], 10);
    const mileage = parseInt(match[2], 10);
    if (price > 500 && price < 500000) {
      results.push({ price, year: null, km: mileage, fuel: null });
    }
  }
  return _dedup(results);
}

function _parseSearchPricesNextData(html, targetMake = null) {
  const results = [];
  const match = html.match(/<script\s+id="__NEXT_DATA__"\s+type="application\/json"[^>]*>([\s\S]*?)<\/script>/i);
  if (!match) return results;

  try {
    const data = JSON.parse(match[1]);
    const listings = data?.props?.pageProps?.listings;
    if (!Array.isArray(listings)) return results;

    for (const listing of listings) {
      const tracking = listing.tracking || {};
      const vehicle = listing.vehicle || {};

      const price = parseInt(tracking.price, 10) || null;
      const km = parseInt(tracking.mileage, 10) || null;

      let year = null;
      if (tracking.firstRegistration) {
        const ym = tracking.firstRegistration.match(/(\d{4})/);
        if (ym) year = parseInt(ym[1], 10);
      }

      const fuel = vehicle.fuel || null;

      if (targetMake) {
        const adBrand = vehicle.make;
        if (adBrand && !brandMatchesAs24(adBrand, targetMake)) {
          continue;
        }
      }

      if (price && price > 500 && price < 500000) {
        results.push({
          price,
          year,
          km,
          fuel,
          gearbox: vehicle.transmission || null,
          horse_power: _parseHpFromVehicleDetails(listing.vehicleDetails),
          _uid: listing.id || null,
        });
      }
    }
  } catch (_) {
    // Malformed __NEXT_DATA__, skip
  }

  return _dedup(results);
}

function _parseHpFromVehicleDetails(details) {
  if (!Array.isArray(details)) return null;
  const power = details.find((d) => d.ariaLabel === 'Leistung' || d.iconName === 'speedometer');
  if (!power?.data) return null;
  const m = power.data.match(/\((\d+)\s*PS\)/i);
  return m ? parseInt(m[1], 10) : null;
}

function _parseSearchPricesJsonLd(html, targetMake = null) {
  const results = [];
  const scriptPattern = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  let scriptMatch;
  while ((scriptMatch = scriptPattern.exec(html)) !== null) {
    try {
      const data = JSON.parse(scriptMatch[1]);
      const items = _extractOfferCatalogItems(data);
      for (const item of items) {
        const price = _extractJsonLdPrice(item);
        const km = _extractJsonLdMileage(item);
        const fuel = _extractJsonLdFuel(item);
        const year = _extractJsonLdYear(item);
        const uid = _extractJsonLdUid(item);
        if (price && price > 500 && price < 500000) {
          if (targetMake) {
            const adBrand = _extractJsonLdBrand(item);
            if (adBrand && !brandMatchesAs24(adBrand, targetMake)) {
              console.debug('[CoPilot] AS24 brand safety: rejet %s (cible: %s)', adBrand, targetMake);
              continue;
            }
          }
          results.push({ price, year, km, fuel, _uid: uid });
        }
      }
    } catch (_) {
      // Malformed JSON-LD block, skip
    }
  }
  return _dedup(results);
}

function _extractOfferCatalogItems(data) {
  if (data?.['@type'] === 'OfferCatalog' && Array.isArray(data.itemListElement)) {
    return data.itemListElement;
  }
  const offers = data?.mainEntity?.offers || data?.offers;
  if (offers?.['@type'] === 'OfferCatalog' && Array.isArray(offers.itemListElement)) {
    return offers.itemListElement;
  }
  if (Array.isArray(data?.['@graph'])) {
    for (const node of data['@graph']) {
      const items = _extractOfferCatalogItems(node);
      if (items.length > 0) return items;
    }
  }
  return [];
}

function _extractJsonLdPrice(item) {
  const price = item?.offers?.price ?? item?.price;
  if (typeof price === 'number') return price;
  if (typeof price === 'string') return parseInt(price, 10) || null;
  return null;
}

function _extractJsonLdMileage(item) {
  const car = item?.offers?.itemOffered || item;
  const odometer = car?.mileageFromOdometer;
  if (!odometer) return null;
  const val = odometer?.value ?? odometer;
  if (typeof val === 'number') return val;
  if (typeof val === 'string') return parseInt(val, 10) || null;
  return null;
}

function _extractJsonLdFuel(item) {
  const car = item?.offers?.itemOffered || item;
  const eng = car?.vehicleEngine;
  const engine = Array.isArray(eng) ? eng[0] : eng;
  return engine?.fuelType || null;
}

function _extractJsonLdYear(item) {
  const car = item?.offers?.itemOffered || item;
  const date = car?.vehicleModelDate || car?.productionDate;
  if (!date) return null;
  const y = parseInt(String(date).slice(0, 4), 10);
  return (y > 1900 && y < 2100) ? y : null;
}

function _extractJsonLdUid(item) {
  const url = item?.url || item?.offers?.url;
  if (!url) return null;
  const m = url.match(/(\d{6,})(?:[/?#]|$)/);
  return m ? m[1] : url;
}

function _dedup(results) {
  const seen = new Set();
  return results.filter((r) => {
    const key = r._uid || `${r.price}-${r.km}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).map(({ _uid, ...rest }) => rest);
}
