"use strict";

/**
 * Extracteur principal La Centrale.
 *
 * Les donnees vehicule vivent dans le monde MAIN (window.CLASSIFIED_GALLERY,
 * window.tc_vars) mais le content script tourne en monde ISOLATED.
 * Le background.js injecte un bridge : il copie ces variables dans des
 * elements DOM caches que le content script peut lire.
 *
 * L'extraction du telephone utilise une strategie prudente :
 * on ne clique que sur le CTA telephone strict de LC (button avec
 * data-page-zone="telephone") pour eviter de declencher d'autres actions.
 */

import { SiteExtractor } from '../base.js';
import { LC_URL_PATTERNS, LC_AD_PAGE_PATTERN } from './constants.js';
import { extractGallery, extractTcVars, extractCoteFromDom, extractJsonLd, extractAutovizaUrl } from './parser.js';
import { normalizeToAdData, buildBonusSignals } from './normalize.js';
import { collectMarketPricesLC } from './collect.js';

/**
 * Lit les donnees bridgees depuis le monde MAIN via un element DOM cache.
 * Le background.js injecte CLASSIFIED_GALLERY / tc_vars dans des divs
 * pour que le content script (monde ISOLATED) puisse y acceder.
 *
 * @param {string} domId - ID de l'element DOM bridge
 * @param {Window} win - Objet window (fallback direct si accessible)
 * @param {string} propName - Nom de la propriete a lire
 * @returns {object} Objet faux-window avec la propriete extraite
 */
function _readBridgedData(domId, win, propName) {
  const fakeWin = {};

  // 1. Bridge DOM (chemin normal en production)
  const el = document.getElementById(domId);
  if (el && el.textContent) {
    try {
      fakeWin[propName] = JSON.parse(el.textContent);
      return fakeWin;
    } catch { /* JSON malformed, fallback */ }
  }

  // 2. Fallback : acces direct a window (en test ou si accessible)
  if (win[propName]) {
    fakeWin[propName] = win[propName];
  }

  return fakeWin;
}

/** Nettoie et valide un numero de telephone francais */
function _cleanPhone(phone) {
  if (!phone) return null;
  const compact = String(phone).replace(/[^\d+]/g, '').trim();
  if (/^\+33\d{9}$/.test(compact) || /^0\d{9}$/.test(compact)) return compact;
  return null;
}

/** Extrait un telephone depuis du texte brut (regex format francais) */
function _extractPhoneFromText(text) {
  if (!text) return null;
  const match = String(text).match(/(?:\+33|0)\s*[1-9](?:[\s.-]*\d{2}){4}/);
  return match ? _cleanPhone(match[0]) : null;
}

/**
 * Cherche le telephone dans les donnees structurees (gallery + JSON-LD).
 * Priorite aux donnees bridgees, puis JSON-LD en fallback.
 */
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
      // JSON-LD malformed
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

/** Cherche un telephone visible dans le document (liens tel: ou texte brut) */
function _extractAnyPhoneFromDocument(root = document) {
  const telLinks = root.querySelectorAll?.('a[href^="tel:"]') || [];
  for (const link of telLinks) {
    const phone = _cleanPhone(link.href.replace(/^tel:/i, ''));
    if (phone) return phone;
  }

  const phoneText = root.body?.innerText
    || root.documentElement?.innerText
    || root.body?.textContent
    || root.documentElement?.textContent
    || '';
  const phoneFromText = _extractPhoneFromText(phoneText);
  if (phoneFromText) return phoneFromText;

  return null;
}

/** Remonte au conteneur de la zone contact pour limiter la recherche de telephone */
function _getPhoneActionContainer(el) {
  return el?.closest?.(
    '[data-page-zone="zoneContact"], [class*="ContactInformation_contactInformation"], section, article, aside, div',
  ) || el?.parentElement || null;
}

/**
 * Evalue un element comme candidat bouton telephone.
 * On est strict : uniquement les vrais CTA telephone de LC,
 * pas les liens FAQ ou contact generiques.
 */
