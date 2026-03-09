"use strict";

import { SiteExtractor } from '../base.js';
import { AD_PAGE_PATTERN, PV_URL_PATTERNS } from './constants.js';
import { parseJsonLd, parseAdPage } from './parser.js';
import { buildBonusSignals, normalizeToAdData } from './normalize.js';

export class ParuVenduExtractor extends SiteExtractor {
  static SITE_ID = 'paruvendu';
  static URL_PATTERNS = PV_URL_PATTERNS;

  _jsonLd = null;
  _domData = null;
  _adData = null;

  isAdPage(url) {
    return AD_PAGE_PATTERN.test(url);
  }

  async extract() {
    this._jsonLd = parseJsonLd(document);
    this._domData = parseAdPage(document, window.location.href);
    this._adData = normalizeToAdData(this._jsonLd, this._domData, window.location.href);

    const hasCoreData = Boolean(
      this._adData?.price_eur || this._adData?.make || this._adData?.model || this._adData?.title
    );
    if (!hasCoreData) return null;

    return {
      type: 'normalized',
      source: 'paruvendu',
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

  isLoggedIn() {
    return true;
  }

  async revealPhone() {
    return this._adData?.phone || null;
  }

  hasPhone() {
    return Boolean(this._adData?.has_phone);
  }

  async detectFreeReport() {
    return null;
  }

  getBonusSignals() {
    return buildBonusSignals(this._domData || {});
  }

  getLocation() {
    return this._adData?.location || null;
  }

  async collectMarketPrices() {
    return { submitted: false, isCurrentVehicle: false };
  }
}
