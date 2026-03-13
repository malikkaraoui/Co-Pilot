"use strict";

/**
 * AutoScout24 — construction d'URL de recherche et extraction de prix.
 *
 * AS24 a deux familles de sites avec des formats d'URL differents :
 * - Sites "GmbH" (de, at, nl, be, it, es, etc.) : /lst/<make>/<model>?params
 * - Sites "SMG" (ch, fr) : /s/mo-<model>/mk-<make>?params
 *
 * L'extraction de prix depuis les resultats utilise 3 strategies en cascade :
 * 1. RSC inline (regex sur price/mileage dans le HTML)
 * 2. __NEXT_DATA__ JSON blob
 * 3. JSON-LD OfferCatalog (schema.org)
 */

import { brandsMatch } from '../../shared/brand.js';
import { SMG_TLDS } from './constants.js';

// ── URL & slug helpers ──────────────────────────────────────────────

/**
 * Extrait le TLD depuis une URL AS24 (ex: "de", "ch", "fr").
 * @param {string} url
 * @returns {string}
 */
export function extractTld(url) {
  const match = url.match(/autoscout24\.(\w+)/);
  return match ? match[1] : 'de';
}

/**
 * Extrait le code langue depuis le chemin URL (ex: "/fr/lst/..." → "fr").
 * @param {string} url
 * @returns {string|null}
 */
export function extractLang(url) {
  const match = url.match(/autoscout24\.\w+\/(fr|de|it|en|nl|es|pl|sv)\//);
  return match ? match[1] : null;
}

/**
 * Convertit un nom en slug URL compatible AS24.
 * Ex: "Mercedes-Benz" → "mercedes-benz"
 * @param {string} name
 * @returns {string}
 */
export function toAs24Slug(name) {
  return String(name || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9\-]/g, '');
}

/**
 * Extrait les slugs make/model depuis une URL de recherche AS24.
 * Gere les deux formats (GmbH = /lst/ et SMG = /s/mk-/mo-).
 *
 * @param {string} url - URL de recherche AS24
 * @param {string|null} tldHint - TLD connu pour eviter de le re-extraire
 * @returns {{makeSlug: string|null, modelSlug: string|null}}
 */
