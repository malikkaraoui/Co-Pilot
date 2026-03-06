"use strict";

import { isBenignRuntimeTeardownError } from '../../utils/fetch.js';
import { shouldSkipCollection, markCollected } from '../../shared/cooldown.js';
import { lbcDeps } from './_deps.js';
import {
  GENERIC_MODELS, EXCLUDED_CATEGORIES, LBC_REGIONS, LBC_FUEL_CODES, LBC_GEARBOX_CODES,
  DUAL_BRAND_ALIASES, MIN_PRICES_FOR_ARGUS, DEFAULT_SEARCH_RADIUS,
  getHorsePowerRange, getMileageRange,
} from './constants.js';
import {
  toLbcBrandToken, extractMileageFromNextData, extractLocationFromNextData,
} from './parser.js';
import { fetchSearchPrices, buildLocationParam } from './search.js';

export async function reportJobDone(jobDoneUrl, jobId, success) {
  if (!jobId) return;
  try {
    await lbcDeps.backendFetch(jobDoneUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, success }),
    });
  } catch (e) {
    if (isBenignRuntimeTeardownError(e)) {
      console.debug("[OKazCar] job-done report skipped (extension reloaded/unloaded)");
      return;
    }
    console.warn("[OKazCar] job-done report failed:", e);
  }
}

export async function executeBonusJobs(bonusJobs, progress) {
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
    const yearVal = (yearMeta.year_from && yearMeta.year_to)
      ? `${yearMeta.year_from}-${yearMeta.year_to}`
      : "?-?";
    return [
      `marque=${make} [${brandToken}]`,
      `model=${model} [${modelToken}]`,
      `fuel=${fuelCode || "any"}`,
      `boite=${gearboxCode || "any"}`,
      `CV=${hpRange || "any"}`,
      `année=${yearVal}`,
    ].join(" · ");
  }

  if (progress) progress.update("bonus", "running", "Exécution de " + bonusJobs.length + " jobs");

  for (const job of bonusJobs) {
    try {
      await new Promise((r) => setTimeout(r, 1000 + Math.random() * 1000));

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
        console.warn("[OKazCar] bonus job: region inconnue '%s', skip", job.region);
        await reportJobDone(jobDoneUrl, job.job_id, false);
        if (progress) progress.addSubStep("bonus", job.region, "skip", "Région inconnue");
        continue;
      }

      let searchUrl = jobCoreUrl + filters + `&locations=${locParam}`;
      const jobYear = parseInt(job.year, 10);
      const yearMeta = _yearMeta(jobYear, 1);
      if (yearMeta.regdate) searchUrl += `&regdate=${yearMeta.regdate}`;

      const bonusPrices = await fetchSearchPrices(searchUrl, jobYear, 1, job.make);
      console.log("[OKazCar] bonus job %s %s %d %s: %d prix", job.make, job.model, job.year, job.region, bonusPrices.length);

      if (progress) {
        const stepStatus = bonusPrices.length >= MIN_BONUS_PRICES ? "done" : "skip";
        const criteriaSummary = _criteriaSummary(
          job.make,
          job.model,
          job.site_brand_token || brandUpper,
          job.site_model_token || `${brandUpper}_${job.model}`,
          (filters.match(/(?:\?|&)fuel=([^&]+)/)?.[1]) || null,
          (filters.match(/(?:\?|&)gearbox=([^&]+)/)?.[1]) || null,
          (filters.match(/(?:\?|&)horse_power_din=([^&]+)/)?.[1]) || job.hp_range || null,
          yearMeta,
        );
        progress.addSubStep(
          "bonus",
          job.make + " " + job.model + " · " + job.region,
          stepStatus,
          bonusPrices.length + " annonces · " + criteriaSummary
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
              step: 1, precision: bonusPrecision, location_type: "region",
              year_spread: 1,
              year_from: yearMeta.year_from,
              year_to: yearMeta.year_to,
              year_filter: yearMeta.regdate ? `regdate=${yearMeta.regdate}` : null,
              criteria_summary: _criteriaSummary(
                job.make,
                job.model,
                job.site_brand_token || brandUpper,
                job.site_model_token || `${brandUpper}_${job.model}`,
                (filters.match(/(?:\?|&)fuel=([^&]+)/)?.[1]) || null,
                (filters.match(/(?:\?|&)gearbox=([^&]+)/)?.[1]) || null,
                (filters.match(/(?:\?|&)horse_power_din=([^&]+)/)?.[1]) || job.hp_range || null,
                yearMeta,
              ),
              filters_applied: [
                ...(filters.includes("fuel=") ? ["fuel"] : []),
                ...(filters.includes("gearbox=") ? ["gearbox"] : []),
                ...(filters.includes("horse_power_din=") ? ["hp"] : []),
              ],
              ads_found: bonusPrices.length, url: searchUrl,
              unique_added: bonusPrices.length,
              url_verdict: _urlVerdict(bonusPrices.length, bonusPrices.length),
              was_selected: true,
              reason: `bonus job queue: ${bonusPrices.length} annonces`,
            }],
          };
          const bResp = await lbcDeps.backendFetch(marketUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(bonusPayload),
          });
          console.log("[OKazCar] bonus job POST %s: %s", job.region, bResp.ok ? "OK" : "FAIL");
          await reportJobDone(jobDoneUrl, job.job_id, bResp.ok);
        } else {
          await reportJobDone(jobDoneUrl, job.job_id, false);
        }
      } else {
        await reportJobDone(jobDoneUrl, job.job_id, false);
      }
    } catch (err) {
      if (isBenignRuntimeTeardownError(err)) {
        console.info("[OKazCar] bonus jobs interrompus: extension rechargée/déchargée");
        if (progress) {
          progress.update("bonus", "warning", "Extension rechargée, jobs bonus interrompus");
        }
        break;
      }
      console.warn("[OKazCar] bonus job %s failed:", job.region, err);
      await reportJobDone(jobDoneUrl, job.job_id, false);
    }
  }
  if (progress) progress.update("bonus", "done");
}

