"use strict";

import { SiteExtractor } from '../base.js';
import { LC_URL_PATTERNS, LC_AD_PAGE_PATTERN } from './constants.js';
import { extractGallery, extractTcVars, extractCoteFromDom, extractJsonLd, extractAutovizaUrl } from './parser.js';
import { normalizeToAdData, buildBonusSignals } from './normalize.js';

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

  async extract() {
    this._gallery = extractGallery(window);
    this._tcVars = extractTcVars(window);
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
