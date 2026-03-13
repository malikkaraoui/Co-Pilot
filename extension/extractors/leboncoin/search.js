"use strict";

/**
 * Recherche de prix sur LeBonCoin.
 *
 * Deux strategies pour recuperer les annonces d'une recherche LBC :
 * 1. API finder (POST sur api.leboncoin.fr) — plus propre, mais peut etre bloquee
 * 2. Scraping HTML du __NEXT_DATA__ de la page de recherche — fallback fiable
 *
 * Les prix recuperes alimentent l'argus (collecte de prix du marche).
 */

import { isChromeRuntimeAvailable } from '../../utils/fetch.js';
import { LBC_REGIONS, DEFAULT_SEARCH_RADIUS, brandMatches } from './constants.js';
import { parseRange, getAdDetails, getAdYear } from './parser.js';

/**
 * Extrait le nom de marque depuis les attributs d'une annonce LBC.
 * Utilise pour le filtrage "brand safety" (eviter les faux positifs).
 * @param {object} ad
 * @returns {string|null}
 */
function _extractAdBrand(ad) {
  const attrs = Array.isArray(ad?.attributes) ? ad.attributes : [];
  const brandAttr = attrs.find((a) => {
    const key = (a?.key || '').toLowerCase();
    return key === 'u_car_brand' || key === 'brand' || key === 'marque';
  });
  return brandAttr?.value_label || brandAttr?.value || null;
}

/**
 * Convertit une URL de recherche LBC en payload de filtres pour l'API finder.
 * L'API attend un format specifique avec category, enums, ranges, location...
 *
 * @param {string} searchUrl - URL de recherche LBC complete
 * @returns {object} Filtres au format API finder
 */
export function buildApiFilters(searchUrl) {
  const url = new URL(searchUrl);
  const params = url.searchParams;

  const filters = {
    category: { id: params.get("category") || "2" },
    enums: { ad_type: ["offer"], country_id: ["FR"] },
    ranges: { price: { min: 500 } },
  };

  // Filtres enum : marque, modele, carburant, boite
  for (const key of ["u_car_brand", "u_car_model", "fuel", "gearbox"]) {
    const val = params.get(key);
    if (val) filters.enums[key] = [val];
  }

  // Recherche texte libre (utilisee pour les modeles generiques)
  const text = params.get("text");
  if (text) filters.keywords = { text };

  // Filtres range : annee, kilometrage, puissance
  for (const key of ["regdate", "mileage", "horse_power_din"]) {
    const range = parseRange(params.get(key));
    if (range) filters.ranges[key] = range;
  }

  // Localisation : region (rn_XX) ou geo (lat_lng_radius)
  const loc = params.get("locations");
  if (loc) {
    if (loc.startsWith("rn_")) {
      filters.location = { regions: [loc.replace("rn_", "")] };
    } else if (loc.includes("__")) {
      // Format geo : "ville_cp__lat_lng_precision_rayon"
      const [, geoPart] = loc.split("__");
      const geoParts = geoPart.split("_");
      filters.location = {
        area: {
          lat: parseFloat(geoParts[0]),
          lng: parseFloat(geoParts[1]),
          radius: parseInt(geoParts[3]) || 30000,
        },
      };
    }
  }

  return filters;
}

/**
 * Filtre et mappe les annonces brutes en {price, year, km, fuel, ...}.
 * Applique le filtre d'annee (±yearSpread) et le filtrage marque (brand safety).
 *
 * @param {Array} ads - Annonces brutes de l'API/HTML
 * @param {number} targetYear - Annee cible
 * @param {number} yearSpread - Tolerance en annees
 * @param {string|null} targetMake - Marque cible pour le brand safety
 * @returns {Array<{price: number, year?: number, km?: number}>}
 */
export function filterAndMapSearchAds(ads, targetYear, yearSpread, targetMake = null) {
  return ads
    .filter((ad) => {
      const rawPrice = Array.isArray(ad?.price) ? ad.price[0] : ad?.price;
      const priceInt = typeof rawPrice === "number"
        ? rawPrice
        : parseInt(String(rawPrice || "0").replace(/[^\d]/g, ""), 10);
      if (!Number.isFinite(priceInt) || priceInt <= 500) return false;
      // Filtrage par annee si on a une cible valide
      if (targetYear >= 1990) {
        const adYear = getAdYear(ad);
        if (adYear && Math.abs(adYear - targetYear) > yearSpread) return false;
      }
      // Brand safety : rejeter les annonces d'une autre marque
      if (targetMake) {
        const adBrand = _extractAdBrand(ad);
        if (adBrand && !brandMatches(adBrand, targetMake)) {
          console.debug('[OKazCar] brand safety: rejet %s (cible: %s)', adBrand, targetMake);
          return false;
        }
      }
      return true;
    })
    .map((ad) => getAdDetails(ad));
}