export async function maybeCollectMarketPrices(vehicle, nextData, progress) {
  const { make, model, year, fuel, gearbox, horse_power } = vehicle;
  if (!make || !model || !year) return { submitted: false };

  const hp = parseInt(horse_power, 10) || 0;
  const hpRange = getHorsePowerRange(hp);

  const urlMatch = window.location.href.match(/\/ad\/([a-z_]+)\//);
  const urlCategory = urlMatch ? urlMatch[1] : null;
  if (urlCategory && EXCLUDED_CATEGORIES.includes(urlCategory)) {
    console.log("[OKazCar] collecte ignoree: categorie exclue", urlCategory);
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
    console.warn("[OKazCar] collecte ignoree: pas de region dans nextData");
    if (progress) {
      progress.update("job", "skip", "Région non disponible");
      progress.update("collect", "skip");
      progress.update("submit", "skip");
      progress.update("bonus", "skip");
    }
    return { submitted: false };
  }
  console.log("[OKazCar] collecte: region=%s, location=%o, km=%d", region, location, mileageKm);

  // 2. Demander au serveur quel vehicule collecter
  if (progress) progress.update("job", "running");
  const fuelForJob = (fuel || "").toLowerCase();
  const gearboxForJob = (gearbox || "").toLowerCase();
  const jobUrl = lbcDeps.apiUrl.replace("/analyze", "/market-prices/next-job")
    + `?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}`
    + `&year=${encodeURIComponent(year)}&region=${encodeURIComponent(region)}`
    + `&site=lbc`
    + (fuelForJob ? `&fuel=${encodeURIComponent(fuelForJob)}` : "")
    + (gearboxForJob ? `&gearbox=${encodeURIComponent(gearboxForJob)}` : "")
    + (hpRange ? `&hp_range=${encodeURIComponent(hpRange)}` : "");

  let jobResp;
  try {
    console.log("[OKazCar] next-job →", jobUrl);
    jobResp = await lbcDeps.backendFetch(jobUrl).then((r) => r.json());
    console.log("[OKazCar] next-job ←", JSON.stringify(jobResp));
  } catch (err) {
    console.warn("[OKazCar] next-job erreur:", err);
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
      console.log("[OKazCar] next-job: collect=false, aucun bonus en queue");
      if (progress) {
        progress.update("job", "done", "Données déjà à jour, pas de collecte nécessaire");
        progress.update("collect", "skip", "Non nécessaire");
        progress.update("submit", "skip");
        progress.update("bonus", "skip");
      }
      return { submitted: false };
    }
    console.log("[OKazCar] next-job: collect=false, %d bonus jobs en queue", queuedJobs.length);
    if (progress) {
      progress.update("job", "done", "Véhicule à jour — " + queuedJobs.length + " jobs en attente");
      progress.update("collect", "skip", "Véhicule déjà à jour");
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
  console.log("[OKazCar] next-job: %d bonus jobs", bonusJobs.length);

  // 3. Cooldown 24h -- uniquement pour les collectes d'AUTRES vehicules
  const isCurrentVehicle =
    target.make.toLowerCase() === make.toLowerCase() &&
    target.model.toLowerCase() === model.toLowerCase();

  if (!isCurrentVehicle) {
    if (shouldSkipCollection()) {
      console.log("[OKazCar] cooldown actif pour autre vehicule, skip collecte redirect — bonus jobs toujours executes");
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
  console.log("[OKazCar] collecte cible: %s %s %d (isCurrentVehicle=%s, redirect=%s)", target.make, target.model, target.year, isCurrentVehicle, isRedirect);

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

  if (!modelIsGeneric) {
    const textQuery = `${target.make} ${target.model}`;
    const textCoreUrl = `https://www.leboncoin.fr/recherche?category=2&text=${encodeURIComponent(textQuery)}`;
    strategies.push({
      loc: "", yearSpread: 2, filters: fuelParam,
      precision: 1, coreUrl: textCoreUrl, isTextFallback: true,
    });
  }

  console.log("[OKazCar] fuel=%s → fuelCode=%s | gearbox=%s → gearboxCode=%s | hp=%d → hpRange=%s | km=%d",
    targetFuel, fuelCode, (gearbox || "").toLowerCase(), gearboxCode, hp, hpRange, mileageKm);
  console.log("[OKazCar] coreUrl:", coreUrl);
  console.log("[OKazCar] %d strategies, geoParam=%s, regionParam=%s", strategies.length, geoParam || "(vide)", regionParam || "(vide)");

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
    const fuelVal = (strategy.filters.match(/(?:\?|&)fuel=([^&]+)/)?.[1]) || null;
    const gearboxVal = (strategy.filters.match(/(?:\?|&)gearbox=([^&]+)/)?.[1]) || null;
    const hpVal = (strategy.filters.match(/(?:\?|&)horse_power_din=([^&]+)/)?.[1]) || null;
    const modelToken = modelIsGeneric ? `text:${target.make}` : effectiveModel;
    const yearVal = (yearMeta.year_from && yearMeta.year_to)
      ? `${yearMeta.year_from}-${yearMeta.year_to}`
      : "?-?";
    return [
      `marque=${target.make} [${effectiveBrand}]`,
      `model=${target.model} [${modelToken}]`,
      `fuel=${fuelVal || "any"}`,
      `boite=${gearboxVal || "any"}`,
      `CV=${hpVal || "any"}`,
      `année=${yearVal}`,
    ].join(" · ");
  }
  if (progress) progress.update("collect", "running");
  try {
    for (let i = 0; i < strategies.length; i++) {
      if (i > 0) await new Promise((r) => setTimeout(r, 800 + Math.random() * 700));

      const strategy = strategies[i];

      if (strategy.isTextFallback && prices.length >= MIN_PRICES_FOR_ARGUS) {
        console.log("[OKazCar] strategie %d: text fallback skipped (already %d prices)", i + 1, prices.length);
        searchLog.push({
          step: i + 1, precision: strategy.precision, location_type: "national",
          year_spread: strategy.yearSpread,
          year_from: null,
          year_to: null,
          year_filter: null,
          criteria_summary: "text fallback skipped",
          filters_applied: strategy.filters.includes("fuel=") ? ["fuel"] : [],
          ads_found: 0, unique_added: 0, total_accumulated: prices.length,
          url_verdict: "empty",
          url: "(skipped)", was_selected: false,
          reason: `text fallback skipped: ${prices.length} >= ${MIN_PRICES_FOR_ARGUS}`,
        });
        if (progress) progress.addSubStep("collect", "Stratégie " + (i + 1) + " · Text search (fallback)", "skip", "Déjà assez de données");
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

      const locLabel = strategy.isTextFallback ? "Text search (fallback)"
        : (strategy.loc === geoParam && geoParam) ? "Géo (" + (location?.city || "local") + " 30km)"
        : (strategy.loc === regionParam && regionParam) ? "Région (" + targetRegion + ")"
        : "National";
      const strategyLabel = "Stratégie " + (i + 1) + " \u00b7 " + locLabel + " \u00b1" + strategy.yearSpread + "an";

      const newPrices = await fetchSearchPrices(searchUrl, targetYear, strategy.yearSpread, target.make);

      const seen = new Set(prices.map((p) => `${p.price}-${p.km}`));
      const unique = newPrices.filter((p) => !seen.has(`${p.price}-${p.km}`));
      prices = [...prices, ...unique];

      const enoughPrices = prices.length >= MIN_PRICES_FOR_ARGUS;
      console.log("[OKazCar] strategie %d (precision=%d): %d nouveaux prix (%d uniques), total=%d | %s",
        i + 1, strategy.precision, newPrices.length, unique.length, prices.length, searchUrl.substring(0, 150));

      if (progress) {
        const stepStatus = unique.length > 0 ? "done" : "skip";
        const stepDetail = unique.length + " nouvelles annonces (total " + prices.length + ")"
          + (enoughPrices && collectedPrecision === null ? " \u2713 seuil atteint" : "")
          + " · " + criteriaSummary;
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
        year_from: yearMeta.year_from,
        year_to: yearMeta.year_to,
        year_filter: yearMeta.regdate ? `regdate=${yearMeta.regdate}` : null,
        criteria_summary: criteriaSummary,
        filters_applied: [
          ...(strategy.filters.includes("fuel=") ? ["fuel"] : []),
          ...(strategy.filters.includes("gearbox=") ? ["gearbox"] : []),
          ...(strategy.filters.includes("horse_power_din=") ? ["hp"] : []),
          ...(strategy.filters.includes("mileage=") ? ["km"] : []),
        ],
        ads_found: newPrices.length,
        unique_added: unique.length,
        url_verdict: _urlVerdict(newPrices.length, unique.length),
        total_accumulated: prices.length,
        url: searchUrl,
        was_selected: enoughPrices,
        reason: enoughPrices
          ? `total ${prices.length} annonces >= ${MIN_PRICES_FOR_ARGUS} minimum`
          : `total ${prices.length} annonces < ${MIN_PRICES_FOR_ARGUS} minimum`,
      });

      if (enoughPrices && collectedPrecision === null) {
        collectedPrecision = strategy.precision;
        console.log("[OKazCar] seuil atteint a la strategie %d (precision=%d), accumulation continue...", i + 1, collectedPrecision);
      }

      if (prices.length >= MAX_PRICES_CAP) {
        console.log("[OKazCar] cap atteint (%d >= %d), arret de la collecte", prices.length, MAX_PRICES_CAP);
        break;
      }
    }

    // Dual-brand strategies
    const secondaryBrand = DUAL_BRAND_ALIASES[brandUpper];
    if (secondaryBrand && !modelIsGeneric && prices.length < MAX_PRICES_CAP) {
      console.log("[OKazCar] dual-brand: %s → secondary brand %s", brandUpper, secondaryBrand);
      const dualQuery = `${target.make} ${target.model}`;
      const dualCoreUrl = `https://www.leboncoin.fr/recherche?category=2`
        + `&u_car_brand=${encodeURIComponent(secondaryBrand)}`
        + `&text=${encodeURIComponent(dualQuery)}`;

      const dualStrategies = [
        { loc: regionParam || "", yearSpread: 2, filters: fuelParam, precision: 2 },
        { loc: "", yearSpread: 2, filters: fuelParam, precision: 1 },
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
          `fuel=${(ds.filters.match(/(?:\?|&)fuel=([^&]+)/)?.[1]) || "any"}`,
          `boite=any`,
          `CV=any`,
          `année=${(dYearMeta.year_from && dYearMeta.year_to) ? `${dYearMeta.year_from}-${dYearMeta.year_to}` : "?-?"}`,
        ].join(" · ");

        const dualLocType = ds.loc ? "region" : "national";
        const dualLabel = `Stratégie ${strategies.length + d + 1} · Dual ${secondaryBrand} (${dualLocType})`;

        const newPrices = await fetchSearchPrices(searchUrl, targetYear, ds.yearSpread, secondaryBrand);
        const seen = new Set(prices.map((p) => `${p.price}-${p.km}`));
        const unique = newPrices.filter((p) => !seen.has(`${p.price}-${p.km}`));
        prices = [...prices, ...unique];

        console.log("[OKazCar] dual-brand strategie %d: %d nouveaux (%d uniques), total=%d | %s",
          strategies.length + d + 1, newPrices.length, unique.length, prices.length, searchUrl.substring(0, 150));

        if (progress) {
          const stepStatus = unique.length > 0 ? "done" : "skip";
          progress.addSubStep(
            "collect",
            dualLabel,
            stepStatus,
            unique.length + " nouvelles annonces (total " + prices.length + ") · " + dCriteriaSummary
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
          reason: `dual-brand ${secondaryBrand}: ${unique.length} uniques, total ${prices.length}`,
        });

        if (prices.length >= MIN_PRICES_FOR_ARGUS && collectedPrecision === null) {
          collectedPrecision = ds.precision;
        }
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
        console.warn("[OKazCar] apres filtrage >500: %d prix valides (< %d requis)", priceInts.length, MIN_PRICES_FOR_ARGUS);
        if (priceInts.length >= 5) {
           console.log("[OKazCar] envoi degradé avec %d prix (min 5)", priceInts.length);
        } else {
           if (progress) {
             progress.update("submit", "warning", "Trop de prix invalides après filtrage");
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
        site_model_token: isCurrentVehicle ? vehicle.site_model_token : null,
      };
      console.log("[OKazCar] POST /api/market-prices:", target.make, target.model, target.year, targetRegion, "fuel=", payload.fuel, "n=", priceInts.length);
      const marketResp = await lbcDeps.backendFetch(marketUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      submitted = marketResp.ok;
      if (!marketResp.ok) {
        const errBody = await marketResp.json().catch(() => null);
        console.warn("[OKazCar] POST /api/market-prices FAILED:", marketResp.status, errBody);
        if (progress) progress.update("submit", "error", "Erreur serveur (" + marketResp.status + ")");
      } else {
        console.log("[OKazCar] POST /api/market-prices OK, submitted=true");
        if (progress) progress.update("submit", "done", priceInts.length + " prix envoyés (" + targetRegion + ")");

        if (bonusJobs.length > 0) {
          await executeBonusJobs(bonusJobs, progress);
        } else {
          if (progress) progress.update("bonus", "skip", "Aucun job en attente");
        }
      }
    } else {
      console.log(`[OKazCar] pas assez de prix apres toutes les strategies: ${prices.length} < ${MIN_PRICES_FOR_ARGUS}`);
      if (progress) {
        progress.update("collect", "warning", prices.length + " annonces trouvées (minimum " + MIN_PRICES_FOR_ARGUS + ")");
        progress.update("submit", "skip", "Pas assez de données");
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
            site_model_token: isCurrentVehicle ? vehicle.site_model_token : null,
          }),
        });
        console.log("[OKazCar] failed search reported to server");
      } catch (e) {
        console.warn("[OKazCar] failed-search report error:", e);
      }
    }
  } catch (err) {
    console.error("[OKazCar] market collection failed:", err);
    if (progress) {
      progress.update("collect", "error", "Erreur pendant la collecte");
      progress.update("submit", "skip");
      progress.update("bonus", "skip");
    }
  }

  // 6. Sauvegarder le timestamp (meme si pas assez de prix)
  markCollected();
  return { submitted, isCurrentVehicle };
}
