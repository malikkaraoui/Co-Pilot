"use strict";
(() => {
  // extension/extractors/leboncoin/_deps.js
  var lbcDeps = {
    backendFetch: null,
    sleep: null,
    apiUrl: null
  };
  function initLbcDeps(deps) {
    lbcDeps.backendFetch = deps.backendFetch;
    lbcDeps.sleep = deps.sleep;
    lbcDeps.apiUrl = deps.apiUrl;
  }

  // extension/shared/cooldown.js
  var COLLECT_COOLDOWN_MS = 24 * 60 * 60 * 1e3;
  var STORAGE_KEY = "copilot_last_collect";
  function shouldSkipCollection() {
    const lastCollect = parseInt(localStorage.getItem(STORAGE_KEY) || "0", 10);
    return Date.now() - lastCollect < COLLECT_COOLDOWN_MS;
  }
  function markCollected() {
    localStorage.setItem(STORAGE_KEY, String(Date.now()));
  }

  // extension/shared/brand.js
  function normalizeBrand(brand) {
    if (!brand) return "";
    return brand.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[-_]/g, " ").trim();
  }
  function brandsMatch(adBrand, targetMake) {
    if (!adBrand || !targetMake) return true;
    const a = normalizeBrand(adBrand);
    const t = normalizeBrand(targetMake);
    if (!a || !t) return true;
    if (a === t) return true;
    if (a === "vw" && t === "volkswagen" || a === "volkswagen" && t === "vw") return true;
    if (a.startsWith("mercedes") && t.startsWith("mercedes")) return true;
    if (a.includes(t) || t.includes(a)) return true;
    return false;
  }

  // extension/shared/ranges.js
  function getHpRange(hp) {
    if (!hp || hp <= 0) return null;
    if (hp < 80) return "min-90";
    if (hp < 110) return "70-120";
    if (hp < 140) return "100-150";
    if (hp < 180) return "130-190";
    if (hp < 250) return "170-260";
    if (hp < 350) return "240-360";
    return "340-max";
  }
  function getMileageRange(km) {
    if (!km || km <= 0) return null;
    if (km <= 1e4) return "min-20000";
    if (km <= 3e4) return "min-50000";
    if (km <= 6e4) return "20000-80000";
    if (km <= 12e4) return "50000-150000";
    return "100000-max";
  }

  // extension/extractors/leboncoin/constants.js
  var GENERIC_MODELS = ["autres", "autre", "other", "divers"];
  var EXCLUDED_CATEGORIES = ["motos", "equipement_moto", "caravaning", "nautisme"];
  var LBC_BRAND_ALIASES = {
    MERCEDES: "MERCEDES-BENZ"
  };
  var DUAL_BRAND_ALIASES = {
    DS: "CITROEN"
  };
  var LBC_REGIONS = {
    "\xCEle-de-France": "rn_12",
    "Auvergne-Rh\xF4ne-Alpes": "rn_22",
    "Provence-Alpes-C\xF4te d'Azur": "rn_21",
    "Occitanie": "rn_16",
    "Nouvelle-Aquitaine": "rn_20",
    "Hauts-de-France": "rn_17",
    "Grand Est": "rn_8",
    "Bretagne": "rn_6",
    "Pays de la Loire": "rn_18",
    "Normandie": "rn_4",
    "Bourgogne-Franche-Comt\xE9": "rn_5",
    "Centre-Val de Loire": "rn_7",
    "Corse": "rn_9",
    "Nord-Pas-de-Calais": "rn_17",
    "Picardie": "rn_17",
    "Rh\xF4ne-Alpes": "rn_22",
    "Auvergne": "rn_22",
    "Midi-Pyr\xE9n\xE9es": "rn_16",
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
    "Franche-Comt\xE9": "rn_5"
  };
  var LBC_FUEL_CODES = {
    "essence": 1,
    "diesel": 2,
    "gpl": 3,
    "electrique": 4,
    "\xE9lectrique": 4,
    "autre": 5,
    "hybride": 6,
    "gnv": 7,
    "gaz naturel": 7,
    "hybride rechargeable": 8,
    "\xE9lectrique & essence": 6,
    "electrique & essence": 6,
    "\xE9lectrique & diesel": 6,
    "electrique & diesel": 6
  };
  var LBC_GEARBOX_CODES = {
    "manuelle": 1,
    "automatique": 2
  };
  var COLLECT_COOLDOWN_MS2 = COLLECT_COOLDOWN_MS;
  var DEFAULT_SEARCH_RADIUS = 3e4;
  var MIN_PRICES_FOR_ARGUS = 20;
  var getHorsePowerRange = getHpRange;
  var getMileageRange2 = getMileageRange;
  var brandMatches = brandsMatch;

  // extension/extractors/leboncoin/parser.js
  function isStaleData(data) {
    const urlMatch = window.location.href.match(/\/(\d+)(?:[?#]|$)/);
    if (!urlMatch) return false;
    const urlAdId = urlMatch[1];
    const ad = data?.props?.pageProps?.ad;
    if (!ad) return true;
    const dataAdId = String(ad.list_id || ad.id || "");
    if (!dataAdId) return true;
    return dataAdId !== urlAdId;
  }
  async function extractNextData() {
    const el = document.getElementById("__copilot_next_data__");
    if (el && el.textContent) {
      try {
        const data = JSON.parse(el.textContent);
        el.remove();
        if (data && !isStaleData(data)) return data;
      } catch {
      }
    }
    const script = document.getElementById("__NEXT_DATA__");
    if (script) {
      try {
        const data = JSON.parse(script.textContent);
        if (data && !isStaleData(data)) return data;
      } catch {
      }
    }
    try {
      const resp = await fetch(window.location.href, {
        credentials: "same-origin",
        headers: { "Accept": "text/html" }
      });
      const html = await resp.text();
      const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
      if (match) return JSON.parse(match[1]);
    } catch {
    }
    return null;
  }
  function extractLbcTokensFromDom() {
    const result = { brandToken: null, modelToken: null };
    try {
      const link = document.querySelector('a[href*="u_car_model"]');
      if (!link) return result;
      const url = new URL(link.href, location.origin);
      const raw = decodeURIComponent(url.pathname + url.search + url.hash);
      const extractToken = (key) => {
        const re = new RegExp(`${key}:(.+?)(?:\\+\\w+:|&|$)`);
        const m = raw.match(re);
        return m ? m[1].replace(/\+/g, " ").trim() : null;
      };
      result.brandToken = extractToken("u_car_brand");
      result.modelToken = extractToken("u_car_model");
      if (!result.brandToken) {
        const qBrand = url.searchParams.get("u_car_brand");
        if (qBrand) result.brandToken = qBrand.trim();
      }
      if (!result.modelToken) {
        const qModel = url.searchParams.get("u_car_model");
        if (qModel) result.modelToken = qModel.trim();
      }
    } catch (e) {
      console.warn("[CoPilot] extractLbcTokensFromDom error:", e);
    }
    return result;
  }
  function extractModelFromTitle(title, make) {
    if (!title || !make) return null;
    let cleaned = title.trim();
    if (cleaned.toLowerCase().startsWith(make.toLowerCase())) {
      cleaned = cleaned.slice(make.length).trim();
    }
    cleaned = cleaned.replace(/\b(19|20)\d{2}\b/g, "").trim();
    const noise = /* @__PURE__ */ new Set([
      "neuf",
      "neuve",
      "occasion",
      "tbe",
      "garantie",
      "full",
      "options",
      "option",
      "pack",
      "premium",
      "edition",
      "limited",
      "sport",
      "line",
      "style",
      "business",
      "confort",
      "first",
      "life",
      "zen",
      "intens",
      "intense",
      "initiale",
      "paris",
      "riviera",
      "alpine",
      "esprit",
      "techno",
      "evolution",
      "iconic",
      "rs",
      "gt",
      "gtline",
      "gt-line"
    ]);
    for (const word of cleaned.split(/[\s,\-./()]+/)) {
      const w = word.trim();
      if (!w || noise.has(w.toLowerCase()) || /^\d+$/.test(w)) continue;
      return w;
    }
    return null;
  }
  function extractVehicleFromNextData(nextData) {
    const ad = nextData?.props?.pageProps?.ad;
    if (!ad) return {};
    const attrs = (ad.attributes || []).reduce((acc, a) => {
      const key = a.key || a.key_label || a.label || a.name;
      const val = a.value_label || a.value || a.text || a.value_text;
      if (key) acc[key] = val;
      return acc;
    }, {});
    const make = attrs["brand"] || attrs["Marque"] || "";
    let model = attrs["model"] || attrs["Mod\xE8le"] || attrs["modele"] || "";
    if (GENERIC_MODELS.includes(model.toLowerCase()) && make) {
      const title = ad.subject || ad.title || "";
      const extracted = extractModelFromTitle(title, make);
      if (extracted) model = extracted;
    }
    const domTokens = extractLbcTokensFromDom();
    return {
      make,
      model,
      year: attrs["regdate"] || attrs["Ann\xE9e mod\xE8le"] || attrs["Ann\xE9e"] || attrs["year"] || "",
      fuel: attrs["fuel"] || attrs["\xC9nergie"] || attrs["energie"] || "",
      gearbox: attrs["gearbox"] || attrs["Bo\xEEte de vitesse"] || attrs["Boite de vitesse"] || attrs["Transmission"] || "",
      horse_power: attrs["horse_power_din"] || attrs["Puissance DIN"] || "",
      site_brand_token: domTokens.brandToken,
      site_model_token: domTokens.modelToken
    };
  }
  function toLbcBrandToken(make) {
    const upper = String(make || "").trim().toUpperCase();
    return LBC_BRAND_ALIASES[upper] || upper;
  }
  function getAdYear(ad) {
    const attrs = ad.attributes || [];
    for (const a of attrs) {
      const key = (a.key || a.key_label || "").toLowerCase();
      if (key === "regdate" || key === "ann\xE9e mod\xE8le" || key === "ann\xE9e") {
        const val = String(a.value || a.value_label || "");
        const y = parseInt(val, 10);
        if (y >= 1990 && y <= 2030) return y;
      }
    }
    return null;
  }
  function extractRegionFromNextData(nextData) {
    if (!nextData) return "";
    const loc = nextData?.props?.pageProps?.ad?.location;
    return loc?.region_name || loc?.region || "";
  }
  function extractLocationFromNextData(nextData) {
    const loc = nextData?.props?.pageProps?.ad?.location;
    if (!loc) return null;
    return {
      city: loc.city || "",
      zipcode: loc.zipcode || "",
      lat: loc.lat || null,
      lng: loc.lng || null,
      region: loc.region_name || loc.region || ""
    };
  }
  function getAdDetails(ad) {
    const rawPrice = Array.isArray(ad?.price) ? ad.price[0] : ad?.price;
    const parsedPrice = typeof rawPrice === "number" ? rawPrice : parseInt(String(rawPrice || "0").replace(/[^\d]/g, ""), 10);
    const attrs = Array.isArray(ad?.attributes) ? ad.attributes : [];
    const details = { price: Number.isFinite(parsedPrice) ? parsedPrice : 0 };
    for (const a of attrs) {
      if (!a || typeof a !== "object") continue;
      const key = (a.key || a.key_label || "").toLowerCase();
      if (key === "regdate" || key === "ann\xE9e mod\xE8le" || key === "ann\xE9e") {
        details.year = parseInt(a.value || a.value_label, 10) || null;
      } else if (key === "mileage" || key === "kilom\xE9trage" || key === "kilometrage") {
        details.km = parseInt(String(a.value || a.value_label || "0").replace(/\s/g, ""), 10) || null;
      } else if (key === "fuel" || key === "\xE9nergie" || key === "energie") {
        details.fuel = a.value_label || a.value || null;
      } else if (key === "gearbox" || key === "bo\xEEte de vitesse" || key === "boite de vitesse") {
        details.gearbox = a.value_label || a.value || null;
      } else if (key === "horse_power_din" || key === "puissance din") {
        details.horse_power = parseInt(String(a.value || a.value_label || "0"), 10) || null;
      }
    }
    return details;
  }
  function parseRange(rangeStr) {
    if (!rangeStr) return null;
    const [minStr, maxStr] = rangeStr.split("-");
    const range = {};
    if (minStr && minStr !== "min") range.min = parseInt(minStr, 10);
    if (maxStr && maxStr !== "max") range.max = parseInt(maxStr, 10);
    return Object.keys(range).length > 0 ? range : null;
  }
  function extractMileageFromNextData(nextData) {
    const ad = nextData?.props?.pageProps?.ad;
    if (!ad) return 0;
    const attrs = (ad.attributes || []).reduce((acc, a) => {
      const key = a.key || a.key_label || a.label || a.name;
      const val = a.value_label || a.value || a.text || a.value_text;
      if (key) acc[key] = val;
      return acc;
    }, {});
    const raw = attrs["mileage"] || attrs["Kilom\xE9trage"] || attrs["kilometrage"] || "0";
    return parseInt(String(raw).replace(/\s/g, ""), 10) || 0;
  }

  // extension/extractors/leboncoin/dom.js
  function isUserLoggedIn() {
    const header = document.querySelector("header");
    if (!header) return false;
    const text = header.textContent.toLowerCase();
    return !text.includes("se connecter") && !text.includes("s'identifier");
  }
  async function detectAutovizaUrl(nextData) {
    for (let attempt = 0; attempt < 4; attempt++) {
      const directLink = document.querySelector('a[href*="autoviza.fr"]');
      if (directLink) return directLink.href;
      const redirectLink = document.querySelector('a[href*="autoviza"]');
      if (redirectLink) {
        const href = redirectLink.href;
        const match = href.match(/(https?:\/\/[^\s&"]*autoviza\.fr[^\s&"]*)/);
        if (match) return match[1];
        return href;
      }
      const allLinks = document.querySelectorAll("a[href], button[data-href]");
      for (const el of allLinks) {
        const text = (el.textContent || "").toLowerCase();
        if (text.includes("rapport") && text.includes("historique") || text.includes("autoviza")) {
          const href = el.href || el.dataset.href || "";
          if (href && href.includes("autoviza")) return href;
        }
      }
      if (attempt < 3) await lbcDeps.sleep(800);
    }
    if (nextData) {
      const json = JSON.stringify(nextData);
      const match = json.match(/(https?:\/\/[^\s"]*autoviza\.fr[^\s"]*)/);
      if (match) return match[1];
    }
    return null;
  }
  async function revealPhoneNumber() {
    const existingTelLinks = document.querySelectorAll('a[href^="tel:"]');
    for (const link of existingTelLinks) {
      const phone = link.href.replace("tel:", "").trim();
      if (phone && phone.length >= 10) return phone;
    }
    const candidates = document.querySelectorAll('button, a, [role="button"]');
    let phoneBtn = null;
    for (const el of candidates) {
      const text = (el.textContent || "").toLowerCase().trim();
      if (text.includes("voir le num\xE9ro") || text.includes("voir le numero") || text.includes("afficher le num\xE9ro") || text.includes("afficher le numero")) {
        phoneBtn = el;
        break;
      }
    }
    if (!phoneBtn) return null;
    phoneBtn.click();
    for (let attempt = 0; attempt < 5; attempt++) {
      await lbcDeps.sleep(500);
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
  function isAdPageLBC() {
    const url = window.location.href;
    return url.includes("leboncoin.fr/ad/") || url.includes("leboncoin.fr/voitures/");
  }

  // extension/utils/fetch.js
  function isChromeRuntimeAvailable() {
    try {
      return typeof chrome !== "undefined" && !!chrome.runtime && typeof chrome.runtime.sendMessage === "function";
    } catch {
      return false;
    }
  }
  function isLocalBackendUrl(url) {
    return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(String(url || ""));
  }
  function isBenignRuntimeTeardownError(err) {
    const msg = String(err?.message || err || "").toLowerCase();
    return msg.includes("extension context invalidated") || msg.includes("runtime_unavailable_for_local_backend") || msg.includes("receiving end does not exist");
  }
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
  async function backendFetch(url, options = {}) {
    const isLocalBackend = isLocalBackendUrl(url);
    if (!isChromeRuntimeAvailable()) {
      try {
        return await fetch(url, options);
      } catch (err) {
        if (isLocalBackend) {
          throw new Error("runtime_unavailable_for_local_backend");
        }
        throw err;
      }
    }
    return new Promise((resolve, reject) => {
      try {
        chrome.runtime.sendMessage(
          {
            action: "backend_fetch",
            url,
            method: options.method || "GET",
            headers: options.headers || null,
            body: options.body || null
          },
          (resp) => {
            let runtimeErrorMsg = null;
            try {
              runtimeErrorMsg = chrome.runtime?.lastError?.message || null;
            } catch (e) {
              runtimeErrorMsg = e?.message || "extension context invalidated";
            }
            if (runtimeErrorMsg || !resp || resp.error) {
              fetch(url, options).then(resolve).catch((fallbackErr) => {
                if (isLocalBackend) {
                  reject(new Error(runtimeErrorMsg || resp?.error || fallbackErr?.message || "runtime_unavailable_for_local_backend"));
                  return;
                }
                reject(fallbackErr);
              });
              return;
            }
            let parsed;
            try {
              parsed = JSON.parse(resp.body);
            } catch {
              parsed = null;
            }
            resolve({
              ok: resp.ok,
              status: resp.status,
              json: async () => {
                if (parsed !== null) return parsed;
                throw new SyntaxError("Invalid JSON");
              },
              text: async () => resp.body
            });
          }
        );
      } catch (err) {
        if (isLocalBackend) {
          reject(err);
          return;
        }
        fetch(url, options).then(resolve).catch(reject);
      }
    });
  }

  // extension/extractors/leboncoin/search.js
  function _extractAdBrand(ad) {
    const attrs = Array.isArray(ad?.attributes) ? ad.attributes : [];
    const brandAttr = attrs.find((a) => {
      const key = (a?.key || "").toLowerCase();
      return key === "u_car_brand" || key === "brand" || key === "marque";
    });
    return brandAttr?.value_label || brandAttr?.value || null;
  }
  function buildApiFilters(searchUrl) {
    const url = new URL(searchUrl);
    const params = url.searchParams;
    const filters = {
      category: { id: params.get("category") || "2" },
      enums: { ad_type: ["offer"], country_id: ["FR"] },
      ranges: { price: { min: 500 } }
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
            radius: parseInt(geoParts[3]) || 3e4
          }
        };
      }
    }
    return filters;
  }
  function filterAndMapSearchAds(ads, targetYear, yearSpread, targetMake = null) {
    return ads.filter((ad) => {
      const rawPrice = Array.isArray(ad?.price) ? ad.price[0] : ad?.price;
      const priceInt = typeof rawPrice === "number" ? rawPrice : parseInt(String(rawPrice || "0").replace(/[^\d]/g, ""), 10);
      if (!Number.isFinite(priceInt) || priceInt <= 500) return false;
      if (targetYear >= 1990) {
        const adYear = getAdYear(ad);
        if (adYear && Math.abs(adYear - targetYear) > yearSpread) return false;
      }
      if (targetMake) {
        const adBrand = _extractAdBrand(ad);
        if (adBrand && !brandMatches(adBrand, targetMake)) {
          console.debug("[CoPilot] brand safety: rejet %s (cible: %s)", adBrand, targetMake);
          return false;
        }
      }
      return true;
    }).map((ad) => getAdDetails(ad));
  }
  async function fetchSearchPricesViaApi(searchUrl) {
    const filters = buildApiFilters(searchUrl);
    const body = JSON.stringify({
      filters,
      limit: 35,
      sort_by: "time",
      sort_order: "desc",
      owner_type: "all"
    });
    if (isChromeRuntimeAvailable()) {
      try {
        const result = await chrome.runtime.sendMessage({
          action: "lbc_api_search",
          body
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
        "Accept": "application/json"
      },
      body
    });
    if (!resp.ok) {
      console.warn("[CoPilot] API finder (direct): HTTP %d", resp.status);
      return null;
    }
    const data = await resp.json();
    return data.ads || data.results || [];
  }
  async function fetchSearchPricesViaHtml(searchUrl) {
    const resp = await fetch(searchUrl, {
      credentials: "same-origin",
      headers: { "Accept": "text/html" }
    });
    const html = await resp.text();
    const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
    if (!match) return [];
    const data = JSON.parse(match[1]);
    const pp = data?.props?.pageProps || {};
    return pp?.searchData?.ads || pp?.initialProps?.searchData?.ads || pp?.ads || pp?.adSearch?.ads || [];
  }
  async function fetchSearchPrices(searchUrl, targetYear, yearSpread, targetMake = null) {
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
  function buildLocationParam(location2, radiusMeters) {
    if (!location2) return "";
    const radius = radiusMeters || DEFAULT_SEARCH_RADIUS;
    if (location2.lat && location2.lng && location2.city && location2.zipcode) {
      return `${location2.city}_${location2.zipcode}__${location2.lat}_${location2.lng}_5000_${radius}`;
    }
    return LBC_REGIONS[location2.region] || "";
  }

  // extension/extractors/leboncoin/collect.js
  async function reportJobDone(jobDoneUrl, jobId, success) {
    if (!jobId) return;
    try {
      await lbcDeps.backendFetch(jobDoneUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, success })
      });
    } catch (e) {
      if (isBenignRuntimeTeardownError(e)) {
        console.debug("[CoPilot] job-done report skipped (extension reloaded/unloaded)");
        return;
      }
      console.warn("[CoPilot] job-done report failed:", e);
    }
  }
  async function executeBonusJobs(bonusJobs, progress) {
    const MIN_BONUS_PRICES = 5;
    const marketUrl = lbcDeps.apiUrl.replace("/analyze", "/market-prices");
    const jobDoneUrl = lbcDeps.apiUrl.replace("/analyze", "/market-prices/job-done");
    function _yearMeta(yearRef, spread = 1) {
      const y = Number.parseInt(yearRef, 10);
      const s = Number.parseInt(spread, 10) || 1;
      if (!Number.isFinite(y) || y < 1990) return { year_from: null, year_to: null, regdate: null };
      return { year_from: y - s, year_to: y + s, regdate: `${y - s}-${y + s}` };
    }
    function _urlVerdict(adsFound, uniqueAdded) {
      if ((adsFound || 0) <= 0) return "empty";
      if ((uniqueAdded || 0) <= 0) return "duplicates_only";
      return "useful";
    }
    function _criteriaSummary(make, model, brandToken, modelToken, fuelCode, gearboxCode, hpRange, yearMeta) {
      const yearVal = yearMeta.year_from && yearMeta.year_to ? `${yearMeta.year_from}-${yearMeta.year_to}` : "?-?";
      return [
        `marque=${make} [${brandToken}]`,
        `model=${model} [${modelToken}]`,
        `fuel=${fuelCode || "any"}`,
        `boite=${gearboxCode || "any"}`,
        `CV=${hpRange || "any"}`,
        `ann\xE9e=${yearVal}`
      ].join(" \xB7 ");
    }
    if (progress) progress.update("bonus", "running", "Ex\xE9cution de " + bonusJobs.length + " jobs");
    for (const job of bonusJobs) {
      try {
        await new Promise((r) => setTimeout(r, 1e3 + Math.random() * 1e3));
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
        const locParam = LBC_REGIONS[job.region];
        if (!locParam) {
          console.warn("[CoPilot] bonus job: region inconnue '%s', skip", job.region);
          await reportJobDone(jobDoneUrl, job.job_id, false);
          if (progress) progress.addSubStep("bonus", job.region, "skip", "R\xE9gion inconnue");
          continue;
        }
        let searchUrl = jobCoreUrl + filters + `&locations=${locParam}`;
        const jobYear = parseInt(job.year, 10);
        const yearMeta = _yearMeta(jobYear, 1);
        if (yearMeta.regdate) searchUrl += `&regdate=${yearMeta.regdate}`;
        const bonusPrices = await fetchSearchPrices(searchUrl, jobYear, 1, job.make);
        console.log("[CoPilot] bonus job %s %s %d %s: %d prix", job.make, job.model, job.year, job.region, bonusPrices.length);
        if (progress) {
          const stepStatus = bonusPrices.length >= MIN_BONUS_PRICES ? "done" : "skip";
          const criteriaSummary = _criteriaSummary(
            job.make,
            job.model,
            job.site_brand_token || brandUpper,
            job.site_model_token || `${brandUpper}_${job.model}`,
            filters.match(/(?:\?|&)fuel=([^&]+)/)?.[1] || null,
            filters.match(/(?:\?|&)gearbox=([^&]+)/)?.[1] || null,
            filters.match(/(?:\?|&)horse_power_din=([^&]+)/)?.[1] || job.hp_range || null,
            yearMeta
          );
          progress.addSubStep(
            "bonus",
            job.make + " " + job.model + " \xB7 " + job.region,
            stepStatus,
            bonusPrices.length + " annonces \xB7 " + criteriaSummary
          );
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
                step: 1,
                precision: bonusPrecision,
                location_type: "region",
                year_spread: 1,
                year_from: yearMeta.year_from,
                year_to: yearMeta.year_to,
                year_filter: yearMeta.regdate ? `regdate=${yearMeta.regdate}` : null,
                criteria_summary: _criteriaSummary(
                  job.make,
                  job.model,
                  job.site_brand_token || brandUpper,
                  job.site_model_token || `${brandUpper}_${job.model}`,
                  filters.match(/(?:\?|&)fuel=([^&]+)/)?.[1] || null,
                  filters.match(/(?:\?|&)gearbox=([^&]+)/)?.[1] || null,
                  filters.match(/(?:\?|&)horse_power_din=([^&]+)/)?.[1] || job.hp_range || null,
                  yearMeta
                ),
                filters_applied: [
                  ...filters.includes("fuel=") ? ["fuel"] : [],
                  ...filters.includes("gearbox=") ? ["gearbox"] : [],
                  ...filters.includes("horse_power_din=") ? ["hp"] : []
                ],
                ads_found: bonusPrices.length,
                url: searchUrl,
                unique_added: bonusPrices.length,
                url_verdict: _urlVerdict(bonusPrices.length, bonusPrices.length),
                was_selected: true,
                reason: `bonus job queue: ${bonusPrices.length} annonces`
              }]
            };
            const bResp = await lbcDeps.backendFetch(marketUrl, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(bonusPayload)
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
          console.info("[CoPilot] bonus jobs interrompus: extension recharg\xE9e/d\xE9charg\xE9e");
          if (progress) {
            progress.update("bonus", "warning", "Extension recharg\xE9e, jobs bonus interrompus");
          }
          break;
        }
        console.warn("[CoPilot] bonus job %s failed:", job.region, err);
        await reportJobDone(jobDoneUrl, job.job_id, false);
      }
    }
    if (progress) progress.update("bonus", "done");
  }
  async function maybeCollectMarketPrices(vehicle, nextData, progress) {
    const { make, model, year, fuel, gearbox, horse_power } = vehicle;
    if (!make || !model || !year) return { submitted: false };
    const hp = parseInt(horse_power, 10) || 0;
    const hpRange = getHorsePowerRange(hp);
    const urlMatch = window.location.href.match(/\/ad\/([a-z_]+)\//);
    const urlCategory = urlMatch ? urlMatch[1] : null;
    if (urlCategory && EXCLUDED_CATEGORIES.includes(urlCategory)) {
      console.log("[CoPilot] collecte ignoree: categorie exclue", urlCategory);
      if (progress) {
        progress.update("job", "skip", "Cat\xE9gorie exclue : " + urlCategory);
        progress.update("collect", "skip");
        progress.update("submit", "skip");
        progress.update("bonus", "skip");
      }
      return { submitted: false };
    }
    const mileageKm = extractMileageFromNextData(nextData);
    const location2 = extractLocationFromNextData(nextData);
    const region = location2?.region || "";
    if (!region) {
      console.warn("[CoPilot] collecte ignoree: pas de region dans nextData");
      if (progress) {
        progress.update("job", "skip", "R\xE9gion non disponible");
        progress.update("collect", "skip");
        progress.update("submit", "skip");
        progress.update("bonus", "skip");
      }
      return { submitted: false };
    }
    console.log("[CoPilot] collecte: region=%s, location=%o, km=%d", region, location2, mileageKm);
    if (progress) progress.update("job", "running");
    const fuelForJob = (fuel || "").toLowerCase();
    const gearboxForJob = (gearbox || "").toLowerCase();
    const jobUrl = lbcDeps.apiUrl.replace("/analyze", "/market-prices/next-job") + `?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}&year=${encodeURIComponent(year)}&region=${encodeURIComponent(region)}&site=lbc` + (fuelForJob ? `&fuel=${encodeURIComponent(fuelForJob)}` : "") + (gearboxForJob ? `&gearbox=${encodeURIComponent(gearboxForJob)}` : "") + (hpRange ? `&hp_range=${encodeURIComponent(hpRange)}` : "");
    let jobResp;
    try {
      console.log("[CoPilot] next-job \u2192", jobUrl);
      jobResp = await lbcDeps.backendFetch(jobUrl).then((r) => r.json());
      console.log("[CoPilot] next-job \u2190", JSON.stringify(jobResp));
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
          progress.update("job", "done", "Donn\xE9es d\xE9j\xE0 \xE0 jour, pas de collecte n\xE9cessaire");
          progress.update("collect", "skip", "Non n\xE9cessaire");
          progress.update("submit", "skip");
          progress.update("bonus", "skip");
        }
        return { submitted: false };
      }
      console.log("[CoPilot] next-job: collect=false, %d bonus jobs en queue", queuedJobs.length);
      if (progress) {
        progress.update("job", "done", "V\xE9hicule \xE0 jour \u2014 " + queuedJobs.length + " jobs en attente");
        progress.update("collect", "skip", "V\xE9hicule d\xE9j\xE0 \xE0 jour");
        progress.update("submit", "skip");
      }
      await executeBonusJobs(queuedJobs, progress);
      markCollected();
      return { submitted: false };
    }
    const target = jobResp.data.vehicle;
    const targetRegion = jobResp.data.region;
    const isRedirect = !!jobResp.data.redirect;
    const bonusJobs = jobResp.data.bonus_jobs || [];
    console.log("[CoPilot] next-job: %d bonus jobs", bonusJobs.length);
    const isCurrentVehicle = target.make.toLowerCase() === make.toLowerCase() && target.model.toLowerCase() === model.toLowerCase();
    if (!isCurrentVehicle) {
      if (shouldSkipCollection()) {
        console.log("[CoPilot] cooldown actif pour autre vehicule, skip collecte redirect \u2014 bonus jobs toujours executes");
        if (progress) {
          progress.update("job", "done", "Cooldown actif (autre v\xE9hicule collect\xE9 r\xE9cemment)");
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
      progress.update("job", "done", targetLabel + (isCurrentVehicle ? " (v\xE9hicule courant)" : " (autre v\xE9hicule du r\xE9f\xE9rentiel)"));
    }
    console.log("[CoPilot] collecte cible: %s %s %d (isCurrentVehicle=%s, redirect=%s)", target.make, target.model, target.year, isCurrentVehicle, isRedirect);
    const targetYear = parseInt(target.year, 10) || 0;
    const modelIsGeneric = GENERIC_MODELS.includes((target.model || "").toLowerCase());
    const brandUpper = toLbcBrandToken(target.make);
    const hasDomTokens = isCurrentVehicle && vehicle.site_brand_token && vehicle.site_model_token;
    const hasServerTokens = target.site_brand_token && target.site_model_token;
    const effectiveBrand = hasDomTokens ? vehicle.site_brand_token : hasServerTokens ? target.site_brand_token : brandUpper;
    const effectiveModel = hasDomTokens ? vehicle.site_model_token : hasServerTokens ? target.site_model_token : `${brandUpper}_${target.model}`;
    const tokenSource = hasDomTokens ? "DOM" : hasServerTokens ? "serveur" : "fallback";
    if (progress) {
      progress.addSubStep(
        "collect",
        "Diagnostic LBC",
        "done",
        `Token marque: ${target.make} \u2192 ${effectiveBrand} (${tokenSource})`
      );
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
        const mileageRange = getMileageRange2(mileageKm);
        if (mileageRange) mileageParam = `&mileage=${mileageRange}`;
      }
      gearboxCode = LBC_GEARBOX_CODES[(gearbox || "").toLowerCase()];
      gearboxParam = gearboxCode ? `&gearbox=${gearboxCode}` : "";
      hpParam = hpRange ? `&horse_power_din=${hpRange}` : "";
    }
    const fullFilters = fuelParam + mileageParam + gearboxParam + hpParam;
    const noHpFilters = fuelParam + mileageParam + gearboxParam;
    const minFilters = fuelParam + gearboxParam;
    const hasGeo = location2?.lat && location2?.lng && location2?.city && location2?.zipcode;
    const geoParam = hasGeo ? buildLocationParam(location2, DEFAULT_SEARCH_RADIUS) : "";
    const regionParam = LBC_REGIONS[region] || "";
    const strategies = [];
    if (geoParam) strategies.push({ loc: geoParam, yearSpread: 1, filters: fullFilters, precision: 5 });
    if (regionParam) strategies.push({ loc: regionParam, yearSpread: 1, filters: fullFilters, precision: 4 });
    if (regionParam) strategies.push({ loc: regionParam, yearSpread: 2, filters: fullFilters, precision: 4 });
    strategies.push({ loc: "", yearSpread: 1, filters: fullFilters, precision: 3 });
    strategies.push({ loc: "", yearSpread: 2, filters: fullFilters, precision: 3 });
    strategies.push({ loc: "", yearSpread: 2, filters: noHpFilters, precision: 2 });
    strategies.push({ loc: "", yearSpread: 3, filters: minFilters, precision: 1 });
    if (!modelIsGeneric) {
      const textQuery = `${target.make} ${target.model}`;
      const textCoreUrl = `https://www.leboncoin.fr/recherche?category=2&text=${encodeURIComponent(textQuery)}`;
      strategies.push({
        loc: "",
        yearSpread: 2,
        filters: fuelParam,
        precision: 1,
        coreUrl: textCoreUrl,
        isTextFallback: true
      });
    }
    console.log(
      "[CoPilot] fuel=%s \u2192 fuelCode=%s | gearbox=%s \u2192 gearboxCode=%s | hp=%d \u2192 hpRange=%s | km=%d",
      targetFuel,
      fuelCode,
      (gearbox || "").toLowerCase(),
      gearboxCode,
      hp,
      hpRange,
      mileageKm
    );
    console.log("[CoPilot] coreUrl:", coreUrl);
    console.log("[CoPilot] %d strategies, geoParam=%s, regionParam=%s", strategies.length, geoParam || "(vide)", regionParam || "(vide)");
    let submitted = false;
    let prices = [];
    let collectedPrecision = null;
    const searchLog = [];
    const MAX_PRICES_CAP = 100;
    function _yearMeta(yearRef, spread = 1) {
      const y = Number.parseInt(yearRef, 10);
      const s = Number.parseInt(spread, 10) || 1;
      if (!Number.isFinite(y) || y < 1990) return { year_from: null, year_to: null, regdate: null };
      return { year_from: y - s, year_to: y + s, regdate: `${y - s}-${y + s}` };
    }
    function _urlVerdict(adsFound, uniqueAdded) {
      if ((adsFound || 0) <= 0) return "empty";
      if ((uniqueAdded || 0) <= 0) return "duplicates_only";
      return "useful";
    }
    function _criteriaSummary(strategy, yearMeta) {
      const fuelVal = strategy.filters.match(/(?:\?|&)fuel=([^&]+)/)?.[1] || null;
      const gearboxVal = strategy.filters.match(/(?:\?|&)gearbox=([^&]+)/)?.[1] || null;
      const hpVal = strategy.filters.match(/(?:\?|&)horse_power_din=([^&]+)/)?.[1] || null;
      const modelToken = modelIsGeneric ? `text:${target.make}` : effectiveModel;
      const yearVal = yearMeta.year_from && yearMeta.year_to ? `${yearMeta.year_from}-${yearMeta.year_to}` : "?-?";
      return [
        `marque=${target.make} [${effectiveBrand}]`,
        `model=${target.model} [${modelToken}]`,
        `fuel=${fuelVal || "any"}`,
        `boite=${gearboxVal || "any"}`,
        `CV=${hpVal || "any"}`,
        `ann\xE9e=${yearVal}`
      ].join(" \xB7 ");
    }
    if (progress) progress.update("collect", "running");
    try {
      for (let i = 0; i < strategies.length; i++) {
        if (i > 0) await new Promise((r) => setTimeout(r, 800 + Math.random() * 700));
        const strategy = strategies[i];
        if (strategy.isTextFallback && prices.length >= MIN_PRICES_FOR_ARGUS) {
          console.log("[CoPilot] strategie %d: text fallback skipped (already %d prices)", i + 1, prices.length);
          searchLog.push({
            step: i + 1,
            precision: strategy.precision,
            location_type: "national",
            year_spread: strategy.yearSpread,
            year_from: null,
            year_to: null,
            year_filter: null,
            criteria_summary: "text fallback skipped",
            filters_applied: strategy.filters.includes("fuel=") ? ["fuel"] : [],
            ads_found: 0,
            unique_added: 0,
            total_accumulated: prices.length,
            url_verdict: "empty",
            url: "(skipped)",
            was_selected: false,
            reason: `text fallback skipped: ${prices.length} >= ${MIN_PRICES_FOR_ARGUS}`
          });
          if (progress) progress.addSubStep("collect", "Strat\xE9gie " + (i + 1) + " \xB7 Text search (fallback)", "skip", "D\xE9j\xE0 assez de donn\xE9es");
          continue;
        }
        const baseCoreUrl = strategy.coreUrl || coreUrl;
        let searchUrl = baseCoreUrl + strategy.filters;
        if (strategy.loc) searchUrl += `&locations=${strategy.loc}`;
        const yearMeta = _yearMeta(targetYear, strategy.yearSpread);
        const criteriaSummary = _criteriaSummary(strategy, yearMeta);
        if (yearMeta.regdate) {
          searchUrl += `&regdate=${yearMeta.regdate}`;
        }
        const locLabel = strategy.isTextFallback ? "Text search (fallback)" : strategy.loc === geoParam && geoParam ? "G\xE9o (" + (location2?.city || "local") + " 30km)" : strategy.loc === regionParam && regionParam ? "R\xE9gion (" + targetRegion + ")" : "National";
        const strategyLabel = "Strat\xE9gie " + (i + 1) + " \xB7 " + locLabel + " \xB1" + strategy.yearSpread + "an";
        const newPrices = await fetchSearchPrices(searchUrl, targetYear, strategy.yearSpread, target.make);
        const seen = new Set(prices.map((p) => `${p.price}-${p.km}`));
        const unique = newPrices.filter((p) => !seen.has(`${p.price}-${p.km}`));
        prices = [...prices, ...unique];
        const enoughPrices = prices.length >= MIN_PRICES_FOR_ARGUS;
        console.log(
          "[CoPilot] strategie %d (precision=%d): %d nouveaux prix (%d uniques), total=%d | %s",
          i + 1,
          strategy.precision,
          newPrices.length,
          unique.length,
          prices.length,
          searchUrl.substring(0, 150)
        );
        if (progress) {
          const stepStatus = unique.length > 0 ? "done" : "skip";
          const stepDetail = unique.length + " nouvelles annonces (total " + prices.length + ")" + (enoughPrices && collectedPrecision === null ? " \u2713 seuil atteint" : "") + " \xB7 " + criteriaSummary;
          progress.addSubStep("collect", strategyLabel, stepStatus, stepDetail);
        }
        const locationType = strategy.loc === geoParam && geoParam ? "geo" : strategy.loc === regionParam && regionParam ? "region" : "national";
        searchLog.push({
          step: i + 1,
          precision: strategy.precision,
          location_type: locationType,
          year_spread: strategy.yearSpread,
          year_from: yearMeta.year_from,
          year_to: yearMeta.year_to,
          year_filter: yearMeta.regdate ? `regdate=${yearMeta.regdate}` : null,
          criteria_summary: criteriaSummary,
          filters_applied: [
            ...strategy.filters.includes("fuel=") ? ["fuel"] : [],
            ...strategy.filters.includes("gearbox=") ? ["gearbox"] : [],
            ...strategy.filters.includes("horse_power_din=") ? ["hp"] : [],
            ...strategy.filters.includes("mileage=") ? ["km"] : []
          ],
          ads_found: newPrices.length,
          unique_added: unique.length,
          url_verdict: _urlVerdict(newPrices.length, unique.length),
          total_accumulated: prices.length,
          url: searchUrl,
          was_selected: enoughPrices,
          reason: enoughPrices ? `total ${prices.length} annonces >= ${MIN_PRICES_FOR_ARGUS} minimum` : `total ${prices.length} annonces < ${MIN_PRICES_FOR_ARGUS} minimum`
        });
        if (enoughPrices && collectedPrecision === null) {
          collectedPrecision = strategy.precision;
          console.log("[CoPilot] seuil atteint a la strategie %d (precision=%d), accumulation continue...", i + 1, collectedPrecision);
        }
        if (prices.length >= MAX_PRICES_CAP) {
          console.log("[CoPilot] cap atteint (%d >= %d), arret de la collecte", prices.length, MAX_PRICES_CAP);
          break;
        }
      }
      const secondaryBrand = DUAL_BRAND_ALIASES[brandUpper];
      if (secondaryBrand && !modelIsGeneric && prices.length < MAX_PRICES_CAP) {
        console.log("[CoPilot] dual-brand: %s \u2192 secondary brand %s", brandUpper, secondaryBrand);
        const dualQuery = `${target.make} ${target.model}`;
        const dualCoreUrl = `https://www.leboncoin.fr/recherche?category=2&u_car_brand=${encodeURIComponent(secondaryBrand)}&text=${encodeURIComponent(dualQuery)}`;
        const dualStrategies = [
          { loc: regionParam || "", yearSpread: 2, filters: fuelParam, precision: 2 },
          { loc: "", yearSpread: 2, filters: fuelParam, precision: 1 }
        ];
        for (let d = 0; d < dualStrategies.length; d++) {
          if (prices.length >= MAX_PRICES_CAP) break;
          await new Promise((r) => setTimeout(r, 800 + Math.random() * 700));
          const ds = dualStrategies[d];
          let searchUrl = dualCoreUrl + ds.filters;
          if (ds.loc) searchUrl += `&locations=${ds.loc}`;
          const dYearMeta = _yearMeta(targetYear, ds.yearSpread);
          if (dYearMeta.regdate) {
            searchUrl += `&regdate=${dYearMeta.regdate}`;
          }
          const dCriteriaSummary = [
            `marque=${target.make} [${secondaryBrand}]`,
            `model=${target.model} [text:${target.make} ${target.model}]`,
            `fuel=${ds.filters.match(/(?:\?|&)fuel=([^&]+)/)?.[1] || "any"}`,
            `boite=any`,
            `CV=any`,
            `ann\xE9e=${dYearMeta.year_from && dYearMeta.year_to ? `${dYearMeta.year_from}-${dYearMeta.year_to}` : "?-?"}`
          ].join(" \xB7 ");
          const dualLocType = ds.loc ? "region" : "national";
          const dualLabel = `Strat\xE9gie ${strategies.length + d + 1} \xB7 Dual ${secondaryBrand} (${dualLocType})`;
          const newPrices = await fetchSearchPrices(searchUrl, targetYear, ds.yearSpread, secondaryBrand);
          const seen = new Set(prices.map((p) => `${p.price}-${p.km}`));
          const unique = newPrices.filter((p) => !seen.has(`${p.price}-${p.km}`));
          prices = [...prices, ...unique];
          console.log(
            "[CoPilot] dual-brand strategie %d: %d nouveaux (%d uniques), total=%d | %s",
            strategies.length + d + 1,
            newPrices.length,
            unique.length,
            prices.length,
            searchUrl.substring(0, 150)
          );
          if (progress) {
            const stepStatus = unique.length > 0 ? "done" : "skip";
            progress.addSubStep(
              "collect",
              dualLabel,
              stepStatus,
              unique.length + " nouvelles annonces (total " + prices.length + ") \xB7 " + dCriteriaSummary
            );
          }
          searchLog.push({
            step: strategies.length + d + 1,
            precision: ds.precision,
            location_type: dualLocType,
            year_spread: ds.yearSpread,
            year_from: dYearMeta.year_from,
            year_to: dYearMeta.year_to,
            year_filter: dYearMeta.regdate ? `regdate=${dYearMeta.regdate}` : null,
            criteria_summary: dCriteriaSummary,
            filters_applied: ds.filters.includes("fuel=") ? ["fuel"] : [],
            ads_found: newPrices.length,
            unique_added: unique.length,
            url_verdict: _urlVerdict(newPrices.length, unique.length),
            total_accumulated: prices.length,
            url: searchUrl,
            was_selected: prices.length >= MIN_PRICES_FOR_ARGUS,
            reason: `dual-brand ${secondaryBrand}: ${unique.length} uniques, total ${prices.length}`
          });
          if (prices.length >= MIN_PRICES_FOR_ARGUS && collectedPrecision === null) {
            collectedPrecision = ds.precision;
          }
        }
      }
      if (prices.length >= MIN_PRICES_FOR_ARGUS) {
        if (progress) {
          progress.update("collect", "done", prices.length + " prix collect\xE9s (pr\xE9cision " + (collectedPrecision || "?") + ")");
          progress.update("submit", "running");
        }
        const priceDetails = prices.filter((p) => Number.isInteger(p?.price) && p.price > 500);
        const priceInts = priceDetails.map((p) => p.price);
        if (priceInts.length < MIN_PRICES_FOR_ARGUS) {
          console.warn("[CoPilot] apres filtrage >500: %d prix valides (< %d requis)", priceInts.length, MIN_PRICES_FOR_ARGUS);
          if (priceInts.length >= 5) {
            console.log("[CoPilot] envoi degrad\xE9 avec %d prix (min 5)", priceInts.length);
          } else {
            if (progress) {
              progress.update("submit", "warning", "Trop de prix invalides apr\xE8s filtrage");
              progress.update("bonus", "skip");
            }
            return { submitted: false, isCurrentVehicle };
          }
        }
        const marketUrl = lbcDeps.apiUrl.replace("/analyze", "/market-prices");
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
          site_model_token: isCurrentVehicle ? vehicle.site_model_token : null
        };
        console.log("[CoPilot] POST /api/market-prices:", target.make, target.model, target.year, targetRegion, "fuel=", payload.fuel, "n=", priceInts.length);
        const marketResp = await lbcDeps.backendFetch(marketUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        submitted = marketResp.ok;
        if (!marketResp.ok) {
          const errBody = await marketResp.json().catch(() => null);
          console.warn("[CoPilot] POST /api/market-prices FAILED:", marketResp.status, errBody);
          if (progress) progress.update("submit", "error", "Erreur serveur (" + marketResp.status + ")");
        } else {
          console.log("[CoPilot] POST /api/market-prices OK, submitted=true");
          if (progress) progress.update("submit", "done", priceInts.length + " prix envoy\xE9s (" + targetRegion + ")");
          if (bonusJobs.length > 0) {
            await executeBonusJobs(bonusJobs, progress);
          } else {
            if (progress) progress.update("bonus", "skip", "Aucun job en attente");
          }
        }
      } else {
        console.log(`[CoPilot] pas assez de prix apres toutes les strategies: ${prices.length} < ${MIN_PRICES_FOR_ARGUS}`);
        if (progress) {
          progress.update("collect", "warning", prices.length + " annonces trouv\xE9es (minimum " + MIN_PRICES_FOR_ARGUS + ")");
          progress.update("submit", "skip", "Pas assez de donn\xE9es");
          progress.update("bonus", "skip");
        }
        try {
          const failedUrl = lbcDeps.apiUrl.replace("/analyze", "/market-prices/failed-search");
          await lbcDeps.backendFetch(failedUrl, {
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
              site_brand_token: isCurrentVehicle ? vehicle.site_brand_token : null,
              site_model_token: isCurrentVehicle ? vehicle.site_model_token : null
            })
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
    markCollected();
    return { submitted, isCurrentVehicle };
  }

  // extension/extractors/base.js
  var SiteExtractor = class {
    /** Identifiant du site ('leboncoin', 'autoscout24'). */
    static SITE_ID = "";
    /** Patterns regex pour detecter le site depuis l'URL. */
    static URL_PATTERNS = [];
    /** @type {Function|null} Backend fetch proxy (injected by content.js) */
    _fetch = null;
    /** @type {string|null} API base URL (injected by content.js) */
    _apiUrl = null;
    /**
     * Injecte les dependances communes (backendFetch, apiUrl).
     * Appele par content.js apres construction de l'extracteur.
     * @param {{fetch: Function, apiUrl: string}} deps
     */
    initDeps(deps) {
      this._fetch = deps.fetch;
      this._apiUrl = deps.apiUrl;
    }
    /**
     * Detecte si l'URL courante est une page d'annonce.
     * @param {string} url
     * @returns {boolean}
     */
    isAdPage(url) {
      throw new Error("isAdPage() must be implemented");
    }
    /**
     * Extrait les donnees vehicule de la page.
     *
     * Retourne un objet avec:
     * - type: 'raw' (envoyer next_data brut) ou 'normalized' (ad_data pre-digere)
     * - next_data: payload brut (si type='raw')
     * - ad_data: dict normalise au format extract_ad_data() (si type='normalized')
     * - source: identifiant du site
     *
     * @returns {Promise<{type: string, source: string, next_data?: object, ad_data?: object}|null>}
     */
    async extract() {
      throw new Error("extract() must be implemented");
    }
    /**
     * Revele le numero de telephone du vendeur si possible.
     * @returns {Promise<string|null>}
     */
    async revealPhone() {
      return null;
    }
    /**
     * Detecte un rapport gratuit (Autoviza, etc.) sur la page.
     * @returns {Promise<string|null>}
     */
    async detectFreeReport() {
      return null;
    }
    /**
     * Verifie si l'utilisateur est connecte sur le site.
     * @returns {boolean}
     */
    isLoggedIn() {
      return false;
    }
    /**
     * Indique si l'annonce a un telephone revelable.
     * @returns {boolean}
     */
    hasPhone() {
      return false;
    }
    /**
     * Collecte les prix du marche pour le vehicule courant.
     * @param {object} progress - Progress tracker pour l'UI
     * @returns {Promise<{submitted: boolean}>}
     */
    async collectMarketPrices(progress) {
      return { submitted: false };
    }
    /**
     * Retourne les signaux bonus specifiques au site.
     * Affiches dans une section popup dediee, pas envoyes au backend.
     *
     * @returns {Array<{label: string, value: string, status: string}>}
     */
    getBonusSignals() {
      return [];
    }
    /**
     * Extrait un resume vehicule court pour le header du progress tracker.
     * @returns {{make: string, model: string, year: string}|null}
     */
    getVehicleSummary() {
      return null;
    }
  };

  // extension/extractors/leboncoin/extractor.js
  var LeBonCoinExtractor = class extends SiteExtractor {
    static SITE_ID = "leboncoin";
    static URL_PATTERNS = [/leboncoin\.fr\/ad\//, /leboncoin\.fr\/voitures\//];
    constructor() {
      super();
      this._nextData = null;
      this._vehicle = null;
    }
    isAdPage(url) {
      return url.includes("leboncoin.fr/ad/") || url.includes("leboncoin.fr/voitures/");
    }
    async extract() {
      const nextData = await extractNextData();
      if (!nextData) return null;
      this._nextData = nextData;
      this._vehicle = extractVehicleFromNextData(nextData);
      return { type: "raw", source: "leboncoin", next_data: nextData };
    }
    getVehicleSummary() {
      if (!this._vehicle) return null;
      return { make: this._vehicle.make, model: this._vehicle.model, year: this._vehicle.year };
    }
    getExtractedVehicle() {
      return this._vehicle;
    }
    getNextData() {
      return this._nextData;
    }
    hasPhone() {
      return !!this._nextData?.props?.pageProps?.ad?.has_phone;
    }
    isLoggedIn() {
      return isUserLoggedIn();
    }
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
  };

  // extension/extractors/autoscout24/constants.js
  var AS24_URL_PATTERNS = [
    /autoscout24\.\w+\/(?:(?:fr|de|it|en|nl|es|pl|sv)\/)?(?:d|angebote|offerte|ofertas|aanbod|offres|annunci|anuncios|oferta|erbjudanden)\//i
  ];
  var AD_PAGE_PATTERN = /autoscout24\.\w+\/(?:(?:fr|de|it|en|nl|es|pl|sv)\/)?(?:d|angebote|offerte|ofertas|aanbod|offres|annunci|anuncios|oferta|erbjudanden)\/[a-z0-9][\w-]*?[-–](?:\d+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9]{6,})(?:[/?#]|$)/i;
  var TLD_TO_COUNTRY = {
    ch: "Suisse",
    de: "Allemagne",
    fr: "France",
    it: "Italie",
    at: "Autriche",
    be: "Belgique",
    nl: "Pays-Bas",
    es: "Espagne",
    pl: "Pologne",
    lu: "Luxembourg",
    se: "Suede",
    com: "International"
  };
  var TLD_TO_CURRENCY = {
    ch: "CHF",
    pl: "PLN",
    se: "SEK"
  };
  var TLD_TO_COUNTRY_CODE = {
    ch: "CH",
    de: "DE",
    fr: "FR",
    it: "IT",
    at: "AT",
    be: "BE",
    nl: "NL",
    es: "ES",
    pl: "PL",
    lu: "LU",
    se: "SE",
    com: "INT"
  };
  var SWISS_ZIP_TO_CANTON = {
    "10": "Vaud",
    "11": "Vaud",
    "12": "Geneve",
    "13": "Vaud",
    "14": "Vaud",
    "15": "Vaud",
    "16": "Fribourg",
    "17": "Fribourg",
    "18": "Vaud",
    "19": "Valais",
    "20": "Neuchatel",
    "21": "Neuchatel",
    "22": "Neuchatel",
    "23": "Neuchatel",
    "24": "Jura",
    "25": "Berne",
    "26": "Berne",
    "27": "Jura",
    "28": "Jura",
    "29": "Jura",
    "30": "Berne",
    "31": "Berne",
    "32": "Berne",
    "33": "Berne",
    "34": "Berne",
    "35": "Berne",
    "36": "Berne",
    "37": "Berne",
    "38": "Berne",
    "39": "Valais",
    "40": "Bale-Ville",
    "41": "Bale-Campagne",
    "42": "Bale-Campagne",
    "43": "Argovie",
    "44": "Bale-Campagne",
    "45": "Soleure",
    "46": "Soleure",
    "47": "Soleure",
    "48": "Argovie",
    "49": "Berne",
    "50": "Argovie",
    "51": "Argovie",
    "52": "Argovie",
    "53": "Argovie",
    "54": "Argovie",
    "55": "Argovie",
    "56": "Argovie",
    "57": "Argovie",
    "58": "Argovie",
    "59": "Argovie",
    "60": "Lucerne",
    "61": "Lucerne",
    "62": "Lucerne",
    "63": "Zoug",
    "64": "Schwyz",
    "65": "Obwald",
    "66": "Tessin",
    "67": "Tessin",
    "68": "Tessin",
    "69": "Tessin",
    "70": "Grisons",
    "71": "Grisons",
    "72": "Grisons",
    "73": "Grisons",
    "74": "Grisons",
    "75": "Grisons",
    "76": "Grisons",
    "77": "Grisons",
    "78": "Grisons",
    "79": "Grisons",
    "80": "Zurich",
    "81": "Zurich",
    "82": "Schaffhouse",
    "83": "Zurich",
    "84": "Zurich",
    "85": "Thurgovie",
    "86": "Zurich",
    "87": "Saint-Gall",
    "88": "Zurich",
    "89": "Saint-Gall",
    "90": "Saint-Gall",
    "91": "Appenzell Rhodes-Exterieures",
    "92": "Saint-Gall",
    "93": "Saint-Gall",
    "94": "Saint-Gall",
    "95": "Thurgovie",
    "96": "Saint-Gall",
    "97": "Saint-Gall"
  };
  var MIN_PRICES = 10;
  var FUEL_MAP = {
    gasoline: "Essence",
    benzin: "Essence",
    benzine: "Essence",
    benzyna: "Essence",
    petrol: "Essence",
    gasolina: "Essence",
    diesel: "Diesel",
    gazole: "Diesel",
    "olej napedowy": "Diesel",
    electric: "Electrique",
    elektryczny: "Electrique",
    elektryczna: "Electrique",
    electricity: "Electrique",
    "mhev-diesel": "Diesel",
    "mhev-gasoline": "Essence",
    "phev-diesel": "Hybride Rechargeable",
    "phev-gasoline": "Hybride Rechargeable",
    cng: "GNV",
    lpg: "GPL",
    hydrogen: "Hydrogene",
    hybrid: "Hybride",
    hybride: "Hybride",
    hybryda: "Hybride",
    "hybrid-diesel": "Hybride",
    "hybrid-gasoline": "Hybride",
    "mild-hybrid": "Hybride",
    "mild-hybrid-diesel": "Diesel",
    "mild-hybrid-gasoline": "Essence",
    "plug-in-hybrid": "Hybride Rechargeable",
    "plug-in-hybrid-diesel": "Hybride Rechargeable",
    "plug-in-hybrid-gasoline": "Hybride Rechargeable",
    ethanol: "Ethanol",
    "e85": "Ethanol",
    bifuel: "Bicarburation"
  };
  var TRANSMISSION_MAP = {
    automatic: "Automatique",
    manual: "Manuelle",
    "semi-automatic": "Automatique"
  };
  var AS24_GEAR_MAP = {
    automatic: "A",
    automatique: "A",
    "semi-automatic": "A",
    manual: "M",
    manuelle: "M"
  };
  var AS24_FUEL_CODE_MAP = {
    gasoline: "B",
    diesel: "D",
    electric: "E",
    benzin: "B",
    benzine: "B",
    benzyna: "B",
    petrol: "B",
    gasolina: "B",
    gazole: "D",
    "olej napedowy": "D",
    cng: "C",
    lpg: "L",
    hydrogen: "H",
    "mhev-diesel": "D",
    "mhev-gasoline": "B",
    "phev-diesel": "2",
    "phev-gasoline": "2",
    essence: "B",
    electrique: "E",
    gnv: "C",
    gpl: "L",
    hydrogene: "H",
    "hybride rechargeable": "2"
  };
  var CANTON_CENTER_ZIP = {
    "Zurich": "8000",
    "Berne": "3000",
    "Lucerne": "6000",
    "Uri": "6460",
    "Schwyz": "6430",
    "Obwald": "6060",
    "Nidwald": "6370",
    "Glaris": "8750",
    "Zoug": "6300",
    "Fribourg": "1700",
    "Soleure": "4500",
    "Bale-Ville": "4000",
    "Bale-Campagne": "4410",
    "Schaffhouse": "8200",
    "Appenzell Rhodes-Exterieures": "9100",
    "Appenzell Rhodes-Interieures": "9050",
    "Saint-Gall": "9000",
    "Grisons": "7000",
    "Argovie": "5000",
    "Thurgovie": "8500",
    "Tessin": "6500",
    "Vaud": "1000",
    "Valais": "1950",
    "Neuchatel": "2000",
    "Geneve": "1200",
    "Jura": "2800"
  };
  var SMG_TLDS = /* @__PURE__ */ new Set(["ch"]);

  // extension/extractors/autoscout24/helpers.js
  function getCantonFromZip(zipcode) {
    const zip = String(zipcode || "").trim();
    if (zip.length < 4) return null;
    const prefix = zip.slice(0, 2);
    return SWISS_ZIP_TO_CANTON[prefix] || null;
  }
  function mapFuelType(fuelType) {
    const raw = typeof fuelType === "string" ? fuelType : String(fuelType || "");
    if (!raw.trim()) return null;
    const key = raw.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
    if (FUEL_MAP[key]) return FUEL_MAP[key];
    if (key.includes("plug") && key.includes("hybrid")) return "Hybride Rechargeable";
    if (key.includes("phev")) return "Hybride Rechargeable";
    if (key.includes("diesel")) return "Diesel";
    if (key.includes("gazole")) return "Diesel";
    if (key.includes("olej") && key.includes("naped")) return "Diesel";
    if (key.includes("gasoline") || key.includes("benzin") || key.includes("benzine") || key.includes("benzyn") || key.includes("essence") || key.includes("petrol") || key.includes("gasolina")) return "Essence";
    if (key.includes("hybrid") || key.includes("hybride") || key.includes("hybryd")) return "Hybride";
    if (key.includes("electri") || key.includes("elektrycz")) return "Electrique";
    if (key.includes("cng") || key.includes("gnv")) return "GNV";
    if (key.includes("lpg") || key.includes("gpl")) return "GPL";
    return raw.length > 50 ? raw.slice(0, 50) : raw;
  }
  function mapTransmission(transmission) {
    const key = (transmission || "").toLowerCase();
    return TRANSMISSION_MAP[key] || transmission;
  }
  function getAs24GearCode(gearbox) {
    return AS24_GEAR_MAP[(gearbox || "").toLowerCase()] || null;
  }
  function getAs24FuelCode(fuel) {
    return AS24_FUEL_CODE_MAP[(fuel || "").toLowerCase()] || null;
  }
  function getAs24PowerParams(hp) {
    if (!hp || hp <= 0) return {};
    if (hp < 80) return { powerto: 90 };
    if (hp < 110) return { powerfrom: 70, powerto: 120 };
    if (hp < 140) return { powerfrom: 100, powerto: 150 };
    if (hp < 180) return { powerfrom: 130, powerto: 190 };
    if (hp < 250) return { powerfrom: 170, powerto: 260 };
    if (hp < 350) return { powerfrom: 240, powerto: 360 };
    return { powerfrom: 340 };
  }
  function getAs24KmParams(km) {
    if (!km || km <= 0) return {};
    if (km <= 1e4) return { kmto: 2e4 };
    if (km <= 3e4) return { kmto: 5e4 };
    if (km <= 6e4) return { kmfrom: 2e4, kmto: 8e4 };
    if (km <= 12e4) return { kmfrom: 5e4, kmto: 15e4 };
    return { kmfrom: 1e5 };
  }
  var getHpRangeString = getHpRange;
  function parseHpRange(hpRange) {
    if (!hpRange) return {};
    const parts = hpRange.split("-");
    if (parts.length !== 2) return {};
    const result = {};
    if (parts[0] !== "min") result.powerfrom = parseInt(parts[0], 10);
    if (parts[1] !== "max") result.powerto = parseInt(parts[1], 10);
    return result;
  }
  function getCantonCenterZip(canton) {
    return CANTON_CENTER_ZIP[canton] || null;
  }

  // extension/extractors/autoscout24/search.js
  function extractTld(url) {
    const match = url.match(/autoscout24\.(\w+)/);
    return match ? match[1] : "de";
  }
  function extractLang(url) {
    const match = url.match(/autoscout24\.\w+\/(fr|de|it|en|nl|es|pl|sv)\//);
    return match ? match[1] : null;
  }
  function toAs24Slug(name) {
    return String(name || "").trim().toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9\-]/g, "");
  }
  function extractAs24SlugsFromSearchUrl(url, tldHint = null) {
    try {
      const u = new URL(url);
      const hostMatch = u.hostname.match(/autoscout24\.(\w+)$/i);
      const tld = (tldHint || (hostMatch ? hostMatch[1] : "") || "").toLowerCase();
      const path = decodeURIComponent(u.pathname || "");
      if (SMG_TLDS.has(tld)) {
        const smg = path.match(/\/s\/(?:mo-([^/]+)\/)?mk-([^/?#]+)/i);
        if (!smg) return { makeSlug: null, modelSlug: null };
        const modelSlug2 = smg[1] ? toAs24Slug(smg[1]) : null;
        const makeSlug2 = smg[2] ? toAs24Slug(smg[2]) : null;
        return { makeSlug: makeSlug2, modelSlug: modelSlug2 };
      }
      const normalizedPath = path.replace(/^\/(fr|de|it|en|nl|es|pl|sv)(?=\/|$)/i, "");
      const gmbh = normalizedPath.match(/^\/lst\/([^/]+)(?:\/([^/?#]+))?/i);
      if (!gmbh) return { makeSlug: null, modelSlug: null };
      const makeSlug = gmbh[1] ? toAs24Slug(gmbh[1]) : null;
      const modelSlug = gmbh[2] ? toAs24Slug(gmbh[2]) : null;
      return { makeSlug, modelSlug };
    } catch {
      return { makeSlug: null, modelSlug: null };
    }
  }
  function buildSearchUrl(makeKey, modelKey, year, tld, options = {}) {
    const { yearSpread = 1, fuel, gear, powerfrom, powerto, kmfrom, kmto, zip, radius, lang, brandOnly } = options;
    const makeSlug = toAs24Slug(makeKey);
    const modelSlug = brandOnly ? "" : toAs24Slug(modelKey);
    let base;
    if (SMG_TLDS.has(tld)) {
      const langPrefix = lang ? `/${lang}` : "/fr";
      if (modelSlug) {
        base = `https://www.autoscout24.${tld}${langPrefix}/s/mo-${modelSlug}/mk-${makeSlug}`;
      } else {
        base = `https://www.autoscout24.${tld}${langPrefix}/s/mk-${makeSlug}`;
      }
    } else {
      const langSegment = lang ? `/${lang}` : "";
      if (modelSlug) {
        base = `https://www.autoscout24.${tld}${langSegment}/lst/${makeSlug}/${modelSlug}`;
      } else {
        base = `https://www.autoscout24.${tld}${langSegment}/lst/${makeSlug}`;
      }
    }
    const params = new URLSearchParams({
      fregfrom: String(year - yearSpread),
      fregto: String(year + yearSpread),
      sort: "standard",
      desc: "0",
      atype: "C",
      ustate: "N,U"
    });
    if (fuel) params.set("fuel", fuel);
    if (gear) params.set("gear", gear);
    if (powerfrom) {
      params.set("powerfrom", String(powerfrom));
      params.set("powertype", "ps");
    }
    if (powerto) {
      params.set("powerto", String(powerto));
      params.set("powertype", "ps");
    }
    if (kmfrom) params.set("kmfrom", String(kmfrom));
    if (kmto) params.set("kmto", String(kmto));
    if (zip) {
      params.set("zip", String(zip));
      params.set("zipr", String(radius || 50));
    }
    return `${base}?${params}`;
  }
  var brandMatchesAs24 = brandsMatch;
  function _extractJsonLdBrand(item) {
    return item?.brand?.name || item?.offers?.itemOffered?.brand?.name || item?.manufacturer || item?.offers?.itemOffered?.manufacturer || null;
  }
  function parseSearchPrices(html, targetMake = null) {
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
  function _parseSearchPricesRSC(html) {
    const results = [];
    const listingPattern = /"price"\s*:\s*(\d+).*?"mileage"\s*:\s*(\d+)/g;
    let match;
    while ((match = listingPattern.exec(html)) !== null) {
      const price = parseInt(match[1], 10);
      const mileage = parseInt(match[2], 10);
      if (price > 500 && price < 5e5) {
        results.push({ price, year: null, km: mileage, fuel: null });
      }
    }
    return _dedup(results);
  }
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
        if (targetMake) {
          const adBrand = vehicle.make;
          if (adBrand && !brandMatchesAs24(adBrand, targetMake)) {
            continue;
          }
        }
        if (price && price > 500 && price < 5e5) {
          results.push({
            price,
            year,
            km,
            fuel,
            gearbox: vehicle.transmission || null,
            horse_power: _parseHpFromVehicleDetails(listing.vehicleDetails),
            _uid: listing.id || null
          });
        }
      }
    } catch (_) {
    }
    return _dedup(results);
  }
  function _parseHpFromVehicleDetails(details) {
    if (!Array.isArray(details)) return null;
    const power = details.find((d) => d.ariaLabel === "Leistung" || d.iconName === "speedometer");
    if (!power?.data) return null;
    const m = power.data.match(/\((\d+)\s*PS\)/i);
    return m ? parseInt(m[1], 10) : null;
  }
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
          if (price && price > 500 && price < 5e5) {
            if (targetMake) {
              const adBrand = _extractJsonLdBrand(item);
              if (adBrand && !brandMatchesAs24(adBrand, targetMake)) {
                console.debug("[CoPilot] AS24 brand safety: rejet %s (cible: %s)", adBrand, targetMake);
                continue;
              }
            }
            results.push({ price, year, km, fuel, _uid: uid });
          }
        }
      } catch (_) {
      }
    }
    return _dedup(results);
  }
  function _extractOfferCatalogItems(data) {
    if (data?.["@type"] === "OfferCatalog" && Array.isArray(data.itemListElement)) {
      return data.itemListElement;
    }
    const offers = data?.mainEntity?.offers || data?.offers;
    if (offers?.["@type"] === "OfferCatalog" && Array.isArray(offers.itemListElement)) {
      return offers.itemListElement;
    }
    if (Array.isArray(data?.["@graph"])) {
      for (const node of data["@graph"]) {
        const items = _extractOfferCatalogItems(node);
        if (items.length > 0) return items;
      }
    }
    return [];
  }
  function _extractJsonLdPrice(item) {
    const price = item?.offers?.price ?? item?.price;
    if (typeof price === "number") return price;
    if (typeof price === "string") return parseInt(price, 10) || null;
    return null;
  }
  function _extractJsonLdMileage(item) {
    const car = item?.offers?.itemOffered || item;
    const odometer = car?.mileageFromOdometer;
    if (!odometer) return null;
    const val = odometer?.value ?? odometer;
    if (typeof val === "number") return val;
    if (typeof val === "string") return parseInt(val, 10) || null;
    return null;
  }
  function _extractJsonLdFuel(item) {
    const car = item?.offers?.itemOffered || item;
    const eng = car?.vehicleEngine;
    const engine = Array.isArray(eng) ? eng[0] : eng;
    return engine?.fuelType || null;
  }
  function _extractJsonLdYear(item) {
    const car = item?.offers?.itemOffered || item;
    const date = car?.vehicleModelDate || car?.productionDate;
    if (!date) return null;
    const y = parseInt(String(date).slice(0, 4), 10);
    return y > 1900 && y < 2100 ? y : null;
  }
  function _extractJsonLdUid(item) {
    const url = item?.url || item?.offers?.url;
    if (!url) return null;
    const m = url.match(/(\d{6,})(?:[/?#]|$)/);
    return m ? m[1] : url;
  }
  function _dedup(results) {
    const seen = /* @__PURE__ */ new Set();
    return results.filter((r) => {
      const key = r._uid || `${r.price}-${r.km}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).map(({ _uid, ...rest }) => rest);
  }

  // extension/extractors/autoscout24/normalize.js
  function _extractFuelToken(value, depth = 0) {
    if (depth > 5 || value == null) return null;
    if (typeof value === "string") {
      const v = value.trim();
      return v || null;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        const found = _extractFuelToken(item, depth + 1);
        if (found) return found;
      }
      return null;
    }
    if (typeof value === "object") {
      const priorityKeys = [
        "label",
        "name",
        "value",
        "type",
        "text",
        "displayValue",
        "fuelType",
        "fuel",
        "raw",
        "slug"
      ];
      for (const key of priorityKeys) {
        if (key in value) {
          const found = _extractFuelToken(value[key], depth + 1);
          if (found) return found;
        }
      }
      for (const v of Object.values(value)) {
        const found = _extractFuelToken(v, depth + 1);
        if (found) return found;
      }
    }
    return null;
  }
  function _yearFromDate(dateStr) {
    if (!dateStr) return null;
    const m = String(dateStr).match(/^(\d{4})/);
    return m ? m[1] : dateStr;
  }
  function _daysOnline(dateStr) {
    if (!dateStr) return null;
    const d = new Date(dateStr);
    if (Number.isNaN(d.getTime())) return null;
    return Math.max(Math.floor((Date.now() - d.getTime()) / 864e5), 0);
  }
  function _daysSinceRefresh(createdStr, modifiedStr) {
    if (!createdStr || !modifiedStr) return null;
    const modified = new Date(modifiedStr);
    if (Number.isNaN(modified.getTime())) return null;
    return Math.max(Math.floor((Date.now() - modified.getTime()) / 864e5), 0);
  }
  function _isRepublished(createdStr, modifiedStr) {
    if (!createdStr || !modifiedStr) return false;
    const created = new Date(createdStr);
    const modified = new Date(modifiedStr);
    if (Number.isNaN(created.getTime()) || Number.isNaN(modified.getTime())) return false;
    return Math.abs(modified.getTime() - created.getTime()) > 864e5;
  }
  function normalizeToAdData(rsc, jsonLd) {
    const ld = jsonLd || {};
    const offers = ld.offers || {};
    const seller = offers.seller || offers.offeredBy || {};
    const sellerAddress = seller.address || {};
    const rawEngine = ld.vehicleEngine || {};
    const engine = Array.isArray(rawEngine) ? rawEngine[0] || {} : rawEngine;
    function resolveOwnerType() {
      if (rsc && rsc.sellerId) return "pro";
      if (seller["@type"] === "AutoDealer") return "pro";
      return "private";
    }
    function resolveMake() {
      if (rsc) {
        const m = typeof rsc.make === "string" ? rsc.make : rsc.make?.name;
        if (m) return m;
      }
      return ld.brand?.name || (typeof ld.brand === "string" ? ld.brand : null) || ld.manufacturer || null;
    }
    function resolveModel() {
      if (rsc) {
        const m = typeof rsc.model === "string" ? rsc.model : rsc.model?.name;
        if (m) return m;
      }
      return ld.model || null;
    }
    function resolveDescription() {
      if (rsc) {
        const full = typeof rsc.description === "string" ? rsc.description.trim() : "";
        if (full) return full;
        const short = typeof rsc.teaser === "string" ? rsc.teaser.trim() : "";
        if (short) return short;
      }
      const ldDesc = typeof ld.description === "string" ? ld.description.trim() : "";
      if (ldDesc) return ldDesc;
      return null;
    }
    function resolveFuel() {
      const rscCandidates = [
        rsc?.fuelType,
        rsc?.fuel,
        rsc?.fuel?.type,
        rsc?.fuel?.name,
        rsc?.fuelCategory,
        rsc?.energySource,
        rsc?.vehicleFuelType
      ];
      for (const candidate of rscCandidates) {
        const token = _extractFuelToken(candidate);
        if (token) {
          return mapFuelType(token);
        }
      }
      const ldFuel = _extractFuelToken(engine.fuelType) || _extractFuelToken(ld.fuelType) || null;
      return ldFuel ? mapFuelType(ldFuel) : null;
    }
    const rating = seller.aggregateRating || {};
    const dealerRating = rating.ratingValue ?? null;
    const dealerReviewCount = rating.reviewCount ?? null;
    const zipcode = sellerAddress.postalCode || null;
    const tld = typeof window !== "undefined" ? extractTld(window.location.href) : null;
    const countryCode = tld ? TLD_TO_COUNTRY_CODE[tld] || null : null;
    const derivedRegion = tld === "ch" && zipcode ? getCantonFromZip(zipcode) : tld ? TLD_TO_COUNTRY[tld] || null : null;
    const resolvedCurrency = offers.priceCurrency || (tld ? TLD_TO_CURRENCY[tld] || null : null) || null;
    if (rsc) {
      return {
        title: rsc.versionFullName || ld.name || null,
        price_eur: rsc.price ?? offers.price ?? null,
        currency: resolvedCurrency,
        make: resolveMake(),
        model: resolveModel(),
        year_model: rsc.firstRegistrationYear || ld.vehicleModelDate || _yearFromDate(ld.productionDate) || null,
        mileage_km: rsc.mileage ?? ld.mileageFromOdometer?.value ?? null,
        fuel: resolveFuel(),
        gearbox: rsc.transmissionType ? mapTransmission(rsc.transmissionType) : ld.vehicleTransmission || null,
        doors: rsc.doors ?? ld.numberOfDoors ?? null,
        seats: rsc.seats ?? ld.vehicleSeatingCapacity ?? ld.seatingCapacity ?? null,
        first_registration: rsc.firstRegistrationDate || ld.productionDate || null,
        color: rsc.bodyColor || ld.color || null,
        power_fiscal_cv: null,
        power_din_hp: rsc.horsePower ?? (Array.isArray(engine.enginePower) ? engine.enginePower[0]?.value : engine.enginePower?.value) ?? null,
        country: countryCode,
        location: {
          city: sellerAddress.addressLocality || null,
          zipcode,
          department: null,
          region: derivedRegion,
          lat: null,
          lng: null
        },
        phone: seller.telephone || null,
        description: resolveDescription(),
        owner_type: resolveOwnerType(),
        owner_name: seller.name || null,
        siret: null,
        dealer_rating: dealerRating,
        dealer_review_count: dealerReviewCount,
        raw_attributes: {},
        image_count: Array.isArray(rsc.images) && rsc.images.length > 0 ? rsc.images.length : Array.isArray(ld.image) ? ld.image.length : 0,
        has_phone: Boolean(seller.telephone),
        has_urgent: false,
        has_highlight: false,
        has_boost: false,
        publication_date: rsc.createdDate || null,
        days_online: _daysOnline(rsc.createdDate),
        index_date: rsc.lastModifiedDate || null,
        days_since_refresh: _daysSinceRefresh(rsc.createdDate, rsc.lastModifiedDate),
        republished: _isRepublished(rsc.createdDate, rsc.lastModifiedDate),
        lbc_estimation: null
      };
    }
    return {
      title: ld.name || null,
      price_eur: offers.price ?? null,
      currency: resolvedCurrency,
      make: ld.brand?.name || ld.manufacturer || null,
      model: ld.model || null,
      year_model: ld.vehicleModelDate || _yearFromDate(ld.productionDate) || null,
      mileage_km: ld.mileageFromOdometer?.value ?? null,
      fuel: _extractFuelToken(engine.fuelType) || _extractFuelToken(ld.fuelType) ? mapFuelType(_extractFuelToken(engine.fuelType) || _extractFuelToken(ld.fuelType)) : null,
      gearbox: ld.vehicleTransmission || null,
      doors: ld.numberOfDoors ?? null,
      seats: ld.vehicleSeatingCapacity ?? ld.seatingCapacity ?? null,
      first_registration: ld.productionDate || null,
      color: ld.color || null,
      power_fiscal_cv: null,
      power_din_hp: (Array.isArray(engine.enginePower) ? engine.enginePower[0]?.value : engine.enginePower?.value) ?? null,
      country: countryCode,
      location: {
        city: sellerAddress.addressLocality || null,
        zipcode,
        department: null,
        region: derivedRegion,
        lat: null,
        lng: null
      },
      phone: seller.telephone || null,
      description: typeof ld.description === "string" && ld.description.trim() || null,
      owner_type: resolveOwnerType(),
      owner_name: seller.name || null,
      siret: null,
      dealer_rating: dealerRating,
      dealer_review_count: dealerReviewCount,
      raw_attributes: {},
      image_count: Array.isArray(ld.image) ? ld.image.length : 0,
      has_phone: Boolean(seller.telephone),
      has_urgent: false,
      has_highlight: false,
      has_boost: false,
      publication_date: null,
      days_online: null,
      index_date: null,
      days_since_refresh: null,
      republished: false,
      lbc_estimation: null
    };
  }
  function buildBonusSignals(rsc, jsonLd) {
    const signals = [];
    if (!rsc) return signals;
    if (typeof rsc.hadAccident === "boolean") {
      signals.push({
        label: "Accident",
        value: rsc.hadAccident ? "Oui" : "Non",
        status: rsc.hadAccident ? "fail" : "pass"
      });
    }
    if (typeof rsc.inspected === "boolean") {
      signals.push({
        label: "CT",
        value: rsc.inspected ? "Passe" : "Non communique",
        status: rsc.inspected ? "pass" : "warning"
      });
    }
    if (rsc.warranty && rsc.warranty.duration) {
      signals.push({
        label: "Garantie",
        value: `${rsc.warranty.duration} mois / ${rsc.warranty.mileage || "?"} km`,
        status: "pass"
      });
    }
    if (rsc.listPrice && rsc.price) {
      signals.push({
        label: "Prix catalogue",
        value: `${rsc.listPrice} EUR`,
        status: "info"
      });
      const decote = Math.round((1 - rsc.price / rsc.listPrice) * 100);
      signals.push({
        label: "Decote",
        value: `${decote}%`,
        status: "info"
      });
    }
    const ld = jsonLd || {};
    const seller = ld.offers?.seller || ld.offers?.offeredBy || {};
    const rating = seller.aggregateRating;
    if (rating && rating.ratingValue) {
      signals.push({
        label: "Note Google",
        value: `${rating.ratingValue}/5 (${rating.reviewCount} avis)`,
        status: "info"
      });
    }
    if (rsc.directImport === true) {
      signals.push({
        label: "Import",
        value: "Import direct",
        status: "warning"
      });
    }
    return signals;
  }

  // extension/extractors/autoscout24/parser.js
  function* extractJsonObjects(text) {
    let i = 0;
    while (i < text.length) {
      if (text[i] !== "{") {
        i++;
        continue;
      }
      let depth = 0;
      let inString = false;
      let escape = false;
      const start = i;
      for (let j = i; j < text.length; j++) {
        const ch = text[j];
        if (escape) {
          escape = false;
          continue;
        }
        if (ch === "\\" && inString) {
          escape = true;
          continue;
        }
        if (ch === '"') {
          inString = !inString;
          continue;
        }
        if (inString) continue;
        if (ch === "{") depth++;
        else if (ch === "}") {
          depth--;
          if (depth === 0) {
            yield text.slice(start, j + 1);
            i = j + 1;
            break;
          }
        }
        if (j === text.length - 1) i = j + 1;
      }
      if (depth !== 0) break;
    }
  }
  function findVehicleNode(input, depth = 0) {
    if (!input || depth > 12) return null;
    if (Array.isArray(input)) {
      for (const item of input) {
        const found = findVehicleNode(item, depth + 1);
        if (found) return found;
      }
      return null;
    }
    if (typeof input !== "object") return null;
    const obj = input;
    const hasMake = !!(typeof obj.make === "string" || obj.make?.name);
    const hasModel = !!(typeof obj.model === "string" || obj.model?.name);
    const isRealVehicle = typeof obj.vehicleCategory === "string" || typeof obj.price === "number" || typeof obj.firstRegistrationDate === "string" || typeof obj.mileage === "number";
    if (hasMake && hasModel && isRealVehicle) return obj;
    for (const value of Object.values(obj)) {
      const found = findVehicleNode(value, depth + 1);
      if (found) return found;
    }
    return null;
  }
  function _findListingDates(input, depth = 0) {
    if (!input || depth > 12) return null;
    if (Array.isArray(input)) {
      for (const item of input) {
        const found = _findListingDates(item, depth + 1);
        if (found) return found;
      }
      return null;
    }
    if (typeof input !== "object") return null;
    if (typeof input.createdDate === "string" && input.createdDate.includes("T")) {
      return {
        createdDate: input.createdDate,
        lastModifiedDate: typeof input.lastModifiedDate === "string" ? input.lastModifiedDate : null
      };
    }
    for (const value of Object.values(input)) {
      const found = _findListingDates(value, depth + 1);
      if (found) return found;
    }
    return null;
  }
  function parseLooselyJsonLd(text) {
    const cleaned = String(text || "").trim().replace(/^<!--\s*/, "").replace(/\s*-->$/, "").trim();
    if (!cleaned) return null;
    try {
      return JSON.parse(cleaned);
    } catch {
      return null;
    }
  }
  function isVehicleLikeLdNode(node) {
    if (!node || typeof node !== "object") return false;
    const type = String(node["@type"] || "").toLowerCase();
    if (type === "car") return true;
    const hasMake = !!(node.brand?.name || node.brand);
    const hasModel = !!node.model;
    if (type === "vehicle") return hasMake && hasModel;
    const hasSignals = !!(node.offers || node.vehicleModelDate || node.mileageFromOdometer || node.vehicleEngine);
    return hasMake && hasModel && hasSignals;
  }
  function findVehicleLikeLdNode(input, depth = 0) {
    if (!input || depth > 12) return null;
    if (Array.isArray(input)) {
      for (const item of input) {
        const found = findVehicleLikeLdNode(item, depth + 1);
        if (found) return found;
      }
      return null;
    }
    if (typeof input !== "object") return null;
    if (isVehicleLikeLdNode(input)) return input;
    const itemOffered = input.offers?.itemOffered;
    if (itemOffered && isVehicleLikeLdNode(itemOffered)) {
      return {
        ...itemOffered,
        offers: input.offers,
        brand: itemOffered.brand || input.brand,
        name: itemOffered.name || input.name,
        image: itemOffered.image || input.image,
        description: itemOffered.description || input.description
      };
    }
    if (Array.isArray(input["@graph"])) {
      for (const item of input["@graph"]) {
        const found = findVehicleLikeLdNode(item, depth + 1);
        if (found) return found;
      }
    }
    for (const value of Object.values(input)) {
      const found = findVehicleLikeLdNode(value, depth + 1);
      if (found) return found;
    }
    return null;
  }
  function extractMakeModelFromUrl(url) {
    try {
      const u = new URL(url);
      const match = u.pathname.match(
        /\/(?:d|angebote|offerte|ofertas|aanbod|offres|annunci|anuncios|oferta|erbjudanden)\/([a-z0-9][\w-]*?)[-–](?:\d+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9]{6,})(?:[/?#]|$)/i
      );
      if (!match) return { make: null, model: null };
      const slug = decodeURIComponent(match[1] || "");
      const tokens = slug.split("-").filter(Boolean);
      if (!tokens.length) return { make: null, model: null };
      return {
        make: tokens[0] ? tokens[0].toUpperCase() : null,
        model: tokens[1] ? tokens[1].toUpperCase() : null
      };
    } catch {
      return { make: null, model: null };
    }
  }
  function _extractImageCountFromNextData(doc) {
    const el = doc.getElementById("__NEXT_DATA__");
    if (!el) return 0;
    try {
      const data = JSON.parse(el.textContent);
      const images = data?.props?.pageProps?.listingDetails?.images;
      return Array.isArray(images) ? images.length : 0;
    } catch (_) {
      return 0;
    }
  }
  function _extractDatesFromDom(doc) {
    const scripts = doc.querySelectorAll("script");
    for (const script of scripts) {
      const text = script.textContent || "";
      if (!text.includes("createdDate")) continue;
      const searchText = text.includes("self.__next_f") ? text.replace(/\\+"/g, '"') : text;
      const createdMatch = searchText.match(/"createdDate"\s*:\s*"([^"]+T[^"]+)"/);
      if (createdMatch) {
        const modifiedMatch = searchText.match(/"lastModifiedDate"\s*:\s*"([^"]+T[^"]+)"/);
        return {
          createdDate: createdMatch[1],
          lastModifiedDate: modifiedMatch ? modifiedMatch[1] : null
        };
      }
    }
    const nextDataEl = doc.getElementById("__NEXT_DATA__");
    if (nextDataEl) {
      try {
        const nd = JSON.parse(nextDataEl.textContent);
        const ts = nd?.props?.pageProps?.listingDetails?.createdTimestampWithOffset;
        if (ts) return { createdDate: ts, lastModifiedDate: null };
      } catch (_) {
      }
    }
    return { createdDate: null, lastModifiedDate: null };
  }
  function _normalizeText(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
  }
  function _extractFuelFromDom(doc) {
    const scripts = doc.querySelectorAll("script");
    for (const script of scripts) {
      const text = script.textContent || "";
      if (!text.includes("fuelType") && !text.includes("Kraftstoff") && !text.includes("Carburant")) continue;
      const fuelTypeMatch = text.match(/"fuelType"\s*:\s*"([^"]{2,40})"/i);
      if (fuelTypeMatch && fuelTypeMatch[1]) return _normalizeText(fuelTypeMatch[1]);
    }
    const fullText = _normalizeText(doc.body?.textContent || "");
    if (!fullText) return null;
    const re = /(?:carburant|kraftstoff|paliwo|combustible|carburante|brandstof|fuel)\s*[:\-]?\s*([A-Za-zÀ-ÿ0-9\- ]{2,48})/i;
    const m = fullText.match(re);
    if (!m || !m[1]) return null;
    const cleaned = _normalizeText(m[1]).replace(/[;,|].*$/, "").split(/\s{2,}/)[0].trim();
    if (!cleaned) return null;
    return cleaned.split(" ").slice(0, 3).join(" ").trim();
  }
  function _extractColorFromDom(doc) {
    const candidates = Array.from(doc.querySelectorAll("li, dt, dd, div, span"));
    const labelRe = /(couleur originale|couleur|farbe|lackierung|color|colore)/i;
    for (const node of candidates) {
      const txt = _normalizeText(node.textContent);
      if (!txt || txt.length < 6 || txt.length > 200) continue;
      if (!labelRe.test(txt)) continue;
      const inline = txt.match(/(?:couleur originale|couleur|farbe|lackierung|color|colore)\s*[:\-]?\s*(.{2,120})$/i);
      if (inline?.[1]) {
        const c = _normalizeText(inline[1]).replace(/[;,|].*$/, "").trim();
        if (c && c.length >= 2) return c;
      }
      const parent = node.closest("li, dl, div, section, article") || node.parentElement;
      if (parent) {
        const ptxt = _normalizeText(parent.textContent || "");
        const m2 = ptxt.match(/(?:couleur originale|couleur|farbe|lackierung|color|colore)\b\s*[:\-]?\s*(.{2,120})/i);
        if (m2?.[1]) {
          const c = _normalizeText(m2[1]).replace(/[;,|].*$/, "").trim();
          if (c && c.length >= 2) return c;
        }
      }
    }
    const fullText = _normalizeText(doc.body?.textContent || "");
    if (!fullText) return null;
    const m = fullText.match(/(?:couleur originale|couleur|farbe|lackierung|color|colore)\b\s*[:\-]?\s*([A-Za-zÀ-ÿ0-9+\- ]{2,80})/i);
    if (!m?.[1]) return null;
    const color = _normalizeText(m[1]).replace(/[;,|].*$/, "").trim();
    return color || null;
  }
  function _extractDescriptionFromDom(doc) {
    const directSelectors = [
      '[data-cy*="description"]',
      '[data-testid*="description"]',
      "#description",
      '[class*="description"]'
    ];
    for (const sel of directSelectors) {
      const nodes = doc.querySelectorAll(sel);
      for (const node of nodes) {
        const txt = _normalizeText(node.textContent);
        if (txt.length >= 50) return txt.slice(0, 2e3);
      }
    }
    const equipmentHeadingRe = /(équipement|equipement|ausstattung|equipment|dotazione|equipaggiamento|opzioni|options?)/i;
    const headings = doc.querySelectorAll("h1,h2,h3,h4,strong,span,div");
    for (const h of headings) {
      const title = _normalizeText(h.textContent);
      if (!title || title.length > 60 || !equipmentHeadingRe.test(title)) continue;
      const container = h.closest("section,article,div") || h.parentElement;
      if (!container) continue;
      const lis = Array.from(container.querySelectorAll("li")).map((li) => _normalizeText(li.textContent)).filter((t) => t.length >= 3 && t.length <= 180);
      const uniq = [...new Set(lis)];
      if (uniq.length >= 3) {
        return uniq.join(" \u2022 ").slice(0, 2e3);
      }
    }
    const ogDesc = _normalizeText(doc.querySelector('meta[property="og:description"]')?.getAttribute("content"));
    if (ogDesc.length >= 50) return ogDesc.slice(0, 2e3);
    const metaDesc = _normalizeText(doc.querySelector('meta[name="description"]')?.getAttribute("content"));
    if (metaDesc.length >= 50) return metaDesc.slice(0, 2e3);
    return null;
  }
  function fallbackAdDataFromDom(doc, url) {
    const h1 = doc.querySelector("h1")?.textContent?.trim() || null;
    const title = h1 || doc.querySelector('meta[property="og:title"]')?.getAttribute("content") || doc.title || null;
    const priceMeta = doc.querySelector('meta[property="product:price:amount"]')?.getAttribute("content");
    const price = priceMeta ? Number(String(priceMeta).replace(/[^\d.]/g, "")) : null;
    const currency = doc.querySelector('meta[property="product:price:currency"]')?.getAttribute("content") || null;
    const fromUrl = extractMakeModelFromUrl(url);
    const domDates = _extractDatesFromDom(doc);
    return {
      title,
      price_eur: Number.isFinite(price) ? price : null,
      currency,
      make: fromUrl.make,
      model: fromUrl.model,
      year_model: null,
      mileage_km: null,
      fuel: null,
      gearbox: null,
      doors: null,
      seats: null,
      first_registration: null,
      color: _extractColorFromDom(doc),
      power_fiscal_cv: null,
      power_din_hp: null,
      location: {
        city: null,
        zipcode: null,
        department: null,
        region: null,
        lat: null,
        lng: null
      },
      phone: null,
      description: _extractDescriptionFromDom(doc),
      owner_type: "private",
      owner_name: null,
      siret: null,
      raw_attributes: {},
      image_count: 0,
      has_phone: false,
      has_urgent: false,
      has_highlight: false,
      has_boost: false,
      publication_date: domDates.createdDate || null,
      days_online: _daysOnline(domDates.createdDate),
      index_date: domDates.lastModifiedDate || null,
      days_since_refresh: _daysSinceRefresh(domDates.createdDate, domDates.lastModifiedDate),
      republished: _isRepublished(domDates.createdDate, domDates.lastModifiedDate),
      lbc_estimation: null
    };
  }
  function _scoreVehicleAgainstUrl(vehicle, urlSlug, expectedMake = null) {
    if (!vehicle || !urlSlug) return 0;
    const make = typeof vehicle.make === "string" ? vehicle.make : vehicle.make?.name;
    const model = typeof vehicle.model === "string" ? vehicle.model : vehicle.model?.name;
    const makeSlug = toAs24Slug(make || "");
    const modelSlug = toAs24Slug(model || "");
    let score = 0;
    if (makeSlug && urlSlug.startsWith(makeSlug)) score += 2;
    if (expectedMake) {
      const expMake = toAs24Slug(expectedMake);
      if (expMake && makeSlug === expMake) score += 1;
    }
    if (modelSlug) {
      if (urlSlug.includes(modelSlug)) {
        score += 4;
      } else {
        const tokenHit = modelSlug.split("-").filter((t) => t.length >= 3).some((t) => urlSlug.includes(t));
        if (tokenHit) score += 2;
      }
    }
    return score;
  }
  function parseRSCPayload(doc, currentUrl = null) {
    const scripts = doc.querySelectorAll("script");
    let lastFound = null;
    const candidates = [];
    let urlSlug = "";
    let expectedMake = null;
    const sourceUrl = currentUrl || (typeof window !== "undefined" ? window.location?.href : null);
    if (sourceUrl) {
      const slugMatch = String(sourceUrl).match(
        /\/(?:d|angebote|offerte|ofertas|aanbod|offres|annunci|anuncios|oferta|erbjudanden)\/([a-z0-9][\w-]*?)[-–](?:\d+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9]{6,})(?:[/?#]|$)/i
      );
      urlSlug = slugMatch ? decodeURIComponent(slugMatch[1]).toLowerCase() : "";
      expectedMake = extractMakeModelFromUrl(String(sourceUrl)).make;
    }
    let order = 0;
    for (const script of scripts) {
      const text = script.textContent || "";
      if (!text.includes("vehicleCategory") && !text.includes("firstRegistrationDate")) {
        continue;
      }
      const candidateSources = [];
      if (text.includes("self.__next_f")) {
        const sentinel = "__AS24_ESCAPED_QUOTE__";
        const decoded = text.replace(/\\\\\\"/g, sentinel).replace(/\\\\"/g, '"').replaceAll(sentinel, '\\"');
        candidateSources.push(decoded);
        candidateSources.push(text.replace(/\\"/g, '"'));
      } else {
        candidateSources.push(text);
      }
      for (const source of candidateSources) {
        for (const candidate of extractJsonObjects(source)) {
          if (!candidate.includes('"vehicleCategory"') && !candidate.includes('"firstRegistrationDate"')) {
            continue;
          }
          try {
            const parsed = JSON.parse(candidate);
            const vehicle = findVehicleNode(parsed);
            if (vehicle) {
              if (!vehicle.createdDate) {
                const dates = _findListingDates(parsed);
                if (dates) {
                  vehicle.createdDate = dates.createdDate;
                  if (!vehicle.lastModifiedDate) {
                    vehicle.lastModifiedDate = dates.lastModifiedDate;
                  }
                }
              }
              lastFound = vehicle;
              candidates.push({ vehicle, order: order++ });
            }
          } catch {
          }
        }
      }
    }
    if (!candidates.length) return null;
    if (!urlSlug) return lastFound;
    let best = null;
    let bestScore = -1;
    for (const c of candidates) {
      const score = _scoreVehicleAgainstUrl(c.vehicle, urlSlug, expectedMake);
      if (score > bestScore || score === bestScore && (!best || c.order > best.order)) {
        best = c;
        bestScore = score;
      }
    }
    return best?.vehicle || lastFound;
  }
  function parseJsonLd(doc) {
    const scripts = doc.querySelectorAll('script[type="application/ld+json"]');
    for (const script of scripts) {
      const data = parseLooselyJsonLd(script.textContent || "");
      if (!data) continue;
      const vehicle = findVehicleLikeLdNode(data);
      if (vehicle) return vehicle;
    }
    return null;
  }
  function _findJsonLdByMake(doc, expectedMake, expectedModel = null, urlSlug = "") {
    const target = (expectedMake || "").toLowerCase();
    if (!target) return null;
    const scripts = doc.querySelectorAll('script[type="application/ld+json"]');
    let best = null;
    let bestScore = -1;
    let order = 0;
    for (const script of scripts) {
      const data = parseLooselyJsonLd(script.textContent || "");
      if (!data) continue;
      const vehicle = findVehicleLikeLdNode(data);
      if (!vehicle) continue;
      const brand = String(vehicle.brand?.name || vehicle.brand || "").toLowerCase();
      if (brand !== target) continue;
      const model = typeof vehicle.model === "string" ? vehicle.model : vehicle.model?.name;
      const modelSlug = toAs24Slug(model || "");
      const expectedModelSlug = toAs24Slug(expectedModel || "");
      let score = 2;
      if (expectedModelSlug && modelSlug && modelSlug === expectedModelSlug) {
        score += 3;
      }
      if (urlSlug && modelSlug && urlSlug.includes(modelSlug)) {
        score += 2;
      }
      const candidate = { vehicle, score, order: order++ };
      if (!best || candidate.score > bestScore || candidate.score === bestScore && candidate.order > best.order) {
        best = candidate;
        bestScore = candidate.score;
      }
    }
    return best?.vehicle || null;
  }

  // extension/extractors/autoscout24/extractor.js
  var AutoScout24Extractor = class extends SiteExtractor {
    static SITE_ID = "autoscout24";
    static URL_PATTERNS = AS24_URL_PATTERNS;
    /** @type {object|null} Cached RSC data */
    _rsc = null;
    /** @type {object|null} Cached JSON-LD data */
    _jsonLd = null;
    /** @type {object|null} Cached ad_data */
    _adData = null;
    isAdPage(url) {
      return AD_PAGE_PATTERN.test(url);
    }
    async extract() {
      this._rsc = parseRSCPayload(document, window.location.href);
      this._jsonLd = parseJsonLd(document);
      if (!this._rsc && !this._jsonLd) {
        this._adData = fallbackAdDataFromDom(document, window.location.href);
        const hasSomeData = Boolean(this._adData.title || this._adData.make || this._adData.model);
        if (!hasSomeData) return null;
        return {
          type: "normalized",
          source: "autoscout24",
          ad_data: this._adData
        };
      }
      this._adData = normalizeToAdData(this._rsc, this._jsonLd);
      const urlHint = extractMakeModelFromUrl(window.location.href);
      const urlSlugMatch = window.location.pathname.match(
        /\/(?:d|angebote|offerte|ofertas|aanbod|offres|annunci|anuncios|oferta|erbjudanden)\/([a-z0-9][\w-]*?)[-–](?:\d+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9]{6,})(?:[/?#]|$)/i
      );
      const urlSlug = urlSlugMatch ? urlSlugMatch[1].toLowerCase() : "";
      if (urlSlug && this._adData.make) {
        const makeSlug = toAs24Slug(this._adData.make);
        const modelSlug = toAs24Slug(this._adData.model || "");
        const hasModelMatch = modelSlug ? urlSlug.includes(modelSlug) || modelSlug.split("-").filter((t) => t.length >= 3).some((t) => urlSlug.includes(t)) : false;
        const vehicleInUrl = urlSlug.startsWith(makeSlug) && hasModelMatch;
        if (!vehicleInUrl) {
          console.warn(
            '[CoPilot] AS24 SPA stale data: extracted %s %s not in URL slug "%s"',
            this._adData.make,
            this._adData.model || "?",
            urlSlug
          );
          const freshLd = _findJsonLdByMake(document, urlHint.make, urlHint.model, urlSlug);
          if (freshLd) {
            console.log("[CoPilot] Found fresh JSON-LD for %s, using it", urlHint.make);
            this._rsc = null;
            this._jsonLd = freshLd;
            this._adData = normalizeToAdData(null, freshLd);
          } else {
            console.log("[CoPilot] No matching JSON-LD, falling back to DOM");
            this._rsc = null;
            this._jsonLd = null;
            this._adData = fallbackAdDataFromDom(document, window.location.href);
          }
        }
      }
      if (!this._adData.publication_date) {
        const domDates = _extractDatesFromDom(document);
        if (domDates.createdDate) {
          this._adData.publication_date = domDates.createdDate;
          this._adData.days_online = _daysOnline(domDates.createdDate);
          this._adData.index_date = domDates.lastModifiedDate || this._adData.index_date;
          this._adData.days_since_refresh = _daysSinceRefresh(domDates.createdDate, domDates.lastModifiedDate);
          this._adData.republished = _isRepublished(domDates.createdDate, domDates.lastModifiedDate);
        }
      }
      if (!this._adData.image_count) {
        const ndImageCount = _extractImageCountFromNextData(document);
        if (ndImageCount > 0) {
          this._adData.image_count = ndImageCount;
        }
      }
      if (!this._adData.description) {
        const domDesc = _extractDescriptionFromDom(document);
        if (domDesc) {
          this._adData.description = domDesc;
        }
      }
      if (!this._adData.fuel) {
        const domFuel = _extractFuelFromDom(document);
        if (domFuel) {
          this._adData.fuel = mapFuelType(domFuel);
        }
      }
      if (!this._adData.color) {
        const domColor = _extractColorFromDom(document);
        if (domColor) {
          this._adData.color = domColor;
        }
      }
      return {
        type: "normalized",
        source: "autoscout24",
        ad_data: this._adData
      };
    }
    getVehicleSummary() {
      if (!this._adData) return null;
      return {
        make: this._adData.make || "",
        model: this._adData.model || "",
        year: String(this._adData.year_model || "")
      };
    }
    isLoggedIn() {
      return true;
    }
    async revealPhone() {
      return this._adData?.phone || null;
    }
    hasPhone() {
      return Boolean(this._adData?.phone);
    }
    getBonusSignals() {
      return buildBonusSignals(this._rsc, this._jsonLd);
    }
    async collectMarketPrices(progress) {
      if (!this._adData?.make || !this._adData?.model || !this._adData?.year_model) {
        return { submitted: false, isCurrentVehicle: false };
      }
      if (!this._fetch || !this._apiUrl) {
        console.warn("[CoPilot] AS24 collectMarketPrices: deps not injected");
        return { submitted: false, isCurrentVehicle: false };
      }
      const tld = extractTld(window.location.href);
      const lang = extractLang(window.location.href);
      const countryName = TLD_TO_COUNTRY[tld] || "Europe";
      const countryCode = TLD_TO_COUNTRY_CODE[tld] || "FR";
      const currency = TLD_TO_CURRENCY[tld] || "EUR";
      const year = parseInt(this._adData.year_model, 10);
      const fuelKey = this._rsc?.fuelType || this._adData?.fuel || null;
      const hp = parseInt(this._adData.power_din_hp, 10) || 0;
      const km = parseInt(this._adData.mileage_km, 10) || 0;
      const gearRaw = this._rsc?.transmissionType || "";
      const gearCode = getAs24GearCode(gearRaw);
      const hpRangeStr = getHpRangeString(hp);
      const zipcode = this._adData?.location?.zipcode;
      const canton = tld === "ch" && zipcode ? getCantonFromZip(zipcode) : null;
      const region = canton || countryName;
      if (progress) progress.update("job", "running");
      const fuelForJob = this._adData.fuel ? this._adData.fuel.toLowerCase() : "";
      const gearboxForJob = this._adData.gearbox ? this._adData.gearbox.toLowerCase() : "";
      const slugMakeForJob = toAs24Slug(this._adData.make);
      const slugModelForJob = toAs24Slug(this._adData.model);
      const jobUrl = this._apiUrl.replace("/analyze", "/market-prices/next-job") + `?make=${encodeURIComponent(this._adData.make)}&model=${encodeURIComponent(this._adData.model)}&year=${encodeURIComponent(year)}&region=${encodeURIComponent(region)}&country=${encodeURIComponent(countryCode)}&site=as24&tld=${encodeURIComponent(tld)}&slug_make=${encodeURIComponent(slugMakeForJob)}&slug_model=${encodeURIComponent(slugModelForJob)}` + (fuelForJob ? `&fuel=${encodeURIComponent(fuelForJob)}` : "") + (gearboxForJob ? `&gearbox=${encodeURIComponent(gearboxForJob)}` : "") + (hpRangeStr ? `&hp_range=${encodeURIComponent(hpRangeStr)}` : "");
      let jobResp;
      try {
        console.log("[CoPilot] AS24 next-job \u2192", jobUrl);
        jobResp = await this._fetch(jobUrl).then((r) => r.json());
        console.log("[CoPilot] AS24 next-job \u2190", JSON.stringify(jobResp));
      } catch (err) {
        console.warn("[CoPilot] AS24 next-job error:", err);
        if (progress) {
          progress.update("job", "error", "Serveur injoignable");
          progress.update("collect", "skip");
          progress.update("submit", "skip");
          progress.update("bonus", "skip");
        }
        return { submitted: false, isCurrentVehicle: false };
      }
      if (!jobResp?.data?.collect) {
        const queuedJobs = jobResp?.data?.bonus_jobs || [];
        if (queuedJobs.length === 0) {
          if (progress) {
            progress.update("job", "done", "Donn\xE9es d\xE9j\xE0 \xE0 jour");
            progress.update("collect", "skip", "Non n\xE9cessaire");
            progress.update("submit", "skip");
            progress.update("bonus", "skip");
          }
          return { submitted: false, isCurrentVehicle: false };
        }
        if (progress) {
          progress.update("job", "done", `\xC0 jour \u2014 ${queuedJobs.length} jobs en attente`);
          progress.update("collect", "skip", "V\xE9hicule d\xE9j\xE0 \xE0 jour");
          progress.update("submit", "skip");
        }
        await this._executeBonusJobs(queuedJobs, tld, progress, lang);
        return { submitted: false, isCurrentVehicle: false };
      }
      const target = jobResp.data.vehicle;
      const targetRegion = jobResp.data.region;
      const isRedirect = !!jobResp.data.redirect;
      const bonusJobs = jobResp.data.bonus_jobs || [];
      const isCurrentVehicle = target.make.toLowerCase() === this._adData.make.toLowerCase() && target.model.toLowerCase() === this._adData.model.toLowerCase();
      if (!isCurrentVehicle) {
        if (shouldSkipCollection()) {
          if (progress) {
            progress.update("job", "done", "Cooldown actif (autre v\xE9hicule collect\xE9 r\xE9cemment)");
            progress.update("collect", "skip", "Cooldown 24h");
            progress.update("submit", "skip");
          }
          if (bonusJobs.length > 0) {
            await this._executeBonusJobs(bonusJobs, tld, progress, lang);
          } else if (progress) {
            progress.update("bonus", "skip");
          }
          return { submitted: false, isCurrentVehicle: false };
        }
      }
      const targetMakeKey = target.as24_slug_make || toAs24Slug(target.make);
      const targetModelKey = target.as24_slug_model || toAs24Slug(target.model);
      const targetYear = parseInt(target.year, 10);
      const targetLabel = `${target.make} ${target.model} ${targetYear}`;
      if (progress) {
        progress.update("job", "done", targetLabel + (isCurrentVehicle ? ` (${targetRegion})` : " (autre v\xE9hicule)"));
      }
      const fuelCode = fuelKey ? getAs24FuelCode(fuelKey) : null;
      const targetCantonZip = getCantonCenterZip(targetRegion);
      const strategies = [];
      function _filtersApplied(opts) {
        const f = [];
        if (opts.fuel) f.push("fuel");
        if (opts.gear) f.push("gearbox");
        if (opts.powerfrom || opts.powerto) f.push("hp");
        if (opts.kmfrom || opts.kmto) f.push("km");
        return f;
      }
      if (isCurrentVehicle) {
        const powerParams = getAs24PowerParams(hp);
        const kmParams = getAs24KmParams(km);
        if (zipcode) {
          const opts = { yearSpread: 1, fuel: fuelCode, gear: gearCode, ...powerParams, ...kmParams, zip: zipcode, radius: 30 };
          strategies.push({ ...opts, precision: 5, label: `ZIP ${zipcode} +30km`, location_type: "zip", filters_applied: _filtersApplied(opts) });
        }
        if (targetCantonZip) {
          const opts1 = { yearSpread: 1, fuel: fuelCode, gear: gearCode, ...powerParams, ...kmParams, zip: targetCantonZip, radius: 50 };
          strategies.push({ ...opts1, precision: 4, label: `${targetRegion} \xB11an`, location_type: "canton", filters_applied: _filtersApplied(opts1) });
          const opts2 = { yearSpread: 2, fuel: fuelCode, gear: gearCode, ...powerParams, zip: targetCantonZip, radius: 50 };
          strategies.push({ ...opts2, precision: 4, label: `${targetRegion} \xB12ans`, location_type: "canton", filters_applied: _filtersApplied(opts2) });
        }
        const opts3 = { yearSpread: 1, fuel: fuelCode, gear: gearCode, ...powerParams };
        strategies.push({ ...opts3, precision: 3, label: "National \xB11an", location_type: "national", filters_applied: _filtersApplied(opts3) });
        const opts4 = { yearSpread: 2, fuel: fuelCode, gear: gearCode };
        strategies.push({ ...opts4, precision: 3, label: "National \xB12ans", location_type: "national", filters_applied: _filtersApplied(opts4) });
        const opts5 = { yearSpread: 2, fuel: fuelCode };
        strategies.push({ ...opts5, precision: 2, label: "National fuel", location_type: "national", filters_applied: _filtersApplied(opts5) });
        strategies.push({ yearSpread: 3, precision: 1, label: "National large", location_type: "national", filters_applied: [] });
        strategies.push({ yearSpread: 2, fuel: fuelCode, brandOnly: true, precision: 0, label: "Marque seule + fuel", location_type: "national", filters_applied: fuelCode ? ["fuel"] : [] });
      } else {
        if (targetCantonZip) {
          strategies.push({
            yearSpread: 1,
            zip: targetCantonZip,
            radius: 50,
            precision: 3,
            label: `${targetRegion} \xB11an`,
            location_type: "canton",
            filters_applied: []
          });
        }
        strategies.push({ yearSpread: 1, precision: 2, label: "National \xB11an", location_type: "national", filters_applied: [] });
        strategies.push({ yearSpread: 2, precision: 1, label: "National \xB12ans", location_type: "national", filters_applied: [] });
        strategies.push({ yearSpread: 2, brandOnly: true, precision: 0, label: "Marque seule", location_type: "national", filters_applied: [] });
      }
      let prices = [];
      let usedPrecision = null;
      const searchLog = [];
      let learnedSlugMake = null;
      let learnedSlugModel = null;
      let slugSource = null;
      function rememberSlugs(url, source) {
        const parsed = extractAs24SlugsFromSearchUrl(url, tld);
        if (parsed.makeSlug) learnedSlugMake = parsed.makeSlug;
        if (parsed.modelSlug) learnedSlugModel = parsed.modelSlug;
        if ((parsed.makeSlug || parsed.modelSlug) && source) slugSource = source;
      }
      if (progress) progress.update("collect", "running");
      const MAX_PRICES_CAP = 100;
      function _as24YearWindow(yearRef, spread = 1) {
        const y = Number.parseInt(yearRef, 10);
        const s = Number.parseInt(spread, 10) || 1;
        if (!Number.isFinite(y)) return { year_from: null, year_to: null, year_filter: null };
        return {
          year_from: y - s,
          year_to: y + s,
          year_filter: `fregfrom=${y - s}&fregto=${y + s}`
        };
      }
      function _urlVerdict(adsFound, uniqueAdded) {
        if ((adsFound || 0) <= 0) return "empty";
        if ((uniqueAdded || 0) <= 0) return "duplicates_only";
        return "useful";
      }
      function _criteriaSummary(opts, yearMeta) {
        const fuelVal = opts.fuel || "any";
        const gearVal = opts.gear || "any";
        const hpVal = opts.powerfrom || opts.powerto ? `${opts.powerfrom ?? "min"}-${opts.powerto ?? "max"}` : "any";
        const modelVal = opts.brandOnly ? `ALL (brandOnly)` : `${target.model} [mo-${targetModelKey}]`;
        const yearVal = yearMeta.year_from && yearMeta.year_to ? `${yearMeta.year_from}-${yearMeta.year_to}` : "?-?";
        return [
          `marque=${target.make} [mk-${targetMakeKey}]`,
          `model=${modelVal}`,
          `fuel=${fuelVal}`,
          `boite=${gearVal}`,
          `CV=${hpVal}`,
          `ann\xE9e=${yearVal}`
        ].join(" \xB7 ");
      }
      for (let i = 0; i < strategies.length; i++) {
        if (i > 0) await new Promise((r) => setTimeout(r, 600 + Math.random() * 400));
        const { precision, label, location_type, filters_applied, ...searchOpts } = strategies[i];
        const searchUrl = buildSearchUrl(targetMakeKey, targetModelKey, targetYear, tld, { ...searchOpts, lang });
        const yearMeta = _as24YearWindow(targetYear, searchOpts.yearSpread || 1);
        const criteriaSummary = _criteriaSummary(searchOpts, yearMeta);
        const logBase = {
          step: i + 1,
          precision,
          location_type,
          year_spread: searchOpts.yearSpread || 1,
          year_from: yearMeta.year_from,
          year_to: yearMeta.year_to,
          year_filter: yearMeta.year_filter,
          criteria_summary: criteriaSummary,
          filters_applied: filters_applied || []
        };
        rememberSlugs(searchUrl, "as24_generated_url");
        try {
          const resp = await fetch(searchUrl, { credentials: "same-origin" });
          if (!resp.ok) {
            searchLog.push({ ...logBase, ads_found: 0, url: searchUrl, was_selected: false, reason: `HTTP ${resp.status}` });
            if (progress) progress.addSubStep?.("collect", `Strat\xE9gie ${i + 1} \xB7 ${label}`, "skip", `HTTP ${resp.status}`);
            continue;
          }
          if (resp.url) rememberSlugs(resp.url, "as24_response_url");
          const html = await resp.text();
          const newPrices = parseSearchPrices(html, target.make);
          const seen = new Set(prices.map((p) => `${p.price}-${p.km}`));
          const unique = newPrices.filter((p) => !seen.has(`${p.price}-${p.km}`));
          prices = [...prices, ...unique];
          const enough = prices.length >= MIN_PRICES;
          console.log(
            "[CoPilot] AS24 strategie %d (precision=%d): %d nouveaux (%d uniques), total=%d | %s",
            i + 1,
            precision,
            newPrices.length,
            unique.length,
            prices.length,
            searchUrl.substring(0, 120)
          );
          searchLog.push({
            ...logBase,
            ads_found: newPrices.length,
            unique_added: unique.length,
            url_verdict: _urlVerdict(newPrices.length, unique.length),
            url: searchUrl,
            was_selected: enough && usedPrecision === null,
            reason: enough ? `total ${prices.length} >= ${MIN_PRICES}` : `total ${prices.length} < ${MIN_PRICES}`
          });
          if (progress) {
            progress.addSubStep?.(
              "collect",
              `Strat\xE9gie ${i + 1} \xB7 ${label}`,
              unique.length > 0 ? "done" : "skip",
              `${newPrices.length} annonces \xB7 ${criteriaSummary}`
            );
          }
          if (enough && usedPrecision === null) {
            usedPrecision = precision;
          }
          if (prices.length >= MAX_PRICES_CAP) {
            console.log("[CoPilot] AS24 cap %d atteint, arret", MAX_PRICES_CAP);
            break;
          }
        } catch (err) {
          console.error("[CoPilot] AS24 search error:", err);
          searchLog.push({ ...logBase, ads_found: 0, url: searchUrl, was_selected: false, reason: err.message });
          if (progress) progress.addSubStep?.("collect", `Strat\xE9gie ${i + 1} \xB7 ${label}`, "skip", "Erreur");
        }
      }
      let submitted = false;
      if (prices.length >= MIN_PRICES) {
        const priceInts = prices.map((p) => p.price);
        const priceDetails = prices;
        if (progress) {
          progress.update("collect", "done", `${priceInts.length} prix (pr\xE9cision ${usedPrecision})`);
          progress.update("submit", "running");
        }
        const marketUrl = this._apiUrl.replace("/analyze", "/market-prices");
        const payload = {
          make: target.make,
          model: target.model,
          year: targetYear,
          region: targetRegion,
          prices: priceInts,
          price_details: priceDetails,
          fuel: isCurrentVehicle && this._adData.fuel ? this._adData.fuel.toLowerCase() : null,
          precision: usedPrecision,
          country: countryCode,
          hp_range: isCurrentVehicle ? hpRangeStr : null,
          gearbox: isCurrentVehicle && this._adData.gearbox ? this._adData.gearbox.toLowerCase() : null,
          search_log: searchLog,
          as24_slug_make: learnedSlugMake || targetMakeKey,
          as24_slug_model: learnedSlugModel || (!searchLog.some((s) => (s.reason || "").startsWith("HTTP 404")) ? targetModelKey : null)
        };
        console.log("[CoPilot] AS24 submit payload:", JSON.stringify({
          make: payload.make,
          model: payload.model,
          year: payload.year,
          region: payload.region,
          precision: payload.precision,
          country: payload.country,
          fuel: payload.fuel,
          hp_range: payload.hp_range,
          gearbox: payload.gearbox,
          prices_count: payload.prices.length,
          prices_sample: payload.prices.slice(0, 3),
          price_details_sample: payload.price_details?.slice(0, 2),
          search_log_count: payload.search_log?.length,
          search_log_sample: payload.search_log?.slice(0, 2),
          as24_slug_make: payload.as24_slug_make,
          as24_slug_model: payload.as24_slug_model
        }));
        try {
          const resp = await this._fetch(marketUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          if (resp.ok) {
            if (progress) progress.update("submit", "done", `${priceInts.length} prix envoy\xE9s (${targetRegion})`);
            submitted = true;
          } else {
            const errBody = await resp.text().catch(() => "");
            console.error("[CoPilot] AS24 market-prices POST %d: %s", resp.status, errBody);
            const errMsg = (() => {
              try {
                return JSON.parse(errBody)?.message || `HTTP ${resp.status}`;
              } catch {
                return `HTTP ${resp.status}`;
              }
            })();
            if (progress) progress.update("submit", "error", errMsg);
          }
        } catch (err) {
          console.error("[CoPilot] AS24 market-prices POST error:", err);
          if (progress) progress.update("submit", "error", "Erreur r\xE9seau");
        }
      } else {
        if (progress) {
          progress.update("collect", "warning", `${prices.length} annonces (min ${MIN_PRICES})`);
          progress.update("submit", "skip", "Pas assez de donn\xE9es");
        }
        try {
          const failedUrl = this._apiUrl.replace("/analyze", "/market-prices/failed-search");
          await this._fetch(failedUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              make: target.make,
              model: target.model,
              year: targetYear,
              region: targetRegion,
              fuel: isCurrentVehicle ? fuelKey || null : null,
              hp_range: isCurrentVehicle ? hpRangeStr : null,
              country: countryCode,
              search_log: searchLog,
              site: "as24",
              tld,
              slug_make_used: learnedSlugMake || targetMakeKey,
              slug_model_used: learnedSlugModel || targetModelKey,
              slug_source: slugSource || "as24_generated_url",
              as24_slug_make: learnedSlugMake || null,
              as24_slug_model: learnedSlugModel || null
            })
          });
        } catch {
        }
      }
      if (bonusJobs.length > 0) {
        await this._executeBonusJobs(bonusJobs, tld, progress, lang);
      } else if (progress) {
        progress.update("bonus", "skip", "Pas de jobs bonus");
      }
      if (!isCurrentVehicle) {
        markCollected();
      }
      return { submitted, isCurrentVehicle };
    }
    async _executeBonusJobs(bonusJobs, tld, progress, lang = null) {
      const marketUrl = this._apiUrl.replace("/analyze", "/market-prices");
      const jobDoneUrl = this._apiUrl.replace("/analyze", "/market-prices/job-done");
      const currency = TLD_TO_CURRENCY[tld] || "EUR";
      const countryCode = TLD_TO_COUNTRY_CODE[tld] || "FR";
      const MIN_BONUS_PRICES = countryCode === "FR" ? 20 : MIN_PRICES;
      function _bonusFiltersApplied(opts) {
        const f = [];
        if (opts.fuel) f.push("fuel");
        if (opts.gear) f.push("gearbox");
        if (opts.powerfrom || opts.powerto) f.push("hp");
        return f;
      }
      function _as24YearWindow(yearRef, spread = 1) {
        const y = Number.parseInt(yearRef, 10);
        const s = Number.parseInt(spread, 10) || 1;
        if (!Number.isFinite(y)) return { year_from: null, year_to: null, year_filter: null };
        return {
          year_from: y - s,
          year_to: y + s,
          year_filter: `fregfrom=${y - s}&fregto=${y + s}`
        };
      }
      function _urlVerdict(adsFound, uniqueAdded) {
        if ((adsFound || 0) <= 0) return "empty";
        if ((uniqueAdded || 0) <= 0) return "duplicates_only";
        return "useful";
      }
      function _bonusCriteriaSummary(job, opts, yearMeta, jobMakeKey, jobModelKey) {
        const fuelVal = opts.fuel || "any";
        const gearVal = opts.gear || "any";
        const hpVal = opts.powerfrom || opts.powerto ? `${opts.powerfrom ?? "min"}-${opts.powerto ?? "max"}` : "any";
        const modelVal = opts.brandOnly ? "ALL (brandOnly)" : `${job.model} [mo-${jobModelKey}]`;
        const yearVal = yearMeta.year_from && yearMeta.year_to ? `${yearMeta.year_from}-${yearMeta.year_to}` : "?-?";
        return [
          `marque=${job.make} [mk-${jobMakeKey}]`,
          `model=${modelVal}`,
          `fuel=${fuelVal}`,
          `boite=${gearVal}`,
          `CV=${hpVal}`,
          `ann\xE9e=${yearVal}`
        ].join(" \xB7 ");
      }
      if (progress) progress.update("bonus", "running", `${bonusJobs.length} jobs`);
      for (const job of bonusJobs) {
        if ((job.country || "FR") !== countryCode) {
          console.log("[CoPilot] AS24 bonus skip: country %s != %s", job.country, countryCode);
          await this._reportJobDone(jobDoneUrl, job.job_id, false);
          if (progress) progress.addSubStep?.("bonus", `${job.make} ${job.model}`, "skip", "Pays diff\xE9rent");
          continue;
        }
        try {
          await new Promise((r) => setTimeout(r, 800 + Math.random() * 600));
          const jobMakeKey = job.slug_make || toAs24Slug(job.make);
          const jobModelKey = job.slug_model || toAs24Slug(job.model);
          const jobYear = parseInt(job.year, 10);
          if (!Number.isFinite(jobYear) || jobYear < 1990 || jobYear > 2030) {
            console.warn("[CoPilot] AS24 bonus skip invalid year for %s %s: %o", job.make, job.model, job.year);
            await this._reportJobDone(jobDoneUrl, job.job_id, false);
            if (progress) progress.addSubStep?.("bonus", `${job.make} ${job.model} \xB7 ${job.region}`, "skip", "Ann\xE9e invalide");
            continue;
          }
          const cantonZip = getCantonCenterZip(job.region);
          const strictSearchOpts = { yearSpread: 1 };
          if (job.fuel) {
            const fc = getAs24FuelCode(job.fuel);
            if (fc) strictSearchOpts.fuel = fc;
          }
          if (job.gearbox) {
            const gc = getAs24GearCode(job.gearbox);
            if (gc) strictSearchOpts.gear = gc;
          }
          if (job.hp_range) {
            const pp = parseHpRange(job.hp_range);
            Object.assign(strictSearchOpts, pp);
          }
          if (cantonZip) {
            strictSearchOpts.zip = cantonZip;
            strictSearchOpts.radius = 50;
          }
          const bonusStrategies = [];
          const seenBonusKeys = /* @__PURE__ */ new Set();
          const pushBonusStrategy = (label, opts, precision = 3) => {
            const strategyOpts = { ...opts };
            const key = JSON.stringify(strategyOpts);
            if (seenBonusKeys.has(key)) return;
            seenBonusKeys.add(key);
            bonusStrategies.push({ label, precision, opts: strategyOpts });
          };
          pushBonusStrategy("Strict local \xB11an", strictSearchOpts, 4);
          if (strictSearchOpts.powerfrom || strictSearchOpts.powerto) {
            const noHp = { ...strictSearchOpts };
            delete noHp.powerfrom;
            delete noHp.powerto;
            pushBonusStrategy("Sans HP \xB11an", noHp, 3);
          }
          if (strictSearchOpts.gear) {
            const noGear = { ...strictSearchOpts };
            delete noGear.gear;
            pushBonusStrategy("Sans boite \xB11an", noGear, 3);
          }
          if (strictSearchOpts.zip) {
            const national = { ...strictSearchOpts };
            delete national.zip;
            delete national.radius;
            pushBonusStrategy("National \xB11an", national, 2);
            const nationalWide = { ...national, yearSpread: 2 };
            pushBonusStrategy("National \xB12ans", nationalWide, 2);
          } else {
            pushBonusStrategy("National \xB12ans", { ...strictSearchOpts, yearSpread: 2 }, 2);
          }
          const fuelOnlyWide = { yearSpread: 2 };
          if (strictSearchOpts.fuel) fuelOnlyWide.fuel = strictSearchOpts.fuel;
          pushBonusStrategy("National fuel \xB12ans", fuelOnlyWide, 2);
          let selected = null;
          let selectedPrices = [];
          let selectedSearchUrl = null;
          let selectedLearned = { makeSlug: null, modelSlug: null };
          let bestAdsCount = 0;
          let httpFailure = null;
          const bonusSearchLog = [];
          for (let step = 0; step < bonusStrategies.length; step++) {
            if (step > 0) await new Promise((r) => setTimeout(r, 400 + Math.random() * 300));
            const strategy = bonusStrategies[step];
            const searchUrl = buildSearchUrl(jobMakeKey, jobModelKey, jobYear, tld, { ...strategy.opts, lang });
            const resp = await fetch(searchUrl, { credentials: "same-origin" });
            const learned = extractAs24SlugsFromSearchUrl(resp.url || searchUrl, tld);
            const yearMeta = _as24YearWindow(jobYear, strategy.opts.yearSpread || 1);
            const criteriaSummary = _bonusCriteriaSummary(job, strategy.opts, yearMeta, jobMakeKey, jobModelKey);
            if (!resp.ok) {
              httpFailure = httpFailure || resp.status;
              bonusSearchLog.push({
                step: step + 1,
                precision: strategy.precision,
                location_type: strategy.opts.zip ? "canton" : "national",
                year_spread: strategy.opts.yearSpread || 1,
                year_from: yearMeta.year_from,
                year_to: yearMeta.year_to,
                year_filter: yearMeta.year_filter,
                criteria_summary: criteriaSummary,
                filters_applied: _bonusFiltersApplied(strategy.opts),
                ads_found: 0,
                unique_added: 0,
                url_verdict: "empty",
                url: searchUrl,
                was_selected: false,
                reason: `HTTP ${resp.status}`
              });
              continue;
            }
            const html = await resp.text();
            const prices = parseSearchPrices(html, job.make);
            bestAdsCount = Math.max(bestAdsCount, prices.length);
            console.log(
              "[CoPilot] AS24 bonus %s %s %d %s [%s]: %d prix",
              job.make,
              job.model,
              jobYear,
              job.region,
              strategy.label,
              prices.length
            );
            bonusSearchLog.push({
              step: step + 1,
              precision: strategy.precision,
              location_type: strategy.opts.zip ? "canton" : "national",
              year_spread: strategy.opts.yearSpread || 1,
              year_from: yearMeta.year_from,
              year_to: yearMeta.year_to,
              year_filter: yearMeta.year_filter,
              criteria_summary: criteriaSummary,
              filters_applied: _bonusFiltersApplied(strategy.opts),
              ads_found: prices.length,
              unique_added: prices.length,
              url_verdict: _urlVerdict(prices.length, prices.length),
              url: searchUrl,
              was_selected: prices.length >= MIN_BONUS_PRICES,
              reason: prices.length >= MIN_BONUS_PRICES ? `total ${prices.length} >= ${MIN_BONUS_PRICES}` : `total ${prices.length} < ${MIN_BONUS_PRICES}`
            });
            if (prices.length >= MIN_BONUS_PRICES) {
              selected = strategy;
              selectedPrices = prices;
              selectedSearchUrl = searchUrl;
              selectedLearned = learned;
              break;
            }
          }
          if (selected && selectedPrices.length >= MIN_BONUS_PRICES) {
            const priceDetails = selectedPrices.filter((p) => Number.isInteger(p?.price) && p.price >= 500);
            const priceInts = priceDetails.map((p) => p.price);
            if (priceInts.length < MIN_BONUS_PRICES) {
              await this._reportJobDone(jobDoneUrl, job.job_id, false);
              if (progress) {
                progress.addSubStep?.(
                  "bonus",
                  `${job.make} ${job.model} \xB7 ${job.region}`,
                  "skip",
                  `${priceInts.length} prix valides (<${MIN_BONUS_PRICES})`
                );
              }
              continue;
            }
            const bonusPrecision = selected.precision;
            const bonusPayload = {
              make: String(job.make || "").trim(),
              model: String(job.model || "").trim(),
              year: jobYear,
              region: String(job.region || "").trim(),
              prices: priceInts,
              price_details: priceDetails,
              fuel: job.fuel || null,
              hp_range: job.hp_range || null,
              precision: bonusPrecision,
              country: countryCode,
              as24_slug_make: selectedLearned.makeSlug || jobMakeKey,
              as24_slug_model: selectedLearned.modelSlug || (selected.opts.brandOnly ? null : jobModelKey),
              search_log: bonusSearchLog
            };
            const postResp = await this._fetch(marketUrl, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(bonusPayload)
            });
            let errMsg = null;
            if (!postResp.ok) {
              const errBody = await postResp.text().catch(() => "");
              console.error("[CoPilot] AS24 bonus POST %d for %s %s: %s", postResp.status, job.make, job.model, errBody);
              try {
                errMsg = JSON.parse(errBody)?.message || null;
              } catch {
                errMsg = null;
              }
            }
            await this._reportJobDone(jobDoneUrl, job.job_id, postResp.ok);
            if (progress) {
              progress.addSubStep?.(
                "bonus",
                `${job.make} ${job.model} \xB7 ${job.region}`,
                postResp.ok ? "done" : "error",
                postResp.ok ? `${priceInts.length} prix (${selected.label}) \xB7 ${_bonusCriteriaSummary(job, selected.opts, _as24YearWindow(jobYear, selected.opts.yearSpread || 1), jobMakeKey, jobModelKey)}` : `${errMsg || `HTTP ${postResp.status}`}`
              );
            }
          } else {
            await this._reportJobDone(jobDoneUrl, job.job_id, false);
            if (progress) {
              progress.addSubStep?.(
                "bonus",
                `${job.make} ${job.model} \xB7 ${job.region}`,
                "skip",
                bestAdsCount > 0 ? `${bestAdsCount} annonces max (<${MIN_BONUS_PRICES})` : `${httpFailure ? `HTTP ${httpFailure}` : `0 annonce`} (<${MIN_BONUS_PRICES})`
              );
            }
          }
        } catch (err) {
          console.warn("[CoPilot] AS24 bonus job error:", err);
          await this._reportJobDone(jobDoneUrl, job.job_id, false);
          if (progress) progress.addSubStep?.("bonus", `${job.make} ${job.model} \xB7 ${job.region}`, "skip", "Erreur");
        }
      }
      if (progress) progress.update("bonus", "done");
    }
    async _reportJobDone(jobDoneUrl, jobId, success) {
      if (!jobId) return;
      try {
        await this._fetch(jobDoneUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: jobId, success, site: "as24" })
        });
      } catch {
      }
    }
  };

  // extension/extractors/index.js
  var EXTRACTORS = [LeBonCoinExtractor, AutoScout24Extractor];
  function getExtractor(url) {
    for (const ExtractorClass of EXTRACTORS) {
      for (const pattern of ExtractorClass.URL_PATTERNS) {
        if (pattern.test(url)) {
          return new ExtractorClass();
        }
      }
    }
    return null;
  }

  // extension/utils/format.js
  function escapeHTML(str) {
    if (typeof str !== "string") return String(str ?? "");
    const el = document.createElement("span");
    el.textContent = str;
    return el.innerHTML;
  }
  var DETAIL_LABELS = {
    fields_present: "Champs renseign\xE9s",
    fields_total: "Champs totaux",
    missing_critical: "Champs critiques manquants",
    missing_secondary: "Champs secondaires manquants",
    matched_model: "Mod\xE8le reconnu",
    confidence: "Confiance",
    km_per_year: "Km / an",
    expected_range: "Fourchette attendue",
    actual_km: "Kilom\xE9trage r\xE9el",
    expected_km: "Kilom\xE9trage attendu",
    price: "Prix annonce",
    argus_price: "Prix Argus",
    price_diff: "\xC9cart de prix",
    price_diff_pct: "\xC9cart (%)",
    mean_price: "Prix moyen",
    std_dev: "\xC9cart-type",
    z_score: "Z-score",
    phone_valid: "T\xE9l\xE9phone valide",
    phone: "T\xE9l\xE9phone",
    siret: "SIRET",
    siret_valid: "SIRET valide",
    company_name: "Raison sociale",
    is_import: "V\xE9hicule import\xE9",
    import_indicators: "Indicateurs import",
    color: "Couleur",
    phone_login_hint: "T\xE9l\xE9phone",
    days_online: "Premi\xE8re publication (jours)",
    republished: "Annonce republi\xE9e",
    stale_below_market: "Prix bas + annonce ancienne",
    delta_eur: "\xC9cart (\u20AC)",
    delta_pct: "\xC9cart (%)",
    price_annonce: "Prix annonce",
    price_reference: "Prix r\xE9f\xE9rence",
    sample_count: "Nb annonces compar\xE9es",
    source: "Source prix",
    price_argus_mid: "Argus (m\xE9dian)",
    price_argus_low: "Argus (bas)",
    price_argus_high: "Argus (haut)",
    precision: "Pr\xE9cision",
    lookup_make: "Lookup marque",
    lookup_model: "Lookup mod\xE8le",
    lookup_year: "Lookup ann\xE9e",
    lookup_region_key: "Lookup r\xE9gion (cl\xE9)",
    lookup_fuel_input: "Lookup \xE9nergie (brute)",
    lookup_fuel_key: "Lookup \xE9nergie (cl\xE9)",
    lookup_min_samples: "Seuil min annonces"
  };
  var PRECISION_LABELS = { 5: "Tres precis", 4: "Precis", 3: "Correct", 2: "Approximatif", 1: "Estimatif" };
  function formatPrecisionStars(n) {
    const filled = "\u2605".repeat(n);
    const empty = "\u2606".repeat(5 - n);
    const label = PRECISION_LABELS[n] || "";
    return `${filled}${empty} ${n}/5 \u2013 ${label}`;
  }
  function formatDetailValue(value) {
    if (Array.isArray(value)) {
      if (value.length === 0) return "Aucun";
      return value.map((v) => escapeHTML(v)).join(", ");
    }
    if (typeof value === "boolean") return value ? "Oui" : "Non";
    if (typeof value === "number") {
      if (Number.isInteger(value)) return value.toLocaleString("fr-FR");
      return value.toLocaleString("fr-FR", { maximumFractionDigits: 2 });
    }
    if (typeof value === "object" && value !== null) {
      return Object.entries(value).map(([k, v]) => `${escapeHTML(DETAIL_LABELS[k] || k)}: ${formatDetailValue(v)}`).join(", ");
    }
    return escapeHTML(value);
  }
  function buildDetailsHTML(details) {
    let phoneHintHTML = "";
    if (details.phone_login_hint) {
      const hintText = typeof details.phone_login_hint === "string" ? details.phone_login_hint : "Connectez-vous sur LeBonCoin pour acc\xE9der au num\xE9ro";
      phoneHintHTML = `
      <div class="copilot-phone-login-hint">
        <span class="copilot-phone-hint-icon">&#x1F4F1;</span>
        <span>${escapeHTML(hintText)}</span>
        <a href="https://auth.leboncoin.fr/login/" target="_blank" rel="noopener noreferrer"
           class="copilot-phone-login-link">Se connecter</a>
      </div>
    `;
    }
    const entries = Object.entries(details).filter(([k, v]) => v !== null && v !== void 0 && k !== "phone_login_hint").map(([k, v]) => {
      const label = DETAIL_LABELS[k] || k;
      const val = k === "precision" && typeof v === "number" ? formatPrecisionStars(v) : formatDetailValue(v);
      return `<div class="copilot-detail-row"><span class="copilot-detail-key">${escapeHTML(label)}</span><span class="copilot-detail-value">${val}</span></div>`;
    }).join("");
    if (!entries && !phoneHintHTML) return "";
    const detailsBlock = entries ? `<details class="copilot-filter-details"><summary>Voir les d\xE9tails</summary><div class="copilot-details-content">${entries}</div></details>` : "";
    return phoneHintHTML + detailsBlock;
  }

  // extension/utils/styles.js
  function scoreColor(score) {
    if (score >= 70) return "#22c55e";
    if (score >= 40) return "#f59e0b";
    return "#ef4444";
  }
  function statusColor(status) {
    switch (status) {
      case "pass":
        return "#22c55e";
      case "warning":
        return "#f59e0b";
      case "fail":
        return "#ef4444";
      case "skip":
        return "#9ca3af";
      case "neutral":
        return "#94a3b8";
      default:
        return "#6b7280";
    }
  }
  function statusIcon(status) {
    switch (status) {
      case "pass":
        return "\u2713";
      case "warning":
        return "\u26A0";
      case "fail":
        return "\u2717";
      case "skip":
        return "\u2014";
      case "neutral":
        return "\u25CB";
      default:
        return "?";
    }
  }
  function filterLabel(filterId, status) {
    const labels = {
      L1: "Compl\xE9tude des donn\xE9es",
      L2: status === "pass" ? "Mod\xE8le reconnu" : "Identification du mod\xE8le",
      L3: "Coh\xE9rence km / ann\xE9e",
      L4: "Prix vs march\xE9",
      L5: "Indice de confiance",
      L6: "T\xE9l\xE9phone",
      L7: "SIRET vendeur",
      L8: "D\xE9tection import",
      L9: "R\xE9sultat de scan",
      L10: "Anciennet\xE9 annonce"
    };
    return labels[filterId] || filterId;
  }

  // extension/ui/dom.js
  var _runAnalysis = null;
  var _apiUrl = null;
  var _lastScanIdGetter = null;
  function initDom({ runAnalysis: runAnalysis2, apiUrl, getLastScanId }) {
    _runAnalysis = runAnalysis2;
    _apiUrl = apiUrl;
    _lastScanIdGetter = getLastScanId;
  }
  function removePopup() {
    const existing = document.getElementById("copilot-popup");
    if (existing) existing.remove();
    const overlay = document.getElementById("copilot-overlay");
    if (overlay) overlay.remove();
  }
  function showPopup(safeHTML) {
    removePopup();
    const overlay = document.createElement("div");
    overlay.id = "copilot-overlay";
    overlay.className = "copilot-overlay";
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) removePopup();
    });
    const template = document.createElement("template");
    template.innerHTML = safeHTML;
    const popupNode = template.content.firstElementChild;
    overlay.appendChild(popupNode);
    document.body.appendChild(overlay);
    const closeBtn = document.getElementById("copilot-close");
    if (closeBtn) closeBtn.addEventListener("click", removePopup);
    const retryBtn = document.getElementById("copilot-retry");
    if (retryBtn) retryBtn.addEventListener("click", () => {
      removePopup();
      if (_runAnalysis) _runAnalysis();
    });
    const premiumBtn = document.getElementById("copilot-premium-btn");
    if (premiumBtn) {
      premiumBtn.addEventListener("click", () => {
        premiumBtn.textContent = "Bient\xF4t disponible !";
        premiumBtn.disabled = true;
      });
    }
    const emailBtn = document.getElementById("copilot-email-btn");
    if (emailBtn) {
      emailBtn.addEventListener("click", async () => {
        const loading = document.getElementById("copilot-email-loading");
        const result = document.getElementById("copilot-email-result");
        const errorDiv = document.getElementById("copilot-email-error");
        const textArea = document.getElementById("copilot-email-text");
        emailBtn.style.display = "none";
        loading.style.display = "flex";
        errorDiv.style.display = "none";
        try {
          const emailUrl = _apiUrl.replace("/analyze", "/email-draft");
          const scanId = _lastScanIdGetter ? _lastScanIdGetter() : null;
          const resp = await backendFetch(emailUrl, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scan_id: scanId }) });
          const data = await resp.json();
          if (data.success) {
            textArea.value = data.data.generated_text;
            result.style.display = "block";
          } else {
            errorDiv.textContent = data.error || "Erreur de g\xE9n\xE9ration";
            errorDiv.style.display = "block";
            emailBtn.style.display = "block";
          }
        } catch (err) {
          errorDiv.textContent = "Service indisponible";
          errorDiv.style.display = "block";
          emailBtn.style.display = "block";
        }
        loading.style.display = "none";
      });
    }
    const copyBtn = document.getElementById("copilot-email-copy");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        const textArea = document.getElementById("copilot-email-text");
        navigator.clipboard.writeText(textArea.value).then(() => {
          const copied = document.getElementById("copilot-email-copied");
          copied.style.display = "inline";
          setTimeout(() => {
            copied.style.display = "none";
          }, 2e3);
        });
      });
    }
  }

  // extension/ui/components.js
  var RADAR_SHORT_LABELS = {
    L1: "Donn\xE9es",
    L2: "Mod\xE8le",
    L3: "Km",
    L4: "Prix",
    L5: "Confiance",
    L6: "T\xE9l\xE9phone",
    L7: "SIRET",
    L8: "Import",
    L9: "Scan",
    L10: "Anciennet\xE9"
  };
  function buildRadarSVG(filters, overallScore) {
    if (!filters || !filters.length) return "";
    const activeFilters = filters.filter((f) => f.status !== "neutral" && f.status !== "skip");
    if (!activeFilters.length) return "";
    const cx = 160, cy = 145, R = 100;
    const n = activeFilters.length;
    const angleStep = 2 * Math.PI / n;
    const startAngle = -Math.PI / 2;
    const mainColor = overallScore >= 70 ? "#22c55e" : overallScore >= 45 ? "#f59e0b" : "#ef4444";
    function pt(i, r) {
      const angle = startAngle + i * angleStep;
      return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
    }
    let gridSVG = "";
    for (const pct of [0.2, 0.4, 0.6, 0.8, 1]) {
      const pts = [];
      for (let i = 0; i < n; i++) {
        const p = pt(i, R * pct);
        pts.push(`${p.x},${p.y}`);
      }
      const cls = pct === 1 ? "copilot-radar-grid-outer" : "copilot-radar-grid";
      gridSVG += `<polygon points="${pts.join(" ")}" class="${cls}"/>`;
    }
    let axesSVG = "";
    for (let i = 0; i < n; i++) {
      const p = pt(i, R);
      axesSVG += `<line x1="${cx}" y1="${cy}" x2="${p.x}" y2="${p.y}" class="copilot-radar-axis-line"/>`;
    }
    const dataPts = [];
    for (let i = 0; i < n; i++) {
      const p = pt(i, R * activeFilters[i].score);
      dataPts.push(`${p.x},${p.y}`);
    }
    const dataStr = dataPts.join(" ");
    let dotsSVG = "";
    let labelsSVG = "";
    const labelPad = 18;
    for (let i = 0; i < n; i++) {
      const f = activeFilters[i];
      const score = f.score;
      const dp = pt(i, R * score);
      let dotColor = "#22c55e";
      if (f.status === "fail") dotColor = "#ef4444";
      else if (f.status === "warning") dotColor = "#f59e0b";
      else if (f.status === "skip") dotColor = "#9ca3af";
      dotsSVG += `<circle cx="${dp.x}" cy="${dp.y}" r="4" fill="${dotColor}" class="copilot-radar-dot"/>`;
      const lp = pt(i, R + labelPad);
      let anchor = "middle";
      if (lp.x < cx - 10) anchor = "end";
      else if (lp.x > cx + 10) anchor = "start";
      const statusCls = f.status === "fail" ? "fail" : f.status === "warning" ? "warning" : "pass";
      const shortLabel = escapeHTML(RADAR_SHORT_LABELS[f.filter_id] || f.filter_id);
      const pctLabel = Math.round(score * 100) + "%";
      labelsSVG += `<text x="${lp.x}" y="${lp.y}" text-anchor="${anchor}" dominant-baseline="central" class="copilot-radar-axis-label ${statusCls}">`;
      labelsSVG += `<tspan>${shortLabel}</tspan>`;
      labelsSVG += `<tspan x="${lp.x}" dy="12" font-size="9" font-weight="700">${pctLabel}</tspan>`;
      labelsSVG += `</text>`;
    }
    return `
    <svg class="copilot-radar-svg" width="320" height="310" viewBox="0 0 320 310">
      ${gridSVG}
      ${axesSVG}
      <polygon points="${dataStr}" fill="${mainColor}" opacity="0.15"/>
      <polygon points="${dataStr}" fill="none" stroke="${mainColor}" stroke-width="2" stroke-linejoin="round"/>
      ${dotsSVG}
      ${labelsSVG}
      <text x="${cx}" y="${cy - 6}" text-anchor="middle" class="copilot-radar-score" fill="${mainColor}">${overallScore}</text>
      <text x="${cx}" y="${cy + 14}" text-anchor="middle" class="copilot-radar-score-label">/100</text>
    </svg>
  `;
  }
  var BOOLEAN_FILTERS = ["L2", "L8"];
  function buildScoreBar(f) {
    const color = statusColor(f.status);
    if (f.status === "neutral") {
      return '<span class="copilot-filter-score copilot-score-na">N/A</span>';
    }
    if (f.status === "skip") {
      return '<div class="copilot-filter-score-bar"><div class="copilot-score-track"><div class="copilot-score-fill" style="width:0%;background:#d1d5db"></div></div><span class="copilot-score-text" style="color:#9ca3af">skip</span></div>';
    }
    if (BOOLEAN_FILTERS.includes(f.filter_id)) {
      const badgeClass = f.status === "pass" ? "copilot-bool-pass" : f.status === "fail" ? "copilot-bool-fail" : "copilot-bool-warn";
      const badgeText = f.status === "pass" ? "\u2713 OK" : f.status === "fail" ? "\u2717 NOK" : "\u26A0";
      return `<span class="copilot-bool-badge ${badgeClass}">${badgeText}</span>`;
    }
    const pct = Math.round(f.score * 100);
    return `<div class="copilot-filter-score-bar"><div class="copilot-score-track"><div class="copilot-score-fill" style="width:${pct}%;background:${color}"></div></div><span class="copilot-score-text" style="color:${color}">${pct}%</span></div>`;
  }

  // extension/ui/filters/l1.js
  var FIELD_LABELS_FR = {
    price_eur: "Prix",
    make: "Marque",
    model: "Mod\xE8le",
    year_model: "Ann\xE9e",
    mileage_km: "Kilom\xE9trage",
    fuel: "\xC9nergie",
    gearbox: "Bo\xEEte",
    phone: "T\xE9l\xE9phone",
    color: "Couleur",
    location: "Localisation"
  };
  function buildL1Body(f, d) {
    const present = d.fields_present || 0;
    const total = d.fields_total || 10;
    const pct = total > 0 ? Math.round(present / total * 100) : 0;
    const color = statusColor(f.status);
    const barHTML = `
    <div class="copilot-l1-bar">
      <div class="copilot-l1-bar-track">
        <div class="copilot-l1-bar-fill" style="width:${pct}%;background:${color}"></div>
      </div>
      <span class="copilot-l1-bar-label">${present}/${total} champs renseign\xE9s</span>
    </div>
  `;
    let statusMsg = "";
    if (f.status === "pass") {
      statusMsg = '<div class="copilot-l1-status copilot-l1-ok">Donn\xE9es compl\xE8tes \u2014 analyse fiable</div>';
    } else {
      statusMsg = `<div class="copilot-l1-status copilot-l1-warn">Donn\xE9es incompl\xE8tes \u2014 l'analyse qui suit peut \xEAtre moins fiable</div>`;
    }
    let missingHTML = "";
    const criticals = d.missing_critical || [];
    const secondaries = d.missing_secondary || [];
    if (criticals.length > 0) {
      const items = criticals.map((f2) => `<li class="copilot-l1-missing-critical">${escapeHTML(FIELD_LABELS_FR[f2] || f2)}</li>`).join("");
      missingHTML += `<div class="copilot-l1-missing"><span class="copilot-l1-missing-title">Critiques :</span><ul>${items}</ul></div>`;
    }
    if (secondaries.length > 0) {
      const items = secondaries.map((f2) => `<li class="copilot-l1-missing-secondary">${escapeHTML(FIELD_LABELS_FR[f2] || f2)}</li>`).join("");
      missingHTML += `<div class="copilot-l1-missing"><span class="copilot-l1-missing-title">Secondaires :</span><ul>${items}</ul></div>`;
    }
    return `<div class="copilot-l1-body">${barHTML}${statusMsg}${missingHTML}</div>`;
  }

  // extension/ui/filters/l2.js
  function buildL2Body(f, d) {
    if (f.status === "skip") {
      return `<div class="copilot-l2-body"><span class="copilot-l2-na">${escapeHTML(f.message)}</span></div>`;
    }
    if (f.status === "pass") {
      const brand = d.brand || "";
      const model = d.model || "";
      const gen = d.generation ? ` \xB7 ${d.generation}` : "";
      return `<div class="copilot-l2-body">
      <span class="copilot-l2-badge copilot-l2-badge-ok">\u2713 ${escapeHTML(brand)} ${escapeHTML(model)}${escapeHTML(gen)}</span>
    </div>`;
    }
    return `<div class="copilot-l2-body">
    <span class="copilot-l2-msg">${escapeHTML(f.message)}</span>
  </div>`;
  }

  // extension/ui/filters/l3.js
  function buildL3Body(f, d) {
    const kmYear = d.km_per_year;
    const expectedKm = d.expected_km;
    const mileage = d.mileage_km;
    const age = d.age;
    const isPro = d.is_pro;
    const warnings = d.warnings || [];
    const avgExpected = d.avg_km_per_year;
    const kmRatio = d.km_ratio;
    if (kmYear == null || expectedKm == null) {
      return `<p class="copilot-filter-message">${escapeHTML(f.message)}</p>`;
    }
    const fmtKm = (n) => Math.round(n).toLocaleString("fr-FR");
    const statHTML = `
    <div class="copilot-l3-stat">
      <span class="copilot-l3-km-year">~${fmtKm(kmYear)} km/an</span>
      <span class="copilot-l3-expected">Attendu : ~${fmtKm(avgExpected || 15e3)} km/an pour un v\xE9hicule de ${age} an${age > 1 ? "s" : ""}</span>
    </div>
  `;
    const maxKm = Math.max(mileage, expectedKm) * 1.3;
    const realPct = Math.min(mileage / maxKm * 100, 100);
    const expectedPct = Math.min(expectedKm / maxKm * 100, 100);
    const barColor = kmRatio < 0.5 ? "#3b82f6" : kmRatio <= 1.5 ? "#22c55e" : kmRatio <= 2 ? "#f59e0b" : "#ef4444";
    const barHTML = `
    <div class="copilot-l3-comparison">
      <div class="copilot-l3-bar-row">
        <span class="copilot-l3-bar-label">R\xE9el</span>
        <div class="copilot-l3-bar-track"><div class="copilot-l3-bar-fill" style="width:${realPct}%;background:${barColor}"></div></div>
        <span class="copilot-l3-bar-value">${fmtKm(mileage)} km</span>
      </div>
      <div class="copilot-l3-bar-row">
        <span class="copilot-l3-bar-label">Attendu</span>
        <div class="copilot-l3-bar-track"><div class="copilot-l3-bar-fill" style="width:${expectedPct}%;background:#9ca3af"></div></div>
        <span class="copilot-l3-bar-value">${fmtKm(expectedKm)} km</span>
      </div>
    </div>
  `;
    const isRecentLowKm = d.is_recent_low_km;
    let verdictHTML = "";
    if (f.status === "pass") {
      verdictHTML = `<div class="copilot-l3-verdict copilot-l3-ok">Kilom\xE9trage coh\xE9rent avec l'\xE2ge du v\xE9hicule</div>`;
    } else if (isRecentLowKm && isPro) {
      verdictHTML = '<div class="copilot-l3-verdict copilot-l3-warn">V\xE9hicule quasi-neuf \u2014 probable immatriculation constructeur</div>';
    } else if (isRecentLowKm) {
      verdictHTML = `<div class="copilot-l3-verdict copilot-l3-warn">V\xE9hicule quasi-neuf \u2014 n'a pas trouv\xE9 preneur</div>`;
    } else if (kmRatio < 0.5) {
      verdictHTML = '<div class="copilot-l3-verdict copilot-l3-alert">Kilom\xE9trage tr\xE8s bas \u2014 compteur remis \xE0 z\xE9ro ?</div>';
    } else if (kmRatio > 2) {
      verdictHTML = '<div class="copilot-l3-verdict copilot-l3-alert">Kilom\xE9trage tr\xE8s \xE9lev\xE9 \u2014 usure acc\xE9l\xE9r\xE9e</div>';
    } else {
      verdictHTML = '<div class="copilot-l3-verdict copilot-l3-warn">Kilom\xE9trage \xE0 surveiller</div>';
    }
    let proHTML = "";
    if (isPro) {
      proHTML = '<span class="copilot-l3-pro-badge">V\xE9hicule pro</span>';
    }
    let warningsHTML = "";
    if (warnings.length > 0) {
      const items = warnings.map((w) => `<li>${escapeHTML(w)}</li>`).join("");
      warningsHTML = `<ul class="copilot-l3-warnings">${items}</ul>`;
    }
    return `<div class="copilot-l3-body">${statHTML}${barHTML}${verdictHTML}${proHTML}${warningsHTML}</div>`;
  }

  // extension/ui/filters/l4.js
  function _detectCurrentSite() {
    try {
      const host = String(window.location.hostname || "").toLowerCase();
      if (host.includes("autoscout24.")) return "autoscout24";
      if (host.includes("leboncoin.")) return "leboncoin";
    } catch {
    }
    return null;
  }
  function buildPriceBarHTML(details, vehicle) {
    const priceAnnonce = details.price_annonce;
    const priceRef = details.price_reference;
    if (!priceAnnonce || !priceRef) return "";
    const deltaEur = details.delta_eur || priceAnnonce - priceRef;
    const deltaPct = details.delta_pct != null ? details.delta_pct : Math.round((priceAnnonce - priceRef) / priceRef * 100);
    const isLocal = vehicle?.currency && vehicle.currency !== "EUR";
    const eurToLocal = isLocal && vehicle.price_original && vehicle.price ? vehicle.price_original / vehicle.price : 1;
    const sym = isLocal ? vehicle.currency : "\u20AC";
    const displayDelta = Math.round(Math.abs(deltaEur) * eurToLocal);
    const displayAnnonce = Math.round(priceAnnonce * eurToLocal);
    const displayRef = Math.round(priceRef * eurToLocal);
    const absPct = Math.abs(Math.round(deltaPct));
    const fmtD = displayDelta.toLocaleString("fr-FR");
    let verdictClass, verdictEmoji, line1, line2;
    if (absPct <= 10) {
      verdictClass = "verdict-fair";
      verdictEmoji = "\u2705";
      line1 = "Prix march\xE9";
      line2 = `Dans la fourchette du march\xE9 (${deltaPct > 0 ? "+" : ""}${Math.round(deltaPct)}%) \u2014 n\xE9gociez sereinement`;
    } else if (absPct <= 25) {
      if (deltaPct < 0) {
        verdictClass = "verdict-below";
        verdictEmoji = "\u{1F7E2}";
        line1 = `${fmtD} ${sym} en dessous du march\xE9`;
        line2 = `Bonne affaire potentielle \u2014 ${absPct}% moins cher`;
      } else {
        verdictClass = "verdict-above-warning";
        verdictEmoji = "\u{1F7E0}";
        line1 = `${fmtD} ${sym} au-dessus du march\xE9`;
        line2 = `N\xE9gociez serr\xE9 \u2014 ${absPct}% plus cher que le march\xE9`;
      }
    } else {
      if (deltaPct < 0) {
        verdictClass = "verdict-below-suspect";
        verdictEmoji = "\u26A0\uFE0F";
        line1 = `${fmtD} ${sym} en dessous du march\xE9`;
        line2 = `Prix tr\xE8s bas \u2014 m\xE9fiez-vous, \xE7a peut cacher quelque chose`;
      } else {
        verdictClass = "verdict-above-fail";
        verdictEmoji = "\u{1F534}";
        line1 = `${fmtD} ${sym} au-dessus du march\xE9`;
        line2 = `Trop cher \u2014 ${absPct}% plus cher, ce n'est pas une affaire`;
      }
    }
    const statusColors = { "verdict-below": "#16a34a", "verdict-below-suspect": "#ea580c", "verdict-fair": "#16a34a", "verdict-above-warning": "#ea580c", "verdict-above-fail": "#dc2626" };
    const fillOpacities = { "verdict-below": "rgba(22,163,74,0.15)", "verdict-below-suspect": "rgba(234,88,12,0.2)", "verdict-fair": "rgba(22,163,74,0.15)", "verdict-above-warning": "rgba(234,88,12,0.2)", "verdict-above-fail": "rgba(220,38,38,0.2)" };
    const color = statusColors[verdictClass] || "#16a34a";
    const fillBg = fillOpacities[verdictClass] || "rgba(22,163,74,0.15)";
    const minP = Math.min(displayAnnonce, displayRef);
    const maxP = Math.max(displayAnnonce, displayRef);
    const gap = maxP - minP || maxP * 0.1;
    const scaleMin = Math.max(0, minP - gap * 0.8);
    const scaleMax = maxP + gap * 0.8;
    const range = scaleMax - scaleMin;
    const pct = (p) => (p - scaleMin) / range * 100;
    const annoncePct = pct(displayAnnonce);
    const argusPct = pct(displayRef);
    const fillLeft = Math.min(annoncePct, argusPct);
    const fillWidth = Math.abs(annoncePct - argusPct);
    const fmtP = (n) => escapeHTML(n.toLocaleString("fr-FR")) + " " + escapeHTML(sym);
    const src = details.source || "";
    let srcLabel = "";
    let srcClass = "copilot-l4-src-default";
    if (src === "marche_leboncoin") {
      srcLabel = "LBC";
      srcClass = "copilot-l4-src-lbc";
    } else if (src === "marche_autoscout24") {
      srcLabel = "AS24";
      srcClass = "copilot-l4-src-as24";
    } else if (src === "argus_seed") {
      srcLabel = "Argus Seed";
      srcClass = "copilot-l4-src-seed";
    } else if (src === "estimation_lbc") {
      srcLabel = "Estimation LBC";
      srcClass = "copilot-l4-src-est";
    }
    const currentSite = _detectCurrentSite();
    const marketSite = src === "marche_leboncoin" ? "leboncoin" : src === "marche_autoscout24" ? "autoscout24" : null;
    const isCrossSource = Boolean(currentSite && marketSite && currentSite !== marketSite);
    if (srcLabel && isCrossSource) {
      srcLabel += " \xB7 march\xE9 externe";
    }
    const sampleCount = details.sample_count;
    const precision = details.precision;
    let precisionStars = "";
    if (precision != null) {
      const full = Math.floor(precision);
      const half = precision - full >= 0.5 ? 1 : 0;
      const empty = 5 - full - half;
      precisionStars = "\u2605".repeat(full) + (half ? "\xBD" : "") + "\u2606".repeat(empty);
    }
    let footerHTML = "";
    if (srcLabel) {
      footerHTML = `<div class="copilot-l4-footer">`;
      footerHTML += `<span class="copilot-l4-source ${escapeHTML(srcClass)}">${escapeHTML(srcLabel)}</span>`;
      if (sampleCount != null) {
        footerHTML += `<span class="copilot-l4-samples">Bas\xE9 sur ${sampleCount} annonce${sampleCount > 1 ? "s" : ""}${isCrossSource ? " (source externe au site)" : ""}</span>`;
      }
      if (precisionStars) footerHTML += `<span class="copilot-l4-precision" title="Pr\xE9cision de l'\xE9chantillon">${precisionStars}</span>`;
      footerHTML += `</div>`;
    }
    let staleHTML = "";
    if (details.stale_below_market) {
      const staleDays = details.days_online || "30+";
      staleHTML = `<div class="copilot-l4-stale">
      <span class="copilot-l4-stale-icon">\u{1F440}</span>
      <div>
        <div class="copilot-l4-stale-title">Prix bas + ${staleDays} jours en ligne</div>
        <div class="copilot-l4-stale-text">Les acheteurs n'ont pas franchi le pas \u2014 il y a peut-\xEAtre anguille sous roche</div>
      </div>
    </div>`;
    }
    return `
    <div class="copilot-price-bar-container">
      <div class="copilot-price-verdict ${escapeHTML(verdictClass)}">
        <span class="copilot-price-verdict-emoji">${verdictEmoji}</span>
        <div>
          <div class="copilot-price-verdict-text">${escapeHTML(line1)}</div>
          <div class="copilot-price-verdict-pct">${escapeHTML(line2)}</div>
        </div>
      </div>
      <div class="copilot-price-bar-track">
        <div class="copilot-price-bar-fill" style="left:${fillLeft}%;width:${fillWidth}%;background:${fillBg}"></div>
        <div class="copilot-price-arrow-zone" style="left:${fillLeft}%;width:${fillWidth}%;border-color:${color}"></div>
        <div class="copilot-price-market-ref" style="left:${argusPct}%">
          <div class="copilot-price-market-line"></div>
          <div class="copilot-price-market-label">March\xE9</div>
          <div class="copilot-price-market-price">${fmtP(displayRef)}</div>
        </div>
        <div class="copilot-price-car" style="left:${annoncePct}%">
          <span class="copilot-price-car-emoji">\u{1F697}</span>
          <div class="copilot-price-car-price" style="color:${color}">${fmtP(displayAnnonce)}</div>
        </div>
      </div>
      <div class="copilot-price-bar-spacer"></div>
      ${footerHTML}
      ${staleHTML}
    </div>
  `;
  }

  // extension/ui/filters/l5.js
  function _detectCurrentSite2() {
    try {
      const host = String(window.location.hostname || "").toLowerCase();
      if (host.includes("autoscout24.")) return "autoscout24";
      if (host.includes("leboncoin.")) return "leboncoin";
    } catch {
    }
    return null;
  }
  function buildL5Body(f, d) {
    if (f.status === "skip") {
      return `<div class="copilot-l5-body"><span class="copilot-l5-na">${escapeHTML(f.message)}</span></div>`;
    }
    const zPrice = d.z_scores?.price;
    const anomalies = d.anomalies || [];
    const refCount = d.ref_count || 0;
    const hasOutlier = anomalies.some((a) => a.includes("outlier"));
    const hasMargin = anomalies.some((a) => a.includes("marge"));
    const dieselOnly = anomalies.length > 0 && anomalies.every((a) => a.includes("Diesel"));
    let cursorPct, zoneClass, verdictText;
    if (hasOutlier) {
      cursorPct = zPrice > 0 ? 8 : 12;
      zoneClass = "copilot-l5-zone-red";
      verdictText = "Anomalie d\xE9tect\xE9e \u2014 prix tr\xE8s \xE9loign\xE9 de la distribution";
    } else if (hasMargin) {
      cursorPct = zPrice > 0 ? 22 : 28;
      zoneClass = "copilot-l5-zone-orange";
      verdictText = "Signal faible \u2014 prix en marge de la distribution";
    } else if (anomalies.length === 0 || dieselOnly) {
      const bonus = Math.min(refCount, 20) / 20 * 20;
      cursorPct = 60 + bonus;
      zoneClass = refCount >= 10 ? "copilot-l5-zone-green" : "copilot-l5-zone-neutral";
      verdictText = refCount >= 10 ? `RAS \u2014 aucune anomalie (${refCount} v\xE9hicules compar\xE9s)` : `RAS \u2014 confiance mod\xE9r\xE9e (${refCount} r\xE9f\xE9rences)`;
    } else {
      cursorPct = 35;
      zoneClass = "copilot-l5-zone-orange";
      verdictText = anomalies[0];
    }
    let html = `<div class="copilot-l5-body">`;
    html += `<div class="copilot-l5-scale">`;
    html += `  <div class="copilot-l5-track">`;
    html += `    <div class="copilot-l5-zone-left"></div>`;
    html += `    <div class="copilot-l5-zone-center"></div>`;
    html += `    <div class="copilot-l5-zone-right"></div>`;
    html += `    <div class="copilot-l5-cursor ${zoneClass}" style="left:${cursorPct}%"></div>`;
    html += `  </div>`;
    html += `  <div class="copilot-l5-labels">`;
    html += `    <span class="copilot-l5-label-left">Louche</span>`;
    html += `    <span class="copilot-l5-label-center">RAS</span>`;
    html += `    <span class="copilot-l5-label-right">Fiable</span>`;
    html += `  </div>`;
    html += `</div>`;
    html += `<div class="copilot-l5-verdict">${escapeHTML(verdictText)}</div>`;
    if (d.diesel_urban) {
      html += `<div class="copilot-l5-diesel">`;
      html += `  <span class="copilot-l5-diesel-icon">\u2699\uFE0F</span>`;
      html += `  <div>`;
      html += `    <div class="copilot-l5-diesel-title">Diesel en zone urbaine dense</div>`;
      html += `    <div class="copilot-l5-diesel-text">Risque FAP, injecteurs, vanne EGR \u2014 les r\xE9g\xE9n\xE9rations ne se font pas en ville</div>`;
      html += `  </div>`;
      html += `</div>`;
    }
    const src = d.source || "";
    let srcLabel = "";
    if (src === "marche_leboncoin") srcLabel = "LBC";
    else if (src === "marche_autoscout24") srcLabel = "AS24";
    else if (src === "argus_seed") srcLabel = "Argus Seed";
    const currentSite = _detectCurrentSite2();
    const marketSite = src === "marche_leboncoin" ? "leboncoin" : src === "marche_autoscout24" ? "autoscout24" : null;
    if (srcLabel && currentSite && marketSite && currentSite !== marketSite) {
      srcLabel += " \xB7 march\xE9 externe";
    }
    if (srcLabel || refCount) {
      html += `<div class="copilot-l5-footer">`;
      if (srcLabel) html += `<span class="copilot-l5-src">${escapeHTML(srcLabel)}</span>`;
      if (refCount) html += `<span class="copilot-l5-refs">Bas\xE9 sur ${refCount} v\xE9hicule${refCount > 1 ? "s" : ""}</span>`;
      html += `</div>`;
    }
    html += `</div>`;
    return html;
  }

  // extension/ui/filters/l6.js
  function buildL6Body(f, d) {
    if (f.status === "neutral") {
      return `<div class="copilot-l6-body"><span class="copilot-l6-na">T\xE9l\xE9phone non disponible</span></div>`;
    }
    if (f.status === "skip" && d.phone_login_hint) {
      const hintText = typeof d.phone_login_hint === "string" ? d.phone_login_hint : "Connectez-vous sur LeBonCoin pour acc\xE9der au num\xE9ro";
      return `<div class="copilot-l6-body">
      <div class="copilot-phone-login-hint">
        <span class="copilot-phone-hint-icon">&#x1F4F1;</span>
        <span>${escapeHTML(hintText)}</span>
        <a href="https://auth.leboncoin.fr/login/" target="_blank" rel="noopener noreferrer"
           class="copilot-phone-login-link">Se connecter</a>
      </div>
    </div>`;
    }
    const phoneType = d.type || "";
    let badgeText = "";
    let badgeClass = "copilot-l6-badge-default";
    if (phoneType.startsWith("mobile")) {
      badgeText = "Mobile";
      badgeClass = "copilot-l6-badge-mobile";
    } else if (phoneType.startsWith("landline")) {
      badgeText = "Fixe";
      badgeClass = "copilot-l6-badge-landline";
    } else if (phoneType === "telemarketing_arcep") {
      badgeText = "D\xE9marchage";
      badgeClass = "copilot-l6-badge-danger";
    } else if (phoneType === "virtual_onoff") {
      badgeText = "Virtuel";
      badgeClass = "copilot-l6-badge-danger";
    } else if (d.is_foreign) {
      const prefix = d.prefix || "";
      const flag = d.prefix_country_flag || "";
      const countryName = d.prefix_country_name || "";
      const suffix = [prefix, flag, countryName].filter(Boolean).join(" ");
      badgeText = `\xC9tranger${suffix ? " (" + suffix + ")" : ""}`;
      badgeClass = "copilot-l6-badge-foreign";
    } else if (phoneType.startsWith("local") || phoneType === "present_unverified") {
      badgeText = "Pr\xE9sent";
      badgeClass = "copilot-l6-badge-ok";
    }
    if (d.no_phone_pro) {
      badgeText = "Pro sans t\xE9l\xE9phone";
      badgeClass = "copilot-l6-badge-danger";
    }
    let html = `<div class="copilot-l6-body">`;
    if (badgeText) {
      html += `<span class="copilot-l6-badge ${badgeClass}">${escapeHTML(badgeText)}</span>`;
    }
    if (f.message && f.status !== "pass") {
      html += `<span class="copilot-l6-msg">${escapeHTML(f.message)}</span>`;
    }
    html += `</div>`;
    return html;
  }

  // extension/ui/filters/l7.js
  function buildL7Body(f, d) {
    const ownerType = (d.owner_type || "").toLowerCase();
    if (f.status === "neutral" || ownerType === "private" || ownerType === "particulier") {
      return `<div class="copilot-l7-body"><span class="copilot-l7-badge copilot-l7-badge-neutral">Particulier</span></div>`;
    }
    if (f.status === "skip") {
      return `<div class="copilot-l7-body"><span class="copilot-l7-na">${escapeHTML(f.message)}</span></div>`;
    }
    let html = `<div class="copilot-l7-body">`;
    if (d.platform_verified) {
      html += `<span class="copilot-l7-badge copilot-l7-badge-verified">Pro v\xE9rifi\xE9</span>`;
      if (d.dealer_rating != null && d.dealer_review_count != null) {
        const stars = "\u2605".repeat(Math.round(Number(d.dealer_rating)));
        html += `<span class="copilot-l7-rating">${stars} ${d.dealer_rating}/5 (${d.dealer_review_count} avis)</span>`;
      }
      html += `</div>`;
      return html;
    }
    if (f.status === "pass") {
      const denom = d.denomination || d.name || "";
      const siretOrUid = d.formatted || d.siret || d.uid || "";
      html += `<span class="copilot-l7-badge copilot-l7-badge-pro">Pro</span>`;
      if (denom) html += `<span class="copilot-l7-denom">${escapeHTML(denom)}</span>`;
      if (siretOrUid) html += `<span class="copilot-l7-id">${escapeHTML(siretOrUid)}</span>`;
      if (d.dealer_rating != null && d.dealer_review_count != null) {
        const stars = "\u2605".repeat(Math.round(Number(d.dealer_rating)));
        html += `<span class="copilot-l7-rating">${stars} ${d.dealer_rating}/5 (${d.dealer_review_count} avis)</span>`;
      }
      html += `</div>`;
      return html;
    }
    if (f.status === "warning") {
      html += `<span class="copilot-l7-badge copilot-l7-badge-warn">Pro non identifi\xE9</span>`;
      html += `<span class="copilot-l7-msg">${escapeHTML(f.message)}</span>`;
      html += `</div>`;
      return html;
    }
    html += `<span class="copilot-l7-badge copilot-l7-badge-fail">Pro suspect</span>`;
    html += `<span class="copilot-l7-msg">${escapeHTML(f.message)}</span>`;
    html += `</div>`;
    return html;
  }

  // extension/ui/filters/l8.js
  function buildL8Body(f, d) {
    const signals = d.signals || [];
    const strongCount = d.strong_count || 0;
    if (f.status === "pass" || signals.length === 0) {
      return `<div class="copilot-l8-body">
      <div class="copilot-l8-clean">
        <span class="copilot-l8-clean-icon">\u2705</span>
        <span>Aucun signal d'import d\xE9tect\xE9</span>
      </div>
    </div>`;
    }
    let headerText = strongCount >= 2 ? "Import probable" : strongCount === 1 ? "Signal d'import d\xE9tect\xE9" : "Signal faible d'import";
    const headerClass = f.status === "fail" ? "copilot-l8-alert-fail" : "copilot-l8-alert-warn";
    let html = `<div class="copilot-l8-body">`;
    html += `<div class="copilot-l8-alert ${headerClass}">`;
    html += `<span class="copilot-l8-alert-icon">${f.status === "fail" ? "\u{1F6A8}" : "\u26A0\uFE0F"}</span>`;
    html += `<span class="copilot-l8-alert-text">${escapeHTML(headerText)} (${signals.length} indice${signals.length > 1 ? "s" : ""})</span>`;
    html += `</div>`;
    html += `<ul class="copilot-l8-signals">`;
    for (const sig of signals) {
      html += `<li class="copilot-l8-signal">${escapeHTML(sig)}</li>`;
    }
    html += `</ul></div>`;
    return html;
  }

  // extension/ui/filters/l9.js
  function buildL9Body(f, d, allFilters) {
    const forts = d.points_forts || [];
    const faibles = d.points_faibles || [];
    const others = (allFilters || []).filter((x) => x.filter_id !== "L9");
    const total = others.length;
    const evaluated = others.filter((x) => x.status !== "skip").length;
    let coverageHTML = "";
    if (total > 0) {
      const coverageColor = evaluated === total ? "#22c55e" : evaluated >= total * 0.7 ? "#f59e0b" : "#ef4444";
      const coverageText = evaluated === total ? "Analyse compl\xE8te" : `Analyse partielle \u2014 ${total - evaluated} filtre${total - evaluated > 1 ? "s" : ""} non \xE9valu\xE9${total - evaluated > 1 ? "s" : ""} (donn\xE9es absentes de l'annonce)`;
      coverageHTML = `
      <div class="copilot-l9-coverage">
        <span class="copilot-l9-coverage-count" style="color:${coverageColor}">${evaluated}/${total} filtres \xE9valu\xE9s</span>
        <span class="copilot-l9-coverage-text">${escapeHTML(coverageText)}</span>
      </div>
    `;
    }
    let fortsHTML = "";
    if (forts.length > 0) {
      const items = forts.map((p) => `<li class="copilot-l9-fort">${escapeHTML(p)}</li>`).join("");
      fortsHTML = `<div class="copilot-l9-list"><div class="copilot-l9-list-title copilot-l9-fort-title">Points forts</div><ul>${items}</ul></div>`;
    }
    let faiblesHTML = "";
    if (faibles.length > 0) {
      const items = faibles.map((p) => `<li class="copilot-l9-faible">${escapeHTML(p)}</li>`).join("");
      faiblesHTML = `<div class="copilot-l9-list"><div class="copilot-l9-list-title copilot-l9-faible-title">Points faibles</div><ul>${items}</ul></div>`;
    }
    let phoneHintHTML = "";
    if (d.phone_login_hint) {
      const hintText = typeof d.phone_login_hint === "string" ? d.phone_login_hint : "Connectez-vous sur LeBonCoin pour acc\xE9der au num\xE9ro";
      phoneHintHTML = `
      <div class="copilot-phone-login-hint">
        <span class="copilot-phone-hint-icon">&#x1F4F1;</span>
        <span>${escapeHTML(hintText)}</span>
        <a href="https://auth.leboncoin.fr/login/" target="_blank" rel="noopener noreferrer"
           class="copilot-phone-login-link">Se connecter</a>
      </div>
    `;
    }
    return `<div class="copilot-l9-body">${coverageHTML}${fortsHTML}${faiblesHTML}${phoneHintHTML}</div>`;
  }

  // extension/ui/filters/l10.js
  function buildL10Body(f, d) {
    const days = d.days_online;
    const threshold = d.threshold_days || 35;
    const ratio = d.ratio || 0;
    const republished = d.republished;
    const thresholdSource = d.threshold_source === "marche" ? "march\xE9" : "prix";
    const marketMedian = d.market_median_days;
    if (days == null) {
      return '<p class="copilot-filter-message">Anciennet\xE9 non disponible</p>';
    }
    let barColor, verdictText;
    if (ratio <= 0.3) {
      barColor = "#22c55e";
      verdictText = "Annonce tr\xE8s r\xE9cente";
    } else if (ratio <= 1) {
      barColor = "#22c55e";
      verdictText = "Dur\xE9e de mise en vente normale";
    } else if (ratio <= 2) {
      barColor = "#f59e0b";
      verdictText = "Au-del\xE0 de la dur\xE9e normale pour ce segment";
    } else {
      barColor = "#ef4444";
      verdictText = "Annonce stagnante \u2014 pourquoi personne n'a achet\xE9 ?";
    }
    const maxDisplay = threshold * 2.5;
    const cursorPct = Math.min(Math.max(days / maxDisplay * 100, 2), 98);
    const thresholdPct = Math.min(threshold / maxDisplay * 100, 95);
    const bigNumber = `<div class="copilot-l10-big"><span class="copilot-l10-days" style="color:${barColor}">${days}</span><span class="copilot-l10-days-label">jour${days > 1 ? "s" : ""} en ligne</span></div>`;
    const barHTML = `
    <div class="copilot-l10-timeline">
      <div class="copilot-l10-track">
        <div class="copilot-l10-fill" style="width:${cursorPct}%;background:${barColor}"></div>
        <div class="copilot-l10-threshold" style="left:${thresholdPct}%">
          <div class="copilot-l10-threshold-line"></div>
          <span class="copilot-l10-threshold-label">Seuil ${threshold}j</span>
        </div>
        <div class="copilot-l10-cursor" style="left:${cursorPct}%;background:${barColor}"></div>
      </div>
      <div class="copilot-l10-scale">
        <span>0j</span>
        <span>${Math.round(maxDisplay)}j</span>
      </div>
    </div>
  `;
    const verdictHTML = `<div class="copilot-l10-verdict" style="color:${barColor}">${escapeHTML(verdictText)}</div>`;
    let metaHTML = `<div class="copilot-l10-meta">Seuil bas\xE9 sur le ${escapeHTML(thresholdSource)}</div>`;
    if (marketMedian != null) {
      metaHTML += `<div class="copilot-l10-meta">M\xE9diane march\xE9 : ${marketMedian} jours</div>`;
    }
    let republishedHTML = "";
    if (republished) {
      republishedHTML = `<div class="copilot-l10-republished">Republication d\xE9tect\xE9e \u2014 l'annonce a \xE9t\xE9 remise en ligne pour para\xEEtre r\xE9cente</div>`;
    }
    return `<div class="copilot-l10-body">${bigNumber}${barHTML}${verdictHTML}${metaHTML}${republishedHTML}</div>`;
  }

  // extension/ui/filters/generic.js
  function buildGenericBody(f) {
    const msgHTML = `<p class="copilot-filter-message">${escapeHTML(f.message)}</p>`;
    const detailsHTML = f.details ? buildDetailsHTML(f.details) : "";
    return msgHTML + detailsHTML;
  }

  // extension/ui/filters/index.js
  var SIMULATED_FILTERS = ["L4", "L5"];
  var FILTER_DISPLAY_ORDER = ["L4", "L10", "L1", "L3", "L5", "L8", "L6", "L7", "L2", "L9"];
  function buildFilterBody(f, vehicle, allFilters) {
    const d = f.details || {};
    switch (f.filter_id) {
      case "L1":
        return buildL1Body(f, d);
      case "L3":
        return buildL3Body(f, d);
      case "L4":
        return buildPriceBarHTML(d, vehicle);
      case "L2":
        return buildL2Body(f, d);
      case "L5":
        return buildL5Body(f, d);
      case "L6":
        return buildL6Body(f, d);
      case "L7":
        return buildL7Body(f, d);
      case "L8":
        return buildL8Body(f, d);
      case "L9":
        return buildL9Body(f, d, allFilters);
      case "L10":
        return buildL10Body(f, d);
      default:
        return buildGenericBody(f);
    }
  }
  function buildFiltersList(filters, vehicle) {
    if (!filters || !filters.length) return "";
    const sorted = [...filters].sort((a, b) => {
      const ia = FILTER_DISPLAY_ORDER.indexOf(a.filter_id);
      const ib = FILTER_DISPLAY_ORDER.indexOf(b.filter_id);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
    return sorted.map((f) => {
      const color = statusColor(f.status);
      const icon = statusIcon(f.status);
      const label = filterLabel(f.filter_id, f.status);
      const simulatedBadge = SIMULATED_FILTERS.includes(f.filter_id) && f.filter_id !== "L4" ? '<span class="copilot-badge-simulated">Donn\xE9es simul\xE9es</span>' : "";
      const scoreBarHTML = buildScoreBar(f);
      const bodyHTML = buildFilterBody(f, vehicle, sorted);
      return `
        <div class="copilot-filter-item" data-status="${escapeHTML(f.status)}">
          <div class="copilot-filter-header">
            <span class="copilot-filter-icon" style="color:${color}">${icon}</span>
            <span class="copilot-filter-label">${escapeHTML(label)}${simulatedBadge}</span>
            ${scoreBarHTML}
          </div>
          ${bodyHTML}
        </div>
      `;
    }).join("");
  }

  // extension/ui/banners.js
  function buildPremiumSection() {
    return `<div class="copilot-premium-section"><div class="copilot-premium-blur"><div class="copilot-premium-fake"><p><strong>Rapport d\xE9taill\xE9 du v\xE9hicule</strong></p><p>Fiche fiabilit\xE9 compl\xE8te avec probl\xE8mes connus, co\xFBts d'entretien pr\xE9vus, historique des rappels constructeur et comparaison avec les alternatives du segment.</p><p>Estimation de la valeur r\xE9elle bas\xE9e sur 12 crit\xE8res r\xE9gionaux.</p><p>Recommandation d'achat personnalis\xE9e avec score de confiance.</p></div></div><div class="copilot-premium-overlay"><div class="copilot-premium-glass"><p class="copilot-premium-title">Analyse compl\xE8te</p><p class="copilot-premium-subtitle">D\xE9bloquez le rapport d\xE9taill\xE9 avec fiabilit\xE9, co\xFBts et recommandations.</p><button class="copilot-premium-cta" id="copilot-premium-btn">D\xE9bloquer \u2013 9,90 \u20AC</div></div></div>`;
  }
  function buildYouTubeBanner(featuredVideo) {
    if (!featuredVideo || !featuredVideo.url) return "";
    const title = featuredVideo.title || "D\xE9couvrir ce mod\xE8le en vid\xE9o";
    const channel = featuredVideo.channel || "";
    return `<div class="copilot-youtube-banner"><a href="${escapeHTML(featuredVideo.url)}" target="_blank" rel="noopener noreferrer" class="copilot-youtube-link"><span class="copilot-youtube-icon">&#x25B6;&#xFE0F;</span><span class="copilot-youtube-text"><strong>D\xE9couvrir ce mod\xE8le en vid\xE9o</strong><small>${escapeHTML(channel)}${channel ? " \xB7 " : ""}${escapeHTML(title).substring(0, 50)}</small></span><span class="copilot-youtube-arrow">&rsaquo;</span></a></div>`;
  }
  function buildAutovizaBanner(autovizaUrl) {
    if (!autovizaUrl) return "";
    return `<div class="copilot-autoviza-banner"><a href="${escapeHTML(autovizaUrl)}" target="_blank" rel="noopener noreferrer" class="copilot-autoviza-link"><span class="copilot-autoviza-icon">&#x1F4CB;</span><span class="copilot-autoviza-text"><strong>Rapport d'historique gratuit</strong><small>Offert par LeBonCoin via Autoviza (valeur 25 \u20AC)</small></span><span class="copilot-autoviza-arrow">&rsaquo;</span></a></div>`;
  }
  function buildEmailBanner() {
    return `<div class="copilot-email-banner" id="copilot-email-section"><button class="copilot-email-btn" id="copilot-email-btn">&#x2709; R\xE9diger un email au vendeur</button><div class="copilot-email-result" id="copilot-email-result" style="display:none;"><textarea class="copilot-email-textarea" id="copilot-email-text" rows="8" readonly></textarea><div class="copilot-email-actions"><button class="copilot-email-copy" id="copilot-email-copy">&#x1F4CB; Copier</button><span class="copilot-email-copied" id="copilot-email-copied" style="display:none;">Copi\xE9 !</span></div></div><div class="copilot-email-loading" id="copilot-email-loading" style="display:none;"><span class="copilot-mini-spinner"></span> G\xE9n\xE9ration en cours...</div><div class="copilot-email-error" id="copilot-email-error" style="display:none;"></div></div>`;
  }

  // extension/ui/popups.js
  function buildResultsPopup(data, options = {}) {
    const { score, is_partial, filters, vehicle, featured_video } = data;
    const { autovizaUrl, bonusSignals } = options;
    const color = scoreColor(score);
    const vehicleInfo = vehicle ? `${vehicle.make || ""} ${vehicle.model || ""} ${vehicle.year || ""}`.trim() : "V\xE9hicule";
    let currencyBadge = "";
    if (vehicle && vehicle.price_original && vehicle.currency) {
      const fmtOrig = vehicle.price_original.toLocaleString("fr-FR");
      const fmtEur = vehicle.price.toLocaleString("fr-FR");
      currencyBadge = `<span class="copilot-currency-badge">${escapeHTML(fmtOrig)} ${escapeHTML(vehicle.currency)} <span style="opacity:0.6">\u2248 ${escapeHTML(fmtEur)} \u20AC</span></span>`;
    }
    const partialBadge = is_partial ? `<span class="copilot-badge-partial">Analyse partielle</span>` : "";
    const l9 = (filters || []).find((f) => f.filter_id === "L9");
    const daysOnline = l9?.details?.days_online;
    const isRepublished = l9?.details?.republished;
    let daysOnlineBadge = "";
    if (daysOnline != null) {
      const badgeColor = daysOnline <= 7 ? "#22c55e" : daysOnline <= 30 ? "#6b7280" : "#f59e0b";
      const label = isRepublished ? `&#x1F4C5; En vente depuis ${daysOnline}j (republi\xE9)` : `&#x1F4C5; ${daysOnline}j en ligne`;
      daysOnlineBadge = `<span class="copilot-days-badge" style="color:${badgeColor}">${label}</span>`;
    }
    let bonusHTML = "";
    if (bonusSignals && bonusSignals.length > 0) {
      bonusHTML = '<div style="margin:12px 0;padding:10px;background:#f0f4ff;border-radius:8px;border:1px solid #d0d8f0;">';
      bonusHTML += '<div style="font-weight:600;font-size:13px;margin-bottom:8px;color:#334155;">Signaux exclusifs</div>';
      for (const signal of bonusSignals) {
        let sIcon, sColor;
        switch (signal.status) {
          case "pass":
            sIcon = "\u2713";
            sColor = "#16a34a";
            break;
          case "warning":
            sIcon = "\u26A0";
            sColor = "#f59e0b";
            break;
          case "fail":
            sIcon = "\u2717";
            sColor = "#ef4444";
            break;
          default:
            sIcon = "\u2139";
            sColor = "#6366f1";
            break;
        }
        bonusHTML += '<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;font-size:12px;">';
        bonusHTML += '<span style="color:#64748b;">' + escapeHTML(signal.label) + "</span>";
        bonusHTML += '<span style="font-weight:600;color:' + sColor + ';">' + sIcon + " " + escapeHTML(signal.value) + "</span>";
        bonusHTML += "</div>";
      }
      bonusHTML += "</div>";
    }
    return `
    <div class="copilot-popup" id="copilot-popup">
      <div class="copilot-popup-header">
        <div class="copilot-popup-title-row">
          <span class="copilot-popup-title">Co-Pilot</span>
          <button class="copilot-popup-close" id="copilot-close">&times;</button>
        </div>
        <p class="copilot-popup-vehicle">${escapeHTML(vehicleInfo)} ${daysOnlineBadge}</p>
        ${currencyBadge ? `<p class="copilot-popup-currency">${currencyBadge}</p>` : ""}
        ${partialBadge}
      </div>
      <div class="copilot-radar-section">
        ${buildRadarSVG(filters, score)}
        <p class="copilot-verdict" style="color:${color}">
          ${score >= 70 ? "Annonce fiable" : score >= 40 ? "Points d'attention" : "Vigilance requise"}
        </p>
      </div>
      <div class="copilot-popup-filters">
        <h3 class="copilot-section-title">D\xE9tails de l'analyse</h3>
        ${buildFiltersList(filters, vehicle)}
      </div>
      ${bonusHTML}
      ${buildPremiumSection()}
      ${buildAutovizaBanner(autovizaUrl)}
      ${buildYouTubeBanner(featured_video)}
      <div class="copilot-carvertical-banner">
        <a href="https://www.carvertical.com/fr" target="_blank" rel="noopener noreferrer"
           class="copilot-carvertical-link" id="copilot-carvertical-btn">
          <img class="copilot-carvertical-logo" src="${typeof chrome !== "undefined" && chrome.runtime ? chrome.runtime.getURL("carvertical_logo.png") : "carvertical_logo.png"}" alt="carVertical"/>
          <span class="copilot-carvertical-text">
            <strong>Historique du v\xE9hicule</strong>
            <small>V\xE9rifier sur carVertical</small>
          </span>
          <span class="copilot-carvertical-arrow">&rsaquo;</span>
        </a>
      </div>
      ${buildEmailBanner()}
      <div class="copilot-popup-footer"><p>Co-Pilot v1.0 &middot; Analyse automatis\xE9e</p></div>
    </div>
  `;
  }
  function buildErrorPopup(message) {
    return `<div class="copilot-popup copilot-popup-error" id="copilot-popup"><div class="copilot-popup-header"><div class="copilot-popup-title-row"><span class="copilot-popup-title">Co-Pilot</span><button class="copilot-popup-close" id="copilot-close">&times;</button></div></div><div class="copilot-error-body"><div class="copilot-error-icon">&#x1F527;</div><p class="copilot-error-message">${escapeHTML(message)}</p><button class="copilot-btn copilot-btn-retry" id="copilot-retry">R\xE9essayer</button></div></div>`;
  }
  function buildNotAVehiclePopup(message, category) {
    return `<div class="copilot-popup" id="copilot-popup"><div class="copilot-popup-header"><div class="copilot-popup-title-row"><span class="copilot-popup-title">Co-Pilot</span><button class="copilot-popup-close" id="copilot-close">&times;</button></div></div><div class="copilot-not-vehicle-body"><div class="copilot-not-vehicle-icon">&#x1F6AB;</div><h3 class="copilot-not-vehicle-title">${escapeHTML(message)}</h3><p class="copilot-not-vehicle-category">Cat&eacute;gorie d&eacute;tect&eacute;e : <strong>${escapeHTML(category || "inconnue")}</strong></p><p class="copilot-not-vehicle-hint">Co-Pilot analyse uniquement les annonces de v&eacute;hicules.</p></div></div>`;
  }
  function buildNotSupportedPopup(message, category) {
    return `<div class="copilot-popup" id="copilot-popup"><div class="copilot-popup-header"><div class="copilot-popup-title-row"><span class="copilot-popup-title">Co-Pilot</span><button class="copilot-popup-close" id="copilot-close">&times;</button></div></div><div class="copilot-not-vehicle-body"><div class="copilot-not-vehicle-icon">&#x1F3CD;</div><h3 class="copilot-not-vehicle-title">${escapeHTML(message)}</h3><p class="copilot-not-vehicle-category">Cat&eacute;gorie : <strong>${escapeHTML(category || "inconnue")}</strong></p><p class="copilot-not-vehicle-hint">On bosse dessus, promis. Restez branch&eacute; !</p></div></div>`;
  }

  // extension/ui/progress.js
  function detectCurrentSite() {
    try {
      const host = String(window.location.hostname || "").toLowerCase();
      if (host.includes("autoscout24.")) return "autoscout24";
      if (host.includes("leboncoin.")) return "leboncoin";
    } catch {
    }
    return null;
  }
  function createProgressTracker() {
    function stepIconHTML(status) {
      switch (status) {
        case "running":
          return '<div class="copilot-mini-spinner"></div>';
        case "done":
          return "\u2713";
        case "warning":
          return "\u26A0";
        case "error":
          return "\u2717";
        case "skip":
          return "\u2014";
        default:
          return "\u25CB";
      }
    }
    function update(stepId, status, detail) {
      const el = document.getElementById("copilot-step-" + stepId);
      if (!el) return;
      el.setAttribute("data-status", status);
      const iconEl = el.querySelector(".copilot-step-icon");
      if (iconEl) {
        iconEl.className = "copilot-step-icon " + status;
        if (status === "running") {
          iconEl.innerHTML = '<div class="copilot-mini-spinner"></div>';
        } else {
          iconEl.textContent = stepIconHTML(status);
        }
      }
      if (detail !== void 0) {
        let detailEl = el.querySelector(".copilot-step-detail");
        if (!detailEl) {
          detailEl = document.createElement("div");
          detailEl.className = "copilot-step-detail";
          el.querySelector(".copilot-step-text").appendChild(detailEl);
        }
        detailEl.textContent = detail;
      }
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    function addSubStep(parentId, text, status, detail) {
      const parentEl = document.getElementById("copilot-step-" + parentId);
      if (!parentEl) return;
      let container = parentEl.querySelector(".copilot-substeps");
      if (!container) {
        container = document.createElement("div");
        container.className = "copilot-substeps";
        parentEl.appendChild(container);
      }
      const subEl = document.createElement("div");
      subEl.className = "copilot-substep";
      const iconSpan = document.createElement("span");
      iconSpan.className = "copilot-substep-icon";
      iconSpan.textContent = stepIconHTML(status);
      subEl.appendChild(iconSpan);
      const textSpan = document.createElement("span");
      let fullText = text;
      if (detail) fullText += " \u2014 " + detail;
      textSpan.textContent = fullText;
      subEl.appendChild(textSpan);
      container.appendChild(subEl);
      subEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    function showFilters(filters) {
      const container = document.getElementById("copilot-progress-filters");
      if (!container || !filters) return;
      filters.forEach(function(f) {
        const color = statusColor(f.status);
        const icon = statusIcon(f.status);
        const label = filterLabel(f.filter_id, f.status);
        const scoreText = f.status === "skip" ? "skip" : Math.round(f.score * 100) + "%";
        const filterDiv = document.createElement("div");
        filterDiv.className = "copilot-progress-filter";
        const iconSpan = document.createElement("span");
        iconSpan.className = "copilot-progress-filter-icon";
        iconSpan.style.color = color;
        iconSpan.textContent = icon;
        filterDiv.appendChild(iconSpan);
        const idSpan = document.createElement("span");
        idSpan.className = "copilot-progress-filter-id";
        idSpan.textContent = f.filter_id;
        filterDiv.appendChild(idSpan);
        const labelSpan = document.createElement("span");
        labelSpan.className = "copilot-progress-filter-label";
        labelSpan.textContent = label;
        filterDiv.appendChild(labelSpan);
        const scoreSpan = document.createElement("span");
        scoreSpan.className = "copilot-progress-filter-score";
        scoreSpan.style.color = color;
        scoreSpan.textContent = scoreText;
        filterDiv.appendChild(scoreSpan);
        container.appendChild(filterDiv);
        const msgDiv = document.createElement("div");
        msgDiv.className = "copilot-progress-filter-msg";
        msgDiv.textContent = f.message;
        container.appendChild(msgDiv);
        if (f.filter_id === "L4" && f.details) {
          appendCascadeDetails(container, f.details);
        }
      });
      container.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    function appendCascadeDetails(container, details) {
      var lines = [];
      if (details.source === "marche_leboncoin" || details.source === "marche_autoscout24") {
        var srcLabel = details.source === "marche_autoscout24" ? "AS24" : "LBC";
        var currentSite = detectCurrentSite();
        var marketSite = details.source === "marche_autoscout24" ? "autoscout24" : "leboncoin";
        var cross = currentSite && currentSite !== marketSite;
        lines.push(
          "Source : march\xE9 " + srcLabel + (cross ? " (externe au site courant)" : "") + " (" + (details.sample_count || "?") + " annonces" + (details.precision ? ", pr\xE9cision " + details.precision : "") + ")"
        );
      } else if (details.source === "argus_seed") {
        lines.push("Source : Argus (donn\xE9es seed)");
      }
      if (details.cascade_tried) {
        details.cascade_tried.forEach(function(tier) {
          var result = details["cascade_" + tier + "_result"] || "non essay\xE9";
          var tierLabel = tier === "market_price" ? "March\xE9 crowdsourc\xE9" : "Argus Seed";
          var tierIcon = result === "found" ? "\u2713" : result === "insufficient" ? "\u26A0" : "\u2014";
          lines.push(tierIcon + " " + tierLabel + " : " + result);
        });
      }
      lines.forEach(function(line) {
        var div = document.createElement("div");
        div.className = "copilot-cascade-detail";
        div.textContent = line;
        container.appendChild(div);
      });
    }
    function showScore(score, verdict) {
      const container = document.getElementById("copilot-progress-score");
      if (!container) return;
      const color = scoreColor(score);
      const labelDiv = document.createElement("div");
      labelDiv.className = "copilot-progress-score-label";
      labelDiv.textContent = "Score global";
      container.appendChild(labelDiv);
      const valueDiv = document.createElement("div");
      valueDiv.className = "copilot-progress-score-value";
      valueDiv.style.color = color;
      valueDiv.textContent = String(score);
      container.appendChild(valueDiv);
      const verdictDiv = document.createElement("div");
      verdictDiv.className = "copilot-progress-score-verdict";
      verdictDiv.style.color = color;
      verdictDiv.textContent = verdict;
      container.appendChild(verdictDiv);
      container.style.display = "block";
      container.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    return { update, addSubStep, showFilters, showScore };
  }
  function showProgress() {
    removePopup();
    const html = [
      '<div class="copilot-popup" id="copilot-popup">',
      '  <div class="copilot-popup-header">',
      '    <div class="copilot-popup-title-row">',
      '      <span class="copilot-popup-title">Co-Pilot</span>',
      '      <button class="copilot-popup-close" id="copilot-close">&times;</button>',
      "    </div>",
      '    <p class="copilot-popup-vehicle" id="copilot-progress-vehicle">Analyse en cours...</p>',
      "  </div>",
      '  <div class="copilot-progress-body">',
      '    <div class="copilot-progress-phase">',
      '      <div class="copilot-progress-phase-title">1. Extraction</div>',
      `      <div class="copilot-step" id="copilot-step-extract" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Extraction des donn\xE9es de l'annonce</div></div>`,
      '      <div class="copilot-step" id="copilot-step-phone" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">R\xE9v\xE9lation du num\xE9ro de t\xE9l\xE9phone</div></div>',
      "    </div>",
      '    <div class="copilot-progress-phase">',
      '      <div class="copilot-progress-phase-title">2. Collecte prix march\xE9</div>',
      '      <div class="copilot-step" id="copilot-step-job" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Demande au serveur : quel v\xE9hicule collecter ?</div></div>',
      '      <div class="copilot-step" id="copilot-step-collect" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Collecte des prix (cascade recherche)</div></div>',
      '      <div class="copilot-step" id="copilot-step-submit" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Envoi des prix au serveur</div></div>',
      '      <div class="copilot-step" id="copilot-step-bonus" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Collecte bonus multi-r\xE9gion</div></div>',
      "    </div>",
      '    <div class="copilot-progress-phase">',
      '      <div class="copilot-progress-phase-title">3. Analyse serveur</div>',
      '      <div class="copilot-step" id="copilot-step-analyze" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Analyse des 10 filtres (L1 \u2013 L10)</div></div>',
      '      <div id="copilot-progress-filters" class="copilot-progress-filters"></div>',
      '      <div class="copilot-step" id="copilot-step-autoviza" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">D\xE9tection rapport Autoviza</div></div>',
      "    </div>",
      '    <hr class="copilot-progress-separator">',
      '    <div id="copilot-progress-score" class="copilot-progress-score" style="display:none"></div>',
      '    <div style="text-align:center; padding: 12px 0;">',
      `      <button class="copilot-btn copilot-btn-retry" id="copilot-progress-details-btn" style="display:none">Voir l'analyse compl\xE8te</button>`,
      "    </div>",
      "  </div>",
      '  <div class="copilot-popup-footer"><p>Co-Pilot v1.0 &middot; Analyse en temps r\xE9el</p></div>',
      "</div>"
    ].join("\n");
    showPopup(html);
    return createProgressTracker();
  }

  // extension/content.js
  var API_URL = true ? "http://localhost:5001/api/analyze" : "http://localhost:5001/api/analyze";
  var lastScanId = null;
  var ERROR_MESSAGES = [
    "Oh mince, on a crev\xE9 ! R\xE9essayez dans un instant.",
    "Le moteur a cal\xE9... Notre serveur fait une pause, retentez !",
    "Panne s\xE8che ! Impossible de joindre le serveur.",
    "Embrayage patin\xE9... L'analyse n'a pas pu d\xE9marrer.",
    "Vidange en cours ! Le serveur revient dans un instant."
  ];
  function getRandomErrorMessage() {
    return ERROR_MESSAGES[Math.floor(Math.random() * ERROR_MESSAGES.length)];
  }
  async function runAnalysis(injectedExtractor) {
    const extractor = injectedExtractor || getExtractor(window.location.href);
    if (!extractor) {
      showPopup(buildErrorPopup("Site non support\xE9."));
      return;
    }
    const progress = showProgress();
    progress.update("extract", "running");
    const payload = await extractor.extract();
    if (!payload) {
      console.warn("[CoPilot] extract() \u2192 null");
      progress.update("extract", "error", "Impossible de lire les donn\xE9es");
      showPopup(buildErrorPopup("Impossible de lire les donn\xE9es de cette page."));
      return;
    }
    const adId = payload.next_data?.props?.pageProps?.ad?.list_id || "";
    progress.update("extract", "done", adId ? "ID annonce : " + adId : "Donn\xE9es extraites");
    const summary = extractor.getVehicleSummary();
    const vehicleLabel = document.getElementById("copilot-progress-vehicle");
    if (vehicleLabel && summary?.make) {
      vehicleLabel.textContent = [summary.make, summary.model, summary.year].filter(Boolean).join(" ");
    }
    if (extractor.hasPhone()) {
      if (extractor.isLoggedIn()) {
        progress.update("phone", "running");
        const phone = await extractor.revealPhone();
        if (phone) {
          progress.update("phone", "done", phone.replace(/(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})/, "$1 $2 $3 $4 $5"));
        } else {
          progress.update("phone", "warning", "Num\xE9ro non r\xE9cup\xE9r\xE9");
        }
      } else {
        progress.update("phone", "skip", "Non connect\xE9");
      }
    } else {
      progress.update("phone", "skip", "Pas de t\xE9l\xE9phone");
    }
    let collectInfo = { submitted: false };
    try {
      collectInfo = await extractor.collectMarketPrices(progress);
    } catch (err) {
      console.error("[CoPilot] collectMarketPrices erreur:", err);
      progress.update("job", "error", "Erreur collecte");
    }
    if (!collectInfo.submitted) {
      const jobEl = document.getElementById("copilot-step-job");
      if (jobEl && jobEl.getAttribute("data-status") === "pending") {
        progress.update("job", "skip", "Collecte non disponible");
        progress.update("collect", "skip");
        progress.update("submit", "skip");
        progress.update("bonus", "skip");
      }
    }
    progress.update("analyze", "running");
    const apiBody = payload.type === "raw" ? { url: window.location.href, next_data: payload.next_data } : { url: window.location.href, ad_data: payload.ad_data, source: payload.source };
    async function fetchAnalysisOnce() {
      const response = await backendFetch(API_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(apiBody) });
      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        if (errorData?.error === "NOT_A_VEHICLE") {
          progress.update("analyze", "skip", "Pas une voiture");
          showPopup(buildNotAVehiclePopup(errorData.message, errorData.data?.category));
          return null;
        }
        if (errorData?.error === "NOT_SUPPORTED") {
          progress.update("analyze", "skip", errorData.message);
          showPopup(buildNotSupportedPopup(errorData.message, errorData.data?.category));
          return null;
        }
        const msg = errorData?.message || getRandomErrorMessage();
        progress.update("analyze", "error", msg);
        showPopup(buildErrorPopup(msg));
        return null;
      }
      const result = await response.json();
      if (!result.success) {
        progress.update("analyze", "error", result.message || "Erreur serveur");
        showPopup(buildErrorPopup(result.message || getRandomErrorMessage()));
        return null;
      }
      return result;
    }
    try {
      let result = await fetchAnalysisOnce();
      if (!result) return;
      if (collectInfo.submitted && collectInfo.isCurrentVehicle) {
        const l4 = (result?.data?.filters || []).find((f) => f.filter_id === "L4");
        if (l4 && l4.status === "skip") {
          progress.update("analyze", "running", "Retry L4...");
          await sleep(2e3);
          const retried = await fetchAnalysisOnce();
          if (retried) result = retried;
        }
      }
      lastScanId = result.data.scan_id || null;
      progress.update("analyze", "done", (result.data.filters || []).length + " filtres analys\xE9s");
      progress.showFilters(result.data.filters || []);
      const score = result.data.score;
      const verdict = score >= 70 ? "Annonce fiable" : score >= 40 ? "Points d'attention" : "Vigilance requise";
      progress.showScore(score, verdict);
      progress.update("autoviza", "running");
      const freeReportUrl = await extractor.detectFreeReport();
      progress.update("autoviza", freeReportUrl ? "done" : "skip", freeReportUrl ? "Rapport gratuit trouv\xE9" : "Aucun rapport disponible");
      const bonusSignals = extractor.getBonusSignals();
      const detailsBtn = document.getElementById("copilot-progress-details-btn");
      if (detailsBtn) {
        detailsBtn.style.display = "inline-block";
        detailsBtn.addEventListener("click", function() {
          showPopup(buildResultsPopup(result.data, { autovizaUrl: freeReportUrl, bonusSignals }));
        });
      }
    } catch (err) {
      progress.update("analyze", "error", "Erreur inattendue");
      showPopup(buildErrorPopup(getRandomErrorMessage()));
    }
  }
  function isAdPage() {
    return isAdPageLBC();
  }
  function init() {
    const extractor = getExtractor(window.location.href);
    if (!extractor || !extractor.isAdPage(window.location.href)) return;
    removePopup();
    if (window.__copilotRunning) return;
    window.__copilotRunning = true;
    initLbcDeps({ backendFetch, sleep, apiUrl: API_URL });
    initDom({ runAnalysis, apiUrl: API_URL, getLastScanId: () => lastScanId });
    extractor.initDeps({ fetch: backendFetch, apiUrl: API_URL });
    runAnalysis(extractor).finally(() => {
      window.__copilotRunning = false;
    });
  }
  init();
})();
