"use strict";

/**
 * Extracteur LeBonCoin — implementation concrete de SiteExtractor.
 *
 * LBC fournit toutes ses donnees dans un blob __NEXT_DATA__ (Next.js).
 * On extrait ce blob et on l'envoie brut au backend (type: 'raw'),
 * contrairement a AS24/LC qui normalisent cote extension.
 */

import { SiteExtractor } from '../base.js';
import { extractNextData, extractVehicleFromNextData } from './parser.js';
import { isUserLoggedIn, revealPhoneNumber, detectAutovizaUrl, isAdPageLBC } from './dom.js';
import { maybeCollectMarketPrices } from './collect.js';

export class LeBonCoinExtractor extends SiteExtractor {
  static SITE_ID = 'leboncoin';
  static URL_PATTERNS = [/leboncoin\.fr\/ad\//, /leboncoin\.fr\/voitures\//];

  constructor() {
    super();
    // Cache du __NEXT_DATA__ et du vehicule parse — evite de re-extraire
    this._nextData = null;
    this._vehicle = null;
  }

  isAdPage(url) {
    return url.includes('leboncoin.fr/ad/') || url.includes('leboncoin.fr/voitures/');
  }

  /**
   * Extrait le __NEXT_DATA__ de LBC et en derive les infos vehicule.
   * On renvoie le payload brut car le backend sait le parser plus finement.
   */
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

  /** Acces direct au vehicule extrait (utilise par collect.js) */
  getExtractedVehicle() { return this._vehicle; }
  /** Acces direct au nextData brut */
  getNextData() { return this._nextData; }

  getLocation() {
    const loc = this._nextData?.props?.pageProps?.ad?.location;
    if (!loc) return null;
    return { city: loc.city || '', zipcode: loc.zipcode || '', department: '' };
  }

  /**
   * LBC expose has_phone dans le JSON de l'annonce.
   * Pas besoin de scraper le DOM pour savoir si le telephone est disponible.
   */
  hasPhone() {
    return !!this._nextData?.props?.pageProps?.ad?.has_phone;
  }

  isLoggedIn() { return isUserLoggedIn(); }

  /**
   * Revele le telephone et le stocke dans le nextData pour que
   * le backend le retrouve au meme endroit que les autres champs.
   */
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

  /**
   * Lance la collecte de prix du marche.
   * On verifie d'abord qu'on a un vehicule exploitable (marque + modele + annee).
   */
  async collectMarketPrices(progress) {
    if (!this._vehicle?.make || !this._vehicle?.model || !this._vehicle?.year) {
      return { submitted: false };
    }
    return maybeCollectMarketPrices(this._vehicle, this._nextData, progress);
  }
}
