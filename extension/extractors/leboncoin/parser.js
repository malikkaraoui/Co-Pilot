"use strict";

import { GENERIC_MODELS, LBC_BRAND_ALIASES } from './constants.js';

export function isStaleData(data) {
  const urlMatch = window.location.href.match(/\/(\d+)(?:[?#]|$)/);
  if (!urlMatch) return false;
  const urlAdId = urlMatch[1];

  const ad = data?.props?.pageProps?.ad;
  if (!ad) return true;

  const dataAdId = String(ad.list_id || ad.id || "");
  if (!dataAdId) return true;

  return dataAdId !== urlAdId;
}

export async function extractNextData() {
  const el = document.getElementById("__okazcar_next_data__");
  if (el && el.textContent) {
    try {
      const data = JSON.parse(el.textContent);
      el.remove();
      if (data && !isStaleData(data)) return data;
    } catch {
      // continue
    }
  }

  const script = document.getElementById("__NEXT_DATA__");
  if (script) {
    try {
      const data = JSON.parse(script.textContent);
      if (data && !isStaleData(data)) return data;
    } catch {
      // continue
    }
  }

  try {
    const resp = await fetch(window.location.href, {
      credentials: "same-origin",
      headers: { "Accept": "text/html" },
    });
    const html = await resp.text();
    const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
    if (match) return JSON.parse(match[1]);
  } catch {
    // extraction impossible
  }

  return null;
}

export function extractLbcTokensFromDom() {
  const result = { brandToken: null, modelToken: null };
  try {
    const link = document.querySelector('a[href*="u_car_model"]');
    if (!link) return result;
    const url = new URL(link.href, location.origin);
    const raw = decodeURIComponent(url.pathname + url.search + url.hash);

    const extractToken = (key) => {
      const re = new RegExp(`${key}:(.+?)(?:\\+\\w+:|&|$)`);
      const m = raw.match(re);
      return m ? m[1].replace(/\+/g, ' ').trim() : null;
    };

    result.brandToken = extractToken('u_car_brand');
    result.modelToken = extractToken('u_car_model');

    if (!result.brandToken) {
      const qBrand = url.searchParams.get('u_car_brand');
      if (qBrand) result.brandToken = qBrand.trim();
    }
    if (!result.modelToken) {
      const qModel = url.searchParams.get('u_car_model');
      if (qModel) result.modelToken = qModel.trim();
    }
  } catch (e) {
    console.warn("[OKazCar] extractLbcTokensFromDom error:", e);
  }
  return result;
}

export function extractModelFromTitle(title, make) {
  if (!title || !make) return null;
  let cleaned = title.trim();
  if (cleaned.toLowerCase().startsWith(make.toLowerCase())) {
    cleaned = cleaned.slice(make.length).trim();
  }
  cleaned = cleaned.replace(/\b(19|20)\d{2}\b/g, "").trim();
  const noise = new Set([
    "neuf", "neuve", "occasion", "tbe", "garantie",
    "full", "options", "option", "pack", "premium", "edition",
    "limited", "sport", "line", "style", "business", "confort",
    "first", "life", "zen", "intens", "intense", "initiale",
    "paris", "riviera", "alpine", "esprit", "techno", "evolution",
    "iconic", "rs", "gt", "gtline", "gt-line",
  ]);
  for (const word of cleaned.split(/[\s,\-./()]+/)) {
    const w = word.trim();
    if (!w || noise.has(w.toLowerCase()) || /^\d+$/.test(w)) continue;
    return w;
  }
  return null;
}

export function extractVehicleFromNextData(nextData) {
  const ad = nextData?.props?.pageProps?.ad;
  if (!ad) return {};

  const attrs = (ad.attributes || []).reduce((acc, a) => {
    const key = a.key || a.key_label || a.label || a.name;
    const val = a.value_label || a.value || a.text || a.value_text;
    if (key) acc[key] = val;
    return acc;
  }, {});

  const make = attrs["brand"] || attrs["Marque"] || "";
  let model = attrs["model"] || attrs["Modèle"] || attrs["modele"] || "";

  if (GENERIC_MODELS.includes(model.toLowerCase()) && make) {
    const title = ad.subject || ad.title || "";
    const extracted = extractModelFromTitle(title, make);
    if (extracted) model = extracted;
  }

  const domTokens = extractLbcTokensFromDom();

  return {
    make,
    model,
    year: attrs["regdate"] || attrs["Année modèle"] || attrs["Année"] || attrs["year"] || "",
    fuel: attrs["fuel"] || attrs["Énergie"] || attrs["energie"] || "",
    gearbox: attrs["gearbox"] || attrs["Boîte de vitesse"] || attrs["Boite de vitesse"] || attrs["Transmission"] || "",
    horse_power: attrs["horse_power_din"] || attrs["Puissance DIN"] || "",
    site_brand_token: domTokens.brandToken,
    site_model_token: domTokens.modelToken,
  };
}

export function toLbcBrandToken(make) {
  const upper = String(make || "").trim().toUpperCase();
  return LBC_BRAND_ALIASES[upper] || upper;
}

export function getAdYear(ad) {
  const attrs = ad.attributes || [];
  for (const a of attrs) {
    const key = (a.key || a.key_label || "").toLowerCase();
    if (key === "regdate" || key === "année modèle" || key === "année") {
      const val = String(a.value || a.value_label || "");
      const y = parseInt(val, 10);
      if (y >= 1990 && y <= 2030) return y;
    }
  }
  return null;
}

export function extractRegionFromNextData(nextData) {
  if (!nextData) return "";
  const loc = nextData?.props?.pageProps?.ad?.location;
  return loc?.region_name || loc?.region || "";
}

export function extractLocationFromNextData(nextData) {
  const loc = nextData?.props?.pageProps?.ad?.location;
  if (!loc) return null;
  return {
    city: loc.city || "",
    zipcode: loc.zipcode || "",
    lat: loc.lat || null,
    lng: loc.lng || null,
    region: loc.region_name || loc.region || "",
  };
}

export function getAdDetails(ad) {
  const rawPrice = Array.isArray(ad?.price) ? ad.price[0] : ad?.price;
  const parsedPrice = typeof rawPrice === "number"
    ? rawPrice
    : parseInt(String(rawPrice || "0").replace(/[^\d]/g, ""), 10);
  const attrs = Array.isArray(ad?.attributes) ? ad.attributes : [];
  const details = { price: Number.isFinite(parsedPrice) ? parsedPrice : 0 };
  for (const a of attrs) {
    if (!a || typeof a !== "object") continue;
    const key = (a.key || a.key_label || "").toLowerCase();
    if (key === "regdate" || key === "année modèle" || key === "année") {
      details.year = parseInt(a.value || a.value_label, 10) || null;
    } else if (key === "mileage" || key === "kilométrage" || key === "kilometrage") {
      details.km = parseInt(String(a.value || a.value_label || "0").replace(/\s/g, ""), 10) || null;
    } else if (key === "fuel" || key === "énergie" || key === "energie") {
      details.fuel = a.value_label || a.value || null;
    } else if (key === "gearbox" || key === "boîte de vitesse" || key === "boite de vitesse") {
      details.gearbox = a.value_label || a.value || null;
    } else if (key === "horse_power_din" || key === "puissance din") {
      details.horse_power = parseInt(String(a.value || a.value_label || "0"), 10) || null;
    }
  }
  return details;
}

export function parseRange(rangeStr) {
  if (!rangeStr) return null;
  const [minStr, maxStr] = rangeStr.split("-");
  const range = {};
  if (minStr && minStr !== "min") range.min = parseInt(minStr, 10);
  if (maxStr && maxStr !== "max") range.max = parseInt(maxStr, 10);
  return Object.keys(range).length > 0 ? range : null;
}

export function extractMileageFromNextData(nextData) {
  const ad = nextData?.props?.pageProps?.ad;
  if (!ad) return 0;
  const attrs = (ad.attributes || []).reduce((acc, a) => {
    const key = a.key || a.key_label || a.label || a.name;
    const val = a.value_label || a.value || a.text || a.value_text;
    if (key) acc[key] = val;
    return acc;
  }, {});
  const raw = attrs["mileage"] || attrs["Kilométrage"] || attrs["kilometrage"] || "0";
  return parseInt(String(raw).replace(/\s/g, ""), 10) || 0;
}