/**
 * Recupere les annonces via l'API finder de LeBonCoin.
 * Essaie d'abord via chrome.runtime (monde MAIN) pour eviter les CORS,
 * puis en fallback direct (meme origine, cookies inclus).
 *
 * @param {string} searchUrl - URL de recherche LBC
 * @returns {Promise<Array|null>} Annonces brutes ou null si echec
 */
export async function fetchSearchPricesViaApi(searchUrl) {
  const filters = buildApiFilters(searchUrl);
  const body = JSON.stringify({
    filters,
    limit: 35,
    sort_by: "time",
    sort_order: "desc",
    owner_type: "all",
  });

  // Passer par le background script pour eviter les restrictions CORS
  if (isChromeRuntimeAvailable()) {
    try {
      const result = await chrome.runtime.sendMessage({
        action: "lbc_api_search",
        body: body,
      });
      if (result?.ok) {
        const ads = result.data?.ads || result.data?.results || [];
        console.log("[OKazCar] API finder (MAIN world): %d ads bruts", ads.length);
        return ads.length > 0 ? ads : null;
      }
      console.warn("[OKazCar] API finder (MAIN): %s", result?.error || `HTTP ${result?.status}`);
    } catch (err) {
      console.debug("[OKazCar] chrome.runtime.sendMessage echoue:", err.message);
    }
  }

  // Fallback : appel direct depuis le content script (meme origine)
  const resp = await fetch("https://api.leboncoin.fr/finder/search", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
    body: body,
  });

  if (!resp.ok) {
    console.warn("[OKazCar] API finder (direct): HTTP %d", resp.status);
    return null;
  }

  const data = await resp.json();
  return data.ads || data.results || [];
}

/**
 * Recupere les annonces en scrappant le HTML de la page de recherche LBC.
 * Methode de fallback quand l'API finder est indisponible.
 *
 * @param {string} searchUrl - URL de recherche LBC
 * @returns {Promise<Array>} Annonces brutes depuis le __NEXT_DATA__
 */
export async function fetchSearchPricesViaHtml(searchUrl) {
  const resp = await fetch(searchUrl, {
    credentials: "same-origin",
    headers: { "Accept": "text/html" },
  });
  const html = await resp.text();

  const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (!match) return [];

  // LBC change regulierement la structure du __NEXT_DATA__,
  // d'ou les multiples chemins tentes
  const data = JSON.parse(match[1]);
  const pp = data?.props?.pageProps || {};
  return pp?.searchData?.ads
      || pp?.initialProps?.searchData?.ads
      || pp?.ads
      || pp?.adSearch?.ads
      || [];
}

/**
 * Point d'entree principal pour recuperer les prix d'une recherche LBC.
 * Essaie l'API en premier, puis le scraping HTML en fallback.
 * Les resultats sont filtres et mappes vers le format {price, year, km}.
 *
 * @param {string} searchUrl - URL de recherche LBC
 * @param {number} targetYear - Annee cible
 * @param {number} yearSpread - Tolerance en annees
 * @param {string|null} targetMake - Marque cible pour brand safety
 * @returns {Promise<Array<{price: number, year?: number, km?: number}>>}
 */
export async function fetchSearchPrices(searchUrl, targetYear, yearSpread, targetMake = null) {
  let ads = null;

  // 1. Tenter l'API finder
  try {
    ads = await fetchSearchPricesViaApi(searchUrl);
    if (ads && ads.length > 0) {
      console.log("[OKazCar] fetchSearchPrices (API): %d ads bruts", ads.length);
      return filterAndMapSearchAds(ads, targetYear, yearSpread, targetMake);
    }
  } catch (err) {
    console.debug("[OKazCar] API finder indisponible:", err.message);
  }

  // 2. Fallback HTML
  try {
    ads = await fetchSearchPricesViaHtml(searchUrl);
    if (ads && ads.length > 0) {
      console.log("[OKazCar] fetchSearchPrices (HTML): %d ads bruts", ads.length);
      return filterAndMapSearchAds(ads, targetYear, yearSpread, targetMake);
    }
    console.log("[OKazCar] fetchSearchPrices: 0 ads (API + HTML)");
  } catch (err) {
    console.debug("[OKazCar] HTML scraping failed:", err.message);
  }

  return [];
}

/**
 * Construit le parametre &locations= pour une recherche LBC geolocalisee.
 * Format LBC : "ville_cp__lat_lng_precision_rayon"
 *
 * @param {object} location - {city, zipcode, lat, lng, region}
 * @param {number} radiusMeters - Rayon en metres
 * @returns {string} Parametre locations LBC ou "" si impossible
 */
export function buildLocationParam(location, radiusMeters) {
  if (!location) return "";
  const radius = radiusMeters || DEFAULT_SEARCH_RADIUS;
  if (location.lat && location.lng && location.city && location.zipcode) {
    return `${location.city}_${location.zipcode}__${location.lat}_${location.lng}_5000_${radius}`;
  }
  // Fallback sur la region si pas de coordonnees GPS
  return LBC_REGIONS[location.region] || "";
}
