"use strict";

import { SiteExtractor } from '../base.js';
import { LC_URL_PATTERNS, LC_AD_PAGE_PATTERN } from './constants.js';
import { extractGallery, extractTcVars, extractCoteFromDom, extractJsonLd, extractAutovizaUrl } from './parser.js';
import { normalizeToAdData, buildBonusSignals } from './normalize.js';

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

/**
 * Reveal the seller's phone number by clicking "Voir le numéro" on La Centrale.
 * Same pattern as LeBonCoin — the phone is hidden behind a button click.
 */
async function _revealPhoneLC() {
  // 1. Check if phone is already visible (tel: link)
  const existingTelLinks = document.querySelectorAll('a[href^="tel:"]');
  for (const link of existingTelLinks) {
    const phone = link.href.replace("tel:", "").trim();
    if (phone && phone.length >= 10) return phone;
  }

  // 2. Find the "Voir le numéro" button
  const candidates = document.querySelectorAll('button, a, [role="button"]');
  let phoneBtn = null;
  for (const el of candidates) {
    const text = (el.textContent || "").toLowerCase().trim();
    if (text.includes("voir le numéro") || text.includes("voir le numero")
        || text.includes("afficher le numéro") || text.includes("afficher le numero")
        || text.includes("n° téléphone") || text.includes("n° telephone")
        || text.includes("appeler")) {
      phoneBtn = el;
      break;
    }
  }
  if (!phoneBtn) return null;

  // 3. Click and wait for phone to appear
  phoneBtn.click();
  for (let attempt = 0; attempt < 5; attempt++) {
    await new Promise((r) => setTimeout(r, 500));

    const telLinks = document.querySelectorAll('a[href^="tel:"]');
    for (const link of telLinks) {
      const phone = link.href.replace("tel:", "").trim();
      if (phone && phone.length >= 10) return phone;
    }

    // Fallback: regex match in button container
    const container = phoneBtn.closest("div") || phoneBtn.parentElement;
    if (container) {
      const match = container.textContent.match(/(?:\+33|0)\s*[1-9](?:[\s.-]*\d{2}){4}/);
      if (match) return match[0].replace(/[\s.-]/g, "");
    }
  }
  return null;
}

/**
 * Detect if a "Voir le numéro" button exists on the page.
 */
function _hasPhoneButtonLC() {
  const candidates = document.querySelectorAll('button, a, [role="button"]');
  for (const el of candidates) {
    const text = (el.textContent || "").toLowerCase().trim();
    if (text.includes("voir le numéro") || text.includes("voir le numero")
        || text.includes("afficher le numéro") || text.includes("afficher le numero")
        || text.includes("n° téléphone") || text.includes("n° telephone")
        || text.includes("appeler")) {
      return true;
    }
  }
  // Also check if phone already revealed (tel: link)
  const telLinks = document.querySelectorAll('a[href^="tel:"]');
  for (const link of telLinks) {
    if (link.href.replace("tel:", "").trim().length >= 10) return true;
  }
  return false;
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
   * Market price collection is explicitly disabled for La Centrale.
   * The listing page format has not been validated yet.
   */
  async collectMarketPrices(_progress) {
    return { submitted: false, isCurrentVehicle: false };
  }
}
