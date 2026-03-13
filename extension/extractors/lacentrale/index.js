"use strict";

/**
 * Barrel re-export — point d'entree unique pour tous les symboles publics
 * du module La Centrale.
 */

export {
  LC_URL_PATTERNS, LC_AD_PAGE_PATTERN,
  LC_FUEL_MAP, LC_GEARBOX_MAP,
  LC_LISTING_BASE, LC_SEARCH_FUEL_CODES, LC_SEARCH_GEARBOX_CODES,
  LC_MIN_PRICES, LC_MAX_PRICES,
} from './constants.js';

export {
  extractGallery, extractTcVars, extractCoteFromDom, extractJsonLd, extractAutovizaUrl,
} from './parser.js';

export {
  normalizeToAdData, buildBonusSignals,
} from './normalize.js';

export { buildLcSearchUrl, getLcMileageRange, fetchLcSearchPrices } from './search.js';

export { collectMarketPricesLC } from './collect.js';

export { LaCentraleExtractor } from './extractor.js';
