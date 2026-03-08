"use strict";

// Barrel re-export — every public symbol from the La Centrale extractor modules.

export {
  LC_URL_PATTERNS, LC_AD_PAGE_PATTERN,
  LC_FUEL_MAP, LC_GEARBOX_MAP,
} from './constants.js';

export {
  extractGallery, extractTcVars, extractCoteFromDom, extractJsonLd, extractAutovizaUrl,
} from './parser.js';

export {
  normalizeToAdData, buildBonusSignals,
} from './normalize.js';

export { LaCentraleExtractor } from './extractor.js';
