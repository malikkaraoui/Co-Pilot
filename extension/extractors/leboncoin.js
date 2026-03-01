/**
 * LeBonCoin Extractor
 *
 * Extrait les donnees vehicule depuis les pages d'annonces LeBonCoin.
 * Gere aussi la collecte crowdsourcee des prix du marche, la revelation
 * du telephone, la detection Autoviza, et les bonus jobs multi-region.
 */

import { SiteExtractor } from './base.js';

// ── Dependencies injected by content.js ───────────────────────────
let _backendFetch, _sleep, _apiUrl;

/**
 * Initialise les dependances injectees par content.js.
 * backendFetch, sleep et apiUrl ne sont pas disponibles dans ce module
 * (ils vivent dans content.js) -- on les injecte au demarrage.
 */
export function initLbcDeps(deps) {
  _backendFetch = deps.backendFetch;
  _sleep = deps.sleep;
  _apiUrl = deps.apiUrl;
}

// ── Small utilities duplicated from content.js ────────────────────
// These are needed by fetchSearchPricesViaApi, reportJobDone, and executeBonusJobs.
// They are small enough to duplicate rather than create a circular dependency.

function isChromeRuntimeAvailable() {
  try {
    return (
      typeof chrome !== "undefined"
      && !!chrome.runtime
      && typeof chrome.runtime.sendMessage === "function"
    );
  } catch {
    return false;
  }
}

function isBenignRuntimeTeardownError(err) {
  const msg = String(err?.message || err || "").toLowerCase();
  return msg.includes("extension context invalidated")
    || msg.includes("runtime_unavailable_for_local_backend")
    || msg.includes("receiving end does not exist");
}

// ── Constants ─────────────────────────────────────────────────────

/** Modeles generiques a ne pas inclure dans la recherche texte. */
export const GENERIC_MODELS = ["autres", "autre", "other", "divers"];

/** Categories LBC exclues de la collecte de prix (pas des voitures). */
export const EXCLUDED_CATEGORIES = ["motos", "equipement_moto", "caravaning", "nautisme"];

/** Alias marque internes -> token marque attendu par LBC dans u_car_brand. */
export const LBC_BRAND_ALIASES = {
  MERCEDES: "MERCEDES-BENZ",
};

/** Mapping des regions LeBonCoin -> codes rn_ (region + voisines).
 *  Les codes rn_ utilisent l'ancienne nomenclature regionale LBC (pre-2016).
 *  Inclut AUSSI les anciens noms de region (LBC retourne parfois les anciens
 *  noms dans region_name, ex: "Nord-Pas-de-Calais" au lieu de "Hauts-de-France"). */
export const LBC_REGIONS = {
  // Regions post-2016
  "Île-de-France": "rn_12",
  "Auvergne-Rhône-Alpes": "rn_22",
  "Provence-Alpes-Côte d'Azur": "rn_21",
  "Occitanie": "rn_16",
  "Nouvelle-Aquitaine": "rn_20",
  "Hauts-de-France": "rn_17",
  "Grand Est": "rn_8",
  "Bretagne": "rn_6",
  "Pays de la Loire": "rn_18",
  "Normandie": "rn_4",
  "Bourgogne-Franche-Comté": "rn_5",
  "Centre-Val de Loire": "rn_7",
  "Corse": "rn_9",
  // Anciennes regions (pre-2016) -- LBC retourne parfois ces noms
  "Nord-Pas-de-Calais": "rn_17",
  "Picardie": "rn_17",
  "Rhône-Alpes": "rn_22",
  "Auvergne": "rn_22",
  "Midi-Pyrénées": "rn_16",
  "Languedoc-Roussillon": "rn_16",
  "Aquitaine": "rn_20",
  "Poitou-Charentes": "rn_20",
  "Limousin": "rn_20",
  "Alsace": "rn_8",
  "Lorraine": "rn_8",
  "Champagne-Ardenne": "rn_8",
  "Basse-Normandie": "rn_4",
  "Haute-Normandie": "rn_4",
  "Bourgogne": "rn_5",
  "Franche-Comté": "rn_5",
};

/** Mapping fuel LBC : texte -> code URL.
 *  Valeurs extraites de l'interface LBC (fevrier 2026). */
export const LBC_FUEL_CODES = {
  "essence": 1,
  "diesel": 2,
  "gpl": 3,
  "electrique": 4,
  "électrique": 4,
  "autre": 5,
  "hybride": 6,
  "gnv": 7,
  "gaz naturel": 7,
  "hybride rechargeable": 8,
  "électrique & essence": 6,
  "electrique & essence": 6,
  "électrique & diesel": 6,
  "electrique & diesel": 6,
};

/** Mapping gearbox LBC : texte -> code URL.
 *  Valeurs extraites de l'interface LBC (fevrier 2026). */
export const LBC_GEARBOX_CODES = {
  "manuelle": 1,
  "automatique": 2,
};

/** Cooldown entre deux collectes (anti-ban). */
export const COLLECT_COOLDOWN_MS = 24 * 60 * 60 * 1000; // 24h

/** Rayon de recherche par defaut en metres (30 km). */
export const DEFAULT_SEARCH_RADIUS = 30000;

