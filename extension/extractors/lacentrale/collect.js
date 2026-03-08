"use strict";

/**
 * La Centrale — market price collection.
 *
 * Same pattern as LeBonCoin: progressive escalation of search strategies,
 * starting narrow (model + fuel + gearbox + km) and widening (brand only).
 * Uses the backend next-job API to decide which vehicle to collect,
 * then builds LC search URLs, fetches listing pages, extracts prices,
 * and submits them to the backend.
 */

import { isBenignRuntimeTeardownError } from '../../utils/fetch.js';
import { shouldSkipCollection, markCollected } from '../../shared/cooldown.js';
import { LC_MIN_PRICES, LC_MAX_PRICES } from './constants.js';
import { buildLcSearchUrl, getLcMileageRange, fetchLcSearchPrices } from './search.js';

// ── Helpers ─────────────────────────────────────────────────────

function _yearMeta(yearRef, spread) {
  const y = parseInt(yearRef, 10);
  const s = parseInt(spread, 10) || 1;
  if (!Number.isFinite(y) || y < 1990) return { yearMin: null, yearMax: null };
  const currentYear = new Date().getFullYear();
  return { yearMin: y - s, yearMax: Math.min(y + s, currentYear) };
}

function _urlVerdict(adsFound, uniqueAdded) {
  if ((adsFound || 0) <= 0) return 'empty';
  if ((uniqueAdded || 0) <= 0) return 'duplicates_only';
  return 'useful';
}

function _criteriaSummary(make, model, fuel, gearbox, yearMeta) {
  const yearVal = (yearMeta.yearMin && yearMeta.yearMax)
    ? `${yearMeta.yearMin}-${yearMeta.yearMax}`
    : '?-?';
  return [
    `marque=${make}`,
    `model=${model || 'any'}`,
    `fuel=${fuel || 'any'}`,
    `boite=${gearbox || 'any'}`,
    `annee=${yearVal}`,
  ].join(' \u00b7 ');
}

// ── Bonus Jobs ──────────────────────────────────────────────────

async function _reportJobDone(backendFetch, apiUrl, jobId, success) {
  if (!jobId) return;
  try {
    const url = apiUrl.replace('/analyze', '/market-prices/job-done');
    await backendFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, success }),
    });
  } catch (e) {
    if (isBenignRuntimeTeardownError(e)) return;
    console.warn('[OKazCar] LC job-done report failed:', e);
  }
}

