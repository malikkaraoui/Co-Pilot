"use strict";

/**
 * Parsing des donnees LeBonCoin depuis le __NEXT_DATA__.
 *
 * LBC est une app Next.js qui stocke toutes les donnees de l'annonce
 * dans une balise <script id="__NEXT_DATA__">. Ce module extrait ce JSON,
 * valide qu'il correspond bien a l'annonce affichee, et en extrait les
 * informations vehicule.
 *
 * Le parsing est tolerant aux changements de structure de LBC : on cherche
 * les attributs par plusieurs noms possibles (key FR/EN, labels, etc.).
 */

import { GENERIC_MODELS, LBC_BRAND_ALIASES } from './constants.js';

/**
 * Detecte si le __NEXT_DATA__ en cache est obsolete (SPA navigation).
 * Compare l'ID d'annonce dans l'URL avec celui du JSON.
 * En navigation SPA, le __NEXT_DATA__ peut rester celui de la page precedente.
 *
 * @param {object} data - Contenu du __NEXT_DATA__
 * @returns {boolean} true si les donnees sont obsoletes
 */
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

/**
 * Extrait le __NEXT_DATA__ de la page LeBonCoin.
 *
 * Trois strategies en cascade :
 * 1. Element DOM injecte par le content script (bridge MAIN -> ISOLATED world)
 * 2. Balise <script id="__NEXT_DATA__"> native de Next.js
 * 3. Re-fetch de la page en dernier recours (navigation SPA sans __NEXT_DATA__)
 *
 * Chaque resultat est verifie avec isStaleData() pour eviter les donnees obsoletes.
 *
 * @returns {Promise<object|null>} Le __NEXT_DATA__ parse ou null
 */
