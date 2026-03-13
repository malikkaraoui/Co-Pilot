"use strict";

/**
 * La Centrale — collecte de prix marche.
 *
 * Meme pattern que LeBonCoin : escalade progressive des strategies
 * de recherche, du plus precis (modele + carburant + boite + km) au plus
 * large (marque seule). Utilise l'API next-job du backend pour decider
 * quel vehicule collecter.
 *
 * IMPORTANT : la collecte directe sur LC est actuellement desactivee
 * a cause de l'anti-bot DataDome. A la place, on delegue au backend
 * qui relance la collecte via LBC/AS24 (failed-search avec delegation).
 * Le code de collecte directe est conserve en dead code apres le return
 * pour pouvoir le reactiver si LC change sa politique anti-bot.
 */

import { isBenignRuntimeTeardownError } from '../../utils/fetch.js';
import { shouldSkipCollection, markCollected } from '../../shared/cooldown.js';
import { LC_MIN_PRICES, LC_MAX_PRICES } from './constants.js';
import { buildLcSearchUrl, getLcMileageRange, fetchLcSearchPrices, fetchLcSearchPricesDetailed } from './search.js';

// ── Helpers ─────────────────────────────────────────────────────

/** Calcule la fenetre d'annees min/max autour d'une annee de reference */
function _yearMeta(yearRef, spread) {
  const y = parseInt(yearRef, 10);
  const s = parseInt(spread, 10) || 1;
  if (!Number.isFinite(y) || y < 1990) return { yearMin: null, yearMax: null };
  const currentYear = new Date().getFullYear();
  return { yearMin: y - s, yearMax: Math.min(y + s, currentYear) };
}

/** Qualifie le resultat d'une recherche pour le diagnostic backend */
function _urlVerdict(adsFound, uniqueAdded) {
  if ((adsFound || 0) <= 0) return 'empty';
  if ((uniqueAdded || 0) <= 0) return 'duplicates_only';
  return 'useful';
}

/** Resume lisible des criteres de recherche pour le search_log */
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

/**
 * Nettoie un token modele pour la recherche LC.
 * Supprime accents, underscores, slashes et normalise les espaces.
 */
function _cleanLcToken(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[_/]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toUpperCase();
}

/** Ajoute une variante de modele sans doublon */
function _pushLcVariant(list, value) {
  const cleaned = _cleanLcToken(value);
  if (!cleaned) return;
  if (!list.includes(cleaned)) list.push(cleaned);
}

/**
 * Genere les variantes de nom de modele a essayer dans les recherches LC.
 * LC est sensible aux noms exacts — on genere plusieurs formes pour
 * maximiser les chances de match (avec/sans +, tirets, apostrophes, etc.)
 */
function _buildLcModelVariants(baseModel, adData) {
  const variants = [];
  const rawCandidates = [
    baseModel,
    adData?.lc_model_raw,
    adData?.lc_commercial_model,
    adData?.lc_family,
    adData?.lc_version,
  ];

  rawCandidates.forEach((candidate) => _pushLcVariant(variants, candidate));

  // Generer des formes alternatives courantes
  for (const candidate of [...variants]) {
    if (candidate.includes('+')) {
      _pushLcVariant(variants, candidate.replace(/\+/g, ''));
      _pushLcVariant(variants, candidate.replace(/\+/g, ' PLUS'));
    }
    _pushLcVariant(variants, candidate.replace(/[-']/g, ' '));
    _pushLcVariant(variants, candidate.replace(/[^A-Z0-9+ ]/g, ' '));
  }

  return variants.filter(Boolean).slice(0, 6);
}

/**
 * Classe les diagnostics LC par severite pour garder le plus informatif.
 * anti_bot est le plus grave, true_zero_results le plus benin.
 */
function _lcDiagnosticRank(tag) {
  switch (tag) {
    case 'anti_bot_403':
      return 6;
    case 'anti_bot_page':
      return 5;
    case 'iframe_blocked':
      return 4;
    case 'parser_no_match':
      return 3;
    case 'html_without_cards':
      return 2;
    case 'true_zero_results':
      return 1;
    default:
      return 0;
  }
}

/** Garde le diagnostic le plus severe entre deux candidats */
function _pickBestLcDiagnostic(current, candidate) {
  if (!candidate) return current || null;
  if (!current) return candidate;
  return _lcDiagnosticRank(candidate.reasonTag) >= _lcDiagnosticRank(current.reasonTag)
    ? candidate
    : current;
}

// ── Bonus Jobs ──────────────────────────────────────────────────

/** Signale au backend qu'un job bonus est termine */
async function _reportJobDone(backendFetch, apiUrl, jobId, success) {
  if (!jobId) return;
  try {
    const url = apiUrl.replace('/analyze', '/market-prices/job-done');
    await backendFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, success, site: 'lacentrale' }),
    });
  } catch (e) {
    if (isBenignRuntimeTeardownError(e)) return;
    console.warn('[OKazCar] LC job-done report failed:', e);
  }
}

