"use strict";

import { isChromeRuntimeAvailable } from '../../utils/fetch.js';
import { LBC_REGIONS, DEFAULT_SEARCH_RADIUS, brandMatches } from './constants.js';
import { parseRange, getAdDetails, getAdYear } from './parser.js';

/** Extrait le nom de marque depuis les attributs d'une annonce LBC. */
function _extractAdBrand(ad) {
  const attrs = Array.isArray(ad?.attributes) ? ad.attributes : [];
  const brandAttr = attrs.find((a) => {
    const key = (a?.key || '').toLowerCase();
    return key === 'u_car_brand' || key === 'brand' || key === 'marque';
  });
  return brandAttr?.value_label || brandAttr?.value || null;
}

export function buildApiFilters(searchUrl) {
  const url = new URL(searchUrl);
  const params = url.searchParams;

  const filters = {
    category: { id: params.get("category") || "2" },
    enums: { ad_type: ["offer"], country_id: ["FR"] },
    ranges: { price: { min: 500 } },
  };

  for (const key of ["u_car_brand", "u_car_model", "fuel", "gearbox"]) {
    const val = params.get(key);
    if (val) filters.enums[key] = [val];
  }

  const text = params.get("text");
  if (text) filters.keywords = { text };

  for (const key of ["regdate", "mileage", "horse_power_din"]) {
    const range = parseRange(params.get(key));
    if (range) filters.ranges[key] = range;
  }

  const loc = params.get("locations");
  if (loc) {
    if (loc.startsWith("rn_")) {
      filters.location = { regions: [loc.replace("rn_", "")] };
    } else if (loc.includes("__")) {
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

export function filterAndMapSearchAds(ads, targetYear, yearSpread, targetMake = null) {
  return ads
    .filter((ad) => {
      const rawPrice = Array.isArray(ad?.price) ? ad.price[0] : ad?.price;
      const priceInt = typeof rawPrice === "number"
        ? rawPrice
        : parseInt(String(rawPrice || "0").replace(/[^\d]/g, ""), 10);
      if (!Number.isFinite(priceInt) || priceInt <= 500) return false;
      if (targetYear >= 1990) {
        const adYear = getAdYear(ad);
        if (adYear && Math.abs(adYear - targetYear) > yearSpread) return false;
      }
      if (targetMake) {
        const adBrand = _extractAdBrand(ad);
        if (adBrand && !brandMatches(adBrand, targetMake)) {
          console.debug('[CoPilot] brand safety: rejet %s (cible: %s)', adBrand, targetMake);
          return false;
        }
      }
      return true;
    })
    .map((ad) => getAdDetails(ad));
}

export async function fetchSearchPricesViaApi(searchUrl) {
  const filters = buildApiFilters(searchUrl);
  const body = JSON.stringify({
    filters,
    limit: 35,
    sort_by: "time",
    sort_order: "desc",
    owner_type: "all",
  });

  if (isChromeRuntimeAvailable()) {
    try {
      const result = await chrome.runtime.sendMessage({
        action: "lbc_api_search",
        body: body,
      });
      if (result?.ok) {
        const ads = result.data?.ads || result.data?.results || [];
        console.log("[CoPilot] API finder (MAIN world): %d ads bruts", ads.length);
        return ads.length > 0 ? ads : null;
      }
      console.warn("[CoPilot] API finder (MAIN): %s", result?.error || `HTTP ${result?.status}`);
    } catch (err) {
      console.debug("[CoPilot] chrome.runtime.sendMessage echoue:", err.message);
    }
  }

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
    console.warn("[CoPilot] API finder (direct): HTTP %d", resp.status);
    return null;
  }

  const data = await resp.json();
  return data.ads || data.results || [];
}

export async function fetchSearchPricesViaHtml(searchUrl) {
  const resp = await fetch(searchUrl, {
    credentials: "same-origin",
    headers: { "Accept": "text/html" },
  });
  const html = await resp.text();

  const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (!match) return [];

  const data = JSON.parse(match[1]);
  const pp = data?.props?.pageProps || {};
  return pp?.searchData?.ads
      || pp?.initialProps?.searchData?.ads
      || pp?.ads
      || pp?.adSearch?.ads
      || [];
}

export async function fetchSearchPrices(searchUrl, targetYear, yearSpread, targetMake = null) {
  let ads = null;

  try {
    ads = await fetchSearchPricesViaApi(searchUrl);
    if (ads && ads.length > 0) {
      console.log("[CoPilot] fetchSearchPrices (API): %d ads bruts", ads.length);
      return filterAndMapSearchAds(ads, targetYear, yearSpread, targetMake);
    }
  } catch (err) {
    console.debug("[CoPilot] API finder indisponible:", err.message);
  }

  try {
    ads = await fetchSearchPricesViaHtml(searchUrl);
    if (ads && ads.length > 0) {
      console.log("[CoPilot] fetchSearchPrices (HTML): %d ads bruts", ads.length);
      return filterAndMapSearchAds(ads, targetYear, yearSpread, targetMake);
    }
    console.log("[CoPilot] fetchSearchPrices: 0 ads (API + HTML)");
  } catch (err) {
    console.debug("[CoPilot] HTML scraping failed:", err.message);
  }

  return [];
}

export function buildLocationParam(location, radiusMeters) {
  if (!location) return "";
  const radius = radiusMeters || DEFAULT_SEARCH_RADIUS;
  if (location.lat && location.lng && location.city && location.zipcode) {
    return `${location.city}_${location.zipcode}__${location.lat}_${location.lng}_5000_${radius}`;
  }
  return LBC_REGIONS[location.region] || "";
}