/** Nombre minimum de prix valides pour constituer un argus fiable.
 *  En-dessous de 20, l'IQR est trop instable pour etre significatif. */
export const MIN_PRICES_FOR_ARGUS = 20;

// ── LBC extraction functions ──────────────────────────────────────

/**
 * Detecte si les donnees __NEXT_DATA__ sont obsoletes (navigation SPA).
 * Compare l'ID de l'annonce dans les donnees avec l'ID dans l'URL courante.
 * Retourne true (= perime) si on ne peut pas confirmer la correspondance.
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
 * Extrait le JSON __NEXT_DATA__ a jour.
 *
 * 1. Lit les donnees injectees par le background (world:MAIN)
 * 2. Verifie la fraicheur (compare ad ID vs URL)
 * 3. Si obsoletes (nav SPA) : re-fetch le HTML de la page pour un __NEXT_DATA__ frais
 */
export async function extractNextData() {
  // 1. Donnees injectees par le background (world:MAIN)
  const el = document.getElementById("__copilot_next_data__");
  if (el && el.textContent) {
    try {
      const data = JSON.parse(el.textContent);
      el.remove();
      if (data && !isStaleData(data)) return data;
    } catch {
      // continue
    }
  }

  // 2. Tag script DOM (premiere page seulement)
  const script = document.getElementById("__NEXT_DATA__");
  if (script) {
    try {
      const data = JSON.parse(script.textContent);
      if (data && !isStaleData(data)) return data;
    } catch {
      // continue
    }
  }

  // 3. Fallback SPA : re-fetch le HTML de la page courante
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
 * Extrait les tokens u_car_brand / u_car_model depuis le DOM de la page LBC.
 *
 * Chaque annonce a un lien "Voir d'autres annonces <modele>" dont le href
 * contient les tokens exacts : /c/voitures/u_car_brand:BMW+u_car_model:BMW_Serie%203
 * Ces tokens sont la source de verite pour les recherches LBC (accents inclus).
 * __NEXT_DATA__ peut renvoyer "Serie 3" (sans accent) alors que LBC attend "Serie 3".
 */
export function extractLbcTokensFromDom() {
  const result = { brandToken: null, modelToken: null };
  try {
    const link = document.querySelector('a[href*="u_car_model"]');
    if (!link) return result;
    const url = new URL(link.href, location.origin);
    const path = decodeURIComponent(url.pathname + url.search + url.hash);
    const brandMatch = path.match(/u_car_brand:([^+&]+)/);
    const modelMatch = path.match(/u_car_model:([^+&]+)/);
    if (brandMatch) result.brandToken = brandMatch[1].trim();
    if (modelMatch) result.modelToken = modelMatch[1].trim();
  } catch (e) {
    console.warn("[CoPilot] extractLbcTokensFromDom error:", e);
  }
  return result;
}

/**
 * Extrait le nom du modele depuis le titre quand LBC met "Autres".
 * "Renault Symbioz Esprit Alpine 2025" -> "Symbioz"
 */
export function extractModelFromTitle(title, make) {
  if (!title || !make) return null;
  let cleaned = title.trim();
  // Retirer la marque du debut
  if (cleaned.toLowerCase().startsWith(make.toLowerCase())) {
    cleaned = cleaned.slice(make.length).trim();
  }
  // Retirer l'annee (4 chiffres)
  cleaned = cleaned.replace(/\b(19|20)\d{2}\b/g, "").trim();
  // Premier mot significatif
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
 * Extrait les infos vehicule (make, model, year, etc.) depuis __NEXT_DATA__.
 */
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

  // Si LBC renvoie un modele generique ("Autres"), tenter d'extraire le vrai
  // nom depuis le titre : "Renault Symbioz Esprit Alpine 2025" -> "Symbioz"
  if (GENERIC_MODELS.includes(model.toLowerCase()) && make) {
    const title = ad.subject || ad.title || "";
    const extracted = extractModelFromTitle(title, make);
    if (extracted) model = extracted;
  }

  // Extraire les tokens LBC depuis le DOM (source de verite pour les URLs de recherche).
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

/** Normalise la marque pour l'URL LBC (u_car_brand). */
export function toLbcBrandToken(make) {
  const upper = String(make || "").trim().toUpperCase();
  return LBC_BRAND_ALIASES[upper] || upper;
}

/**
 * Extrait l'annee depuis les attributs d'une annonce de recherche LBC.
 * Les ads de recherche ont un format d'attributs different.
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

// ── LBC DOM interaction ───────────────────────────────────────────

/**
 * Detecte si l'utilisateur est connecte sur LeBonCoin.
 * LBC affiche "Se connecter" dans le header si non connecte.
 */
export function isUserLoggedIn() {
  const header = document.querySelector("header");
  if (!header) return false;
  const text = header.textContent.toLowerCase();
  return !text.includes("se connecter") && !text.includes("s'identifier");
}

/**
 * Detecte un lien vers un rapport Autoviza sur la page LBC.
 * Certaines annonces offrent un rapport d'historique gratuit (valeur 25 EUR).
 * Le lien peut etre lazy-loaded par React, donc on retente plusieurs fois.
 * On cherche aussi dans __NEXT_DATA__ en fallback.
 * Retourne l'URL du rapport ou null si absent.
 */
export async function detectAutovizaUrl(nextData) {
  // 1. Chercher dans le DOM (plusieurs tentatives car lazy-load React)
  for (let attempt = 0; attempt < 4; attempt++) {
    // Lien direct vers autoviza.fr
    const directLink = document.querySelector('a[href*="autoviza.fr"]');
    if (directLink) return directLink.href;

    // Lien via redirect LBC (href contient autoviza en param)
    const redirectLink = document.querySelector('a[href*="autoviza"]');
    if (redirectLink) {
      const href = redirectLink.href;
      const match = href.match(/(https?:\/\/[^\s&"]*autoviza\.fr[^\s&"]*)/);
      if (match) return match[1];
      return href;
    }

    // Bouton/lien avec texte "rapport d'historique" ou "rapport historique"
    const allLinks = document.querySelectorAll('a[href], button[data-href]');
    for (const el of allLinks) {
      const text = (el.textContent || "").toLowerCase();
      if ((text.includes("rapport") && text.includes("historique")) ||
          text.includes("autoviza")) {
        const href = el.href || el.dataset.href || "";
        if (href && href.includes("autoviza")) return href;
      }
    }

    if (attempt < 3) await _sleep(800);
  }

  // 2. Fallback : chercher une URL autoviza dans __NEXT_DATA__
  if (nextData) {
    const json = JSON.stringify(nextData);
    const match = json.match(/(https?:\/\/[^\s"]*autoviza\.fr[^\s"]*)/);
    if (match) return match[1];
  }

  return null;
}

/**
 * Recupere le numero de telephone sur la page LBC.
 * 1. Verifie si un lien tel: existe deja (numero deja revele)
 * 2. Sinon clique "Voir le numero" (utilisateur connecte uniquement)
 * Retourne le numero (string) ou null si indisponible.
 */
export async function revealPhoneNumber() {
  // 1. Le numero est peut-etre deja visible (revele lors d'un precedent scan)
  const existingTelLinks = document.querySelectorAll('a[href^="tel:"]');
  for (const link of existingTelLinks) {
    const phone = link.href.replace("tel:", "").trim();
    if (phone && phone.length >= 10) return phone;
  }

  // 2. Sinon chercher le bouton "Voir le numero" et cliquer
  const candidates = document.querySelectorAll('button, a, [role="button"]');
  let phoneBtn = null;

  for (const el of candidates) {
    const text = (el.textContent || "").toLowerCase().trim();
    if (text.includes("voir le numéro") || text.includes("voir le numero")
        || text.includes("afficher le numéro") || text.includes("afficher le numero")) {
      phoneBtn = el;
      break;
    }
  }

  if (!phoneBtn) return null;

  phoneBtn.click();

  // 3. Attendre que le DOM se mette a jour
  for (let attempt = 0; attempt < 5; attempt++) {
    await _sleep(500);

    const telLinks = document.querySelectorAll('a[href^="tel:"]');
    for (const link of telLinks) {
      const phone = link.href.replace("tel:", "").trim();
      if (phone && phone.length >= 10) return phone;
    }

    const container = phoneBtn.closest("div") || phoneBtn.parentElement;
    if (container) {
      const match = container.textContent.match(/(?:\+33|0)\s*[1-9](?:[\s.-]*\d{2}){4}/);
      if (match) return match[0].replace(/[\s.-]/g, "");
    }
  }

  return null;
}

/** Verifie qu'on est bien sur une page d'annonce LeBonCoin. */
export function isAdPageLBC() {
  const url = window.location.href;
  return url.includes("leboncoin.fr/ad/") || url.includes("leboncoin.fr/voitures/");
}

// ── Market price collection ───────────────────────────────────────

/** Calcule le range de puissance DIN pour la recherche LBC. */
export function getHorsePowerRange(hp) {
  if (!hp || hp <= 0) return null;
  if (hp < 80)  return "min-90";
  if (hp < 110) return "70-120";
  if (hp < 140) return "100-150";
  if (hp < 180) return "130-190";
  if (hp < 250) return "170-260";
  if (hp < 350) return "240-360";
  return "340-max";
}

/** Calcule le range de kilometrage pour la recherche LBC. */
export function getMileageRange(km) {
  if (!km || km <= 0) return null;
  if (km <= 10000) return "min-20000";
  if (km <= 30000) return "min-50000";
  if (km <= 60000) return "20000-80000";
  if (km <= 120000) return "50000-150000";
  return "100000-max";
}

/** Extrait la region depuis les donnees __NEXT_DATA__. */
export function extractRegionFromNextData(nextData) {
  if (!nextData) return "";
  const loc = nextData?.props?.pageProps?.ad?.location;
  return loc?.region_name || loc?.region || "";
}

/** Extrait les donnees de localisation completes depuis __NEXT_DATA__.
 *  Retourne { city, zipcode, lat, lng, region } ou null si absent. */
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

/** Extrait les details d'une annonce LBC (prix, annee, km, fuel). */
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

/** Parse une range URL "min-max" en objet {min?, max?}. */
export function parseRange(rangeStr) {
  if (!rangeStr) return null;
  const [minStr, maxStr] = rangeStr.split("-");
  const range = {};
  if (minStr && minStr !== "min") range.min = parseInt(minStr, 10);
  if (maxStr && maxStr !== "max") range.max = parseInt(maxStr, 10);
  return Object.keys(range).length > 0 ? range : null;
}

/** Convertit les params URL de recherche LBC en filtres pour l'API finder. */
export function buildApiFilters(searchUrl) {
  const url = new URL(searchUrl);
  const params = url.searchParams;

  const filters = {
    category: { id: params.get("category") || "2" },
    enums: { ad_type: ["offer"], country_id: ["FR"] },
    ranges: { price: { min: 500 } },
  };

  // Enums (brand, model, fuel, gearbox)
  for (const key of ["u_car_brand", "u_car_model", "fuel", "gearbox"]) {
    const val = params.get(key);
    if (val) filters.enums[key] = [val];
  }

  // Text search (modeles generiques)
  const text = params.get("text");
  if (text) filters.keywords = { text };

  // Ranges (regdate, mileage, horse_power_din)
  for (const key of ["regdate", "mileage", "horse_power_din"]) {
    const range = parseRange(params.get(key));
    if (range) filters.ranges[key] = range;
  }

  // Location
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

/** Filtre et mappe les ads bruts en tableau de {price, year, km, fuel}. */
export function filterAndMapSearchAds(ads, targetYear, yearSpread) {
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
      return true;
    })
    .map((ad) => getAdDetails(ad));
}

/** Fetch les prix via l'API LBC finder/search (methode principale). */
export async function fetchSearchPricesViaApi(searchUrl) {
  const filters = buildApiFilters(searchUrl);
  const body = JSON.stringify({
    filters,
    limit: 35,
    sort_by: "time",
    sort_order: "desc",
    owner_type: "all",
  });

  // 1. Via background -> MAIN world (production : cookies LBC natifs)
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

  // 2. Fallback : direct fetch (tests + si background indisponible)
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

/** Fetch les prix via HTML scraping __NEXT_DATA__ (fallback). */
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

/** Fetch une page de recherche LBC et extrait les prix valides. */
export async function fetchSearchPrices(searchUrl, targetYear, yearSpread) {
  let ads = null;

  // 1. API LBC finder/search (methode principale depuis que LBC est CSR)
  try {
    ads = await fetchSearchPricesViaApi(searchUrl);
    if (ads && ads.length > 0) {
      console.log("[CoPilot] fetchSearchPrices (API): %d ads bruts", ads.length);
      return filterAndMapSearchAds(ads, targetYear, yearSpread);
    }
  } catch (err) {
    console.debug("[CoPilot] API finder indisponible:", err.message);
  }

  // 2. Fallback HTML __NEXT_DATA__ (au cas ou l'API ne marche pas)
  try {
    ads = await fetchSearchPricesViaHtml(searchUrl);
    if (ads && ads.length > 0) {
      console.log("[CoPilot] fetchSearchPrices (HTML): %d ads bruts", ads.length);
      return filterAndMapSearchAds(ads, targetYear, yearSpread);
    }
    console.log("[CoPilot] fetchSearchPrices: 0 ads (API + HTML)");
  } catch (err) {
    console.debug("[CoPilot] HTML scraping failed:", err.message);
  }

  return [];
}

/** Construit le parametre `locations=` pour une recherche LBC. */
export function buildLocationParam(location, radiusMeters) {
  if (!location) return "";
  const radius = radiusMeters || DEFAULT_SEARCH_RADIUS;
  if (location.lat && location.lng && location.city && location.zipcode) {
    return `${location.city}_${location.zipcode}__${location.lat}_${location.lng}_5000_${radius}`;
  }
  return LBC_REGIONS[location.region] || "";
}

/** Extrait le kilometrage (en km) depuis les donnees __NEXT_DATA__. */
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

/** Report job completion to server. */
export async function reportJobDone(jobDoneUrl, jobId, success) {
  if (!jobId) return;
  try {
    await _backendFetch(jobDoneUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, success }),
    });
  } catch (e) {
    if (isBenignRuntimeTeardownError(e)) {
      console.debug("[CoPilot] job-done report skipped (extension reloaded/unloaded)");
      return;
    }
    console.warn("[CoPilot] job-done report failed:", e);
  }
}

