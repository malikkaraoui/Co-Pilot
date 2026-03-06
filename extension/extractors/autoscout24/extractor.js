"use strict";

import { SiteExtractor } from '../base.js';
import { shouldSkipCollection, markCollected } from '../../shared/cooldown.js';
import {
  AS24_URL_PATTERNS, AD_PAGE_PATTERN,
  TLD_TO_COUNTRY, TLD_TO_CURRENCY, TLD_TO_COUNTRY_CODE, MIN_PRICES,
} from './constants.js';
import {
  getCantonFromZip, getCantonCenterZip, getAs24GearCode, getAs24FuelCode,
  getAs24PowerParams, getAs24KmParams, getHpRangeString, parseHpRange, mapFuelType,
} from './helpers.js';
import {
  parseRSCPayload, parseJsonLd, fallbackAdDataFromDom,
  extractMakeModelFromUrl, _extractDatesFromDom, _extractImageCountFromNextData,
  _extractDescriptionFromDom, _extractFuelFromDom, _extractColorFromDom, _findJsonLdByMake,
} from './parser.js';
import {
  normalizeToAdData, buildBonusSignals,
  _daysOnline, _daysSinceRefresh, _isRepublished,
} from './normalize.js';
import {
  extractTld, extractLang, toAs24Slug, extractAs24SlugsFromSearchUrl,
  buildSearchUrl, parseSearchPrices,
} from './search.js';

