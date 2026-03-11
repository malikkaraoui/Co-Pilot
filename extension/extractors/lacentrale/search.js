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

import { isChromeRuntimeAvailable } from '../../utils/fetch.js';
import {
  LC_AD_PAGE_PATTERN,
  LC_LISTING_BASE, LC_SEARCH_FUEL_CODES, LC_SEARCH_GEARBOX_CODES,
  LC_SEARCH_REGION_CODES,
} from './constants.js';

const LC_IFRAME_LOAD_TIMEOUT_MS = 5000;
const LC_IFRAME_RENDER_WAIT_MS = 2000;
const LC_IFRAME_POLL_INTERVAL_MS = 500;

const LC_DIAGNOSTIC_BODY_EXCERPT_MAX = 320;
const LC_DIAGNOSTIC_REASON_MAX = 180;

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

  // Brand + optional model: "PEUGEOT" or "PEUGEOT::308" (double colon!)
  // Verified 2026-03-09: LC uses BRAND::MODEL (not single colon).
  const make = (opts.make || '').toUpperCase();
  if (make) {
    const token = opts.model
      ? `${make}::${opts.model.toUpperCase()}`
      : make;
    params.set('makesModelsCommercialNames', token);
  }

  // Year range
  // Verified 2026-03-09: omit yearMax when it equals current year (LC convention).
  if (opts.yearMin) params.set('yearMin', String(opts.yearMin));
  const currentYear = new Date().getFullYear();
  if (opts.yearMax && opts.yearMax < currentYear) {
    params.set('yearMax', String(opts.yearMax));
  }

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

  // Regions (optional, comma-separated ISO codes)
  if (opts.regions && Array.isArray(opts.regions) && opts.regions.length > 0) {
    const codes = opts.regions
      .map((r) => LC_SEARCH_REGION_CODES[r] || r)
      .filter(Boolean);
    if (codes.length > 0) params.set('regions', codes.join(','));
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

function _sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function _normalizeText(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

function _clipLcText(text, maxLen) {
  const normalized = _normalizeText(text);
  if (!normalized) return '';
  if (normalized.length <= maxLen) return normalized;
  return `${normalized.slice(0, Math.max(0, maxLen - 1))}…`;
}

function _extractLcBodyExcerpt(html) {
  if (!html) return null;
  const excerpt = _clipLcText(
    String(html)
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<[^>]+>/g, ' '),
    LC_DIAGNOSTIC_BODY_EXCERPT_MAX,
  );
  return excerpt || null;
}

function _extractLcTitleFromHtml(html) {
  const match = String(html || '').match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  return match ? _clipLcText(match[1], 140) : null;
}

function _looksLikeZeroResultsPage(html) {
  return /\b0\s*(?:resultat|résultat|annonce)s?\b|aucun\s+(?:resultat|résultat|vehicule|véhicule|annonce)|pas de resultats|pas de résultats/i.test(html || '');
}

function _hasLcAdSignals(html) {
  return /occasion-annonce-|"classifieds"|__NEXT_DATA__|application\/ld\+json|ItemList|ListItem|moteur de recherche|searchData/i.test(html || '');
}

function _summarizeLcResources(resources) {
  if (!Array.isArray(resources) || resources.length === 0) return null;
  return _clipLcText(resources.slice(0, 5).join(' | '), 500);
}

function _buildLcDiagnostic(overrides = {}) {
  return {
    reasonTag: null,
    reason: '',
    fetchMode: null,
    httpStatus: null,
    bodyExcerpt: null,
    htmlTitle: null,
    resourceSample: null,
    responseBytes: null,
    antiBotDetected: false,
    ...overrides,
  };
}

function _finalizeLcDiagnostic(diagnostic = {}) {
  return {
    reasonTag: diagnostic.reasonTag || null,
    reason: _clipLcText(diagnostic.reason || '', LC_DIAGNOSTIC_REASON_MAX),
    fetchMode: diagnostic.fetchMode || null,
    httpStatus: Number.isInteger(diagnostic.httpStatus) ? diagnostic.httpStatus : null,
    bodyExcerpt: diagnostic.bodyExcerpt ? _clipLcText(diagnostic.bodyExcerpt, LC_DIAGNOSTIC_BODY_EXCERPT_MAX) : null,
    htmlTitle: diagnostic.htmlTitle ? _clipLcText(diagnostic.htmlTitle, 140) : null,
    resourceSample: diagnostic.resourceSample ? _clipLcText(diagnostic.resourceSample, 500) : null,
    responseBytes: Number.isInteger(diagnostic.responseBytes) ? diagnostic.responseBytes : null,
    antiBotDetected: Boolean(diagnostic.antiBotDetected),
  };
}

function _classifyLcEmptyHtml(html, baseDiagnostic = {}) {
  const antiBot = _looksLikeAntiBotPage(html);
  if (antiBot) {
    return _finalizeLcDiagnostic({
      ...baseDiagnostic,
      reasonTag: baseDiagnostic.httpStatus === 403 ? 'anti_bot_403' : 'anti_bot_page',
      reason: baseDiagnostic.httpStatus === 403
        ? 'Réponse 403 avec signature anti-bot La Centrale/DataDome'
        : 'HTML de challenge anti-bot détecté',
      antiBotDetected: true,
      bodyExcerpt: baseDiagnostic.bodyExcerpt || _extractLcBodyExcerpt(html),
      htmlTitle: baseDiagnostic.htmlTitle || _extractLcTitleFromHtml(html),
    });
  }

  if (_looksLikeZeroResultsPage(html)) {
    return _finalizeLcDiagnostic({
      ...baseDiagnostic,
      reasonTag: 'true_zero_results',
      reason: 'Page listing valide mais zéro résultat affiché par La Centrale',
      bodyExcerpt: baseDiagnostic.bodyExcerpt || _extractLcBodyExcerpt(html),
      htmlTitle: baseDiagnostic.htmlTitle || _extractLcTitleFromHtml(html),
    });
  }

  if (_hasLcAdSignals(html)) {
    return _finalizeLcDiagnostic({
      ...baseDiagnostic,
      reasonTag: 'parser_no_match',
      reason: 'HTML reçu avec signaux d’annonces mais parsing resté vide',
      bodyExcerpt: baseDiagnostic.bodyExcerpt || _extractLcBodyExcerpt(html),
      htmlTitle: baseDiagnostic.htmlTitle || _extractLcTitleFromHtml(html),
    });
  }

  return _finalizeLcDiagnostic({
    ...baseDiagnostic,
    reasonTag: 'html_without_cards',
    reason: 'HTML reçu sans cartes d’annonces détectables',
    bodyExcerpt: baseDiagnostic.bodyExcerpt || _extractLcBodyExcerpt(html),
    htmlTitle: baseDiagnostic.htmlTitle || _extractLcTitleFromHtml(html),
  });
}

function _parseLcPrice(text) {
  const norm = _normalizeText(text);
  // Try with € first (most reliable)
  const withEuro = norm.match(/(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{4,6})\s*€/i);
  if (withEuro) {
    const price = parseInt(withEuro[1].replace(/[\s\u00a0]/g, ''), 10);
    if (Number.isFinite(price) && price >= 500) return price;
  }
  // Fallback: LC boosted cards omit €. Grab the last number that looks
  // like a price (skip km-suffixed numbers and bare years 1900-2099).
  const allNums = [...norm.matchAll(/(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{4,6})(?!\s*km(?!\d))/gi)];
  for (let i = allNums.length - 1; i >= 0; i--) {
    const raw = allNums[i][1].replace(/[\s\u00a0]/g, '');
    const val = parseInt(raw, 10);
    if (!Number.isFinite(val) || val < 500 || val > 200000) continue;
    if (val >= 1900 && val <= 2099 && raw.length === 4) continue;
    return val;
  }
  return null;
}

function _parseLcYear(text) {
  // Use (?<!\d) / (?!\d) instead of \b because LC concatenates text
  // without spaces (e.g. "SUPER2018Manuelle") and \b fails between
  // two word-class chars (letter → digit).
  const match = _normalizeText(text).match(/(?<!\d)((?:19|20)\d{2})(?!\d)/);
  return match ? parseInt(match[1], 10) : null;
}

function _parseLcKm(text) {
  // Use (?!\d) instead of \b after "km" because LC concatenates text
  // without spaces (e.g. "94 373 kmEssence").
  const match = _normalizeText(text).match(/(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{4,6})\s*km(?!\d)/i);
  if (!match) return null;
  const km = parseInt(match[1].replace(/[\s\u00a0]/g, ''), 10);
  return Number.isFinite(km) ? km : null;
}

function _parseLcMaybeNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return null;
  const match = value.match(/(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{4,7})/);
  if (!match) return null;
  const num = parseInt(match[1].replace(/[\s\u00a0]/g, ''), 10);
  return Number.isFinite(num) ? num : null;
}

