"use strict";

import { toAs24Slug } from './search.js';
import { _daysOnline, _daysSinceRefresh, _isRepublished } from './normalize.js';

// ── RSC payload parsing ─────────────────────────────────────────────

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
      if (j === text.length - 1) i = j + 1;
    }
    if (depth !== 0) break;
  }
}

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

function _findListingDates(input, depth = 0) {
  if (!input || depth > 12) return null;

  if (Array.isArray(input)) {
    for (const item of input) {
      const found = _findListingDates(item, depth + 1);
      if (found) return found;
    }
    return null;
  }

  if (typeof input !== 'object') return null;

  if (typeof input.createdDate === 'string' && input.createdDate.includes('T')) {
    return {
      createdDate: input.createdDate,
      lastModifiedDate: typeof input.lastModifiedDate === 'string' ? input.lastModifiedDate : null,
    };
  }

  for (const value of Object.values(input)) {
    const found = _findListingDates(value, depth + 1);
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

  const itemOffered = input.offers?.itemOffered;
  if (itemOffered && isVehicleLikeLdNode(itemOffered)) {
    return {
      ...itemOffered,
      offers: input.offers,
      brand: itemOffered.brand || input.brand,
      name: itemOffered.name || input.name,
      image: itemOffered.image || input.image,
      description: itemOffered.description || input.description,
    };
  }

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

export function extractMakeModelFromUrl(url) {
  try {
    const u = new URL(url);
    const match = u.pathname.match(
      /\/(?:d|angebote|offerte|ofertas|aanbod)\/([a-z0-9][\w-]*?)[-–](?:\d+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})(?:[/?#]|$)/i
    );
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

// ── DOM extraction helpers ──────────────────────────────────────────

export function _extractImageCountFromNextData(doc) {
  const el = doc.getElementById('__NEXT_DATA__');
  if (!el) return 0;
  try {
    const data = JSON.parse(el.textContent);
    const images = data?.props?.pageProps?.listingDetails?.images;
    return Array.isArray(images) ? images.length : 0;
  } catch (_) { return 0; }
}

export function _extractDatesFromDom(doc) {
  const scripts = doc.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    if (!text.includes('createdDate')) continue;

    const searchText = text.includes('self.__next_f')
      ? text.replace(/\\+"/g, '"')
      : text;

    const createdMatch = searchText.match(/"createdDate"\s*:\s*"([^"]+T[^"]+)"/);
    if (createdMatch) {
      const modifiedMatch = searchText.match(/"lastModifiedDate"\s*:\s*"([^"]+T[^"]+)"/);
      return {
        createdDate: createdMatch[1],
        lastModifiedDate: modifiedMatch ? modifiedMatch[1] : null,
      };
    }
  }

  const nextDataEl = doc.getElementById('__NEXT_DATA__');
  if (nextDataEl) {
    try {
      const nd = JSON.parse(nextDataEl.textContent);
      const ts = nd?.props?.pageProps?.listingDetails?.createdTimestampWithOffset;
      if (ts) return { createdDate: ts, lastModifiedDate: null };
    } catch (_) { /* ignore parse errors */ }
  }

  return { createdDate: null, lastModifiedDate: null };
}

function _normalizeText(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

export function _extractDescriptionFromDom(doc) {
  const directSelectors = [
    '[data-cy*="description"]',
    '[data-testid*="description"]',
    '#description',
    '[class*="description"]',
  ];

  for (const sel of directSelectors) {
    const nodes = doc.querySelectorAll(sel);
    for (const node of nodes) {
      const txt = _normalizeText(node.textContent);
      if (txt.length >= 50) return txt.slice(0, 2000);
    }
  }

  const equipmentHeadingRe = /(équipement|equipement|ausstattung|equipment|dotazione|equipaggiamento|opzioni|options?)/i;
  const headings = doc.querySelectorAll('h1,h2,h3,h4,strong,span,div');
  for (const h of headings) {
    const title = _normalizeText(h.textContent);
    if (!title || title.length > 60 || !equipmentHeadingRe.test(title)) continue;

    const container = h.closest('section,article,div') || h.parentElement;
    if (!container) continue;

    const lis = Array.from(container.querySelectorAll('li'))
      .map((li) => _normalizeText(li.textContent))
      .filter((t) => t.length >= 3 && t.length <= 180);

    const uniq = [...new Set(lis)];
    if (uniq.length >= 3) {
      return uniq.join(' • ').slice(0, 2000);
    }
  }

  const ogDesc = _normalizeText(doc.querySelector('meta[property="og:description"]')?.getAttribute('content'));
  if (ogDesc.length >= 50) return ogDesc.slice(0, 2000);

  const metaDesc = _normalizeText(doc.querySelector('meta[name="description"]')?.getAttribute('content'));
  if (metaDesc.length >= 50) return metaDesc.slice(0, 2000);

  return null;
}

export function fallbackAdDataFromDom(doc, url) {
  const h1 = doc.querySelector('h1')?.textContent?.trim() || null;
  const title = h1 || doc.querySelector('meta[property="og:title"]')?.getAttribute('content') || doc.title || null;
  const priceMeta = doc.querySelector('meta[property="product:price:amount"]')?.getAttribute('content');
  const price = priceMeta ? Number(String(priceMeta).replace(/[^\d.]/g, '')) : null;
  const currency = doc.querySelector('meta[property="product:price:currency"]')?.getAttribute('content') || null;
  const fromUrl = extractMakeModelFromUrl(url);
  const domDates = _extractDatesFromDom(doc);

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
    description: _extractDescriptionFromDom(doc),
    owner_type: 'private',
    owner_name: null,
    siret: null,
    raw_attributes: {},
    image_count: 0,
    has_phone: false,
    has_urgent: false,
    has_highlight: false,
    has_boost: false,
    publication_date: domDates.createdDate || null,
    days_online: _daysOnline(domDates.createdDate),
    index_date: domDates.lastModifiedDate || null,
    days_since_refresh: _daysSinceRefresh(domDates.createdDate, domDates.lastModifiedDate),
    republished: _isRepublished(domDates.createdDate, domDates.lastModifiedDate),
    lbc_estimation: null,
  };
}

// ── SPA scoring ─────────────────────────────────────────────────────

function _scoreVehicleAgainstUrl(vehicle, urlSlug, expectedMake = null) {
  if (!vehicle || !urlSlug) return 0;

  const make = typeof vehicle.make === 'string' ? vehicle.make : vehicle.make?.name;
  const model = typeof vehicle.model === 'string' ? vehicle.model : vehicle.model?.name;
  const makeSlug = toAs24Slug(make || '');
  const modelSlug = toAs24Slug(model || '');

  let score = 0;
  if (makeSlug && urlSlug.startsWith(makeSlug)) score += 2;

  if (expectedMake) {
    const expMake = toAs24Slug(expectedMake);
    if (expMake && makeSlug === expMake) score += 1;
  }

  if (modelSlug) {
    if (urlSlug.includes(modelSlug)) {
      score += 4;
    } else {
      const tokenHit = modelSlug
        .split('-')
        .filter((t) => t.length >= 3)
        .some((t) => urlSlug.includes(t));
      if (tokenHit) score += 2;
    }
  }

  return score;
}

// ── Main parsing exports ────────────────────────────────────────────

export function parseRSCPayload(doc, currentUrl = null) {
  const scripts = doc.querySelectorAll('script');
  let lastFound = null;
  const candidates = [];

  let urlSlug = '';
  let expectedMake = null;
  const sourceUrl = currentUrl || (typeof window !== 'undefined' ? window.location?.href : null);
  if (sourceUrl) {
    const slugMatch = String(sourceUrl).match(
      /\/(?:d|angebote|offerte|ofertas|aanbod)\/([a-z0-9][\w-]*?)[-–](?:\d+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})(?:[/?#]|$)/i
    );
    urlSlug = slugMatch ? decodeURIComponent(slugMatch[1]).toLowerCase() : '';
    expectedMake = extractMakeModelFromUrl(String(sourceUrl)).make;
  }

  let order = 0;
  for (const script of scripts) {
    const text = script.textContent || '';
    if (!text.includes('vehicleCategory') && !text.includes('firstRegistrationDate')) {
      continue;
    }

    const candidateSources = [];

    if (text.includes('self.__next_f')) {
      const sentinel = '__AS24_ESCAPED_QUOTE__';
      const decoded = text
        .replace(/\\\\\\"/g, sentinel)
        .replace(/\\\\"/g, '"')
        .replaceAll(sentinel, '\\"');
      candidateSources.push(decoded);
      candidateSources.push(text.replace(/\\"/g, '"'));
    } else {
      candidateSources.push(text);
    }

    for (const source of candidateSources) {
      for (const candidate of extractJsonObjects(source)) {
      if (!candidate.includes('"vehicleCategory"') && !candidate.includes('"firstRegistrationDate"')) {
        continue;
      }
      try {
        const parsed = JSON.parse(candidate);
        const vehicle = findVehicleNode(parsed);
        if (vehicle) {
          if (!vehicle.createdDate) {
            const dates = _findListingDates(parsed);
            if (dates) {
              vehicle.createdDate = dates.createdDate;
              if (!vehicle.lastModifiedDate) {
                vehicle.lastModifiedDate = dates.lastModifiedDate;
              }
            }
          }
          lastFound = vehicle;
          candidates.push({ vehicle, order: order++ });
        }
      } catch {
        // Not valid JSON, try next candidate
      }
      }
    }
  }

  if (!candidates.length) return null;

  if (!urlSlug) return lastFound;

  let best = null;
  let bestScore = -1;
  for (const c of candidates) {
    const score = _scoreVehicleAgainstUrl(c.vehicle, urlSlug, expectedMake);
    if (score > bestScore || (score === bestScore && (!best || c.order > best.order))) {
      best = c;
      bestScore = score;
    }
  }

  return best?.vehicle || lastFound;
}

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

export function _findJsonLdByMake(doc, expectedMake, expectedModel = null, urlSlug = '') {
  const target = (expectedMake || '').toLowerCase();
  if (!target) return null;
  const scripts = doc.querySelectorAll('script[type="application/ld+json"]');

  let best = null;
  let bestScore = -1;
  let order = 0;

  for (const script of scripts) {
    const data = parseLooselyJsonLd(script.textContent || '');
    if (!data) continue;
    const vehicle = findVehicleLikeLdNode(data);
    if (!vehicle) continue;

    const brand = String(vehicle.brand?.name || vehicle.brand || '').toLowerCase();
    if (brand !== target) continue;

    const model = typeof vehicle.model === 'string' ? vehicle.model : vehicle.model?.name;
    const modelSlug = toAs24Slug(model || '');
    const expectedModelSlug = toAs24Slug(expectedModel || '');

    let score = 2;
    if (expectedModelSlug && modelSlug && modelSlug === expectedModelSlug) {
      score += 3;
    }
    if (urlSlug && modelSlug && urlSlug.includes(modelSlug)) {
      score += 2;
    }

    const candidate = { vehicle, score, order: order++ };
    if (!best || candidate.score > bestScore || (candidate.score === bestScore && candidate.order > best.order)) {
      best = candidate;
      bestScore = candidate.score;
    }
  }
  return best?.vehicle || null;
}
