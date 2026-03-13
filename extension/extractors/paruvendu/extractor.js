"use strict";

/**
 * Extracteur principal ParuVendu.
 *
 * ParuVendu est le plus simple des extracteurs : pas de collecte de prix
 * marche (volume insuffisant sur le site), pas de revelation de telephone,
 * pas de rapport gratuit. On se contente d'extraire les donnees de l'annonce
 * depuis le JSON-LD et le DOM.
 */

import { SiteExtractor } from '../base.js';
import { AD_PAGE_PATTERN, PV_URL_PATTERNS } from './constants.js';
import { parseJsonLd, parseAdPage } from './parser.js';
import { buildBonusSignals, normalizeToAdData } from './normalize.js';

export class ParuVenduExtractor extends SiteExtractor {
  static SITE_ID = 'paruvendu';
  static URL_PATTERNS = PV_URL_PATTERNS;

  /** @type {object|null} Donnees JSON-LD en cache */
  _jsonLd = null;
  /** @type {object|null} Donnees extraites du DOM en cache */
  _domData = null;
  /** @type {object|null} ad_data normalise en cache */
  _adData = null;

  isAdPage(url) {
    return AD_PAGE_PATTERN.test(url);
  }

  /**
   * Extrait les donnees de l'annonce ParuVendu.
   * Combine JSON-LD (donnees structurees) et scraping DOM (complement).
   */
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

  /** PV n'a pas de mur de connexion */
  isLoggedIn() {
    return true;
  }

  /** Le telephone est deja dans les donnees (pas de bouton a cliquer) */
  async revealPhone() {
    return this._adData?.phone || null;
  }

  hasPhone() {
    return Boolean(this._adData?.has_phone);
  }

  /** PV ne propose pas de rapport historique gratuit */
  async detectFreeReport() {
    return null;
  }

  getBonusSignals() {
    return buildBonusSignals(this._domData || {});
  }

  getLocation() {
    return this._adData?.location || null;
  }

  /** Pas de collecte de prix marche sur PV (volume trop faible) */
  async collectMarketPrices() {
    return { submitted: false, isCurrentVehicle: false };
  }
}