function _parseLcJsonLdYear(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (!value) return null;
  const match = String(value).match(/(?<!\d)((?:19|20)\d{2})(?!\d)/);
  return match ? parseInt(match[1], 10) : null;
}

function _findLcAdCard(link) {
  let node = link;
  while (node && node !== node.ownerDocument?.body) {
    const text = _normalizeText(node.textContent);
    // Accept card if it has a year (with relaxed boundary) AND either €
    // or a price-like number (boosted cards omit €).
    if (text && text.length >= 20 && text.length < 2000
      && /(?<!\d)(?:19|20)\d{2}(?!\d)/.test(text)
      && (/€/.test(text) || /\d{4,6}/.test(text))) {
      return node;
    }
    node = node.parentElement;
  }
  return link;
}

function _collectLcInterestingResources(win) {
  try {
    return win.performance
      .getEntriesByType('resource')
      .map((entry) => entry?.name)
      .filter((name) => typeof name === 'string')
      .filter((name) => /lacentrale\.fr/i.test(name))
      .filter((name) => /api|graphql|search|listing|classified|annonce|vehicle/i.test(name))
      .slice(0, 30);
  } catch {
    return [];
  }
}

function _dedupeAds(ads) {
  const seen = new Set();
  return (ads || []).filter((ad) => {
    if (!ad || !Number.isFinite(ad.price)) return false;
    const key = `${ad.price}-${ad.year || '?'}-${ad.km || '?'}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function _extractAdsFromJsonLdNode(node, out) {
  if (!node) return;

  if (Array.isArray(node)) {
    node.forEach((item) => _extractAdsFromJsonLdNode(item, out));
    return;
  }

  if (typeof node !== 'object') return;

  const price = _parseLcMaybeNumber(
    node.offers?.price
    ?? node.price
    ?? node.priceSpecification?.price
    ?? node.offers?.priceSpecification?.price,
  );
  const year = _parseLcJsonLdYear(
    node.vehicleModelDate
    ?? node.productionDate
    ?? node.releaseDate
    ?? node.dateVehicleFirstRegistered
    ?? node.datePublished,
  );
  const km = _parseLcMaybeNumber(
    node.mileageFromOdometer?.value
    ?? node.mileageFromOdometer
    ?? node.mileage
    ?? node.vehicleConfiguration?.mileageFromOdometer?.value,
  );
  const typeLabel = String(node['@type'] || '').toLowerCase();
  const hasVehicleContext = Boolean(
    year != null
    || km != null
    || node.brand
    || node.model
    || node.name
    || node.url
    || typeLabel.includes('car')
    || typeLabel.includes('vehicle')
    || typeLabel.includes('product')
    || typeLabel.includes('listitem'),
  );

  if (price && price >= 500 && hasVehicleContext) {
    out.push({ price, year, km });
  }

  if (node.itemListElement) _extractAdsFromJsonLdNode(node.itemListElement, out);
  if (node.item) _extractAdsFromJsonLdNode(node.item, out);

  Object.values(node).forEach((value) => {
    if (value && typeof value === 'object') {
      _extractAdsFromJsonLdNode(value, out);
    }
  });
}

function _extractAdsFromJsonLdScripts(root) {
  if (!root?.querySelectorAll) return [];

  const ads = [];
  const scripts = Array.from(root.querySelectorAll('script[type="application/ld+json"]'));
  for (const script of scripts) {
    const raw = script.textContent?.trim();
    if (!raw) continue;
    try {
      const data = JSON.parse(raw);
      _extractAdsFromJsonLdNode(data, ads);
    } catch {
      // ignore malformed JSON-LD blocks
    }
  }
  return _dedupeAds(ads);
}

function _createLcProbeIframe() {
  const iframe = document.createElement('iframe');
  iframe.setAttribute('aria-hidden', 'true');
  iframe.tabIndex = -1;
  iframe.style.position = 'fixed';
  iframe.style.left = '-200vw';
  iframe.style.top = '0';
  iframe.style.width = '1440px';
  iframe.style.height = '3200px';
  iframe.style.opacity = '0.01';
  iframe.style.pointerEvents = 'none';
  iframe.style.border = '0';
  iframe.style.zIndex = '-2147483647';
  return iframe;
}

function _canUseLcIframeProbe(searchUrl) {
  if (typeof document === 'undefined' || typeof window === 'undefined') return false;
  if (!document.body) return false;
  try {
    const pageUrl = new URL(window.location.href);
    const targetUrl = new URL(searchUrl, window.location.href);
    return /(^|\.)lacentrale\.fr$/i.test(pageUrl.hostname)
      && /(^|\.)lacentrale\.fr$/i.test(targetUrl.hostname)
      && pageUrl.origin === targetUrl.origin;
  } catch {
    return false;
  }
}

export function extractLcAdsFromRenderedDom(root) {
  if (!root?.querySelectorAll) return [];

  const links = Array.from(root.querySelectorAll('a[href*="occasion-annonce-"]'));
  const seenHrefs = new Set();

  return links
    .map((link) => {
      const href = link.href || link.getAttribute('href') || '';
      if (!href || seenHrefs.has(href)) return null;
      if (!LC_AD_PAGE_PATTERN.test(href)) return null;
      seenHrefs.add(href);

      const card = _findLcAdCard(link);
      const text = _normalizeText(card?.textContent || link.textContent || '');
      if (!text || text.length < 20) return null;

      const price = _parseLcPrice(text);
      if (!price) return null;

      return {
        price,
        year: _parseLcYear(text),
        km: _parseLcKm(text),
        href,
      };
    })
    .filter((ad) => ad && Number.isFinite(ad.price))
    .map(({ href, ...ad }) => ad);
}

function _looksLikeAntiBotPage(html) {
  return /captcha-delivery\.com|Please enable JS and disable any ad blocker|data-cfasync="false"/i.test(html || '');
}

async function _probeLcListingViaIframe(searchUrl) {
  if (!_canUseLcIframeProbe(searchUrl)) {
    return {
      ok: false,
      diagnostic: _finalizeLcDiagnostic({
        reasonTag: 'iframe_blocked',
        reason: 'Iframe same-origin indisponible depuis ce contexte',
        fetchMode: 'iframe',
      }),
    };
  }

  const iframe = _createLcProbeIframe();

  try {
    const loadResult = await new Promise((resolve) => {
      const timeoutId = window.setTimeout(() => {
        cleanup();
        resolve({ ok: false, reason: 'timeout' });
      }, LC_IFRAME_LOAD_TIMEOUT_MS);

      const cleanup = () => {
        iframe.onload = null;
        iframe.onerror = null;
        window.clearTimeout(timeoutId);
      };

      iframe.onload = () => {
        cleanup();
        resolve({ ok: true });
      };
      iframe.onerror = () => {
        cleanup();
        resolve({ ok: false, reason: 'error' });
      };

      document.body.appendChild(iframe);
      iframe.src = searchUrl;
    });

    if (!loadResult.ok) {
      console.debug('[OKazCar] LC iframe probe failed: %s', loadResult.reason);
      return {
        ok: false,
        diagnostic: _finalizeLcDiagnostic({
          reasonTag: 'iframe_blocked',
          reason: `Iframe same-origin indisponible (${loadResult.reason})`,
          fetchMode: 'iframe',
        }),
      };
    }

    const frameWin = iframe.contentWindow;
    const frameDoc = iframe.contentDocument;
    if (!frameWin || !frameDoc?.documentElement) {
      console.debug('[OKazCar] LC iframe probe: inaccessible document');
      return {
        ok: false,
        diagnostic: _finalizeLcDiagnostic({
          reasonTag: 'iframe_blocked',
          reason: 'Iframe chargée mais document inaccessible',
          fetchMode: 'iframe',
        }),
      };
    }

    let ads = [];
    let jsonLdAds = [];
    let waited = 0;
    while (waited < LC_IFRAME_RENDER_WAIT_MS) {
      ads = extractLcAdsFromRenderedDom(frameDoc);
      jsonLdAds = _extractAdsFromJsonLdScripts(frameDoc);
      if (ads.length > 0 || jsonLdAds.length > 0) break;

      try {
        frameWin.scrollTo(0, Math.max(
          frameDoc.documentElement?.scrollHeight || 0,
          frameDoc.body?.scrollHeight || 0,
        ));
      } catch {
        // ignore scroll errors
      }

      await _sleep(LC_IFRAME_POLL_INTERVAL_MS);
      waited += LC_IFRAME_POLL_INTERVAL_MS;
    }

    const html = frameDoc.documentElement.outerHTML || '';
    const resources = _collectLcInterestingResources(frameWin);
    const inlineAds = _extractAdsFromInlineJson(html) || _extractAdsFromNextData(html) || [];
    const mergedAds = _dedupeAds([...ads, ...jsonLdAds, ...inlineAds]);

    if (resources.length > 0) {
      console.debug('[OKazCar] LC iframe resources: %o', resources);
    }

    return {
      ok: true,
      html,
      ads: mergedAds,
      title: frameDoc.title || '',
      resources,
      diagnostic: _finalizeLcDiagnostic({
        fetchMode: 'iframe',
        bodyExcerpt: _extractLcBodyExcerpt(html),
        htmlTitle: frameDoc.title || _extractLcTitleFromHtml(html),
        resourceSample: _summarizeLcResources(resources),
        responseBytes: html.length,
        antiBotDetected: _looksLikeAntiBotPage(html),
      }),
    };
  } catch (err) {
    console.debug('[OKazCar] LC iframe probe error:', err.message);
    return {
      ok: false,
      diagnostic: _finalizeLcDiagnostic({
        reasonTag: 'iframe_blocked',
        reason: `Erreur iframe: ${err.message}`,
        fetchMode: 'iframe',
      }),
    };
  } finally {
    iframe.remove();
  }
}

async function _fetchLcListingHtml(searchUrl) {
  if (isChromeRuntimeAvailable()) {
    try {
      const result = await chrome.runtime.sendMessage({
        action: 'lc_listing_fetch',
        url: searchUrl,
      });
      if (result && typeof result.body === 'string') {
        return {
          ok: Boolean(result.ok),
          status: Number.isInteger(result.status) ? result.status : null,
          body: result.body,
          fetchMode: 'main',
          error: result.error || null,
        };
      }
      if (result && !result.ok) {
        console.warn('[OKazCar] LC listing fetch (MAIN): %s', result.error || `HTTP ${result.status}`);
        return {
          ok: false,
          status: Number.isInteger(result.status) ? result.status : null,
          body: null,
          fetchMode: 'main',
          error: result.error || `HTTP ${result.status}`,
        };
      }
    } catch (err) {
      console.debug('[OKazCar] LC listing MAIN fetch indisponible:', err.message);
    }
  }

  try {
    const resp = await fetch(searchUrl, {
      credentials: 'include',
      headers: { 'Accept': 'text/html' },
    });
    const body = await resp.text();
    if (!resp.ok) {
      console.warn('[OKazCar] LC listing fetch HTTP %d for %s', resp.status, searchUrl.substring(0, 120));
      return {
        ok: false,
        status: resp.status,
        body,
        fetchMode: 'direct',
        error: `HTTP ${resp.status}`,
      };
    }
    return {
      ok: true,
      status: resp.status,
      body,
      fetchMode: 'direct',
      error: null,
    };
  } catch (err) {
    console.warn('[OKazCar] LC listing fetch error:', err.message);
    return {
      ok: false,
      status: null,
      body: null,
      fetchMode: 'direct',
      error: err.message,
    };
  }
}

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
export async function fetchLcSearchPricesDetailed(searchUrl, targetYear, yearSpread) {
  const iframeProbe = await _probeLcListingViaIframe(searchUrl);
  let lastDiagnostic = iframeProbe?.diagnostic || _finalizeLcDiagnostic();

  if (iframeProbe?.ok && iframeProbe?.html) {
    if (_looksLikeAntiBotPage(iframeProbe.html)) {
      console.warn('[OKazCar] LC listing blocked in iframe for %s', searchUrl.substring(0, 120));
      return {
        prices: [],
        diagnostic: _classifyLcEmptyHtml(iframeProbe.html, {
          ...iframeProbe.diagnostic,
          fetchMode: 'iframe',
        }),
      };
    }

    if (iframeProbe.ads?.length > 0) {
      console.log('[OKazCar] LC listing (rendered DOM): %d ads extracted from %s', iframeProbe.ads.length, searchUrl.substring(0, 100));
      return {
        prices: _filterAds(iframeProbe.ads, targetYear, yearSpread),
        diagnostic: _finalizeLcDiagnostic({
          ...iframeProbe.diagnostic,
          reasonTag: 'ok',
          reason: `Extraction DOM iframe réussie (${iframeProbe.ads.length} annonces)`,
          fetchMode: 'iframe',
        }),
      };
    }

    console.debug('[OKazCar] LC iframe loaded but no ad cards found (%s)', iframeProbe.title || 'no title');
    lastDiagnostic = _classifyLcEmptyHtml(iframeProbe.html, {
      ...iframeProbe.diagnostic,
      fetchMode: 'iframe',
      htmlTitle: iframeProbe.title || iframeProbe.diagnostic?.htmlTitle,
      resourceSample: _summarizeLcResources(iframeProbe.resources),
    });
  }

  const fetchResult = await _fetchLcListingHtml(searchUrl);
  const html = fetchResult?.body || null;
  if (!html) {
    return {
      prices: [],
      diagnostic: _finalizeLcDiagnostic({
        ...lastDiagnostic,
        reasonTag: fetchResult?.status === 403 ? 'anti_bot_403' : (lastDiagnostic.reasonTag || 'html_unavailable'),
        reason: fetchResult?.status === 403
          ? 'Réponse 403 sans HTML exploitable renvoyée par La Centrale'
          : (fetchResult?.error || lastDiagnostic.reason || 'Aucun HTML récupéré pour la recherche La Centrale'),
        fetchMode: fetchResult?.fetchMode || lastDiagnostic.fetchMode,
        httpStatus: fetchResult?.status,
        antiBotDetected: fetchResult?.status === 403 || lastDiagnostic.antiBotDetected,
      }),
    };
  }

  if (_looksLikeAntiBotPage(html)) {
    console.warn('[OKazCar] LC listing blocked by anti-bot for %s', searchUrl.substring(0, 120));
    return {
      prices: [],
      diagnostic: _classifyLcEmptyHtml(html, {
        ...lastDiagnostic,
        fetchMode: fetchResult?.fetchMode,
        httpStatus: fetchResult?.status,
        bodyExcerpt: _extractLcBodyExcerpt(html),
        htmlTitle: _extractLcTitleFromHtml(html),
        responseBytes: html.length,
      }),
    };
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
    return {
      prices: [],
      diagnostic: _classifyLcEmptyHtml(html, {
        ...lastDiagnostic,
        fetchMode: fetchResult?.fetchMode,
        httpStatus: fetchResult?.status,
        bodyExcerpt: _extractLcBodyExcerpt(html),
        htmlTitle: _extractLcTitleFromHtml(html),
        responseBytes: html.length,
      }),
    };
  }

  // Filter by year tolerance and minimum price
  return {
    prices: _filterAds(ads, targetYear, yearSpread),
    diagnostic: _finalizeLcDiagnostic({
      ...lastDiagnostic,
      reasonTag: 'ok',
      reason: `Extraction HTML réussie (${ads.length} annonces brutes)`,
      fetchMode: fetchResult?.fetchMode,
      httpStatus: fetchResult?.status,
      bodyExcerpt: _extractLcBodyExcerpt(html),
      htmlTitle: _extractLcTitleFromHtml(html),
      responseBytes: html.length,
    }),
  };
}

export async function fetchLcSearchPrices(searchUrl, targetYear, yearSpread) {
  const result = await fetchLcSearchPricesDetailed(searchUrl, targetYear, yearSpread);
  return result.prices;
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
