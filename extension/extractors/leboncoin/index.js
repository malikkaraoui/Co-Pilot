"use strict";

/**
 * Barrel re-export — point d'entree unique pour tous les symboles publics
 * du module LeBonCoin.
 *
 * Les consommateurs (content.js, extractors/index.js, tests) importent depuis ici
 * sans avoir a connaitre la structure interne des sous-modules.
 */

export { initLbcDeps, lbcDeps } from './_deps.js';

export {
  GENERIC_MODELS, EXCLUDED_CATEGORIES,
  LBC_BRAND_ALIASES, DUAL_BRAND_ALIASES,
  LBC_REGIONS, LBC_FUEL_CODES, LBC_GEARBOX_CODES,
  COLLECT_COOLDOWN_MS, DEFAULT_SEARCH_RADIUS, MIN_PRICES_FOR_ARGUS,
  getHorsePowerRange, getMileageRange, brandMatches,
} from './constants.js';

export {
  isStaleData, extractNextData, extractLbcTokensFromDom,
  extractModelFromTitle, extractVehicleFromNextData,
  toLbcBrandToken, getAdYear,
  extractRegionFromNextData, extractLocationFromNextData,
  getAdDetails, parseRange, extractMileageFromNextData,
} from './parser.js';

export {
  isUserLoggedIn, detectAutovizaUrl, revealPhoneNumber, isAdPageLBC,
} from './dom.js';

export {
  buildApiFilters, filterAndMapSearchAds,
  fetchSearchPricesViaApi, fetchSearchPricesViaHtml,
  fetchSearchPrices, buildLocationParam,
} from './search.js';

export {
  reportJobDone, executeBonusJobs, maybeCollectMarketPrices,
} from './collect.js';

export { LeBonCoinExtractor } from './extractor.js';
