"use strict";
(() => {
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

  // extension/extractors/leboncoin.js
  var _backendFetch;
  var _sleep;
  var _apiUrl;
  function initLbcDeps(deps) {
    _backendFetch = deps.backendFetch;
    _sleep = deps.sleep;
    _apiUrl = deps.apiUrl;
  }
  function isChromeRuntimeAvailable() {
    try {
      return typeof chrome !== "undefined" && !!chrome.runtime && typeof chrome.runtime.sendMessage === "function";
    } catch {
      return false;
    }
  }
  function isBenignRuntimeTeardownError(err) {
    const msg = String(err?.message || err || "").toLowerCase();
    return msg.includes("extension context invalidated") || msg.includes("runtime_unavailable_for_local_backend") || msg.includes("receiving end does not exist");
  }
  var GENERIC_MODELS = ["autres", "autre", "other", "divers"];
  var EXCLUDED_CATEGORIES = ["motos", "equipement_moto", "caravaning", "nautisme"];
  var LBC_BRAND_ALIASES = {
    MERCEDES: "MERCEDES-BENZ"
  };
  var LBC_REGIONS = {
    // Regions post-2016
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
    // Anciennes regions (pre-2016) -- LBC retourne parfois ces noms
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
    "electrique": 4,
    "\xE9lectrique": 4,
    "hybride": 6,
    "hybride rechargeable": 7,
    "gpl": 3,
    "\xE9lectrique & essence": 6,
    "electrique & essence": 6,
    "\xE9lectrique & diesel": 6,
    "electrique & diesel": 6
  };
  var LBC_GEARBOX_CODES = {
    "manuelle": 1,
    "automatique": 2
  };
  var COLLECT_COOLDOWN_MS = 24 * 60 * 60 * 1e3;
  var DEFAULT_SEARCH_RADIUS = 3e4;
  var MIN_PRICES_FOR_ARGUS = 20;
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
      if (attempt < 3) await _sleep(800);
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
  function isAdPageLBC() {
    const url = window.location.href;
    return url.includes("leboncoin.fr/ad/") || url.includes("leboncoin.fr/voitures/");
  }
  function getHorsePowerRange(hp) {
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
  function filterAndMapSearchAds(ads, targetYear, yearSpread) {
    return ads.filter((ad) => {
      const rawPrice = Array.isArray(ad?.price) ? ad.price[0] : ad?.price;
      const priceInt = typeof rawPrice === "number" ? rawPrice : parseInt(String(rawPrice || "0").replace(/[^\d]/g, ""), 10);
      if (!Number.isFinite(priceInt) || priceInt <= 500) return false;
      if (targetYear >= 1990) {
        const adYear = getAdYear(ad);
        if (adYear && Math.abs(adYear - targetYear) > yearSpread) return false;
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
  async function fetchSearchPrices(searchUrl, targetYear, yearSpread) {
    let ads = null;
    try {
      ads = await fetchSearchPricesViaApi(searchUrl);
      if (ads && ads.length > 0) {
        console.log("[CoPilot] fetchSearchPrices (API): %d ads bruts", ads.length);
        return filterAndMapSearchAds(ads, targetYear, yearSpread);
      }
    } catch (err) {
      console.debug("[CoPilot] API finder indisponible:", err.message);
    }
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
  function buildLocationParam(location2, radiusMeters) {
    if (!location2) return "";
    const radius = radiusMeters || DEFAULT_SEARCH_RADIUS;
    if (location2.lat && location2.lng && location2.city && location2.zipcode) {
      return `${location2.city}_${location2.zipcode}__${location2.lat}_${location2.lng}_5000_${radius}`;
    }
    return LBC_REGIONS[location2.region] || "";
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
  async function reportJobDone(jobDoneUrl, jobId, success) {
    if (!jobId) return;
    try {
      await _backendFetch(jobDoneUrl, {
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
    const marketUrl = _apiUrl.replace("/analyze", "/market-prices");
    const jobDoneUrl = _apiUrl.replace("/analyze", "/market-prices/job-done");
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
        if (jobYear >= 1990) searchUrl += `&regdate=${jobYear - 1}-${jobYear + 1}`;
        const bonusPrices = await fetchSearchPrices(searchUrl, jobYear, 1);
        console.log("[CoPilot] bonus job %s %s %d %s: %d prix", job.make, job.model, job.year, job.region, bonusPrices.length);
        if (progress) {
          const stepStatus = bonusPrices.length >= MIN_BONUS_PRICES ? "done" : "skip";
          progress.addSubStep("bonus", job.make + " " + job.model + " \xB7 " + job.region, stepStatus, bonusPrices.length + " annonces");
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
                filters_applied: [
                  ...filters.includes("fuel=") ? ["fuel"] : [],
                  ...filters.includes("gearbox=") ? ["gearbox"] : [],
                  ...filters.includes("horse_power_din=") ? ["hp"] : []
                ],
                ads_found: bonusPrices.length,
                url: searchUrl,
                was_selected: true,
                reason: `bonus job queue: ${bonusPrices.length} annonces`
              }]
            };
            const bResp = await _backendFetch(marketUrl, {
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
    const jobUrl = _apiUrl.replace("/analyze", "/market-prices/next-job") + `?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}&year=${encodeURIComponent(year)}&region=${encodeURIComponent(region)}` + (fuelForJob ? `&fuel=${encodeURIComponent(fuelForJob)}` : "") + (gearboxForJob ? `&gearbox=${encodeURIComponent(gearboxForJob)}` : "") + (hpRange ? `&hp_range=${encodeURIComponent(hpRange)}` : "");
    let jobResp;
    try {
      console.log("[CoPilot] next-job \u2192", jobUrl);
      jobResp = await _backendFetch(jobUrl).then((r) => r.json());
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
      localStorage.setItem("copilot_last_collect", String(Date.now()));
      return { submitted: false };
    }
    const target = jobResp.data.vehicle;
    const targetRegion = jobResp.data.region;
    const isRedirect = !!jobResp.data.redirect;
    const bonusJobs = jobResp.data.bonus_jobs || [];
    console.log("[CoPilot] next-job: %d bonus jobs", bonusJobs.length);
    const isCurrentVehicle = target.make.toLowerCase() === make.toLowerCase() && target.model.toLowerCase() === model.toLowerCase();
    if (!isCurrentVehicle) {
      const lastCollect = parseInt(localStorage.getItem("copilot_last_collect") || "0", 10);
      if (Date.now() - lastCollect < COLLECT_COOLDOWN_MS) {
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
        const locLabel = strategy.loc === geoParam && geoParam ? "G\xE9o (" + (location2?.city || "local") + " 30km)" : strategy.loc === regionParam && regionParam ? "R\xE9gion (" + targetRegion + ")" : "National";
        const strategyLabel = "Strat\xE9gie " + (i + 1) + " \xB7 " + locLabel + " \xB1" + strategy.yearSpread + "an";
        prices = await fetchSearchPrices(searchUrl, targetYear, strategy.yearSpread);
        const enoughPrices = prices.length >= MIN_PRICES_FOR_ARGUS;
        console.log(
          "[CoPilot] strategie %d (precision=%d): %d prix trouv\xE9s | %s",
          i + 1,
          strategy.precision,
          prices.length,
          searchUrl.substring(0, 150)
        );
        if (progress) {
          const stepStatus = enoughPrices ? "done" : "skip";
          const stepDetail = prices.length + " annonces" + (enoughPrices ? " \u2713 seuil atteint" : "");
          progress.addSubStep("collect", strategyLabel, stepStatus, stepDetail);
        }
        const locationType = strategy.loc === geoParam && geoParam ? "geo" : strategy.loc === regionParam && regionParam ? "region" : "national";
        searchLog.push({
          step: i + 1,
          precision: strategy.precision,
          location_type: locationType,
          year_spread: strategy.yearSpread,
          filters_applied: [
            ...strategy.filters.includes("fuel=") ? ["fuel"] : [],
            ...strategy.filters.includes("gearbox=") ? ["gearbox"] : [],
            ...strategy.filters.includes("horse_power_din=") ? ["hp"] : [],
            ...strategy.filters.includes("mileage=") ? ["km"] : []
          ],
          ads_found: prices.length,
          url: searchUrl,
          was_selected: enoughPrices,
          reason: enoughPrices ? `${prices.length} annonces >= ${MIN_PRICES_FOR_ARGUS} minimum` : `${prices.length} annonces < ${MIN_PRICES_FOR_ARGUS} minimum`
        });
        if (enoughPrices) {
          collectedPrecision = strategy.precision;
          console.log("[CoPilot] assez de prix (%d >= %d), precision=%d", prices.length, MIN_PRICES_FOR_ARGUS, collectedPrecision);
          break;
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
          site_model_token: isCurrentVehicle ? vehicle.site_model_token : null
        };
        console.log("[CoPilot] POST /api/market-prices:", target.make, target.model, target.year, targetRegion, "fuel=", payload.fuel, "n=", priceInts.length);
        const marketResp = await _backendFetch(marketUrl, {
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
              search_log: searchLog
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
    localStorage.setItem("copilot_last_collect", String(Date.now()));
    return { submitted, isCurrentVehicle };
  }
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

  // extension/extractors/autoscout24.js
  var AS24_URL_PATTERNS = [
    /autoscout24\.\w+\/(?:fr|de|it|en|nl|es)?\/?d\//,
    /autoscout24\.\w+\/angebote\//,
    /autoscout24\.\w+\/offerte\//,
    /autoscout24\.\w+\/ofertas\//,
    /autoscout24\.\w+\/aanbod\//
  ];
  var AD_PAGE_PATTERN = /autoscout24\.\w+\/.*\/d\/.*-\d+/;
  var TLD_TO_COUNTRY = {
    ch: "Suisse",
    de: "Allemagne",
    fr: "France",
    it: "Italie",
    at: "Autriche",
    be: "Belgique",
    nl: "Pays-Bas",
    es: "Espagne"
  };
  var TLD_TO_CURRENCY = {
    ch: "CHF"
  };
  var CHF_TO_EUR = 0.94;
  var TLD_TO_COUNTRY_CODE = {
    ch: "CH",
    de: "DE",
    fr: "FR",
    it: "IT",
    at: "AT",
    be: "BE",
    nl: "NL",
    es: "ES"
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
  function getCantonFromZip(zipcode) {
    const zip = String(zipcode || "").trim();
    if (zip.length < 4) return null;
    const prefix = zip.slice(0, 2);
    return SWISS_ZIP_TO_CANTON[prefix] || null;
  }
  var MIN_PRICES = 10;
  var FUEL_MAP = {
    gasoline: "Essence",
    diesel: "Diesel",
    electric: "Electrique",
    "mhev-diesel": "Diesel",
    "mhev-gasoline": "Essence",
    "phev-diesel": "Hybride Rechargeable",
    "phev-gasoline": "Hybride Rechargeable",
    cng: "GNV",
    lpg: "GPL",
    hydrogen: "Hydrogene"
  };
  function mapFuelType(fuelType) {
    const key = (fuelType || "").toLowerCase();
    return FUEL_MAP[key] || fuelType;
  }
  var TRANSMISSION_MAP = {
    automatic: "Automatique",
    manual: "Manuelle",
    "semi-automatic": "Automatique"
  };
  function mapTransmission(transmission) {
    const key = (transmission || "").toLowerCase();
    return TRANSMISSION_MAP[key] || transmission;
  }
  var AS24_GEAR_MAP = {
    automatic: "A",
    automatique: "A",
    "semi-automatic": "A",
    manual: "M",
    manuelle: "M"
  };
  function getAs24GearCode(gearbox) {
    return AS24_GEAR_MAP[(gearbox || "").toLowerCase()] || null;
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
  function getHpRangeString(hp) {
    if (!hp || hp <= 0) return null;
    if (hp < 80) return "min-90";
    if (hp < 110) return "70-120";
    if (hp < 140) return "100-150";
    if (hp < 180) return "130-190";
    if (hp < 250) return "170-260";
    if (hp < 350) return "240-360";
    return "340-max";
  }
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
  function getCantonCenterZip(canton) {
    return CANTON_CENTER_ZIP[canton] || null;
  }
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
      const match = u.pathname.match(/\/d\/([^/]+)-(\d+)(?:\/|$)/i);
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
  function fallbackAdDataFromDom(doc, url) {
    const h1 = doc.querySelector("h1")?.textContent?.trim() || null;
    const title = h1 || doc.querySelector('meta[property="og:title"]')?.getAttribute("content") || doc.title || null;
    const priceMeta = doc.querySelector('meta[property="product:price:amount"]')?.getAttribute("content");
    const price = priceMeta ? Number(String(priceMeta).replace(/[^\d.]/g, "")) : null;
    const currency = doc.querySelector('meta[property="product:price:currency"]')?.getAttribute("content") || null;
    const fromUrl = extractMakeModelFromUrl(url);
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
      color: null,
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
      description: null,
      owner_type: "private",
      owner_name: null,
      siret: null,
      raw_attributes: {},
      image_count: 0,
      has_phone: false,
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
  function parseRSCPayload(doc) {
    const scripts = doc.querySelectorAll("script");
    for (const script of scripts) {
      const text = script.textContent || "";
      if (!text.includes("vehicleCategory") && !text.includes("firstRegistrationDate")) {
        continue;
      }
      const searchText = text.includes("self.__next_f") ? text.replace(/\\+"/g, '"') : text;
      for (const candidate of extractJsonObjects(searchText)) {
        if (!candidate.includes('"vehicleCategory"') && !candidate.includes('"firstRegistrationDate"')) {
          continue;
        }
        try {
          const parsed = JSON.parse(candidate);
          const vehicle = findVehicleNode(parsed);
          if (vehicle) return vehicle;
        } catch {
        }
      }
    }
    return null;
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
  function normalizeToAdData(rsc, jsonLd) {
    const ld = jsonLd || {};
    const offers = ld.offers || {};
    const seller = offers.seller || {};
    const sellerAddress = seller.address || {};
    const engine = ld.vehicleEngine || {};
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
      return ld.brand?.name || (typeof ld.brand === "string" ? ld.brand : null) || null;
    }
    function resolveModel() {
      if (rsc) {
        const m = typeof rsc.model === "string" ? rsc.model : rsc.model?.name;
        if (m) return m;
      }
      return ld.model || null;
    }
    const rating = seller.aggregateRating || {};
    const dealerRating = rating.ratingValue ?? null;
    const dealerReviewCount = rating.reviewCount ?? null;
    const zipcode = sellerAddress.postalCode || null;
    const tld = typeof window !== "undefined" ? extractTld(window.location.href) : null;
    const countryCode = tld ? TLD_TO_COUNTRY_CODE[tld] || null : null;
    const derivedRegion = tld === "ch" && zipcode ? getCantonFromZip(zipcode) : null;
    if (rsc) {
      return {
        title: rsc.versionFullName || ld.name || null,
        price_eur: rsc.price ?? offers.price ?? null,
        currency: offers.priceCurrency || null,
        make: resolveMake(),
        model: resolveModel(),
        year_model: rsc.firstRegistrationYear || ld.vehicleModelDate || null,
        mileage_km: rsc.mileage ?? ld.mileageFromOdometer?.value ?? null,
        fuel: rsc.fuelType ? mapFuelType(rsc.fuelType) : engine.fuelType || null,
        gearbox: rsc.transmissionType ? mapTransmission(rsc.transmissionType) : ld.vehicleTransmission || null,
        doors: rsc.doors ?? ld.numberOfDoors ?? null,
        seats: rsc.seats ?? ld.vehicleSeatingCapacity ?? null,
        first_registration: rsc.firstRegistrationDate || null,
        color: rsc.bodyColor || ld.color || null,
        power_fiscal_cv: null,
        power_din_hp: rsc.horsePower ?? engine.enginePower?.value ?? null,
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
        description: rsc.teaser || null,
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
        days_online: null,
        index_date: rsc.lastModifiedDate || null,
        days_since_refresh: null,
        republished: false,
        lbc_estimation: null
      };
    }
    return {
      title: ld.name || null,
      price_eur: offers.price ?? null,
      currency: offers.priceCurrency || null,
      make: ld.brand?.name || null,
      model: ld.model || null,
      year_model: ld.vehicleModelDate || null,
      mileage_km: ld.mileageFromOdometer?.value ?? null,
      fuel: engine.fuelType || null,
      gearbox: ld.vehicleTransmission || null,
      doors: ld.numberOfDoors ?? null,
      seats: ld.vehicleSeatingCapacity ?? null,
      first_registration: null,
      color: ld.color || null,
      power_fiscal_cv: null,
      power_din_hp: engine.enginePower?.value ?? null,
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
      description: null,
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
    const seller = ld.offers?.seller || {};
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
  function extractTld(url) {
    const match = url.match(/autoscout24\.(\w+)/);
    return match ? match[1] : "de";
  }
  function buildSearchUrl(makeKey, modelKey, year, tld, options = {}) {
    const { yearSpread = 1, fuel, gear, powerfrom, powerto, kmfrom, kmto, zip, radius } = options;
    const base = `https://www.autoscout24.${tld}/lst/${makeKey}/${modelKey}`;
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
  function parseSearchPrices(html) {
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
    const seen = /* @__PURE__ */ new Set();
    return results.filter((r) => {
      const key = `${r.price}-${r.km}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }
  var AutoScout24Extractor = class extends SiteExtractor {
    static SITE_ID = "autoscout24";
    static URL_PATTERNS = AS24_URL_PATTERNS;
    /** @type {object|null} Cached RSC data */
    _rsc = null;
    /** @type {object|null} Cached JSON-LD data */
    _jsonLd = null;
    /** @type {object|null} Cached ad_data */
    _adData = null;
    /**
     * @param {string} url
     * @returns {boolean}
     */
    isAdPage(url) {
      return AD_PAGE_PATTERN.test(url);
    }
    /**
     * Extracts vehicle data from the current page.
     * @returns {Promise<{type: string, source: string, ad_data: object}|null>}
     */
    async extract() {
      this._rsc = parseRSCPayload(document);
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
      return {
        type: "normalized",
        source: "autoscout24",
        ad_data: this._adData
      };
    }
    /**
     * @returns {{make: string, model: string, year: string}|null}
     */
    getVehicleSummary() {
      if (!this._adData) return null;
      return {
        make: this._adData.make || "",
        model: this._adData.model || "",
        year: String(this._adData.year_model || "")
      };
    }
    /**
     * AS24 phone data is public (JSON-LD), no login needed.
     * @returns {boolean}
     */
    isLoggedIn() {
      return true;
    }
    /**
     * Returns the phone number already extracted from JSON-LD.
     * No DOM interaction needed (unlike LBC where a button click reveals it).
     * @returns {Promise<string|null>}
     */
    async revealPhone() {
      return this._adData?.phone || null;
    }
    /**
     * AS24 ads include the phone in JSON-LD (seller.telephone).
     * @returns {boolean}
     */
    hasPhone() {
      return Boolean(this._adData?.phone);
    }
    /**
     * @returns {Array<{label: string, value: string, status: string}>}
     */
    getBonusSignals() {
      return buildBonusSignals(this._rsc, this._jsonLd);
    }
    /**
     * Collects market prices from AS24 search results for the current vehicle.
     * Uses a 7-strategy cascade (precision 5→1) matching LBC parity:
     *   1. ZIP+30km ±1yr, all filters (fuel+gear+hp+km)
     *   2. Canton center+50km ±1yr, all filters
     *   3. Canton center+50km ±2yrs, fuel+gear+hp (no km)
     *   4. National ±1yr, fuel+gear+hp
     *   5. National ±2yrs, fuel+gear
     *   6. National ±2yrs, fuel only
     *   7. National ±3yrs, no filters
     *
     * @param {object} progress - Progress tracker for UI updates
     * @returns {Promise<{submitted: boolean, isCurrentVehicle: boolean}>}
     */
    async collectMarketPrices(progress) {
      if (!this._adData?.make || !this._adData?.model || !this._adData?.year_model) {
        return { submitted: false, isCurrentVehicle: false };
      }
      if (!this._fetch || !this._apiUrl) {
        console.warn("[CoPilot] AS24 collectMarketPrices: deps not injected");
        return { submitted: false, isCurrentVehicle: false };
      }
      const tld = extractTld(window.location.href);
      const countryName = TLD_TO_COUNTRY[tld] || "Europe";
      const countryCode = TLD_TO_COUNTRY_CODE[tld] || "FR";
      const currency = TLD_TO_CURRENCY[tld] || "EUR";
      const makeKey = (this._rsc?.make?.key || this._adData.make).toLowerCase();
      const modelKey = (this._rsc?.model?.key || this._adData.model).toLowerCase();
      const year = parseInt(this._adData.year_model, 10);
      const fuelKey = this._rsc?.fuelType || null;
      const hp = parseInt(this._adData.power_din_hp, 10) || 0;
      const km = parseInt(this._adData.mileage_km, 10) || 0;
      const gearRaw = this._rsc?.transmissionType || "";
      const gearCode = getAs24GearCode(gearRaw);
      const powerParams = getAs24PowerParams(hp);
      const kmParams = getAs24KmParams(km);
      const hpRangeStr = getHpRangeString(hp);
      const zipcode = this._adData?.location?.zipcode;
      const canton = tld === "ch" && zipcode ? getCantonFromZip(zipcode) : null;
      const region = canton || countryName;
      const cantonZip = canton ? getCantonCenterZip(canton) : null;
      if (progress) progress.update("job", "done", `${this._adData.make} ${this._adData.model} ${year} (${region})`);
      const strategies = [];
      if (zipcode) {
        strategies.push({
          yearSpread: 1,
          fuel: fuelKey,
          gear: gearCode,
          ...powerParams,
          ...kmParams,
          zip: zipcode,
          radius: 30,
          precision: 5,
          label: `ZIP ${zipcode} +30km`
        });
      }
      if (cantonZip) {
        strategies.push({
          yearSpread: 1,
          fuel: fuelKey,
          gear: gearCode,
          ...powerParams,
          ...kmParams,
          zip: cantonZip,
          radius: 50,
          precision: 4,
          label: `${canton} \xB11an`
        });
      }
      if (cantonZip) {
        strategies.push({
          yearSpread: 2,
          fuel: fuelKey,
          gear: gearCode,
          ...powerParams,
          zip: cantonZip,
          radius: 50,
          precision: 4,
          label: `${canton} \xB12ans`
        });
      }
      strategies.push({
        yearSpread: 1,
        fuel: fuelKey,
        gear: gearCode,
        ...powerParams,
        precision: 3,
        label: "National \xB11an"
      });
      strategies.push({
        yearSpread: 2,
        fuel: fuelKey,
        gear: gearCode,
        precision: 3,
        label: "National \xB12ans"
      });
      strategies.push({
        yearSpread: 2,
        fuel: fuelKey,
        precision: 2,
        label: "National fuel"
      });
      strategies.push({
        yearSpread: 3,
        precision: 1,
        label: "National large"
      });
      let prices = [];
      let usedPrecision = null;
      const searchLog = [];
      if (progress) progress.update("collect", "running");
      for (let i = 0; i < strategies.length; i++) {
        if (i > 0) await new Promise((r) => setTimeout(r, 600 + Math.random() * 400));
        const { precision, label, ...searchOpts } = strategies[i];
        const searchUrl = buildSearchUrl(makeKey, modelKey, year, tld, searchOpts);
        try {
          const resp = await fetch(searchUrl, { credentials: "same-origin" });
          if (!resp.ok) {
            console.warn(`[CoPilot] AS24 search HTTP ${resp.status}: ${searchUrl}`);
            searchLog.push({
              step: i + 1,
              precision,
              label,
              ads_found: 0,
              url: searchUrl,
              was_selected: false,
              reason: `HTTP ${resp.status}`
            });
            if (progress) progress.addSubStep?.("collect", `Strat\xE9gie ${i + 1} \xB7 ${label}`, "skip", `HTTP ${resp.status}`);
            continue;
          }
          const html = await resp.text();
          prices = parseSearchPrices(html);
          const enough = prices.length >= MIN_PRICES;
          console.log(
            "[CoPilot] AS24 strategie %d (precision=%d): %d prix | %s",
            i + 1,
            precision,
            prices.length,
            searchUrl.substring(0, 150)
          );
          searchLog.push({
            step: i + 1,
            precision,
            label,
            ads_found: prices.length,
            url: searchUrl,
            was_selected: enough,
            reason: enough ? `${prices.length} >= ${MIN_PRICES}` : `${prices.length} < ${MIN_PRICES}`
          });
          if (progress) {
            progress.addSubStep?.(
              "collect",
              `Strat\xE9gie ${i + 1} \xB7 ${label}`,
              enough ? "done" : "skip",
              `${prices.length} annonces`
            );
          }
          if (enough) {
            usedPrecision = precision;
            break;
          }
        } catch (err) {
          console.error("[CoPilot] AS24 search error:", err);
          searchLog.push({
            step: i + 1,
            precision,
            label,
            ads_found: 0,
            url: searchUrl,
            was_selected: false,
            reason: err.message
          });
          if (progress) progress.addSubStep?.("collect", `Strat\xE9gie ${i + 1} \xB7 ${label}`, "skip", "Erreur");
        }
      }
      if (prices.length >= MIN_PRICES) {
        let priceInts = prices.map((p) => p.price);
        let priceDetails = prices;
        if (currency === "CHF") {
          priceInts = priceInts.map((p) => Math.round(p * CHF_TO_EUR));
          priceDetails = prices.map((p) => ({
            ...p,
            price: Math.round(p.price * CHF_TO_EUR)
          }));
        }
        if (progress) {
          progress.update("collect", "done", `${priceInts.length} prix (pr\xE9cision ${usedPrecision})`);
          progress.update("submit", "running");
        }
        const marketUrl = this._apiUrl.replace("/analyze", "/market-prices");
        const payload = {
          make: this._adData.make,
          model: this._adData.model,
          year,
          region,
          prices: priceInts,
          price_details: priceDetails,
          fuel: this._adData.fuel ? this._adData.fuel.toLowerCase() : null,
          precision: usedPrecision,
          country: countryCode,
          hp_range: hpRangeStr,
          gearbox: this._adData.gearbox ? this._adData.gearbox.toLowerCase() : null,
          search_log: searchLog
        };
        try {
          const resp = await this._fetch(marketUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          if (resp.ok) {
            if (progress) {
              progress.update("submit", "done", `${priceInts.length} prix envoy\xE9s (${region})`);
              progress.update("bonus", "skip", "Pas de jobs bonus");
            }
            return { submitted: true, isCurrentVehicle: true };
          }
          const errBody = await resp.json().catch(() => null);
          console.warn("[CoPilot] AS24 market-prices POST failed:", resp.status, errBody);
          if (progress) progress.update("submit", "error", `Erreur serveur (${resp.status})`);
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
              make: this._adData.make,
              model: this._adData.model,
              year,
              region,
              fuel: fuelKey || null,
              hp_range: hpRangeStr,
              country: countryCode,
              search_log: searchLog
            })
          });
          console.log("[CoPilot] AS24 failed search reported");
        } catch {
        }
      }
      if (progress) progress.update("bonus", "skip");
      return { submitted: prices.length >= MIN_PRICES, isCurrentVehicle: true };
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

  // extension/content.js
  var API_URL = typeof __API_URL__ !== "undefined" ? __API_URL__ : "http://localhost:5001/api/analyze";
  var lastScanId = null;
  var ERROR_MESSAGES = [
    "Oh mince, on a crev\xE9 ! R\xE9essayez dans un instant.",
    "Le moteur a cal\xE9... Notre serveur fait une pause, retentez !",
    "Panne s\xE8che ! Impossible de joindre le serveur.",
    "Embrayage patin\xE9... L'analyse n'a pas pu d\xE9marrer.",
    "Vidange en cours ! Le serveur revient dans un instant."
  ];
  function isChromeRuntimeAvailable2() {
    try {
      return typeof chrome !== "undefined" && !!chrome.runtime && typeof chrome.runtime.sendMessage === "function";
    } catch {
      return false;
    }
  }
  function isLocalBackendUrl(url) {
    return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(String(url || ""));
  }
  async function backendFetch(url, options = {}) {
    const isLocalBackend = isLocalBackendUrl(url);
    if (!isChromeRuntimeAvailable2()) {
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
  function escapeHTML(str) {
    if (typeof str !== "string") return String(str ?? "");
    const el = document.createElement("span");
    el.textContent = str;
    return el.innerHTML;
  }
  function getRandomErrorMessage() {
    return ERROR_MESSAGES[Math.floor(Math.random() * ERROR_MESSAGES.length)];
  }
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
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
      default:
        return "?";
    }
  }
  function filterLabel(filterId) {
    const labels = {
      L1: "Compl\xE9tude des donn\xE9es",
      L2: "Mod\xE8le reconnu",
      L3: "Coh\xE9rence km / ann\xE9e",
      L4: "Prix vs Argus",
      L5: "Analyse statistique",
      L6: "T\xE9l\xE9phone",
      L7: "SIRET vendeur",
      L8: "D\xE9tection import",
      L9: "\xC9valuation globale",
      L10: "Anciennet\xE9 annonce"
    };
    return labels[filterId] || filterId;
  }
  var RADAR_SHORT_LABELS = {
    L1: "Donn\xE9es",
    L2: "Mod\xE8le",
    L3: "Km",
    L4: "Prix",
    L5: "Stats",
    L6: "T\xE9l\xE9phone",
    L7: "SIRET",
    L8: "Import",
    L9: "\xC9val",
    L10: "Anciennet\xE9"
  };
  function buildRadarSVG(filters, overallScore) {
    if (!filters || !filters.length) return "";
    const cx = 160, cy = 145, R = 100;
    const n = filters.length;
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
      const p = pt(i, R * filters[i].score);
      dataPts.push(`${p.x},${p.y}`);
    }
    const dataStr = dataPts.join(" ");
    let dotsSVG = "";
    let labelsSVG = "";
    const labelPad = 18;
    for (let i = 0; i < n; i++) {
      const f = filters[i];
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
  var SIMULATED_FILTERS = ["L4", "L5"];
  function buildFiltersList(filters) {
    if (!filters || !filters.length) return "";
    return filters.map((f) => {
      const color = statusColor(f.status);
      const icon = statusIcon(f.status);
      const label = filterLabel(f.filter_id);
      const isL4 = f.filter_id === "L4";
      const priceBarHTML = isL4 && f.details ? buildPriceBarHTML(f.details) : "";
      const detailsHTML = isL4 ? "" : f.details ? buildDetailsHTML(f.details) : "";
      const simulatedBadge = !isL4 && SIMULATED_FILTERS.includes(f.filter_id) ? '<span class="copilot-badge-simulated">Donn\xE9es simul\xE9es</span>' : "";
      return `
        <div class="copilot-filter-item" data-status="${escapeHTML(f.status)}">
          <div class="copilot-filter-header">
            <span class="copilot-filter-icon" style="color:${color}">${icon}</span>
            <span class="copilot-filter-label">${escapeHTML(label)}${simulatedBadge}</span>
            <span class="copilot-filter-score" style="color:${color}">${Math.round(f.score * 100)}%</span>
          </div>
          ${priceBarHTML || `<p class="copilot-filter-message">${escapeHTML(f.message)}</p>`}
          ${detailsHTML}
        </div>
      `;
    }).join("");
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
  function buildPriceBarHTML(details) {
    const priceAnnonce = details.price_annonce;
    const priceRef = details.price_reference;
    if (!priceAnnonce || !priceRef) return "";
    const deltaEur = details.delta_eur || priceAnnonce - priceRef;
    const deltaPct = details.delta_pct != null ? details.delta_pct : Math.round((priceAnnonce - priceRef) / priceRef * 100);
    const absDelta = Math.abs(deltaEur);
    const absPct = Math.abs(Math.round(deltaPct));
    let verdictClass, verdictEmoji, line1, line2;
    if (absPct <= 10) {
      verdictClass = deltaPct < 0 ? "verdict-below" : "verdict-fair";
      verdictEmoji = deltaPct < 0 ? "\u{1F7E2}" : "\u2705";
      line1 = deltaPct < 0 ? `${absDelta.toLocaleString("fr-FR")} \u20AC en dessous du march\xE9` : "Prix juste";
      line2 = deltaPct < 0 ? `Bon prix \u2014 ${absPct}% moins cher que le march\xE9` : `Dans la fourchette du march\xE9 (${deltaPct > 0 ? "+" : ""}${Math.round(deltaPct)}%)`;
    } else if (absPct <= 25) {
      if (deltaPct < 0) {
        verdictClass = "verdict-below";
        verdictEmoji = "\u{1F7E2}";
        line1 = `${absDelta.toLocaleString("fr-FR")} \u20AC en dessous du march\xE9`;
        line2 = `Bon prix \u2014 ${absPct}% moins cher que le march\xE9`;
      } else {
        verdictClass = "verdict-above-warning";
        verdictEmoji = "\u{1F7E0}";
        line1 = `${absDelta.toLocaleString("fr-FR")} \u20AC au-dessus du march\xE9`;
        line2 = `Prix \xE9lev\xE9 \u2014 ${absPct}% plus cher que le march\xE9`;
      }
    } else {
      if (deltaPct < 0) {
        verdictClass = "verdict-below";
        verdictEmoji = "\u{1F7E2}";
        line1 = `${absDelta.toLocaleString("fr-FR")} \u20AC en dessous du march\xE9`;
        line2 = `Tr\xE8s bon prix \u2014 ${absPct}% moins cher que le march\xE9`;
      } else {
        verdictClass = "verdict-above-fail";
        verdictEmoji = "\u{1F534}";
        line1 = `${absDelta.toLocaleString("fr-FR")} \u20AC au-dessus du march\xE9`;
        line2 = `Trop cher \u2014 ${absPct}% plus cher que le march\xE9`;
      }
    }
    const statusColors = { "verdict-below": "#16a34a", "verdict-fair": "#16a34a", "verdict-above-warning": "#ea580c", "verdict-above-fail": "#dc2626" };
    const fillOpacities = { "verdict-below": "rgba(22,163,74,0.15)", "verdict-fair": "rgba(22,163,74,0.15)", "verdict-above-warning": "rgba(234,88,12,0.2)", "verdict-above-fail": "rgba(220,38,38,0.2)" };
    const color = statusColors[verdictClass] || "#16a34a";
    const fillBg = fillOpacities[verdictClass] || "rgba(22,163,74,0.15)";
    const minP = Math.min(priceAnnonce, priceRef);
    const maxP = Math.max(priceAnnonce, priceRef);
    const gap = maxP - minP || maxP * 0.1;
    const scaleMin = Math.max(0, minP - gap * 0.8);
    const scaleMax = maxP + gap * 0.8;
    const range = scaleMax - scaleMin;
    const pct = (p) => (p - scaleMin) / range * 100;
    const annoncePct = pct(priceAnnonce);
    const argusPct = pct(priceRef);
    const fillLeft = Math.min(annoncePct, argusPct);
    const fillWidth = Math.abs(annoncePct - argusPct);
    const fmtP = (n) => escapeHTML(n.toLocaleString("fr-FR")) + " \u20AC";
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
          <div class="copilot-price-market-price">${fmtP(priceRef)}</div>
        </div>
        <div class="copilot-price-car" style="left:${annoncePct}%">
          <span class="copilot-price-car-emoji">\u{1F697}</span>
          <div class="copilot-price-car-price" style="color:${color}">${fmtP(priceAnnonce)}</div>
        </div>
      </div>
      <div class="copilot-price-bar-spacer"></div>
    </div>
  `;
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
        ${buildFiltersList(filters)}
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
  function removePopup() {
    const existing = document.getElementById("copilot-popup");
    if (existing) existing.remove();
    const overlay = document.getElementById("copilot-overlay");
    if (overlay) overlay.remove();
  }
  function showPopup(html) {
    removePopup();
    const overlay = document.createElement("div");
    overlay.id = "copilot-overlay";
    overlay.className = "copilot-overlay";
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) removePopup();
    });
    const container = document.createElement("div");
    container.innerHTML = html;
    overlay.appendChild(container.firstElementChild);
    document.body.appendChild(overlay);
    const closeBtn = document.getElementById("copilot-close");
    if (closeBtn) closeBtn.addEventListener("click", removePopup);
    const retryBtn = document.getElementById("copilot-retry");
    if (retryBtn) retryBtn.addEventListener("click", () => {
      removePopup();
      runAnalysis();
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
          const emailUrl = API_URL.replace("/analyze", "/email-draft");
          const resp = await backendFetch(emailUrl, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scan_id: lastScanId }) });
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
        const label = filterLabel(f.filter_id);
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
      if (details.source === "marche_leboncoin") {
        lines.push("Source : march\xE9 LBC (" + (details.sample_count || "?") + " annonces" + (details.precision ? ", pr\xE9cision " + details.precision : "") + ")");
      } else if (details.source === "argus_seed") {
        lines.push("Source : Argus (donn\xE9es seed)");
      }
      if (details.cascade_tried) {
        details.cascade_tried.forEach(function(tier) {
          var result = details["cascade_" + tier + "_result"] || "non essay\xE9";
          var tierLabel = tier === "market_price" ? "March\xE9 LBC" : "Argus Seed";
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
      '      <div class="copilot-step" id="copilot-step-collect" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Collecte des prix (cascade LeBonCoin)</div></div>',
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
    extractor.initDeps({ fetch: backendFetch, apiUrl: API_URL });
    runAnalysis(extractor).finally(() => {
      window.__copilotRunning = false;
    });
  }
  init();
})();
