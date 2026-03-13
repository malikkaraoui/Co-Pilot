"use strict";

/**
 * La Centrale — construction d'URL de recherche et extraction de prix.
 *
 * Parametres URL reverse-engineered depuis lacentrale.fr/listing :
 *   ?makesModelsCommercialNames=PEUGEOT         (marque)
 *   ?makesModelsCommercialNames=PEUGEOT%3A308    (marque:modele)
 *   ?energies=dies                               (carburant)
 *   ?gearbox=man                                 (boite)
 *   ?yearMin=2020&yearMax=2024                   (fourchette annees)
 *   ?mileageMin=10000&mileageMax=80000           (fourchette km)
 *
 * L'extraction de prix combine 3 strategies :
 * 1. Iframe same-origin (rendu JS complet, le plus fiable)
 * 2. Fetch HTML + __NEXT_DATA__ / JSON inline
 * 3. Regex sur les elements prix dans le HTML brut
 *
 * LC deploie un anti-bot DataDome (captcha) qui peut bloquer les fetches.
 * L'iframe same-origin fonctionne mieux car elle partage les cookies
 * de session de l'utilisateur.
 */

import { isChromeRuntimeAvailable } from '../../utils/fetch.js';
import {
  LC_AD_PAGE_PATTERN,
  LC_LISTING_BASE, LC_SEARCH_FUEL_CODES, LC_SEARCH_GEARBOX_CODES,
  LC_SEARCH_REGION_CODES,
} from './constants.js';

/** Timeout de chargement de l'iframe en ms */
const LC_IFRAME_LOAD_TIMEOUT_MS = 5000;
/** Temps d'attente pour le rendu JS dans l'iframe */
const LC_IFRAME_RENDER_WAIT_MS = 2000;
/** Intervalle de polling pour verifier si les annonces sont apparues */
const LC_IFRAME_POLL_INTERVAL_MS = 500;

/** Longueur max des excerpts dans les diagnostics */
const LC_DIAGNOSTIC_BODY_EXCERPT_MAX = 320;
const LC_DIAGNOSTIC_REASON_MAX = 180;

// ── URL Builder ─────────────────────────────────────────────────

/**
 * Construit une URL de recherche La Centrale depuis les criteres vehicule.
 *
 * @param {object} opts
 * @param {string} opts.make - Nom de marque (ex: "PEUGEOT")
 * @param {string} [opts.model] - Nom de modele (ex: "308")
 * @param {number} [opts.yearMin] - Annee minimum
 * @param {number} [opts.yearMax] - Annee maximum
 * @param {number} [opts.mileageMin] - Kilometrage minimum
 * @param {number} [opts.mileageMax] - Kilometrage maximum
 * @param {string} [opts.fuel] - Carburant normalise (ex: "diesel")
 * @param {string} [opts.gearbox] - Boite normalisee (ex: "manual")
 * @returns {string} URL de listing complete
 */
export function buildLcSearchUrl(opts) {
  const params = new URLSearchParams();

  // Marque + modele optionnel : "PEUGEOT" ou "PEUGEOT::308" (double deux-points !)
  // Verifie le 2026-03-09 : LC utilise BRAND::MODEL (pas un seul deux-points)
  const make = (opts.make || '').toUpperCase();
  if (make) {
    const token = opts.model
      ? `${make}::${opts.model.toUpperCase()}`
      : make;
    params.set('makesModelsCommercialNames', token);
  }

  // Fourchette d'annees
  // Convention LC : on omet yearMax quand il egale l'annee courante
  if (opts.yearMin) params.set('yearMin', String(opts.yearMin));
  const currentYear = new Date().getFullYear();
  if (opts.yearMax && opts.yearMax < currentYear) {
    params.set('yearMax', String(opts.yearMax));
  }

  // Fourchette de kilometrage
  if (opts.mileageMin != null) params.set('mileageMin', String(opts.mileageMin));
  if (opts.mileageMax != null) params.set('mileageMax', String(opts.mileageMax));

  // Carburant
  if (opts.fuel) {
    const code = LC_SEARCH_FUEL_CODES[(opts.fuel || '').toLowerCase()];
    if (code) params.set('energies', code);
  }

  // Boite de vitesses
  if (opts.gearbox) {
    const code = LC_SEARCH_GEARBOX_CODES[(opts.gearbox || '').toLowerCase()];
    if (code) params.set('gearbox', code);
  }

  // Regions (optionnel, codes ISO separes par virgules)
  if (opts.regions && Array.isArray(opts.regions) && opts.regions.length > 0) {
    const codes = opts.regions
      .map((r) => LC_SEARCH_REGION_CODES[r] || r)
      .filter(Boolean);
    if (codes.length > 0) params.set('regions', codes.join(','));
  }

  return `${LC_LISTING_BASE}?${params.toString()}`;
}

