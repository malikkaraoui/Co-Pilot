"use strict";

import { SiteExtractor } from '../base.js';
import { LC_URL_PATTERNS, LC_AD_PAGE_PATTERN } from './constants.js';
import { extractGallery, extractTcVars, extractCoteFromDom, extractJsonLd, extractAutovizaUrl } from './parser.js';
import { normalizeToAdData, buildBonusSignals } from './normalize.js';
import { collectMarketPricesLC } from './collect.js';

/**
 * Read data bridged from MAIN world via a hidden DOM element.
 * The background.js injects CLASSIFIED_GALLERY / tc_vars into DOM divs
 * so the content script (ISOLATED world) can access them.
 *
 * Returns a fake "window-like" object with the property set.
 */
function _readBridgedData(domId, win, propName) {
  const fakeWin = {};

  // 1. Try the DOM bridge (normal runtime path)
  const el = document.getElementById(domId);
  if (el && el.textContent) {
    try {
      fakeWin[propName] = JSON.parse(el.textContent);
      return fakeWin;
    } catch { /* malformed JSON, fall through */ }
  }

  // 2. Fallback: try window directly (works in tests or if somehow accessible)
  if (win[propName]) {
    fakeWin[propName] = win[propName];
  }

  return fakeWin;
}

function _cleanPhone(phone) {
  if (!phone) return null;
  const compact = String(phone).replace(/[^\d+]/g, '').trim();
  if (/^\+33\d{9}$/.test(compact) || /^0\d{9}$/.test(compact)) return compact;
  return null;
}

function _extractPhoneFromText(text) {
  if (!text) return null;
  const match = String(text).match(/(?:\+33|0)\s*[1-9](?:[\s.-]*\d{2}){4}/);
  return match ? _cleanPhone(match[0]) : null;
}

function _getStructuredPhone() {
  const galleryWin = _readBridgedData('__okazcar_lc_gallery__', window, 'CLASSIFIED_GALLERY');
  const jsonLdCandidates = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
  let jsonLdPhone = null;

  for (const script of jsonLdCandidates) {
    try {
      const data = JSON.parse(script.textContent || '{}');
      if (data?.telephone) {
        jsonLdPhone = data.telephone;
        break;
      }
      const graphPhone = Array.isArray(data?.['@graph'])
        ? data['@graph'].find((item) => item?.telephone)?.telephone
        : null;
      if (graphPhone) {
        jsonLdPhone = graphPhone;
        break;
      }
    } catch {
      // ignore malformed JSON-LD
    }
  }

  const gallery = galleryWin.CLASSIFIED_GALLERY?.data || galleryWin.CLASSIFIED_GALLERY || {};
  const classified = gallery.classified || {};
  const candidates = [
    classified.contactPhone,
    classified.phone,
    classified.telephone,
    Array.isArray(classified.phones) ? classified.phones[0] : classified.phones,
    jsonLdPhone,
  ];

  for (const candidate of candidates) {
    const cleaned = _cleanPhone(candidate);
    if (cleaned) return cleaned;
  }
  return null;
}

function _extractAnyPhoneFromDocument(root = document) {
  const telLinks = root.querySelectorAll?.('a[href^="tel:"]') || [];
  for (const link of telLinks) {
    const phone = _cleanPhone(link.href.replace(/^tel:/i, ''));
    if (phone) return phone;
  }

  const phoneFromText = _extractPhoneFromText(root.body?.innerText || root.documentElement?.innerText || '');
  if (phoneFromText) return phoneFromText;

  return null;
}

function _findPhoneActionElements() {
  const candidates = Array.from(document.querySelectorAll('button, a, [role="button"], [data-testid], [aria-label], [title]'));
  return candidates.filter((el) => {
    const haystack = [
      el.textContent,
      el.getAttribute('aria-label'),
      el.getAttribute('title'),
      el.getAttribute('data-testid'),
      el.getAttribute('href'),
    ].filter(Boolean).join(' ').toLowerCase();

    return haystack.includes('voir le numéro')
      || haystack.includes('voir le numero')
      || haystack.includes('afficher le numéro')
      || haystack.includes('afficher le numero')
      || haystack.includes('n° téléphone')
      || haystack.includes('n° telephone')
      || haystack.includes('téléphone')
      || haystack.includes('telephone')
      || haystack.includes('appeler')
      || haystack.includes('contact');
  });
}

async function _clickPhoneActionElement(el) {
  if (!el) return;
  try {
    el.scrollIntoView({ block: 'center', inline: 'center' });
  } catch {
    // ignore scroll failures
  }

  const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
  for (const type of events) {
    try {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    } catch {
      // ignore event failures
    }
  }

  try { el.click(); } catch { /* ignore */ }

  try {
    el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }));
    el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter' }));
  } catch {
    // ignore keyboard event failures
  }
}