/**
 * Execute bonus jobs from the CollectionJob queue.
 */
export async function executeBonusJobs(bonusJobs, progress) {
  const MIN_BONUS_PRICES = 5;
  const marketUrl = _apiUrl.replace("/analyze", "/market-prices");
  const jobDoneUrl = _apiUrl.replace("/analyze", "/market-prices/job-done");

  if (progress) progress.update("bonus", "running", "Exécution de " + bonusJobs.length + " jobs");

  for (const job of bonusJobs) {
    try {
      await new Promise((r) => setTimeout(r, 1000 + Math.random() * 1000));

      // Build LBC URL from job data
      const brandUpper = toLbcBrandToken(job.make);
      const modelIsGeneric = GENERIC_MODELS.includes((job.model || "").toLowerCase());
      let jobCoreUrl = "https://www.leboncoin.fr/recherche?category=2";
      if (modelIsGeneric) {
        jobCoreUrl += `&text=${encodeURIComponent(job.make)}`;
      } else {
        const jobBrand = job.site_brand_token || brandUpper;
        const jobModel = job.site_model_token || `${brandUpper}_${job.model}`;
        jobCoreUrl += `&u_car_brand=${encodeURIComponent(jobBrand)}`;
        jobCoreUrl += `&u_car_model=${encodeURIComponent(jobModel)}`;
      }

      // Add filters from job data
      let filters = "";
      if (job.fuel) {
        const fc = LBC_FUEL_CODES[job.fuel.toLowerCase()];
        if (fc) filters += `&fuel=${fc}`;
      }
      if (job.gearbox) {
        const gc = LBC_GEARBOX_CODES[job.gearbox.toLowerCase()];
        if (gc) filters += `&gearbox=${gc}`;
      }
      if (job.hp_range) {
        filters += `&horse_power_din=${job.hp_range}`;
      }

      // Region
      const locParam = LBC_REGIONS[job.region];
      if (!locParam) {
        console.warn("[CoPilot] bonus job: region inconnue '%s', skip", job.region);
        await reportJobDone(jobDoneUrl, job.job_id, false);
        if (progress) progress.addSubStep("bonus", job.region, "skip", "Région inconnue");
        continue;
      }

      let searchUrl = jobCoreUrl + filters + `&locations=${locParam}`;
      const jobYear = parseInt(job.year, 10);
      if (jobYear >= 1990) searchUrl += `&regdate=${jobYear - 1}-${jobYear + 1}`;

      const bonusPrices = await fetchSearchPrices(searchUrl, jobYear, 1);
      console.log("[CoPilot] bonus job %s %s %d %s: %d prix", job.make, job.model, job.year, job.region, bonusPrices.length);

      if (progress) {
        const stepStatus = bonusPrices.length >= MIN_BONUS_PRICES ? "done" : "skip";
        progress.addSubStep("bonus", job.make + " " + job.model + " · " + job.region, stepStatus, bonusPrices.length + " annonces");
      }

      if (bonusPrices.length >= MIN_BONUS_PRICES) {
        const bDetails = bonusPrices.filter((p) => Number.isInteger(p?.price) && p.price > 500);
        const bInts = bDetails.map((p) => p.price);
        if (bInts.length >= MIN_BONUS_PRICES) {
          const bonusPrecision = bonusPrices.length >= 20 ? 4 : 2;
          const bonusPayload = {
            make: job.make,
            model: job.model,
            year: jobYear,
            region: job.region,
            prices: bInts,
            price_details: bDetails,
            fuel: job.fuel || null,
            hp_range: job.hp_range || null,
            precision: bonusPrecision,
            search_log: [{
              step: 1, precision: bonusPrecision, location_type: "region",
              year_spread: 1,
              filters_applied: [
                ...(filters.includes("fuel=") ? ["fuel"] : []),
                ...(filters.includes("gearbox=") ? ["gearbox"] : []),
                ...(filters.includes("horse_power_din=") ? ["hp"] : []),
              ],
              ads_found: bonusPrices.length, url: searchUrl,
              was_selected: true,
              reason: `bonus job queue: ${bonusPrices.length} annonces`,
            }],
          };
          const bResp = await _backendFetch(marketUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(bonusPayload),
          });
          console.log("[CoPilot] bonus job POST %s: %s", job.region, bResp.ok ? "OK" : "FAIL");
          await reportJobDone(jobDoneUrl, job.job_id, bResp.ok);
        } else {
          await reportJobDone(jobDoneUrl, job.job_id, false);
        }
      } else {
        await reportJobDone(jobDoneUrl, job.job_id, false);
      }
    } catch (err) {
      if (isBenignRuntimeTeardownError(err)) {
        console.info("[CoPilot] bonus jobs interrompus: extension rechargée/déchargée");
        if (progress) {
          progress.update("bonus", "warning", "Extension rechargée, jobs bonus interrompus");
        }
        break;
      }
      console.warn("[CoPilot] bonus job %s failed:", job.region, err);
      await reportJobDone(jobDoneUrl, job.job_id, false);
    }
  }
  if (progress) progress.update("bonus", "done");
}