export async function extractNextData() {
  // Donnees bridgees depuis le monde MAIN via un element DOM cache
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

  // Balise __NEXT_DATA__ native
  const script = document.getElementById("__NEXT_DATA__");
  if (script) {
    try {
      const data = JSON.parse(script.textContent);
      if (data && !isStaleData(data)) return data;
    } catch {
      // continue
    }
  }

  // Re-fetch de la page complete pour extraire le __NEXT_DATA__ du HTML
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

/**
 * Extrait les tokens marque/modele LBC depuis le DOM de la page.
 * LBC genere des liens internes contenant les tokens u_car_brand et u_car_model
 * (ex: dans le lien "Voir toutes les annonces de cette marque").
 * Ces tokens sont les identifiants internes que LBC utilise pour ses filtres
 * de recherche — on en a besoin pour construire les URL de collecte.
 *
 * @returns {{brandToken: string|null, modelToken: string|null}}
 */
export function extractLbcTokensFromDom() {
  const result = { brandToken: null, modelToken: null };
  try {
    const link = document.querySelector('a[href*="u_car_model"]');
    if (!link) return result;
    const url = new URL(link.href, location.origin);
    const raw = decodeURIComponent(url.pathname + url.search + url.hash);

    // LBC encode parfois les tokens dans le path (format "key:value+key:value")
    const extractToken = (key) => {
      const re = new RegExp(`${key}:(.+?)(?:\\+\\w+:|&|$)`);
      const m = raw.match(re);
      return m ? m[1].replace(/\+/g, ' ').trim() : null;
    };

    result.brandToken = extractToken('u_car_brand');
    result.modelToken = extractToken('u_car_model');

    // Fallback : chercher dans les query params classiques
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

/**
 * Extrait le nom du modele depuis le titre de l'annonce.
 * Utilise quand le champ "model" est generique (ex: "Autres").
 * On retire la marque, les annees, et les mots de bruit (finitions, etc.)
 * pour ne garder que le premier mot significatif = le modele.
 *
 * @param {string} title - Titre de l'annonce
 * @param {string} make - Marque du vehicule
 * @returns {string|null} Nom du modele extrait ou null
 */
export function extractModelFromTitle(title, make) {
  if (!title || !make) return null;
  let cleaned = title.trim();
  if (cleaned.toLowerCase().startsWith(make.toLowerCase())) {
    cleaned = cleaned.slice(make.length).trim();
  }
  cleaned = cleaned.replace(/\b(19|20)\d{2}\b/g, "").trim();
  // Mots a ignorer : finitions, niveaux d'equipement, etats, etc.
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

/**
 * Extrait les informations vehicule structurees depuis le __NEXT_DATA__.
 * Les attributs LBC sont un tableau d'objets {key, value, value_label, ...}
 * qu'on normalise en dictionnaire plat. On cherche chaque champ par
 * plusieurs noms possibles car LBC utilise parfois les keys techniques
 * (brand, fuel) et parfois les labels francais (Marque, Energie).
 *
 * @param {object} nextData - Le __NEXT_DATA__ complet
 * @returns {object} Donnees vehicule normalisees {make, model, year, fuel, gearbox, ...}
 */
export function extractVehicleFromNextData(nextData) {
  const ad = nextData?.props?.pageProps?.ad;
  if (!ad) return {};

  // Aplatir les attributs en dictionnaire {key: value}
  const attrs = (ad.attributes || []).reduce((acc, a) => {
    const key = a.key || a.key_label || a.label || a.name;
    const val = a.value_label || a.value || a.text || a.value_text;
    if (key) acc[key] = val;
    return acc;
  }, {});

  const make = attrs["brand"] || attrs["Marque"] || "";
  let model = attrs["model"] || attrs["Modèle"] || attrs["modele"] || "";

  // Si le modele est generique ("Autres"), tenter de l'extraire du titre
  if (GENERIC_MODELS.includes(model.toLowerCase()) && make) {
    const title = ad.subject || ad.title || "";
    const extracted = extractModelFromTitle(title, make);
    if (extracted) model = extracted;
  }

  // Recuperer les tokens LBC depuis le DOM pour la collecte de prix
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

/**
 * Convertit un nom de marque en token LBC (majuscules + aliases).
 * Ex: "Mercedes" -> "MERCEDES-BENZ"
 *
 * @param {string} make - Nom de la marque
 * @returns {string} Token LBC normalise
 */
export function toLbcBrandToken(make) {
  const upper = String(make || "").trim().toUpperCase();
  return LBC_BRAND_ALIASES[upper] || upper;
}

/**
 * Extrait l'annee du vehicule depuis les attributs d'une annonce LBC.
 * Utilise dans le filtrage des resultats de recherche.
 *
 * @param {object} ad - Objet annonce LBC
 * @returns {number|null} Annee entre 1990 et 2030, ou null
 */
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

/**
 * Extrait le nom de region depuis le __NEXT_DATA__.
 * @param {object} nextData
 * @returns {string} Nom de la region ou chaine vide
 */
export function extractRegionFromNextData(nextData) {
  if (!nextData) return "";
  const loc = nextData?.props?.pageProps?.ad?.location;
  return loc?.region_name || loc?.region || "";
}

/**
 * Extrait les informations de localisation completes depuis le __NEXT_DATA__.
 * Inclut les coordonnees GPS quand disponibles (utile pour la recherche geo).
 *
 * @param {object} nextData
 * @returns {{city: string, zipcode: string, lat: number|null, lng: number|null, region: string}|null}
 */
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

/**
 * Extrait les details d'une annonce LBC pour la collecte de prix.
 * Retourne un objet {price, year, km, fuel, gearbox, horse_power}
 * utilise dans le mapping des resultats de recherche.
 *
 * @param {object} ad - Objet annonce brut de l'API/HTML
 * @returns {object} Details normalises de l'annonce
 */
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

/**
 * Parse une chaine de range LBC (ex: "5-10", "min-150000") en objet {min, max}.
 * Utilise pour les filtres de puissance et de kilometrage dans l'API.
 *
 * @param {string} rangeStr - Chaine au format "min-max"
 * @returns {{min?: number, max?: number}|null}
 */
export function parseRange(rangeStr) {
  if (!rangeStr) return null;
  const [minStr, maxStr] = rangeStr.split("-");
  const range = {};
  if (minStr && minStr !== "min") range.min = parseInt(minStr, 10);
  if (maxStr && maxStr !== "max") range.max = parseInt(maxStr, 10);
  return Object.keys(range).length > 0 ? range : null;
}

/**
 * Extrait le kilometrage depuis le __NEXT_DATA__.
 * @param {object} nextData
 * @returns {number} Kilometrage en km, ou 0 si non disponible
 */
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