export class AutoScout24Extractor extends SiteExtractor {
  static SITE_ID = 'autoscout24';
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
        type: 'normalized',
        source: 'autoscout24',
        ad_data: this._adData,
      };
    }

    this._adData = normalizeToAdData(this._rsc, this._jsonLd);

    // SPA guard: cross-validate make AND model against URL slug
    const urlHint = extractMakeModelFromUrl(window.location.href);
    const urlSlugMatch = window.location.pathname.match(
      /\/(?:d|angebote|offerte|ofertas|aanbod|offres|annunci|anuncios|oferta|erbjudanden)\/([a-z0-9][\w-]*?)[-–](?:\d+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9]{6,})(?:[/?#]|$)/i
    );
    const urlSlug = urlSlugMatch ? urlSlugMatch[1].toLowerCase() : '';
    if (urlSlug && this._adData.make) {
      const makeSlug = toAs24Slug(this._adData.make);
      const modelSlug = toAs24Slug(this._adData.model || '');
      const hasModelMatch = modelSlug
        ? (urlSlug.includes(modelSlug)
          || modelSlug.split('-').filter((t) => t.length >= 3).some((t) => urlSlug.includes(t)))
        : false;
      const vehicleInUrl = urlSlug.startsWith(makeSlug)
        && hasModelMatch;
      if (!vehicleInUrl) {
        console.warn(
          '[OKazCar] AS24 SPA stale data: extracted %s %s not in URL slug "%s"',
          this._adData.make, this._adData.model || '?', urlSlug
        );
        const freshLd = _findJsonLdByMake(document, urlHint.make, urlHint.model, urlSlug);
        if (freshLd) {
          console.log('[OKazCar] Found fresh JSON-LD for %s, using it', urlHint.make);
          this._rsc = null;
          this._jsonLd = freshLd;
          this._adData = normalizeToAdData(null, freshLd);
        } else {
          console.log('[OKazCar] No matching JSON-LD, falling back to DOM');
          this._rsc = null;
          this._jsonLd = null;
          this._adData = fallbackAdDataFromDom(document, window.location.href);
        }
      }
    }

    // Final fallback: if dates are still missing, search DOM scripts
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

    // Fallback image count from __NEXT_DATA__
    if (!this._adData.image_count) {
      const ndImageCount = _extractImageCountFromNextData(document);
      if (ndImageCount > 0) {
        this._adData.image_count = ndImageCount;
      }
    }

    // Final fallback: description from DOM blocks
    if (!this._adData.description) {
      const domDesc = _extractDescriptionFromDom(document);
      if (domDesc) {
        this._adData.description = domDesc;
      }
    }

    // Final fallback: fuel from visible DOM labels (Carburant/Kraftstoff/...)
    if (!this._adData.fuel) {
      const domFuel = _extractFuelFromDom(document);
      if (domFuel) {
        this._adData.fuel = mapFuelType(domFuel);
      }
    }

    // Final fallback: color from visible DOM labels (Couleur originale / Farbe / Color ...)
    if (!this._adData.color) {
      const domColor = _extractColorFromDom(document);
      if (domColor) {
        this._adData.color = domColor;
      }
    }

    return {
      type: 'normalized',
      source: 'autoscout24',
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
      console.warn('[OKazCar] AS24 collectMarketPrices: deps not injected');
      return { submitted: false, isCurrentVehicle: false };
    }

    const tld = extractTld(window.location.href);
    const lang = extractLang(window.location.href);
    const countryName = TLD_TO_COUNTRY[tld] || 'Europe';
    const countryCode = TLD_TO_COUNTRY_CODE[tld] || 'FR';
    const currency = TLD_TO_CURRENCY[tld] || 'EUR';
    const year = parseInt(this._adData.year_model, 10);
    const fuelKey = this._rsc?.fuelType || this._adData?.fuel || null;

    const hp = parseInt(this._adData.power_din_hp, 10) || 0;
    const km = parseInt(this._adData.mileage_km, 10) || 0;
    const gearRaw = this._rsc?.transmissionType || this._adData?.gearbox || '';
    const gearCode = getAs24GearCode(gearRaw);
    const hpRangeStr = getHpRangeString(hp);

    const zipcode = this._adData?.location?.zipcode;
    const canton = (tld === 'ch' && zipcode) ? getCantonFromZip(zipcode) : null;
    const region = canton || countryName;

    // ── 1. Call next-job API ──────────────────────────────────────
    if (progress) progress.update('job', 'running');

    const fuelForJob = this._adData.fuel ? this._adData.fuel.toLowerCase() : '';
    const gearboxForJob = this._adData.gearbox ? this._adData.gearbox.toLowerCase() : '';
    const slugMakeForJob = toAs24Slug(this._adData.make);
    const slugModelForJob = toAs24Slug(this._adData.model);
    const jobUrl = this._apiUrl.replace('/analyze', '/market-prices/next-job')
      + `?make=${encodeURIComponent(this._adData.make)}&model=${encodeURIComponent(this._adData.model)}`
      + `&year=${encodeURIComponent(year)}&region=${encodeURIComponent(region)}`
      + `&country=${encodeURIComponent(countryCode)}`
      + `&site=as24&tld=${encodeURIComponent(tld)}`
      + `&slug_make=${encodeURIComponent(slugMakeForJob)}&slug_model=${encodeURIComponent(slugModelForJob)}`
      + (fuelForJob ? `&fuel=${encodeURIComponent(fuelForJob)}` : '')
      + (gearboxForJob ? `&gearbox=${encodeURIComponent(gearboxForJob)}` : '')
      + (hpRangeStr ? `&hp_range=${encodeURIComponent(hpRangeStr)}` : '');

    let jobResp;
    try {
      console.log('[OKazCar] AS24 next-job →', jobUrl);
      jobResp = await this._fetch(jobUrl).then((r) => r.json());
      console.log('[OKazCar] AS24 next-job ←', JSON.stringify(jobResp));
    } catch (err) {
      console.warn('[OKazCar] AS24 next-job error:', err);
      if (progress) {
        progress.update('job', 'error', 'Serveur injoignable');
        progress.update('collect', 'skip');
        progress.update('submit', 'skip');
        progress.update('bonus', 'skip');
      }
      return { submitted: false, isCurrentVehicle: false };
    }

    // ── 2. Handle collect=false ───────────────────────────────────
    if (!jobResp?.data?.collect) {
      const queuedJobs = jobResp?.data?.bonus_jobs || [];
      if (queuedJobs.length === 0) {
        if (progress) {
          progress.update('job', 'done', 'Données déjà à jour');
          progress.update('collect', 'skip', 'Non nécessaire');
          progress.update('submit', 'skip');
          progress.update('bonus', 'skip');
        }
        return { submitted: false, isCurrentVehicle: false };
      }
      if (progress) {
        progress.update('job', 'done', `À jour — ${queuedJobs.length} jobs en attente`);
        progress.update('collect', 'skip', 'Véhicule déjà à jour');
        progress.update('submit', 'skip');
      }
      await this._executeBonusJobs(queuedJobs, tld, progress, lang);
      return { submitted: false, isCurrentVehicle: false };
    }

    // ── 3. Determine target vehicle ───────────────────────────────
    const target = jobResp.data.vehicle;
    const targetRegion = jobResp.data.region;
    const isRedirect = !!jobResp.data.redirect;
    const bonusJobs = jobResp.data.bonus_jobs || [];

    const isCurrentVehicle =
      target.make.toLowerCase() === this._adData.make.toLowerCase()
      && target.model.toLowerCase() === this._adData.model.toLowerCase();

    if (!isCurrentVehicle) {
      if (shouldSkipCollection()) {
        if (progress) {
          progress.update('job', 'done', 'Cooldown actif (autre véhicule collecté récemment)');
          progress.update('collect', 'skip', 'Cooldown 24h');
          progress.update('submit', 'skip');
        }
        if (bonusJobs.length > 0) {
          await this._executeBonusJobs(bonusJobs, tld, progress, lang);
        } else if (progress) {
          progress.update('bonus', 'skip');
        }
        return { submitted: false, isCurrentVehicle: false };
      }
    }

    const targetMakeKey = target.as24_slug_make || toAs24Slug(target.make);
    const targetModelKey = target.as24_slug_model || toAs24Slug(target.model);
    const targetYear = parseInt(target.year, 10);
    const targetLabel = `${target.make} ${target.model} ${targetYear}`;

    if (progress) {
      progress.update('job', 'done', targetLabel
        + (isCurrentVehicle ? ` (${targetRegion})` : ' (autre véhicule)'));
    }

    // ── 4. Build cascade strategies ───────────────────────────────
    const normalizedAdFuel = this._adData?.fuel ? mapFuelType(this._adData.fuel) : null;
    const normalizedTargetFuel = target?.fuel ? mapFuelType(target.fuel) : null;
    const fuelCode = getAs24FuelCode(this._rsc?.fuelType)
      || getAs24FuelCode(this._rsc?.fuel)
      || getAs24FuelCode(this._adData?.fuel)
      || getAs24FuelCode(normalizedAdFuel)
      || getAs24FuelCode(target?.fuel)
      || getAs24FuelCode(normalizedTargetFuel)
      || (fuelKey ? getAs24FuelCode(fuelKey) : null)
      || null;
    const targetCantonZip = getCantonCenterZip(targetRegion);
    const strategies = [];

    function _filtersApplied(opts) {
      const f = [];
      if (opts.fuel) f.push('fuel');
      if (opts.gear) f.push('gearbox');
      if (opts.powerfrom || opts.powerto) f.push('hp');
      if (opts.kmfrom || opts.kmto) f.push('km');
      return f;
    }

    if (isCurrentVehicle) {
      const powerParams = getAs24PowerParams(hp);
      const kmParams = getAs24KmParams(km);
      const hasFuel = Boolean(fuelCode);
      const hasHp = Boolean(powerParams.powerfrom || powerParams.powerto);

      const withRelevantFilters = (baseOpts, { includeGear = true, includeKm = false, includeFuel = true } = {}) => {
        const opts = { ...baseOpts };
        if (includeFuel && hasFuel) opts.fuel = fuelCode;
        if (hasHp) Object.assign(opts, powerParams);
        if (includeGear && gearCode) opts.gear = gearCode;
        if (includeKm) Object.assign(opts, kmParams);
        return opts;
      };

      if (zipcode) {
        const opts = withRelevantFilters({ yearSpread: 1, zip: zipcode, radius: 30 }, { includeGear: true, includeKm: true });
        strategies.push({ ...opts, precision: 5, label: `ZIP ${zipcode} +30km`, location_type: 'zip', filters_applied: _filtersApplied(opts) });
      }
      if (targetCantonZip) {
        const opts1 = withRelevantFilters({ yearSpread: 1, zip: targetCantonZip, radius: 50 }, { includeGear: true, includeKm: true });
        strategies.push({ ...opts1, precision: 4, label: `${targetRegion} ±1an`, location_type: 'canton', filters_applied: _filtersApplied(opts1) });
        const opts2 = withRelevantFilters({ yearSpread: 2, zip: targetCantonZip, radius: 50 }, { includeGear: true, includeKm: false });
        strategies.push({ ...opts2, precision: 4, label: `${targetRegion} ±2ans`, location_type: 'canton', filters_applied: _filtersApplied(opts2) });
      }
      const opts3 = withRelevantFilters({ yearSpread: 1 }, { includeGear: true, includeKm: false });
      strategies.push({ ...opts3, precision: 3, label: 'National ±1an', location_type: 'national', filters_applied: _filtersApplied(opts3) });
      const opts4 = withRelevantFilters({ yearSpread: 2 }, { includeGear: true, includeKm: false });
      strategies.push({ ...opts4, precision: 3, label: 'National ±2ans', location_type: 'national', filters_applied: _filtersApplied(opts4) });
      if (gearCode) {
        const opts5 = withRelevantFilters({ yearSpread: 2 }, { includeGear: false, includeKm: false });
        strategies.push({ ...opts5, precision: 2, label: 'National ±2ans (sans boîte)', location_type: 'national', filters_applied: _filtersApplied(opts5) });
      }

      const isHybridFuelCode = fuelCode === '2' || fuelCode === '3';
      if (isHybridFuelCode) {
        const opts6 = withRelevantFilters({ yearSpread: 1 }, { includeGear: true, includeKm: false, includeFuel: false });
        strategies.push({ ...opts6, precision: 2, label: 'National ±1an (sans carburant)', location_type: 'national', filters_applied: _filtersApplied(opts6) });
        const opts7 = withRelevantFilters({ yearSpread: 2 }, { includeGear: true, includeKm: false, includeFuel: false });
        strategies.push({ ...opts7, precision: 2, label: 'National ±2ans (sans carburant)', location_type: 'national', filters_applied: _filtersApplied(opts7) });
      }
    } else {
      if (targetCantonZip) {
        strategies.push({
          yearSpread: 1, zip: targetCantonZip, radius: 50,
          precision: 3, label: `${targetRegion} ±1an`, location_type: 'canton', filters_applied: [],
        });
      }
      strategies.push({ yearSpread: 1, precision: 2, label: 'National ±1an', location_type: 'national', filters_applied: [] });
      strategies.push({ yearSpread: 2, precision: 1, label: 'National ±2ans', location_type: 'national', filters_applied: [] });
    }

    // ── 5. Execute cascade ────────────────────────────────────────
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

    if (progress) progress.update('collect', 'running');

    const MAX_PRICES_CAP = 100;

    function _as24YearWindow(yearRef, spread = 1) {
      const y = Number.parseInt(yearRef, 10);
      const s = Number.parseInt(spread, 10) || 1;
      if (!Number.isFinite(y)) return { year_from: null, year_to: null, year_filter: null };
      return {
        year_from: y - s,
        year_to: y + s,
        year_filter: `fregfrom=${y - s}&fregto=${y + s}`,
      };
    }

    function _urlVerdict(adsFound, uniqueAdded) {
      if ((adsFound || 0) <= 0) return 'empty';
      if ((uniqueAdded || 0) <= 0) return 'duplicates_only';
      return 'useful';
    }

    function _criteriaSummary(opts, yearMeta) {
      const fuelVal = opts.fuel || 'any';
      const gearVal = opts.gear || 'any';
      const powerVal = (opts.powerfrom || opts.powerto)
        ? `${opts.powerfrom ?? 'min'}-${opts.powerto ?? 'max'}`
        : 'any';
      const modelVal = `${target.model} [mo-${targetModelKey}]`;
      const yearVal = (yearMeta.year_from && yearMeta.year_to)
        ? `${yearMeta.year_from}-${yearMeta.year_to}`
        : '?-?';
      return [
        `marque=${target.make} [mk-${targetMakeKey}]`,
        `model=${modelVal}`,
        `fuel=${fuelVal}`,
        `boite=${gearVal}`,
        `kW=${powerVal}`,
        `année=${yearVal}`,
      ].join(' · ');
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
        filters_applied: filters_applied || [],
      };
      rememberSlugs(searchUrl, 'as24_generated_url');

      try {
        const resp = await fetch(searchUrl, { credentials: 'same-origin' });
        if (!resp.ok) {
          searchLog.push({ ...logBase, ads_found: 0, url: searchUrl, was_selected: false, reason: `HTTP ${resp.status}` });
          if (progress) progress.addSubStep?.('collect', `Stratégie ${i + 1} · ${label}`, 'skip', `HTTP ${resp.status}`);
          continue;
        }

        if (resp.url) rememberSlugs(resp.url, 'as24_response_url');

        const html = await resp.text();
        const newPrices = parseSearchPrices(html, target.make);

        const seen = new Set(prices.map((p) => `${p.price}-${p.km}`));
        const unique = newPrices.filter((p) => !seen.has(`${p.price}-${p.km}`));
        prices = [...prices, ...unique];

        const enough = prices.length >= MIN_PRICES;

        console.log('[OKazCar] AS24 strategie %d (precision=%d): %d nouveaux (%d uniques), total=%d | %s',
          i + 1, precision, newPrices.length, unique.length, prices.length, searchUrl.substring(0, 120));

        searchLog.push({
          ...logBase, ads_found: newPrices.length,
          unique_added: unique.length,
          url_verdict: _urlVerdict(newPrices.length, unique.length),
          url: searchUrl, was_selected: enough && usedPrecision === null,
          reason: enough ? `total ${prices.length} >= ${MIN_PRICES}` : `total ${prices.length} < ${MIN_PRICES}`,
        });

        if (progress) {
          progress.addSubStep?.('collect', `Stratégie ${i + 1} · ${label}`,
            unique.length > 0 ? 'done' : 'skip', `${newPrices.length} annonces · ${criteriaSummary}`);
        }

        if (enough && usedPrecision === null) {
          usedPrecision = precision;
          break;
        }

        if (prices.length >= MAX_PRICES_CAP) {
          console.log('[OKazCar] AS24 cap %d atteint, arret', MAX_PRICES_CAP);
          break;
        }
      } catch (err) {
        console.error('[OKazCar] AS24 search error:', err);
        searchLog.push({ ...logBase, ads_found: 0, url: searchUrl, was_selected: false, reason: err.message });
        if (progress) progress.addSubStep?.('collect', `Stratégie ${i + 1} · ${label}`, 'skip', 'Erreur');
      }
    }

    // ── 6. Submit or report failure ───────────────────────────────
    let submitted = false;

    if (prices.length >= MIN_PRICES) {
      const priceInts = prices.map((p) => p.price);
      const priceDetails = prices;

      if (progress) {
        progress.update('collect', 'done', `${priceInts.length} prix (précision ${usedPrecision})`);
        progress.update('submit', 'running');
      }

      const marketUrl = this._apiUrl.replace('/analyze', '/market-prices');
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
        as24_slug_model: learnedSlugModel || (!searchLog.some((s) => (s.reason || '').startsWith('HTTP 404')) ? targetModelKey : null),
      };

      console.log('[OKazCar] AS24 submit payload:', JSON.stringify({
        make: payload.make, model: payload.model, year: payload.year,
        region: payload.region, precision: payload.precision, country: payload.country,
        fuel: payload.fuel, hp_range: payload.hp_range, gearbox: payload.gearbox,
        prices_count: payload.prices.length, prices_sample: payload.prices.slice(0, 3),
        price_details_sample: payload.price_details?.slice(0, 2),
        search_log_count: payload.search_log?.length,
        search_log_sample: payload.search_log?.slice(0, 2),
        as24_slug_make: payload.as24_slug_make, as24_slug_model: payload.as24_slug_model,
      }));

      try {
        const resp = await this._fetch(marketUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (resp.ok) {
          if (progress) progress.update('submit', 'done', `${priceInts.length} prix envoyés (${targetRegion})`);
          submitted = true;
        } else {
          const errBody = await resp.text().catch(() => '');
          console.error('[OKazCar] AS24 market-prices POST %d: %s', resp.status, errBody);
          const errMsg = (() => {
            try { return JSON.parse(errBody)?.message || `HTTP ${resp.status}`; } catch { return `HTTP ${resp.status}`; }
          })();
          if (progress) progress.update('submit', 'error', errMsg);
        }
      } catch (err) {
        console.error('[OKazCar] AS24 market-prices POST error:', err);
        if (progress) progress.update('submit', 'error', 'Erreur réseau');
      }
    } else {
      if (progress) {
        progress.update('collect', 'warning', `${prices.length} annonces (min ${MIN_PRICES})`);
        progress.update('submit', 'skip', 'Pas assez de données');
      }
      try {
        const failedUrl = this._apiUrl.replace('/analyze', '/market-prices/failed-search');
        await this._fetch(failedUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            make: target.make, model: target.model, year: targetYear,
            region: targetRegion,
            fuel: isCurrentVehicle ? (fuelKey || null) : null,
            hp_range: isCurrentVehicle ? hpRangeStr : null,
            country: countryCode, search_log: searchLog,
            site: 'as24',
            tld,
            slug_make_used: learnedSlugMake || targetMakeKey,
            slug_model_used: learnedSlugModel || targetModelKey,
            slug_source: slugSource || 'as24_generated_url',
            as24_slug_make: learnedSlugMake || null,
            as24_slug_model: learnedSlugModel || null,
          }),
        });
      } catch { /* ignore */ }
    }

    // ── 7. Execute bonus jobs ─────────────────────────────────────
    if (bonusJobs.length > 0) {
      await this._executeBonusJobs(bonusJobs, tld, progress, lang);
    } else if (progress) {
      progress.update('bonus', 'skip', 'Pas de jobs bonus');
    }

    if (!isCurrentVehicle) {
      markCollected();
    }

    return { submitted, isCurrentVehicle };
  }

  async _executeBonusJobs(bonusJobs, tld, progress, lang = null) {
    const marketUrl = this._apiUrl.replace('/analyze', '/market-prices');
    const jobDoneUrl = this._apiUrl.replace('/analyze', '/market-prices/job-done');
    const currency = TLD_TO_CURRENCY[tld] || 'EUR';
    const countryCode = TLD_TO_COUNTRY_CODE[tld] || 'FR';
    const MIN_BONUS_PRICES = countryCode === 'FR' ? 20 : MIN_PRICES;

    function _bonusFiltersApplied(opts) {
      const f = [];
      if (opts.fuel) f.push('fuel');
      if (opts.gear) f.push('gearbox');
      if (opts.powerfrom || opts.powerto) f.push('hp');
      return f;
    }

    function _as24YearWindow(yearRef, spread = 1) {
      const y = Number.parseInt(yearRef, 10);
      const s = Number.parseInt(spread, 10) || 1;
      if (!Number.isFinite(y)) return { year_from: null, year_to: null, year_filter: null };
      return {
        year_from: y - s,
        year_to: y + s,
        year_filter: `fregfrom=${y - s}&fregto=${y + s}`,
      };
    }

    function _urlVerdict(adsFound, uniqueAdded) {
      if ((adsFound || 0) <= 0) return 'empty';
      if ((uniqueAdded || 0) <= 0) return 'duplicates_only';
      return 'useful';
    }

    function _bonusCriteriaSummary(job, opts, yearMeta, jobMakeKey, jobModelKey) {
      const fuelVal = opts.fuel || 'any';
      const gearVal = opts.gear || 'any';
      const powerVal = (opts.powerfrom || opts.powerto)
        ? `${opts.powerfrom ?? 'min'}-${opts.powerto ?? 'max'}`
        : 'any';
      const modelVal = opts.brandOnly
        ? 'ALL (brandOnly)'
        : `${job.model} [mo-${jobModelKey}]`;
      const yearVal = (yearMeta.year_from && yearMeta.year_to)
        ? `${yearMeta.year_from}-${yearMeta.year_to}`
        : '?-?';
      return [
        `marque=${job.make} [mk-${jobMakeKey}]`,
        `model=${modelVal}`,
        `fuel=${fuelVal}`,
        `boite=${gearVal}`,
        `kW=${powerVal}`,
        `année=${yearVal}`,
      ].join(' · ');
    }

    if (progress) progress.update('bonus', 'running', `${bonusJobs.length} jobs`);

    for (const job of bonusJobs) {
      if ((job.country || 'FR') !== countryCode) {
        console.log('[OKazCar] AS24 bonus skip: country %s != %s', job.country, countryCode);
        await this._reportJobDone(jobDoneUrl, job.job_id, false);
        if (progress) progress.addSubStep?.('bonus', `${job.make} ${job.model}`, 'skip', 'Pays différent');
        continue;
      }

      try {
        await new Promise((r) => setTimeout(r, 800 + Math.random() * 600));

        const jobMakeKey = job.slug_make || toAs24Slug(job.make);
        const jobModelKey = job.slug_model || toAs24Slug(job.model);
        const jobYear = parseInt(job.year, 10);
        if (!Number.isFinite(jobYear) || jobYear < 1990 || jobYear > 2030) {
          console.warn('[OKazCar] AS24 bonus skip invalid year for %s %s: %o', job.make, job.model, job.year);
          await this._reportJobDone(jobDoneUrl, job.job_id, false);
          if (progress) progress.addSubStep?.('bonus', `${job.make} ${job.model} · ${job.region}`, 'skip', 'Année invalide');
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
        const seenBonusKeys = new Set();

        const pushBonusStrategy = (label, opts, precision = 3) => {
          const strategyOpts = { ...opts };
          const key = JSON.stringify(strategyOpts);
          if (seenBonusKeys.has(key)) return;
          seenBonusKeys.add(key);
          bonusStrategies.push({ label, precision, opts: strategyOpts });
        };

        pushBonusStrategy('Strict local ±1an', strictSearchOpts, 4);

        if (strictSearchOpts.gear) {
          const noGear = { ...strictSearchOpts };
          delete noGear.gear;
          pushBonusStrategy('Sans boite ±1an', noGear, 3);
        }

        if (strictSearchOpts.zip) {
          const national = { ...strictSearchOpts };
          delete national.zip;
          delete national.radius;
          pushBonusStrategy('National ±1an', national, 2);

          const nationalWide = { ...national, yearSpread: 2 };
          pushBonusStrategy('National ±2ans', nationalWide, 2);
        } else {
          pushBonusStrategy('National ±2ans', { ...strictSearchOpts, yearSpread: 2 }, 2);
        }

        const isHybridBonusFuel = strictSearchOpts.fuel === '2' || strictSearchOpts.fuel === '3';
        if (isHybridBonusFuel) {
          const noFuel = { ...strictSearchOpts };
          delete noFuel.fuel;
          pushBonusStrategy('Sans carburant ±1an', noFuel, 2);
          pushBonusStrategy('Sans carburant ±2ans', { ...noFuel, yearSpread: 2 }, 2);
        }

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
          const resp = await fetch(searchUrl, { credentials: 'same-origin' });
          const learned = extractAs24SlugsFromSearchUrl(resp.url || searchUrl, tld);
          const yearMeta = _as24YearWindow(jobYear, strategy.opts.yearSpread || 1);
          const criteriaSummary = _bonusCriteriaSummary(job, strategy.opts, yearMeta, jobMakeKey, jobModelKey);

          if (!resp.ok) {
            httpFailure = httpFailure || resp.status;
            bonusSearchLog.push({
              step: step + 1,
              precision: strategy.precision,
              location_type: strategy.opts.zip ? 'canton' : 'national',
              year_spread: strategy.opts.yearSpread || 1,
              year_from: yearMeta.year_from,
              year_to: yearMeta.year_to,
              year_filter: yearMeta.year_filter,
              criteria_summary: criteriaSummary,
              filters_applied: _bonusFiltersApplied(strategy.opts),
              ads_found: 0,
              unique_added: 0,
              url_verdict: 'empty',
              url: searchUrl,
              was_selected: false,
              reason: `HTTP ${resp.status}`,
            });
            continue;
          }

          const html = await resp.text();
          const prices = parseSearchPrices(html, job.make);
          bestAdsCount = Math.max(bestAdsCount, prices.length);

          console.log('[OKazCar] AS24 bonus %s %s %d %s [%s]: %d prix',
            job.make, job.model, jobYear, job.region, strategy.label, prices.length);

          bonusSearchLog.push({
            step: step + 1,
            precision: strategy.precision,
            location_type: strategy.opts.zip ? 'canton' : 'national',
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
            reason: prices.length >= MIN_BONUS_PRICES
              ? `total ${prices.length} >= ${MIN_BONUS_PRICES}`
              : `total ${prices.length} < ${MIN_BONUS_PRICES}`,
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
                'bonus',
                `${job.make} ${job.model} · ${job.region}`,
                'skip',
                `${priceInts.length} prix valides (<${MIN_BONUS_PRICES})`
              );
            }
            continue;
          }

          const bonusPrecision = selected.precision;
          const bonusPayload = {
            make: String(job.make || '').trim(),
            model: String(job.model || '').trim(),
            year: jobYear,
            region: String(job.region || '').trim(),
            prices: priceInts,
            price_details: priceDetails,
            fuel: job.fuel || null, hp_range: job.hp_range || null,
            precision: bonusPrecision, country: countryCode,
            as24_slug_make: selectedLearned.makeSlug || jobMakeKey,
            as24_slug_model: selectedLearned.modelSlug || (selected.opts.brandOnly ? null : jobModelKey),
            search_log: bonusSearchLog,
          };

          const postResp = await this._fetch(marketUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bonusPayload),
          });
          let errMsg = null;
          if (!postResp.ok) {
            const errBody = await postResp.text().catch(() => '');
            console.error('[OKazCar] AS24 bonus POST %d for %s %s: %s', postResp.status, job.make, job.model, errBody);
            try {
              errMsg = JSON.parse(errBody)?.message || null;
            } catch {
              errMsg = null;
            }
          }
          await this._reportJobDone(jobDoneUrl, job.job_id, postResp.ok);
          if (progress) {
            progress.addSubStep?.(
              'bonus',
              `${job.make} ${job.model} · ${job.region}`,
              postResp.ok ? 'done' : 'error',
              postResp.ok
                ? `${priceInts.length} prix (${selected.label}) · ${_bonusCriteriaSummary(job, selected.opts, _as24YearWindow(jobYear, selected.opts.yearSpread || 1), jobMakeKey, jobModelKey)}`
                : `${errMsg || `HTTP ${postResp.status}`}`
            );
          }
        } else {
          await this._reportJobDone(jobDoneUrl, job.job_id, false);
          if (progress) {
            progress.addSubStep?.(
              'bonus',
              `${job.make} ${job.model} · ${job.region}`,
              'skip',
              bestAdsCount > 0
                ? `${bestAdsCount} annonces max (<${MIN_BONUS_PRICES})`
                : `${httpFailure ? `HTTP ${httpFailure}` : `0 annonce`} (<${MIN_BONUS_PRICES})`
            );
          }
        }
      } catch (err) {
        console.warn('[OKazCar] AS24 bonus job error:', err);
        await this._reportJobDone(jobDoneUrl, job.job_id, false);
        if (progress) progress.addSubStep?.('bonus', `${job.make} ${job.model} · ${job.region}`, 'skip', 'Erreur');
      }
    }

    if (progress) progress.update('bonus', 'done');
  }

  async _reportJobDone(jobDoneUrl, jobId, success) {
    if (!jobId) return;
    try {
      await this._fetch(jobDoneUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId, success, site: 'as24' }),
      });
    } catch { /* ignore */ }
  }
}
