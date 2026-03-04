"use strict";

import { SiteExtractor } from '../base.js';
import { extractNextData, extractVehicleFromNextData } from './parser.js';
import { isUserLoggedIn, revealPhoneNumber, detectAutovizaUrl, isAdPageLBC } from './dom.js';
import { maybeCollectMarketPrices } from './collect.js';

export class LeBonCoinExtractor extends SiteExtractor {
  static SITE_ID = 'leboncoin';
  static URL_PATTERNS = [/leboncoin\.fr\/ad\//, /leboncoin\.fr\/voitures\//];

  constructor() {
    super();
    this._nextData = null;
    this._vehicle = null;
  }

  isAdPage(url) {
    return url.includes('leboncoin.fr/ad/') || url.includes('leboncoin.fr/voitures/');
  }

  async extract() {
    const nextData = await extractNextData();
    if (!nextData) return null;
    this._nextData = nextData;
    this._vehicle = extractVehicleFromNextData(nextData);
    return { type: 'raw', source: 'leboncoin', next_data: nextData };
  }

  getVehicleSummary() {
    if (!this._vehicle) return null;
    return { make: this._vehicle.make, model: this._vehicle.model, year: this._vehicle.year };
  }

  getExtractedVehicle() { return this._vehicle; }
  getNextData() { return this._nextData; }

  hasPhone() {
    return !!this._nextData?.props?.pageProps?.ad?.has_phone;
  }

  isLoggedIn() { return isUserLoggedIn(); }

  async revealPhone() {
    const ad = this._nextData?.props?.pageProps?.ad;
    if (!ad?.has_phone || !isUserLoggedIn()) return null;
    const phone = await revealPhoneNumber();
    if (phone && ad) {
      if (!ad.owner) ad.owner = {};
      ad.owner.phone = phone;
    }
    return phone;
  }

  async detectFreeReport() {
    return detectAutovizaUrl(this._nextData);
  }

  async collectMarketPrices(progress) {
    if (!this._vehicle?.make || !this._vehicle?.model || !this._vehicle?.year) {
      return { submitted: false };
    }
    return maybeCollectMarketPrices(this._vehicle, this._nextData, progress);
  }
}