/**
 * Calcule une fourchette de kilometrage raisonnable autour du km actuel.
 * LC utilise des min/max explicites, on cree des brackets larges
 * pour capter les vehicules comparables.
 *
 * @param {number} km - Kilometrage actuel du vehicule
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

// ── Extraction de prix ────────────────────────────────────────────

function _sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Normalise les espaces dans un texte */
function _normalizeText(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

/** Tronque un texte a une longueur max avec ellipse */
function _clipLcText(text, maxLen) {
  const normalized = _normalizeText(text);
  if (!normalized) return '';
  if (normalized.length <= maxLen) return normalized;
  return `${normalized.slice(0, Math.max(0, maxLen - 1))}\u2026`;
}

/** Extrait un apercu du body HTML pour le diagnostic (sans scripts/styles) */
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

/** Extrait le contenu de la balise <title> depuis le HTML brut */
function _extractLcTitleFromHtml(html) {
  const match = String(html || '').match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  return match ? _clipLcText(match[1], 140) : null;
}

/** Detecte si la page affiche zero resultats (pas un blocage — juste vide) */
function _looksLikeZeroResultsPage(html) {
  return /\b0\s*(?:resultat|r\u00e9sultat|annonce)s?\b|aucun\s+(?:resultat|r\u00e9sultat|vehicule|v\u00e9hicule|annonce)|pas de resultats|pas de r\u00e9sultats/i.test(html || '');
}

/** Detecte si le HTML contient des signaux d'annonces (meme si le parsing echoue) */
function _hasLcAdSignals(html) {
  return /occasion-annonce-|"classifieds"|__NEXT_DATA__|application\/ld\+json|ItemList|ListItem|moteur de recherche|searchData/i.test(html || '');
}

/** Resume les ressources reseau LC interessantes (pour diagnostic) */
function _summarizeLcResources(resources) {
  if (!Array.isArray(resources) || resources.length === 0) return null;
  return _clipLcText(resources.slice(0, 5).join(' | '), 500);
}

/** Cree un objet diagnostic avec des valeurs par defaut */
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

/** Finalise un diagnostic en tronquant les champs texte */
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

/**
 * Classifie un HTML vide : anti-bot, zero resultats, ou HTML sans annonces.
 * Retourne un diagnostic structure pour le search_log du backend.
 */
function _classifyLcEmptyHtml(html, baseDiagnostic = {}) {
  const antiBot = _looksLikeAntiBotPage(html);
  if (antiBot) {
    return _finalizeLcDiagnostic({
      ...baseDiagnostic,
      reasonTag: baseDiagnostic.httpStatus === 403 ? 'anti_bot_403' : 'anti_bot_page',
      reason: baseDiagnostic.httpStatus === 403
        ? 'R\u00e9ponse 403 avec signature anti-bot La Centrale/DataDome'
        : 'HTML de challenge anti-bot d\u00e9tect\u00e9',
      antiBotDetected: true,
      bodyExcerpt: baseDiagnostic.bodyExcerpt || _extractLcBodyExcerpt(html),
      htmlTitle: baseDiagnostic.htmlTitle || _extractLcTitleFromHtml(html),
    });
  }

  if (_looksLikeZeroResultsPage(html)) {
    return _finalizeLcDiagnostic({
      ...baseDiagnostic,
      reasonTag: 'true_zero_results',
      reason: 'Page listing valide mais z\u00e9ro r\u00e9sultat affich\u00e9 par La Centrale',
      bodyExcerpt: baseDiagnostic.bodyExcerpt || _extractLcBodyExcerpt(html),
      htmlTitle: baseDiagnostic.htmlTitle || _extractLcTitleFromHtml(html),
    });
  }

  if (_hasLcAdSignals(html)) {
    return _finalizeLcDiagnostic({
      ...baseDiagnostic,
      reasonTag: 'parser_no_match',
      reason: 'HTML re\u00e7u avec signaux d\u2019annonces mais parsing rest\u00e9 vide',
      bodyExcerpt: baseDiagnostic.bodyExcerpt || _extractLcBodyExcerpt(html),
      htmlTitle: baseDiagnostic.htmlTitle || _extractLcTitleFromHtml(html),
    });
  }

  return _finalizeLcDiagnostic({
    ...baseDiagnostic,
    reasonTag: 'html_without_cards',
    reason: 'HTML re\u00e7u sans cartes d\u2019annonces d\u00e9tectables',
    bodyExcerpt: baseDiagnostic.bodyExcerpt || _extractLcBodyExcerpt(html),
    htmlTitle: baseDiagnostic.htmlTitle || _extractLcTitleFromHtml(html),
  });
}

/**
 * Parse un prix depuis le texte d'une carte annonce LC.
 * Essaie d'abord avec le symbole euro, puis fallback sur le dernier
 * nombre qui ressemble a un prix (les cartes boostees omettent parfois le signe euro).
 */
function _parseLcPrice(text) {
  const norm = _normalizeText(text);
  const withEuro = norm.match(/(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{4,6})\s*\u20ac/i);
  if (withEuro) {
    const price = parseInt(withEuro[1].replace(/[\s\u00a0]/g, ''), 10);
    if (Number.isFinite(price) && price >= 500) return price;
  }
  // Fallback : dernier nombre "prix-like" (en evitant les km et les annees)
  const allNums = [...norm.matchAll(/(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{4,6})(?!\s*km(?!\d))/gi)];
  for (let i = allNums.length - 1; i >= 0; i--) {
    const raw = allNums[i][1].replace(/[\s\u00a0]/g, '');
    const val = parseInt(raw, 10);
    if (!Number.isFinite(val) || val < 500 || val > 200000) continue;
    // Exclure les annees isolees (ex: "2018" tout seul)
    if (val >= 1900 && val <= 2099 && raw.length === 4) continue;
    return val;
  }
  return null;
}

/**
 * Parse une annee depuis le texte d'une carte.
 * Utilise (?<!\d)/(?!\d) au lieu de \b car LC concatene le texte
 * sans espaces (ex: "SUPER2018Manuelle") et \b echoue entre lettre et chiffre.
 */
function _parseLcYear(text) {
  const match = _normalizeText(text).match(/(?<!\d)((?:19|20)\d{2})(?!\d)/);
  return match ? parseInt(match[1], 10) : null;
}

/**
 * Parse le kilometrage depuis le texte d'une carte.
 * Meme astuce avec (?!\d) apres "km" car LC concatene (ex: "94 373 kmEssence").
 */
function _parseLcKm(text) {
  const match = _normalizeText(text).match(/(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{4,6})\s*km(?!\d)/i);
  if (!match) return null;
  const km = parseInt(match[1].replace(/[\s\u00a0]/g, ''), 10);
  return Number.isFinite(km) ? km : null;
}

/** Parse un nombre depuis une valeur qui peut etre string ou number */
function _parseLcMaybeNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return null;
  const match = value.match(/(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{4,7})/);
  if (!match) return null;
  const num = parseInt(match[1].replace(/[\s\u00a0]/g, ''), 10);
  return Number.isFinite(num) ? num : null;
}