export function extractAs24SlugsFromSearchUrl(url, tldHint = null) {
  try {
    const u = new URL(url);
    const hostMatch = u.hostname.match(/autoscout24\.(\w+)$/i);
    const tld = (tldHint || (hostMatch ? hostMatch[1] : '') || '').toLowerCase();
    const path = decodeURIComponent(u.pathname || '');

    // Format SMG : /s/mo-<model>/mk-<make>
    if (SMG_TLDS.has(tld)) {
      const smg = path.match(/\/s\/(?:mo-([^/]+)\/)?mk-([^/?#]+)/i);
      if (!smg) return { makeSlug: null, modelSlug: null };
      const modelSlug = smg[1] ? toAs24Slug(smg[1]) : null;
      const makeSlug = smg[2] ? toAs24Slug(smg[2]) : null;
      return { makeSlug, modelSlug };
    }

    // Format GmbH : /lst/<make>/<model>
    // On retire le prefixe de langue (/fr, /de, etc.) avant de parser
    const normalizedPath = path.replace(/^\/(fr|de|it|en|nl|es|pl|sv)(?=\/|$)/i, '');
    const gmbh = normalizedPath.match(/^\/lst\/([^/]+)(?:\/([^/?#]+))?/i);
    if (!gmbh) return { makeSlug: null, modelSlug: null };
    const makeSlug = gmbh[1] ? toAs24Slug(gmbh[1]) : null;
    const modelSlug = gmbh[2] ? toAs24Slug(gmbh[2]) : null;
    return { makeSlug, modelSlug };
  } catch {
    return { makeSlug: null, modelSlug: null };
  }
}

/**
 * Construit une URL de recherche AS24 complete.
 *
 * @param {string} makeKey - Slug marque
 * @param {string} modelKey - Slug modele
 * @param {number} year - Annee cible
 * @param {string} tld - TLD du site AS24
 * @param {object} options - Filtres optionnels (yearSpread, fuel, gear, etc.)
 * @returns {string} URL de recherche complete
 */
export function buildSearchUrl(makeKey, modelKey, year, tld, options = {}) {
  const { yearSpread = 1, fuel, gear, powerfrom, powerto, kmfrom, kmto, zip, radius, lang, brandOnly } = options;

  const makeSlug = toAs24Slug(makeKey);
  const modelSlug = brandOnly ? '' : toAs24Slug(modelKey);

  let base;

  // Construction du chemin selon le type de site (SMG vs GmbH)
  if (SMG_TLDS.has(tld)) {
    const langPrefix = lang ? `/${lang}` : '/fr';
    if (modelSlug) {
      base = `https://www.autoscout24.${tld}${langPrefix}/s/mo-${modelSlug}/mk-${makeSlug}`;
    } else {
      base = `https://www.autoscout24.${tld}${langPrefix}/s/mk-${makeSlug}`;
    }
  } else {
    const langSegment = lang ? `/${lang}` : '';
    if (modelSlug) {
      base = `https://www.autoscout24.${tld}${langSegment}/lst/${makeSlug}/${modelSlug}`;
    } else {
      base = `https://www.autoscout24.${tld}${langSegment}/lst/${makeSlug}`;
    }
  }

  const params = new URLSearchParams({
    fregfrom: String(year - yearSpread),
    fregto: String(year + yearSpread),
    sort: 'standard',
    desc: '0',
    atype: 'C',           // voitures classiques (pas utilitaires)
    ustate: 'N,U',        // neuves et occasions
  });
  if (fuel) params.set('fuel', fuel);
  if (gear) params.set('gear', gear);
  if (powerfrom) params.set('powerfrom', String(powerfrom));
  if (powerto) params.set('powerto', String(powerto));
  if (kmfrom) params.set('kmfrom', String(kmfrom));
  if (kmto) params.set('kmto', String(kmto));
  if (zip) { params.set('zip', String(zip)); params.set('zipr', String(radius || 50)); }
  return `${base}?${params}`;
}

/** Re-export pour retrocompatibilite — voir shared/brand.js */
export const brandMatchesAs24 = brandsMatch;

// ── Extraction de prix depuis les resultats de recherche ─────────────

/**
 * Extrait la marque depuis un item JSON-LD de type OfferCatalog.
 * AS24 utilise plusieurs structures possibles pour stocker la marque.
 */
function _extractJsonLdBrand(item) {
  return item?.brand?.name
    || item?.offers?.itemOffered?.brand?.name
    || item?.manufacturer
    || item?.offers?.itemOffered?.manufacturer
    || null;
}

/**
 * Point d'entree principal : extrait les prix depuis le HTML d'une page de resultats.
 * Essaie 3 strategies en cascade : RSC inline, __NEXT_DATA__, JSON-LD.
 *
 * @param {string} html - HTML brut de la page de resultats
 * @param {string|null} targetMake - Marque cible pour filtrer les faux positifs
 * @returns {Array<{price: number, year: number|null, km: number|null, fuel: string|null}>}
 */
export function parseSearchPrices(html, targetMake = null) {
  const results = _parseSearchPricesRSC(html);

  if (results.length === 0) {
    const nextDataResults = _parseSearchPricesNextData(html, targetMake);
    if (nextDataResults.length > 0) return nextDataResults;
  }

  if (results.length === 0) {
    const jsonLdResults = _parseSearchPricesJsonLd(html, targetMake);
    if (jsonLdResults.length > 0) return jsonLdResults;
  }

  return results;
}

/**
 * Strategie 1 : extraction RSC inline via regex.
 * Les pages de resultats AS24 contiennent souvent les donnees en inline
 * sous forme de paires price/mileage dans le HTML.
 */
function _parseSearchPricesRSC(html) {
  const results = [];
  const listingPattern = /"price"\s*:\s*(\d+).*?"mileage"\s*:\s*(\d+)/g;
  let match;
  while ((match = listingPattern.exec(html)) !== null) {
    const price = parseInt(match[1], 10);
    const mileage = parseInt(match[2], 10);
    if (price > 500 && price < 500000) {
      results.push({ price, year: null, km: mileage, fuel: null });
    }
  }
  return _dedup(results);
}

/**
 * Strategie 2 : extraction depuis le __NEXT_DATA__ JSON blob.
 * Plus riche que le RSC inline car contient annee, carburant, boite, CV.
 */
function _parseSearchPricesNextData(html, targetMake = null) {
  const results = [];
  const match = html.match(/<script\s+id="__NEXT_DATA__"\s+type="application\/json"[^>]*>([\s\S]*?)<\/script>/i);
  if (!match) return results;

  try {
    const data = JSON.parse(match[1]);
    const listings = data?.props?.pageProps?.listings;
    if (!Array.isArray(listings)) return results;

    for (const listing of listings) {
      const tracking = listing.tracking || {};
      const vehicle = listing.vehicle || {};

      const price = parseInt(tracking.price, 10) || null;
      const km = parseInt(tracking.mileage, 10) || null;

      let year = null;
      if (tracking.firstRegistration) {
        const ym = tracking.firstRegistration.match(/(\d{4})/);
        if (ym) year = parseInt(ym[1], 10);
      }

      const fuel = vehicle.fuel || null;

      // Verification de marque : on rejette les annonces d'une autre marque
      // (peut arriver si AS24 melange des resultats sponsorises)
      if (targetMake) {
        const adBrand = vehicle.make;
        if (adBrand && !brandMatchesAs24(adBrand, targetMake)) {
          continue;
        }
      }

      if (price && price > 500 && price < 500000) {
        results.push({
          price,
          year,
          km,
          fuel,
          gearbox: vehicle.transmission || null,
          horse_power: _parseHpFromVehicleDetails(listing.vehicleDetails),
          _uid: listing.id || null,
        });
      }
    }
  } catch (_) {
    // __NEXT_DATA__ malformed, on passe
  }

  return _dedup(results);
}

/** Extrait la puissance (PS) depuis les details vehicule du __NEXT_DATA__ */
function _parseHpFromVehicleDetails(details) {
  if (!Array.isArray(details)) return null;
  const power = details.find((d) => d.ariaLabel === 'Leistung' || d.iconName === 'speedometer');
  if (!power?.data) return null;
  const m = power.data.match(/\((\d+)\s*PS\)/i);
  return m ? parseInt(m[1], 10) : null;
}

/**
 * Strategie 3 : extraction depuis les blocs JSON-LD (schema.org OfferCatalog).
 * Dernier recours quand ni le RSC ni le __NEXT_DATA__ ne sont disponibles.
 */
function _parseSearchPricesJsonLd(html, targetMake = null) {
  const results = [];
  const scriptPattern = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  let scriptMatch;
  while ((scriptMatch = scriptPattern.exec(html)) !== null) {
    try {
      const data = JSON.parse(scriptMatch[1]);
      const items = _extractOfferCatalogItems(data);
      for (const item of items) {
        const price = _extractJsonLdPrice(item);
        const km = _extractJsonLdMileage(item);
        const fuel = _extractJsonLdFuel(item);
        const year = _extractJsonLdYear(item);
        const uid = _extractJsonLdUid(item);
        if (price && price > 500 && price < 500000) {
          // Filtrage par marque pour eviter les faux positifs inter-marques
          if (targetMake) {
            const adBrand = _extractJsonLdBrand(item);
            if (adBrand && !brandMatchesAs24(adBrand, targetMake)) {
              console.debug('[OKazCar] AS24 brand safety: rejet %s (cible: %s)', adBrand, targetMake);
              continue;
            }
          }
          results.push({ price, year, km, fuel, _uid: uid });
        }
      }
    } catch (_) {
      // Bloc JSON-LD malformed, on passe au suivant
    }
  }
  return _dedup(results);
}

/**
 * Descend dans la structure JSON-LD pour trouver les items d'un OfferCatalog.
 * AS24 peut imbriquer le catalogue dans mainEntity, offers, ou @graph.
 */
function _extractOfferCatalogItems(data) {
  if (data?.['@type'] === 'OfferCatalog' && Array.isArray(data.itemListElement)) {
    return data.itemListElement;
  }
  const offers = data?.mainEntity?.offers || data?.offers;
  if (offers?.['@type'] === 'OfferCatalog' && Array.isArray(offers.itemListElement)) {
    return offers.itemListElement;
  }
  if (Array.isArray(data?.['@graph'])) {
    for (const node of data['@graph']) {
      const items = _extractOfferCatalogItems(node);
      if (items.length > 0) return items;
    }
  }
  return [];
}

/** Extrait le prix depuis un item JSON-LD (number ou string) */
function _extractJsonLdPrice(item) {
  const price = item?.offers?.price ?? item?.price;
  if (typeof price === 'number') return price;
  if (typeof price === 'string') return parseInt(price, 10) || null;
  return null;
}

/** Extrait le kilometrage depuis un item JSON-LD (mileageFromOdometer) */
function _extractJsonLdMileage(item) {
  const car = item?.offers?.itemOffered || item;
  const odometer = car?.mileageFromOdometer;
  if (!odometer) return null;
  const val = odometer?.value ?? odometer;
  if (typeof val === 'number') return val;
  if (typeof val === 'string') return parseInt(val, 10) || null;
  return null;
}

/** Extrait le carburant depuis un item JSON-LD (vehicleEngine.fuelType) */
function _extractJsonLdFuel(item) {
  const car = item?.offers?.itemOffered || item;
  const eng = car?.vehicleEngine;
  const engine = Array.isArray(eng) ? eng[0] : eng;
  return engine?.fuelType || null;
}

/** Extrait l'annee depuis un item JSON-LD (vehicleModelDate ou productionDate) */
function _extractJsonLdYear(item) {
  const car = item?.offers?.itemOffered || item;
  const date = car?.vehicleModelDate || car?.productionDate;
  if (!date) return null;
  const y = parseInt(String(date).slice(0, 4), 10);
  return (y > 1900 && y < 2100) ? y : null;
}

/** Extrait un identifiant unique depuis l'URL de l'annonce dans le JSON-LD */
function _extractJsonLdUid(item) {
  const url = item?.url || item?.offers?.url;
  if (!url) return null;
  const m = url.match(/(\d{6,})(?:[/?#]|$)/);
  return m ? m[1] : url;
}

/** Deduplique les resultats par _uid ou par combinaison prix+km */
function _dedup(results) {
  const seen = new Set();
  return results.filter((r) => {
    const key = r._uid || `${r.price}-${r.km}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).map(({ _uid, ...rest }) => rest);
}