async function _executeBonusJobs(bonusJobs, backendFetch, apiUrl, progress) {
  const MIN_BONUS_PRICES = 5;
  const marketUrl = apiUrl.replace('/analyze', '/market-prices');

  if (progress) progress.update('bonus', 'running', 'Execution de ' + bonusJobs.length + ' jobs');

  for (const job of bonusJobs) {
    try {
      await new Promise((r) => setTimeout(r, 1000 + Math.random() * 1000));

      const jobYear = parseInt(job.year, 10);
      const yearMeta = _yearMeta(jobYear, 1);

      const searchUrl = buildLcSearchUrl({
        make: job.make,
        model: job.model,
        yearMin: yearMeta.yearMin,
        yearMax: yearMeta.yearMax,
        fuel: job.fuel,
        gearbox: job.gearbox,
      });

      const prices = await fetchLcSearchPrices(searchUrl, jobYear, 1);
      console.log('[OKazCar] LC bonus job %s %s %d: %d prix', job.make, job.model, job.year, prices.length);

      if (progress) {
        const status = prices.length >= MIN_BONUS_PRICES ? 'done' : 'skip';
        const summary = _criteriaSummary(job.make, job.model, job.fuel, job.gearbox, yearMeta);
        progress.addSubStep('bonus', job.make + ' ' + job.model, status, prices.length + ' annonces \u00b7 ' + summary);
      }

      if (prices.length >= MIN_BONUS_PRICES) {
        const validPrices = prices.filter((p) => Number.isInteger(p?.price) && p.price > 500);
        const priceInts = validPrices.map((p) => p.price);
        if (priceInts.length >= MIN_BONUS_PRICES) {
          const payload = {
            make: job.make,
            model: job.model,
            year: jobYear,
            region: job.region || 'France',
            prices: priceInts,
            price_details: validPrices,
            fuel: job.fuel || null,
            precision: priceInts.length >= 20 ? 4 : 2,
            search_log: [{
              step: 1, precision: 3, location_type: 'national',
              year_spread: 1, ads_found: prices.length, url: searchUrl,
              unique_added: prices.length,
              url_verdict: _urlVerdict(prices.length, prices.length),
              was_selected: true,
              reason: `LC bonus job: ${prices.length} annonces`,
            }],
          };
          const resp = await backendFetch(marketUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          console.log('[OKazCar] LC bonus job POST: %s', resp.ok ? 'OK' : 'FAIL');
          await _reportJobDone(backendFetch, apiUrl, job.job_id, resp.ok);
        } else {
          await _reportJobDone(backendFetch, apiUrl, job.job_id, false);
        }
      } else {
        await _reportJobDone(backendFetch, apiUrl, job.job_id, false);
      }
    } catch (err) {
      if (isBenignRuntimeTeardownError(err)) {
        if (progress) progress.update('bonus', 'warning', 'Extension rechargee, jobs bonus interrompus');
        break;
      }
      console.warn('[OKazCar] LC bonus job failed:', err);
      await _reportJobDone(backendFetch, apiUrl, job.job_id, false);
    }
  }
  if (progress) progress.update('bonus', 'done');
}

// ── Main Collection ─────────────────────────────────────────────

/**
 * Collect market prices for a La Centrale vehicle.
 *
 * @param {object} adData - Normalized ad_data from the LC extractor
 * @param {Function} backendFetch - Backend fetch function (injected)
 * @param {string} apiUrl - API base URL (e.g. "http://localhost:5001/api/analyze")
 * @param {object} progress - Progress UI tracker
 * @returns {Promise<{submitted: boolean, isCurrentVehicle: boolean}>}
 */
export async function collectMarketPricesLC(adData, backendFetch, apiUrl, progress) {
  const make = adData?.make;
  const model = adData?.model;
  const year = adData?.year_model;
  const fuel = adData?.fuel || null;
  const gearbox = adData?.gearbox || null;
  const mileageKm = adData?.mileage_km || 0;

  if (!make || !model || !year) {
    console.log('[OKazCar] LC collect: missing make/model/year, skip');
    return { submitted: false, isCurrentVehicle: false };
  }

  const targetYear = parseInt(year, 10) || 0;

  // 1. Ask backend for next-job
  if (progress) progress.update('job', 'running');

  const jobUrl = apiUrl.replace('/analyze', '/market-prices/next-job')
    + `?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}`
    + `&year=${encodeURIComponent(year)}&region=France`
    + `&site=lacentrale`
    + (fuel ? `&fuel=${encodeURIComponent(fuel)}` : '')
    + (gearbox ? `&gearbox=${encodeURIComponent(gearbox)}` : '');

  let jobResp;
  try {
    console.log('[OKazCar] LC next-job ->', jobUrl);
    const raw = await backendFetch(jobUrl);
    if (!raw.ok) {
      console.warn('[OKazCar] LC next-job HTTP %d', raw.status);
      if (progress) {
        progress.update('job', 'error', 'Erreur serveur (' + raw.status + ')');
        progress.update('collect', 'skip');
        progress.update('submit', 'skip');
        progress.update('bonus', 'skip');
      }
      return { submitted: false, isCurrentVehicle: false };
    }
    jobResp = await raw.json();
    console.log('[OKazCar] LC next-job <-', JSON.stringify(jobResp));
  } catch (err) {
    console.warn('[OKazCar] LC next-job error:', err);
    if (progress) {
      progress.update('job', 'error', 'Serveur injoignable');
      progress.update('collect', 'skip');
      progress.update('submit', 'skip');
      progress.update('bonus', 'skip');
    }
    return { submitted: false, isCurrentVehicle: false };
  }

  // No collection needed?
  if (!jobResp?.data?.collect) {
    const bonusJobs = jobResp?.data?.bonus_jobs || [];
    if (bonusJobs.length === 0) {
      if (progress) {
        progress.update('job', 'done', 'Donnees deja a jour');
        progress.update('collect', 'skip', 'Non necessaire');
        progress.update('submit', 'skip');
        progress.update('bonus', 'skip');
      }
      return { submitted: false, isCurrentVehicle: false };
    }
    if (progress) {
      progress.update('job', 'done', 'Vehicule a jour — ' + bonusJobs.length + ' jobs en attente');
      progress.update('collect', 'skip', 'Vehicule deja a jour');
      progress.update('submit', 'skip');
    }
    await _executeBonusJobs(bonusJobs, backendFetch, apiUrl, progress);
    markCollected();
    return { submitted: false, isCurrentVehicle: false };
  }

  const target = jobResp.data.vehicle;
  const bonusJobs = jobResp.data.bonus_jobs || [];

  // 2. Cooldown check for OTHER vehicles
  const isCurrentVehicle =
    target.make.toLowerCase() === make.toLowerCase() &&
    target.model.toLowerCase() === model.toLowerCase();

  if (!isCurrentVehicle) {
    if (shouldSkipCollection()) {
      if (progress) {
        progress.update('job', 'done', 'Cooldown actif (autre vehicule collecte recemment)');
        progress.update('collect', 'skip', 'Cooldown 24h');
        progress.update('submit', 'skip');
      }
      if (bonusJobs.length > 0) {
        await _executeBonusJobs(bonusJobs, backendFetch, apiUrl, progress);
      } else if (progress) {
        progress.update('bonus', 'skip');
      }
      return { submitted: false, isCurrentVehicle: false };
    }
  }

  const tYear = parseInt(target.year, 10) || targetYear;
  const targetLabel = target.make + ' ' + target.model + ' ' + target.year;
  if (progress) {
    progress.update('job', 'done', targetLabel + (isCurrentVehicle ? ' (vehicule courant)' : ' (autre vehicule)'));
  }
  console.log('[OKazCar] LC collect target: %s (isCurrentVehicle=%s)', targetLabel, isCurrentVehicle);

  // 3. Build progressive search strategies
  //    LC is national (no geo/region in URL), so escalation = loosen filters
  const mileageRange = isCurrentVehicle ? getLcMileageRange(mileageKm) : null;
  const targetFuel = isCurrentVehicle ? fuel : (target.fuel || null);
  const targetGearbox = isCurrentVehicle ? gearbox : (target.gearbox || null);

  const strategies = [
    // S1: Full filters (model + fuel + gearbox + km) ±1 year
    { model: target.model, fuel: targetFuel, gearbox: targetGearbox, mileage: mileageRange, yearSpread: 1, precision: 5 },
    // S2: Model + fuel ±2 years (drop gearbox + km)
    { model: target.model, fuel: targetFuel, gearbox: null, mileage: null, yearSpread: 2, precision: 4 },
    // S3: Model only ±2 years (drop all sub-filters)
    { model: target.model, fuel: null, gearbox: null, mileage: null, yearSpread: 2, precision: 3 },
    // S4: Model only ±3 years
    { model: target.model, fuel: null, gearbox: null, mileage: null, yearSpread: 3, precision: 2 },
    // S5: Brand only ±2 years (last resort)
    { model: null, fuel: targetFuel, gearbox: null, mileage: null, yearSpread: 2, precision: 1 },
  ];

  if (progress) progress.update('collect', 'running');

  let submitted = false;
  let prices = [];
  let collectedPrecision = null;
  const searchLog = [];

  try {
    for (let i = 0; i < strategies.length; i++) {
      if (i > 0) await new Promise((r) => setTimeout(r, 800 + Math.random() * 700));

      const s = strategies[i];
      const yearMeta = _yearMeta(tYear, s.yearSpread);

      const searchUrl = buildLcSearchUrl({
        make: target.make,
        model: s.model,
        yearMin: yearMeta.yearMin,
        yearMax: yearMeta.yearMax,
        mileageMin: s.mileage?.mileageMin,
        mileageMax: s.mileage?.mileageMax,
        fuel: s.fuel,
        gearbox: s.gearbox,
      });

      const critSummary = _criteriaSummary(target.make, s.model, s.fuel, s.gearbox, yearMeta);
      const strategyLabel = 'Strategie ' + (i + 1) + ' \u00b7 \u00b1' + s.yearSpread + 'an';

      const newPrices = await fetchLcSearchPrices(searchUrl, tYear, s.yearSpread);

      // Deduplicate against accumulated prices
      const seen = new Set(prices.map((p) => `${p.price}-${p.km}`));
      const unique = newPrices.filter((p) => !seen.has(`${p.price}-${p.km}`));
      prices = [...prices, ...unique];

      const enoughPrices = prices.length >= LC_MIN_PRICES;
      console.log('[OKazCar] LC strategie %d (precision=%d): %d nouveaux (%d uniques), total=%d | %s',
        i + 1, s.precision, newPrices.length, unique.length, prices.length, searchUrl.substring(0, 120));

      if (progress) {
        const stepStatus = unique.length > 0 ? 'done' : 'skip';
        const stepDetail = unique.length + ' nouvelles annonces (total ' + prices.length + ')'
          + (enoughPrices && collectedPrecision === null ? ' \u2713 seuil atteint' : '')
          + ' \u00b7 ' + critSummary;
        progress.addSubStep('collect', strategyLabel, stepStatus, stepDetail);
      }

      searchLog.push({
        step: i + 1,
        precision: s.precision,
        location_type: 'national',
        year_spread: s.yearSpread,
        year_from: yearMeta.yearMin,
        year_to: yearMeta.yearMax,
        criteria_summary: critSummary,
        filters_applied: [
          ...(s.fuel ? ['fuel'] : []),
          ...(s.gearbox ? ['gearbox'] : []),
          ...(s.mileage ? ['km'] : []),
        ],
        ads_found: newPrices.length,
        unique_added: unique.length,
        url_verdict: _urlVerdict(newPrices.length, unique.length),
        total_accumulated: prices.length,
        url: searchUrl,
        was_selected: enoughPrices,
        reason: enoughPrices
          ? `total ${prices.length} annonces >= ${LC_MIN_PRICES} minimum`
          : `total ${prices.length} annonces < ${LC_MIN_PRICES} minimum`,
      });

      if (enoughPrices && collectedPrecision === null) {
        collectedPrecision = s.precision;
        console.log('[OKazCar] LC seuil atteint strategie %d (precision=%d)', i + 1, collectedPrecision);
      }

      if (prices.length >= LC_MAX_PRICES) {
        console.log('[OKazCar] LC cap atteint (%d >= %d)', prices.length, LC_MAX_PRICES);
        break;
      }
    }

    // 4. Submit if enough prices
    if (prices.length >= LC_MIN_PRICES) {
      if (progress) {
        progress.update('collect', 'done', prices.length + ' prix collectes (precision ' + (collectedPrecision || '?') + ')');
        progress.update('submit', 'running');
      }

      const validPrices = prices.filter((p) => Number.isInteger(p?.price) && p.price > 500);
      const priceInts = validPrices.map((p) => p.price);

      if (priceInts.length < 5) {
        if (progress) {
          progress.update('submit', 'warning', 'Trop de prix invalides apres filtrage');
          progress.update('bonus', 'skip');
        }
        return { submitted: false, isCurrentVehicle };
      }

      const marketUrl = apiUrl.replace('/analyze', '/market-prices');
      const payload = {
        make: target.make,
        model: target.model,
        year: tYear,
        region: 'France',
        prices: priceInts,
        price_details: validPrices,
        fuel: targetFuel || null,
        precision: collectedPrecision,
        search_log: searchLog,
      };

      console.log('[OKazCar] LC POST /api/market-prices:', target.make, target.model, tYear, 'n=', priceInts.length);
      const marketResp = await backendFetch(marketUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      submitted = marketResp.ok;
      if (!marketResp.ok) {
        const errBody = await marketResp.json().catch(() => null);
        console.warn('[OKazCar] LC POST /api/market-prices FAILED:', marketResp.status, errBody);
        if (progress) progress.update('submit', 'error', 'Erreur serveur (' + marketResp.status + ')');
      } else {
        console.log('[OKazCar] LC POST /api/market-prices OK');
        if (progress) progress.update('submit', 'done', priceInts.length + ' prix envoyes');

        if (bonusJobs.length > 0) {
          await _executeBonusJobs(bonusJobs, backendFetch, apiUrl, progress);
        } else if (progress) {
          progress.update('bonus', 'skip', 'Aucun job en attente');
        }
      }
    } else {
      console.log('[OKazCar] LC pas assez de prix: %d < %d', prices.length, LC_MIN_PRICES);
      if (progress) {
        progress.update('collect', 'warning', prices.length + ' annonces trouvees (minimum ' + LC_MIN_PRICES + ')');
        progress.update('submit', 'skip', 'Pas assez de donnees');
        progress.update('bonus', 'skip');
      }

      // Report failed search for diagnostics
      try {
        const failedUrl = apiUrl.replace('/analyze', '/market-prices/failed-search');
        await backendFetch(failedUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            make: target.make,
            model: target.model,
            year: tYear,
            region: 'France',
            fuel: targetFuel || null,
            search_log: searchLog,
          }),
        });
      } catch (e) {
        console.warn('[OKazCar] LC failed-search report error:', e);
      }
    }
  } catch (err) {
    if (isBenignRuntimeTeardownError(err)) {
      console.info('[OKazCar] LC collection interrompue: extension rechargee');
    } else {
      console.error('[OKazCar] LC market collection failed:', err);
    }
    if (progress) {
      progress.update('collect', 'error', 'Erreur pendant la collecte');
      progress.update('submit', 'skip');
      progress.update('bonus', 'skip');
    }
  }

  // 5. Save timestamp (even if not enough prices)
  markCollected();
  return { submitted, isCurrentVehicle };
}