/**
 * Execute les bonus jobs (collectes de prix pour d'autres vehicules).
 * Chaque job fait une recherche LC simplifiee et soumet les prix au backend.
 */
async function _executeBonusJobs(bonusJobs, backendFetch, apiUrl, progress) {
  const MIN_BONUS_PRICES = 5;
  const marketUrl = apiUrl.replace('/analyze', '/market-prices');

  if (progress) progress.update('bonus', 'running', 'Execution de ' + bonusJobs.length + ' jobs');

  for (const job of bonusJobs) {
    try {
      // Delai entre jobs pour eviter le rate limiting
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
 * Collecte les prix marche pour un vehicule La Centrale.
 *
 * Actuellement, la collecte directe est desactivee (anti-bot DataDome).
 * On envoie un failed-search au backend pour declencher une delegation
 * automatique vers LBC/AS24 qui peuvent collecter sans blocage.
 *
 * @param {object} adData - ad_data normalise depuis l'extracteur LC
 * @param {Function} backendFetch - Fonction fetch vers le backend (injectee)
 * @param {string} apiUrl - URL de base de l'API (ex: "http://localhost:5001/api/analyze")
 * @param {object} progress - Tracker UI pour afficher l'avancement
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

  if (progress) {
    progress.update('job', 'done', 'Collecte marché LC désactivée');
  }

  if (shouldSkipCollection()) {
    if (progress) {
      progress.update('collect', 'skip', 'Relance externe déjà demandée récemment');
      progress.update('submit', 'skip', 'Cooldown 24h');
      progress.update('bonus', 'skip');
    }
    return { submitted: false, isCurrentVehicle: false };
  }

  // ── Delegation vers LBC/AS24 ──
  // On envoie un failed-search avec diagnostic "strategy_disabled"
  // pour que le backend cree automatiquement des jobs sur d'autres sites
  if (progress) {
    progress.update('collect', 'skip', 'Pas de listing LC : délégation vers LBC/AS24');
    progress.update('submit', 'running', 'Création des relances automatiques');
  }

  try {
    const failedUrl = apiUrl.replace('/analyze', '/market-prices/failed-search');
    const searchLog = [{
      step: 1,
      precision: 0,
      location_type: 'delegated',
      year_spread: 1,
      filters_applied: [],
      ads_found: 0,
      url: (typeof window !== 'undefined' && window.location?.href) ? window.location.href : 'https://www.lacentrale.fr/',
      was_selected: false,
      label: 'LC désactivé',
      diagnostic_tag: 'strategy_disabled',
      reason: 'Collecte listing La Centrale désactivée : fallback automatique vers LBC/AS24.',
      fetch_mode: 'disabled',
      anti_bot_detected: false,
    }];

    const resp = await backendFetch(failedUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        make,
        model,
        year: parseInt(year, 10) || year,
        region: 'France',
        fuel,
        gearbox,
        hp_range: adData?.hp_range || null,
        site: 'lacentrale',
        country: 'FR',
        search_log: searchLog,
      }),
    });

    if (resp.ok) {
      if (progress) {
        progress.update('submit', 'done', 'Relance LBC/AS24 demandée');
        progress.update('bonus', 'skip', 'LC non utilisé pour les bonus');
      }
      markCollected();
      return { submitted: false, isCurrentVehicle: false };
    }

    console.warn('[OKazCar] LC delegated failed-search POST failed:', resp.status);
    if (progress) {
      progress.update('submit', 'warning', 'Relance externe non confirmée');
      progress.update('bonus', 'skip');
    }
  } catch (err) {
    if (isBenignRuntimeTeardownError(err)) {
      console.info('[OKazCar] LC delegated collection interrompue: extension rechargee');
    } else {
      console.warn('[OKazCar] LC delegated failed-search error:', err);
    }
    if (progress) {
      progress.update('submit', 'warning', 'Relance externe interrompue');
      progress.update('bonus', 'skip');
    }
  }

  return { submitted: false, isCurrentVehicle: false };

  // ══════════════════════════════════════════════════════════════
  // Dead code ci-dessous : collecte directe desactivee a cause
  // de l'anti-bot DataDome. Conserve pour pouvoir etre reactive.
  // ══════════════════════════════════════════════════════════════

  const targetYear = parseInt(year, 10) || 0;

  // 1. Demander au backend quel vehicule collecter
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

  // Pas de collecte necessaire
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

  // 2. Cooldown pour les vehicules tiers
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

  // 3. Construction des strategies progressives
  //    LC est national (pas de geo dans l'URL) — escalade = relacher les filtres
  const mileageRange = isCurrentVehicle ? getLcMileageRange(mileageKm) : null;
  const targetFuel = isCurrentVehicle ? fuel : (target.fuel || null);
  const targetGearbox = isCurrentVehicle ? gearbox : (target.gearbox || null);

  const strategies = [
    // S1 : Tous filtres (modele + carburant + boite + km) ±1an
    { model: target.model, fuel: targetFuel, gearbox: targetGearbox, mileage: mileageRange, yearSpread: 1, precision: 5 },
    // S2 : Modele + carburant ±2ans (sans boite ni km)
    { model: target.model, fuel: targetFuel, gearbox: null, mileage: null, yearSpread: 2, precision: 4 },
    // S3 : Modele seul ±2ans
    { model: target.model, fuel: null, gearbox: null, mileage: null, yearSpread: 2, precision: 3 },
    // S4 : Modele seul ±3ans
    { model: target.model, fuel: null, gearbox: null, mileage: null, yearSpread: 3, precision: 2 },
    // S5 : Marque seule ±2ans (dernier recours)
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

      // Essayer plusieurs variantes du nom de modele pour maximiser les chances
      const modelVariants = s.model ? _buildLcModelVariants(s.model, isCurrentVehicle ? adData : null) : [null];
      const triedModels = [];
      let searchUrl = null;
      let newPrices = [];
      let bestDiagnostic = null;

      for (const modelVariant of modelVariants) {
        searchUrl = buildLcSearchUrl({
          make: target.make,
          model: modelVariant,
          yearMin: yearMeta.yearMin,
          yearMax: yearMeta.yearMax,
          mileageMin: s.mileage?.mileageMin,
          mileageMax: s.mileage?.mileageMax,
          fuel: s.fuel,
          gearbox: s.gearbox,
        });

        triedModels.push(modelVariant || '(brand-only)');
        const searchResult = await fetchLcSearchPricesDetailed(searchUrl, tYear, s.yearSpread);
        newPrices = searchResult.prices;
        bestDiagnostic = _pickBestLcDiagnostic(bestDiagnostic, searchResult.diagnostic);
        if (newPrices.length > 0) break;
      }

      const critSummary = _criteriaSummary(target.make, triedModels[0] || s.model, s.fuel, s.gearbox, yearMeta);
      const strategyLabel = 'Strategie ' + (i + 1) + ' \u00b7 \u00b1' + s.yearSpread + 'an';

      // Deduplication progressive
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
          + ' \u00b7 ' + critSummary
          + (triedModels.length > 1 ? ` \u00b7 variantes=${triedModels.join(' | ')}` : '');
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
        model_variants: triedModels,
        diagnostic_tag: bestDiagnostic?.reasonTag || null,
        fetch_mode: bestDiagnostic?.fetchMode || null,
        http_status: bestDiagnostic?.httpStatus || null,
        body_excerpt: bestDiagnostic?.bodyExcerpt || null,
        html_title: bestDiagnostic?.htmlTitle || null,
        resource_sample: bestDiagnostic?.resourceSample || null,
        response_bytes: bestDiagnostic?.responseBytes || null,
        anti_bot_detected: Boolean(bestDiagnostic?.antiBotDetected),
        was_selected: enoughPrices,
        reason: enoughPrices
          ? `total ${prices.length} annonces >= ${LC_MIN_PRICES} minimum`
          : (bestDiagnostic?.reason || `total ${prices.length} annonces < ${LC_MIN_PRICES} minimum`),
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

    // 4. Soumission si assez de prix
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
      // Pas assez de prix — signaler l'echec au backend pour diagnostic
      console.log('[OKazCar] LC pas assez de prix: %d < %d', prices.length, LC_MIN_PRICES);
      if (progress) {
        progress.update('collect', 'warning', prices.length + ' annonces trouvees (minimum ' + LC_MIN_PRICES + ')');
        progress.update('submit', 'skip', 'Pas assez de donnees');
        progress.update('bonus', 'skip');
      }

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
            site: 'lacentrale',
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

  // 5. Sauvegarder le timestamp (meme si pas assez de prix)
  markCollected();
  return { submitted, isCurrentVehicle };
}