/**
 * Collecte intelligente : demande au serveur quel vehicule a besoin de
 * mise a jour, puis collecte les prix sur LeBonCoin.
 */
export async function maybeCollectMarketPrices(vehicle, nextData, progress) {
  const { make, model, year, fuel, gearbox, horse_power } = vehicle;
  if (!make || !model || !year) return { submitted: false };

  const hp = parseInt(horse_power, 10) || 0;
  const hpRange = getHorsePowerRange(hp);

  // Ne pas collecter de prix pour les categories non-voiture
  const urlMatch = window.location.href.match(/\/ad\/([a-z_]+)\//);
  const urlCategory = urlMatch ? urlMatch[1] : null;
  if (urlCategory && EXCLUDED_CATEGORIES.includes(urlCategory)) {
    console.log("[CoPilot] collecte ignoree: categorie exclue", urlCategory);
    if (progress) {
      progress.update("job", "skip", "Catégorie exclue : " + urlCategory);
      progress.update("collect", "skip");
      progress.update("submit", "skip");
      progress.update("bonus", "skip");
    }
    return { submitted: false };
  }

  const mileageKm = extractMileageFromNextData(nextData);
  const location = extractLocationFromNextData(nextData);
  const region = location?.region || "";
  if (!region) {
    console.warn("[CoPilot] collecte ignoree: pas de region dans nextData");
    if (progress) {
      progress.update("job", "skip", "Région non disponible");
      progress.update("collect", "skip");
      progress.update("submit", "skip");
      progress.update("bonus", "skip");
    }
    return { submitted: false };
  }
  console.log("[CoPilot] collecte: region=%s, location=%o, km=%d", region, location, mileageKm);

  // 2. Demander au serveur quel vehicule collecter
  if (progress) progress.update("job", "running");
  const fuelForJob = (fuel || "").toLowerCase();
  const gearboxForJob = (gearbox || "").toLowerCase();
  const jobUrl = _apiUrl.replace("/analyze", "/market-prices/next-job")
    + `?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}`
    + `&year=${encodeURIComponent(year)}&region=${encodeURIComponent(region)}`
    + `&site=lbc`
    + (fuelForJob ? `&fuel=${encodeURIComponent(fuelForJob)}` : "")
    + (gearboxForJob ? `&gearbox=${encodeURIComponent(gearboxForJob)}` : "")
    + (hpRange ? `&hp_range=${encodeURIComponent(hpRange)}` : "");

  let jobResp;
  try {
    console.log("[CoPilot] next-job →", jobUrl);
    jobResp = await _backendFetch(jobUrl).then((r) => r.json());
    console.log("[CoPilot] next-job ←", JSON.stringify(jobResp));
  } catch (err) {
    console.warn("[CoPilot] next-job erreur:", err);
    if (progress) {
      progress.update("job", "error", "Serveur injoignable");
      progress.update("collect", "skip");
      progress.update("submit", "skip");
      progress.update("bonus", "skip");
    }
    return { submitted: false };
  }
  if (!jobResp?.data?.collect) {
    const queuedJobs = jobResp?.data?.bonus_jobs || [];
    if (queuedJobs.length === 0) {
      console.log("[CoPilot] next-job: collect=false, aucun bonus en queue");
      if (progress) {
        progress.update("job", "done", "Données déjà à jour, pas de collecte nécessaire");
        progress.update("collect", "skip", "Non nécessaire");
        progress.update("submit", "skip");
        progress.update("bonus", "skip");
      }
      return { submitted: false };
    }
    console.log("[CoPilot] next-job: collect=false, %d bonus jobs en queue", queuedJobs.length);
    if (progress) {
      progress.update("job", "done", "Véhicule à jour — " + queuedJobs.length + " jobs en attente");
      progress.update("collect", "skip", "Véhicule déjà à jour");
      progress.update("submit", "skip");
    }
    await executeBonusJobs(queuedJobs, progress);
    localStorage.setItem("copilot_last_collect", String(Date.now()));
    return { submitted: false };
  }

  const target = jobResp.data.vehicle;
  const targetRegion = jobResp.data.region;
  const isRedirect = !!jobResp.data.redirect;
  const bonusJobs = jobResp.data.bonus_jobs || [];
  console.log("[CoPilot] next-job: %d bonus jobs", bonusJobs.length);

  // 3. Cooldown 24h -- uniquement pour les collectes d'AUTRES vehicules
  const isCurrentVehicle =
    target.make.toLowerCase() === make.toLowerCase() &&
    target.model.toLowerCase() === model.toLowerCase();

  if (!isCurrentVehicle) {
    const lastCollect = parseInt(localStorage.getItem("copilot_last_collect") || "0", 10);
    if (Date.now() - lastCollect < COLLECT_COOLDOWN_MS) {
      console.log("[CoPilot] cooldown actif pour autre vehicule, skip collecte redirect — bonus jobs toujours executes");
      if (progress) {
        progress.update("job", "done", "Cooldown actif (autre véhicule collecté récemment)");
        progress.update("collect", "skip", "Cooldown 24h");
        progress.update("submit", "skip");
      }
      if (bonusJobs.length > 0) {
        await executeBonusJobs(bonusJobs, progress);
      } else if (progress) {
        progress.update("bonus", "skip");
      }
      return { submitted: false };
    }
  }
  const targetLabel = target.make + " " + target.model + " " + target.year;
  if (progress) {
    progress.update("job", "done", targetLabel + (isCurrentVehicle ? " (véhicule courant)" : " (autre véhicule du référentiel)"));
  }
  console.log("[CoPilot] collecte cible: %s %s %d (isCurrentVehicle=%s, redirect=%s)", target.make, target.model, target.year, isCurrentVehicle, isRedirect);

  // 4. Construire l'URL de recherche LeBonCoin
  const targetYear = parseInt(target.year, 10) || 0;
  const modelIsGeneric = GENERIC_MODELS.includes((target.model || "").toLowerCase());

  const brandUpper = toLbcBrandToken(target.make);
  const hasDomTokens = isCurrentVehicle && vehicle.site_brand_token && vehicle.site_model_token;
  const hasServerTokens = target.site_brand_token && target.site_model_token;
  const effectiveBrand = hasDomTokens ? vehicle.site_brand_token
    : hasServerTokens ? target.site_brand_token
    : brandUpper;
  const effectiveModel = hasDomTokens ? vehicle.site_model_token
    : hasServerTokens ? target.site_model_token
    : `${brandUpper}_${target.model}`;
  const tokenSource = hasDomTokens ? "DOM" : hasServerTokens ? "serveur" : "fallback";
  if (progress) {
    progress.addSubStep("collect", "Diagnostic LBC", "done",
      `Token marque: ${target.make} → ${effectiveBrand} (${tokenSource})`);
  }
  let coreUrl = "https://www.leboncoin.fr/recherche?category=2";
  if (modelIsGeneric) {
    coreUrl += `&text=${encodeURIComponent(target.make)}`;
  } else {
    coreUrl += `&u_car_brand=${encodeURIComponent(effectiveBrand)}`;
    coreUrl += `&u_car_model=${encodeURIComponent(effectiveModel)}`;
  }

  let fuelParam = "";
  let mileageParam = "";
  let gearboxParam = "";
  let hpParam = "";
  let targetFuel = null;
  let fuelCode = null;
  let gearboxCode = null;
  if (!isRedirect) {
    targetFuel = (fuel || "").toLowerCase();
    fuelCode = LBC_FUEL_CODES[targetFuel];
    fuelParam = fuelCode ? `&fuel=${fuelCode}` : "";

    if (mileageKm > 0) {
      const mileageRange = getMileageRange(mileageKm);
      if (mileageRange) mileageParam = `&mileage=${mileageRange}`;
    }

    gearboxCode = LBC_GEARBOX_CODES[(gearbox || "").toLowerCase()];
    gearboxParam = gearboxCode ? `&gearbox=${gearboxCode}` : "";

    hpParam = hpRange ? `&horse_power_din=${hpRange}` : "";
  }

  const fullFilters = fuelParam + mileageParam + gearboxParam + hpParam;
  const noHpFilters = fuelParam + mileageParam + gearboxParam;
  const minFilters = fuelParam + gearboxParam;

  // 5. Escalade progressive
  const hasGeo = location?.lat && location?.lng && location?.city && location?.zipcode;
  const geoParam = hasGeo ? buildLocationParam(location, DEFAULT_SEARCH_RADIUS) : "";
  const regionParam = LBC_REGIONS[region] || "";

  const strategies = [];
  if (geoParam)    strategies.push({ loc: geoParam,    yearSpread: 1, filters: fullFilters, precision: 5 });
  if (regionParam) strategies.push({ loc: regionParam, yearSpread: 1, filters: fullFilters, precision: 4 });
  if (regionParam) strategies.push({ loc: regionParam, yearSpread: 2, filters: fullFilters, precision: 4 });
  strategies.push({ loc: "", yearSpread: 1, filters: fullFilters, precision: 3 });
  strategies.push({ loc: "", yearSpread: 2, filters: fullFilters, precision: 3 });
  strategies.push({ loc: "", yearSpread: 2, filters: noHpFilters, precision: 2 });
  strategies.push({ loc: "", yearSpread: 3, filters: minFilters,  precision: 1 });

  console.log("[CoPilot] fuel=%s → fuelCode=%s | gearbox=%s → gearboxCode=%s | hp=%d → hpRange=%s | km=%d",
    targetFuel, fuelCode, (gearbox || "").toLowerCase(), gearboxCode, hp, hpRange, mileageKm);
  console.log("[CoPilot] coreUrl:", coreUrl);
  console.log("[CoPilot] %d strategies, geoParam=%s, regionParam=%s", strategies.length, geoParam || "(vide)", regionParam || "(vide)");

  let submitted = false;
  let prices = [];
  let collectedPrecision = null;
  const searchLog = [];
  if (progress) progress.update("collect", "running");
  try {
    for (let i = 0; i < strategies.length; i++) {
      if (i > 0) await new Promise((r) => setTimeout(r, 800 + Math.random() * 700));

      const strategy = strategies[i];
      let searchUrl = coreUrl + strategy.filters;
      if (strategy.loc) searchUrl += `&locations=${strategy.loc}`;
      if (targetYear >= 1990) {
        searchUrl += `&regdate=${targetYear - strategy.yearSpread}-${targetYear + strategy.yearSpread}`;
      }

      const locLabel = (strategy.loc === geoParam && geoParam) ? "Géo (" + (location?.city || "local") + " 30km)"
        : (strategy.loc === regionParam && regionParam) ? "Région (" + targetRegion + ")"
        : "National";
      const strategyLabel = "Stratégie " + (i + 1) + " \u00b7 " + locLabel + " \u00b1" + strategy.yearSpread + "an";

      prices = await fetchSearchPrices(searchUrl, targetYear, strategy.yearSpread);
      const enoughPrices = prices.length >= MIN_PRICES_FOR_ARGUS;
      console.log("[CoPilot] strategie %d (precision=%d): %d prix trouvés | %s",
        i + 1, strategy.precision, prices.length, searchUrl.substring(0, 150));

      if (progress) {
        const stepStatus = enoughPrices ? "done" : "skip";
        const stepDetail = prices.length + " annonces" + (enoughPrices ? " \u2713 seuil atteint" : "");
        progress.addSubStep("collect", strategyLabel, stepStatus, stepDetail);
      }

      const locationType = (strategy.loc === geoParam && geoParam) ? "geo"
        : (strategy.loc === regionParam && regionParam) ? "region"
        : "national";
      searchLog.push({
        step: i + 1,
        precision: strategy.precision,
        location_type: locationType,
        year_spread: strategy.yearSpread,
        filters_applied: [
          ...(strategy.filters.includes("fuel=") ? ["fuel"] : []),
          ...(strategy.filters.includes("gearbox=") ? ["gearbox"] : []),
          ...(strategy.filters.includes("horse_power_din=") ? ["hp"] : []),
          ...(strategy.filters.includes("mileage=") ? ["km"] : []),
        ],
        ads_found: prices.length,
        url: searchUrl,
        was_selected: enoughPrices,
        reason: enoughPrices
          ? `${prices.length} annonces >= ${MIN_PRICES_FOR_ARGUS} minimum`
          : `${prices.length} annonces < ${MIN_PRICES_FOR_ARGUS} minimum`,
      });

      if (enoughPrices) {
        collectedPrecision = strategy.precision;
        console.log("[CoPilot] assez de prix (%d >= %d), precision=%d", prices.length, MIN_PRICES_FOR_ARGUS, collectedPrecision);
        break;
      }
    }

    if (prices.length >= MIN_PRICES_FOR_ARGUS) {
      if (progress) {
        progress.update("collect", "done", prices.length + " prix collectés (précision " + (collectedPrecision || "?") + ")");
        progress.update("submit", "running");
      }
      const priceDetails = prices.filter((p) => Number.isInteger(p?.price) && p.price > 500);
      const priceInts = priceDetails.map((p) => p.price);
      if (priceInts.length < MIN_PRICES_FOR_ARGUS) {
        console.warn("[CoPilot] apres filtrage >500: %d prix valides (< %d requis)", priceInts.length, MIN_PRICES_FOR_ARGUS);
        if (priceInts.length >= 5) {
           console.log("[CoPilot] envoi degradé avec %d prix (min 5)", priceInts.length);
        } else {
           if (progress) {
             progress.update("submit", "warning", "Trop de prix invalides après filtrage");
             progress.update("bonus", "skip");
           }
           return { submitted: false, isCurrentVehicle };
        }
      }
      const marketUrl = _apiUrl.replace("/analyze", "/market-prices");
      const payload = {
        make: target.make,
        model: target.model,
        year: parseInt(target.year, 10),
        region: targetRegion,
        prices: priceInts,
        price_details: priceDetails,
        category: urlCategory,
        fuel: fuelCode ? targetFuel : null,
        hp_range: hpRange || null,
        precision: collectedPrecision,
        search_log: searchLog,
        site_brand_token: isCurrentVehicle ? vehicle.site_brand_token : null,
        site_model_token: isCurrentVehicle ? vehicle.site_model_token : null,
      };
      console.log("[CoPilot] POST /api/market-prices:", target.make, target.model, target.year, targetRegion, "fuel=", payload.fuel, "n=", priceInts.length);
      const marketResp = await _backendFetch(marketUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      submitted = marketResp.ok;
      if (!marketResp.ok) {
        const errBody = await marketResp.json().catch(() => null);
        console.warn("[CoPilot] POST /api/market-prices FAILED:", marketResp.status, errBody);
        if (progress) progress.update("submit", "error", "Erreur serveur (" + marketResp.status + ")");
      } else {
        console.log("[CoPilot] POST /api/market-prices OK, submitted=true");
        if (progress) progress.update("submit", "done", priceInts.length + " prix envoyés (" + targetRegion + ")");

        if (bonusJobs.length > 0) {
          await executeBonusJobs(bonusJobs, progress);
        } else {
          if (progress) progress.update("bonus", "skip", "Aucun job en attente");
        }
      }
    } else {
      console.log(`[CoPilot] pas assez de prix apres toutes les strategies: ${prices.length} < ${MIN_PRICES_FOR_ARGUS}`);
      if (progress) {
        progress.update("collect", "warning", prices.length + " annonces trouvées (minimum " + MIN_PRICES_FOR_ARGUS + ")");
        progress.update("submit", "skip", "Pas assez de données");
        progress.update("bonus", "skip");
      }

      // Reporter la recherche echouee au serveur pour diagnostic
      try {
        const failedUrl = _apiUrl.replace("/analyze", "/market-prices/failed-search");
        await _backendFetch(failedUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            make: target.make,
            model: target.model,
            year: parseInt(target.year, 10),
            region: targetRegion,
            fuel: targetFuel || null,
            hp_range: hpRange || null,
            brand_token_used: effectiveBrand,
            model_token_used: effectiveModel,
            token_source: tokenSource,
            search_log: searchLog,
          }),
        });
        console.log("[CoPilot] failed search reported to server");
      } catch (e) {
        console.warn("[CoPilot] failed-search report error:", e);
      }
    }
  } catch (err) {
    console.error("[CoPilot] market collection failed:", err);
    if (progress) {
      progress.update("collect", "error", "Erreur pendant la collecte");
      progress.update("submit", "skip");
      progress.update("bonus", "skip");
    }
  }

  // 6. Sauvegarder le timestamp (meme si pas assez de prix)
  localStorage.setItem("copilot_last_collect", String(Date.now()));
  return { submitted, isCurrentVehicle };
}

// ── LeBonCoinExtractor class ──────────────────────────────────────

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