function _scoreStrictPhoneButton(el) {
  if (!el || el.tagName !== 'BUTTON') return 0;
  if ((el.getAttribute('type') || '').toLowerCase() !== 'button') return 0;
  if (el.closest('header, nav, footer')) return 0;

  const text = (el.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const pageZone = (el.getAttribute('data-page-zone') || '').toLowerCase();
  const testid = (el.getAttribute('data-testid') || '').toLowerCase();
  const tracking = (el.getAttribute('data-tracking-click-id') || '').toLowerCase();
  const className = typeof el.className === 'string' ? el.className.toLowerCase() : '';

  let score = 0;
  if (pageZone === 'telephone') score += 120;
  if (className.includes('contactinformation_phone')) score += 90;
  if (tracking.includes('phone') || tracking.includes('telephone')) score += 60;
  if (testid === 'button') score += 10;
  if (text.includes('n° téléphone') || text.includes('n° telephone')) score += 80;
  if (text.includes('voir le numéro') || text.includes('voir le numero')) score += 80;
  if (text.includes('appeler')) score += 40;

  return score;
}

/** Trouve les boutons telephone stricts, tries par score decroissant */
function _findPhoneActionElements() {
  const candidates = Array.from(document.querySelectorAll('button[type="button"], button[data-page-zone], button[data-tracking-click-id]'));
  return candidates
    .map((el) => ({ el, score: _scoreStrictPhoneButton(el) }))
    .filter(({ score }) => score >= 100)
    .sort((a, b) => b.score - a.score)
    .map(({ el }) => el);
}

/**
 * Simule un clic complet sur un element (pointer + mouse + click).
 * Necessaire car LC ecoute parfois des evenements specifiques.
 */
async function _clickPhoneActionElement(el) {
  if (!el) return;

  try {
    el.scrollIntoView({ block: 'center', inline: 'center' });
  } catch {
    // scroll peut echouer dans certains contextes
  }

  const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
  for (const type of events) {
    try {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    } catch {
      // ignore les echecs de dispatch
    }
  }

  try { el.click(); } catch { /* ignore */ }
}

/**
 * Revele le numero de telephone du vendeur sur La Centrale.
 *
 * Politique de securite : on ne clique que sur les CTA telephone stricts
 * (button[data-page-zone="telephone"] et equivalents proches).
 * Ca evite de matcher des liens FAQ/contact tout en preservant
 * l'extraction reelle quand le widget telephone est present.
 */
async function _revealPhoneLC() {
  // D'abord chercher dans les donnees structurees (pas besoin de clic)
  const structuredPhone = _getStructuredPhone();
  if (structuredPhone) return structuredPhone;

  // Puis chercher un numero deja visible dans le DOM
  const visiblePhone = _extractAnyPhoneFromDocument(document);
  if (visiblePhone) return visiblePhone;

  // En dernier recours : cliquer le CTA telephone et attendre la revelation
  const phoneButtons = _findPhoneActionElements();
  if (phoneButtons.length === 0) return null;

  for (const phoneBtn of phoneButtons) {
    await _clickPhoneActionElement(phoneBtn);

    for (let attempt = 0; attempt < 8; attempt++) {
      await new Promise((r) => setTimeout(r, 300));

      const docPhone = _extractAnyPhoneFromDocument(document);
      if (docPhone) return docPhone;

      // Chercher aussi dans le conteneur local du bouton
      const container = _getPhoneActionContainer(phoneBtn);
      if (container) {
        const localPhone = _extractPhoneFromText(container.textContent || '');
        if (localPhone) return localPhone;
      }
    }
  }

  return null;
}

/** Verifie si un telephone est disponible ou revelable via le CTA strict */
function _hasPhoneButtonLC() {
  return Boolean(_getStructuredPhone() || _extractAnyPhoneFromDocument(document) || _findPhoneActionElements().length > 0);
}

export class LaCentraleExtractor extends SiteExtractor {
  static SITE_ID = 'lacentrale';
  static URL_PATTERNS = LC_URL_PATTERNS;

  /** @type {object|null} Donnees gallery en cache */
  _gallery = null;
  /** @type {object} Variables tc_vars en cache */
  _tcVars = {};
  /** @type {object} Donnees cotation en cache */
  _cote = { quotation: null, trustIndex: null };
  /** @type {object|null} JSON-LD en cache */
  _jsonLd = null;
  /** @type {object|null} ad_data normalise en cache */
  _adData = null;

  isAdPage(url) {
    return LC_AD_PAGE_PATTERN.test(url);
  }

  hasPhone() {
    return _hasPhoneButtonLC();
  }

  /** LC n'a pas de mur de connexion pour voir les annonces */
  isLoggedIn() {
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

  /**
   * Extrait les donnees de l'annonce La Centrale.
   *
   * CLASSIFIED_GALLERY et tc_vars vivent dans le monde MAIN.
   * Le background script les bridge dans des elements DOM caches
   * lisibles depuis le content script (monde ISOLATED).
   */
  async extract() {
    const galleryWin = _readBridgedData('__okazcar_lc_gallery__', window, 'CLASSIFIED_GALLERY');
    const tcVarsWin = _readBridgedData('__okazcar_lc_tcvars__', window, 'tc_vars');

    this._gallery = extractGallery(galleryWin);
    this._tcVars = extractTcVars(tcVarsWin);
    this._cote = extractCoteFromDom(document);
    this._jsonLd = extractJsonLd(document);

    // Il faut au moins gallery ou JSON-LD pour produire des donnees utiles
    if (!this._gallery && !this._jsonLd) {
      console.warn('[OKazCar] La Centrale: no CLASSIFIED_GALLERY and no JSON-LD found');
      return null;
    }

    this._adData = normalizeToAdData(this._gallery, this._tcVars, this._cote, this._jsonLd);

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

  getLocation() {
    return this._adData?.location || null;
  }

  async detectFreeReport() {
    return extractAutovizaUrl(document);
  }

  /**
   * Collecte de prix marche pour La Centrale.
   * Delegue a collectMarketPricesLC qui gere la construction d'URL,
   * le fetch des pages listing et l'extraction de prix.
   */
  async collectMarketPrices(progress) {
    if (!this._adData || !this._fetch || !this._apiUrl) {
      return { submitted: false, isCurrentVehicle: false };
    }
    return collectMarketPricesLC(this._adData, this._fetch, this._apiUrl, progress);
  }
}
