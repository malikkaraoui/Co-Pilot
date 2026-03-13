"use strict";

/**
 * Barrel re-export — point d'entree unique pour tous les symboles publics
 * du module ParuVendu.
 */

export {
  PV_URL_PATTERNS,
  AD_PAGE_PATTERN,
  JSONLD_SELECTOR,
  FUEL_MAP,
  TRANSMISSION_MAP,
  OWNER_TYPE_PATTERNS,
} from './constants.js';

export { parseJsonLd, parseAdPage } from './parser.js';

export { normalizeToAdData, buildBonusSignals } from './normalize.js';

export { ParuVenduExtractor } from './extractor.js';