/** Parse une annee depuis un champ JSON-LD (peut etre string, number, ou date) */
function _parseLcJsonLdYear(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (!value) return null;
  const match = String(value).match(/(?<!\d)((?:19|20)\d{2})(?!\d)/);
  return match ? parseInt(match[1], 10) : null;
}

/**
 * Remonte le DOM depuis un lien d'annonce pour trouver la carte parente.
 * La carte doit contenir une annee et un prix pour etre consideree valide.
 */
function _findLcAdCard(link) {
  let node = link;
  while (node && node !== node.ownerDocument?.body) {
    const text = _normalizeText(node.textContent);
    if (text && text.length >= 20 && text.length < 2000
      && /(?<!\d)(?:19|20)\d{2}(?!\d)/.test(text)
      && (/\u20ac/.test(text) || /\d{4,6}/.test(text))) {
      return node;
    }
    node = node.parentElement;
  }
  return link;
}

/** Collecte les ressources reseau LC interessantes depuis performance API */
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

/** Deduplique les annonces par combinaison prix+annee+km */
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

/**
 * Descend recursivement dans un noeud JSON-LD pour extraire les annonces.
 * Gere les structures OfferCatalog, ItemList, @graph et imbrications arbitraires.
 */
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

/** Extrait les annonces depuis tous les blocs JSON-LD d'un document */
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
      // JSON-LD malformed, on passe
    }
  }
  return _dedupeAds(ads);
}