/**
 * Reveal the seller's phone number by clicking "Voir le numéro" on La Centrale.
 * Same pattern as LeBonCoin — the phone is hidden behind a button click.
 */
async function _revealPhoneLC() {
  const structuredPhone = _getStructuredPhone();
  if (structuredPhone) return structuredPhone;

  const visiblePhone = _extractAnyPhoneFromDocument(document);
  if (visiblePhone) return visiblePhone;

  const phoneButtons = _findPhoneActionElements();
  if (phoneButtons.length === 0) return null;

  for (const phoneBtn of phoneButtons) {
    await _clickPhoneActionElement(phoneBtn);

    for (let attempt = 0; attempt < 8; attempt++) {
      await new Promise((r) => setTimeout(r, 400));

      const docPhone = _extractAnyPhoneFromDocument(document);
      if (docPhone) return docPhone;

      const container = phoneBtn.closest('section, article, div, aside') || phoneBtn.parentElement;
      if (container) {
        const localPhone = _extractPhoneFromText(container.textContent || '');
        if (localPhone) return localPhone;
      }
    }
  }

  return null;
}

/**
 * Detect if a "Voir le numéro" button exists on the page.
 */
function _hasPhoneButtonLC() {
  return Boolean(_getStructuredPhone() || _extractAnyPhoneFromDocument(document) || _findPhoneActionElements().length > 0);
}

export class LaCentraleExtractor extends SiteExtractor {
  static SITE_ID = 'lacentrale';
  static URL_PATTERNS = LC_URL_PATTERNS;

  /** @type {object|null} Cached gallery data */
  _gallery = null;
  /** @type {object} Cached tc_vars */
  _tcVars = {};
  /** @type {object} Cached cote data */
  _cote = { quotation: null, trustIndex: null };
  /** @type {object|null} Cached JSON-LD */
  _jsonLd = null;
  /** @type {object|null} Cached ad_data */
  _adData = null;

  isAdPage(url) {
    return LC_AD_PAGE_PATTERN.test(url);
  }

  hasPhone() {
    return _hasPhoneButtonLC();
  }

  isLoggedIn() {
    // La Centrale shows phone without login requirement
    return true;
  }

  async revealPhone() {
    const phone = await _revealPhoneLC();
    if (phone && this._adData) {
      this._adData.phone = phone;
      this._adData.has_phone = true;
    }
    return phone;
  }

  async extract() {
    // CLASSIFIED_GALLERY and tc_vars live in MAIN world.
    // The background script bridges them into hidden DOM elements
    // that we can read from the ISOLATED content script context.
    const galleryWin = _readBridgedData('__okazcar_lc_gallery__', window, 'CLASSIFIED_GALLERY');
    const tcVarsWin = _readBridgedData('__okazcar_lc_tcvars__', window, 'tc_vars');

    this._gallery = extractGallery(galleryWin);
    this._tcVars = extractTcVars(tcVarsWin);
    this._cote = extractCoteFromDom(document);
    this._jsonLd = extractJsonLd(document);

    // Need at least gallery or JSON-LD to produce meaningful data
    if (!this._gallery && !this._jsonLd) {
      console.warn('[OKazCar] La Centrale: no CLASSIFIED_GALLERY and no JSON-LD found');
      return null;
    }

    this._adData = normalizeToAdData(this._gallery, this._tcVars, this._cote, this._jsonLd);

    // Minimum viability check: need at least make or model
    if (!this._adData.make && !this._adData.model) {
      console.warn('[OKazCar] La Centrale: no make/model extracted');
      return null;
    }

    return {
      type: 'normalized',
      source: 'lacentrale',
      ad_data: this._adData,
    };
  }

  getVehicleSummary() {
    if (!this._adData) return null;
    return {
      make: this._adData.make || '',
      model: this._adData.model || '',
      year: String(this._adData.year_model || ''),
    };
  }

  getBonusSignals() {
    return buildBonusSignals(this._gallery, this._tcVars, this._cote);
  }

  async detectFreeReport() {
    return extractAutovizaUrl(document);
  }

  /**
   * Market price collection for La Centrale.
   * Builds search URLs from reverse-engineered listing params,
   * fetches listing pages, extracts prices, submits to backend.
   */
  async collectMarketPrices(progress) {
    if (!this._adData || !this._fetch || !this._apiUrl) {
      return { submitted: false, isCurrentVehicle: false };
    }
    return collectMarketPricesLC(this._adData, this._fetch, this._apiUrl, progress);
  }
}