/**
 * Cree une iframe invisible pour charger une page LC.
 * Grande taille (1440x3200) pour forcer le rendu de toutes les annonces.
 */
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

/**
 * Verifie si on peut utiliser l'iframe same-origin.
 * Necessaire : etre sur lacentrale.fr et que l'URL cible soit same-origin.
 */
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

/**
 * Extrait les annonces depuis le DOM rendu d'une page de resultats LC.
 * Cherche les liens vers des pages d'annonces et remonte au conteneur carte
 * pour extraire prix, annee et km.
 *
 * @param {Document} root - Document (principal ou iframe)
 * @returns {Array<{price: number, year: number|null, km: number|null}>}
 */
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

/** Detecte les signatures de page anti-bot (DataDome/captcha) */
function _looksLikeAntiBotPage(html) {
  return /captcha-delivery\.com|Please enable JS and disable any ad blocker|data-cfasync="false"/i.test(html || '');
}

/**
 * Charge une page de listing LC dans une iframe same-origin pour extraire les annonces.
 * L'iframe beneficie des cookies de session → moins de chances d'etre bloquee par l'anti-bot.
 * On poll le DOM de l'iframe pendant le rendu JS pour detecter les annonces.
 */
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
          reason: 'Iframe charg\u00e9e mais document inaccessible',
          fetchMode: 'iframe',
        }),
      };
    }

    // Polling : attendre que les annonces apparaissent dans le DOM rendu
    let ads = [];
    let jsonLdAds = [];
    let waited = 0;
    while (waited < LC_IFRAME_RENDER_WAIT_MS) {
      ads = extractLcAdsFromRenderedDom(frameDoc);
      jsonLdAds = _extractAdsFromJsonLdScripts(frameDoc);
      if (ads.length > 0 || jsonLdAds.length > 0) break;

      // Scroller pour forcer le lazy-loading
      try {
        frameWin.scrollTo(0, Math.max(
          frameDoc.documentElement?.scrollHeight || 0,
          frameDoc.body?.scrollHeight || 0,
        ));
      } catch {
        // ignore les erreurs de scroll
      }

      await _sleep(LC_IFRAME_POLL_INTERVAL_MS);
      waited += LC_IFRAME_POLL_INTERVAL_MS;
    }

    const html = frameDoc.documentElement.outerHTML || '';
    const resources = _collectLcInterestingResources(frameWin);
    // Combiner toutes les sources d'annonces
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

/**
 * Fetch le HTML d'une page listing LC.
 * Essaie d'abord via le background script (monde MAIN, meilleurs cookies)
 * puis fallback sur fetch direct depuis le content script.
 */
async function _fetchLcListingHtml(searchUrl) {
  // Strategie 1 : fetch via le background script (monde MAIN)
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

  // Strategie 2 : fetch direct (content script)
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
 * Fetch et extrait les prix depuis une page de listing La Centrale (version detaillee).
 *
 * Pipeline d'extraction :
 * 1. Iframe same-origin (rendu JS complet, le plus fiable)
 * 2. Fetch HTML + __NEXT_DATA__ JSON blob
 * 3. Fetch HTML + JSON inline (window.__INITIAL_STATE__)
 * 4. Regex fallback sur les elements prix dans le HTML brut
 *
 * Retourne aussi un diagnostic detaille pour le search_log du backend.
 *
 * @param {string} searchUrl - URL de listing LC complete
 * @param {number} targetYear - Annee cible pour le filtrage
 * @param {number} yearSpread - Tolerance en annees autour de la cible
 * @returns {Promise<{prices: Array, diagnostic: object}>}
 */
export async function fetchLcSearchPricesDetailed(searchUrl, targetYear, yearSpread) {
  // D'abord essayer l'iframe (meilleur rendu JS)
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
          reason: `Extraction DOM iframe r\u00e9ussie (${iframeProbe.ads.length} annonces)`,
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

  // Fallback : fetch HTML classique
  const fetchResult = await _fetchLcListingHtml(searchUrl);
  const html = fetchResult?.body || null;
  if (!html) {
    return {
      prices: [],
      diagnostic: _finalizeLcDiagnostic({
        ...lastDiagnostic,
        reasonTag: fetchResult?.status === 403 ? 'anti_bot_403' : (lastDiagnostic.reasonTag || 'html_unavailable'),
        reason: fetchResult?.status === 403
          ? 'R\u00e9ponse 403 sans HTML exploitable renvoy\u00e9e par La Centrale'
          : (fetchResult?.error || lastDiagnostic.reason || 'Aucun HTML r\u00e9cup\u00e9r\u00e9 pour la recherche La Centrale'),
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

  // Extraction en cascade depuis le HTML
  let ads = _extractAdsFromNextData(html);

  if (!ads || ads.length === 0) {
    ads = _extractAdsFromInlineJson(html);
  }

  // Dernier recours : regex sur les prix dans le HTML brut
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

  return {
    prices: _filterAds(ads, targetYear, yearSpread),
    diagnostic: _finalizeLcDiagnostic({
      ...lastDiagnostic,
      reasonTag: 'ok',
      reason: `Extraction HTML r\u00e9ussie (${ads.length} annonces brutes)`,
      fetchMode: fetchResult?.fetchMode,
      httpStatus: fetchResult?.status,
      bodyExcerpt: _extractLcBodyExcerpt(html),
      htmlTitle: _extractLcTitleFromHtml(html),
      responseBytes: html.length,
    }),
  };
}

/** Version simplifiee qui retourne juste le tableau de prix */
export async function fetchLcSearchPrices(searchUrl, targetYear, yearSpread) {
  const result = await fetchLcSearchPricesDetailed(searchUrl, targetYear, yearSpread);
  return result.prices;
}

// ── Helpers internes d'extraction ─────────────────────────────────

/**
 * Extrait les annonces depuis le __NEXT_DATA__ JSON blob.
 * LC (Next.js) stocke les classifieds dans plusieurs chemins possibles
 * selon la version de la page.
 */
function _extractAdsFromNextData(html) {
  const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (!match) return null;

  try {
    const data = JSON.parse(match[1]);
    const pp = data?.props?.pageProps || {};

    // Essayer tous les chemins connus pour les classifieds LC
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

    // Essayer un wrapper results
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

/**
 * Extrait les annonces depuis le JSON inline (window.__INITIAL_STATE__ ou similaire).
 * Certaines pages LC utilisent cette alternative au __NEXT_DATA__.
 */
function _extractAdsFromInlineJson(html) {
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
    } catch { /* continuer avec le pattern suivant */ }
  }
  return null;
}

/** Dernier recours : extraction de prix par regex dans le HTML brut */
function _extractPricesFromHtml(html) {
  const pricePattern = /(\d{1,3}(?:[\s\u00a0]\d{3})*)\s*\u20ac/g;
  const prices = [];
  let m;
  while ((m = pricePattern.exec(html)) !== null) {
    const raw = m[1].replace(/[\s\u00a0]/g, '');
    const price = parseInt(raw, 10);
    if (price >= 500 && price <= 200000) {
      prices.push({ price, year: null, km: null });
    }
  }
  // Deduplication (meme prix = probablement le meme element rendu 2x)
  const seen = new Set();
  return prices.filter((p) => {
    if (seen.has(p.price)) return false;
    seen.add(p.price);
    return true;
  });
}

/**
 * Convertit les objets classified LC vers notre format interne {price, year, km}.
 * Gere les multiples formes possibles des champs LC.
 */
function _mapLcClassifieds(classifieds) {
  return classifieds
    .map((c) => {
      const price = c.price ?? c.priceListing ?? c.priceLabel ?? null;
      const priceInt = typeof price === 'number' ? price
        : typeof price === 'string' ? parseInt(price.replace(/[^\d]/g, ''), 10)
        : null;

      let year = c.year ?? c.vehicle?.year ?? null;
      if (!year && c.vehicle?.firstTrafficDate) {
        const ym = String(c.vehicle.firstTrafficDate).match(/^(\d{4})/);
        if (ym) year = parseInt(ym[1], 10);
      }
      if (!year && c.firstTrafficDate) {
        const ym = String(c.firstTrafficDate).match(/^(\d{4})/);
        if (ym) year = parseInt(ym[1], 10);
      }

      const km = c.mileage ?? c.vehicle?.mileage ?? c.km ?? null;

      return { price: priceInt, year, km };
    })
    .filter((a) => a.price && Number.isFinite(a.price) && a.price >= 500);
}

/** Filtre les annonces par tolerance d'annee et prix minimum */
function _filterAds(ads, targetYear, yearSpread) {
  return ads.filter((a) => {
    if (a.price < 500) return false;
    if (targetYear >= 1990 && a.year) {
      if (Math.abs(a.year - targetYear) > yearSpread) return false;
    }
    return true;
  });
}
