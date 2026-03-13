"use strict";

/**
 * Barrel re-export — point d'entree unique pour tous les symboles publics
 * du module AutoScout24.
 *
 * Les consommateurs (extractors/index.js, tests) importent depuis ici
 * sans avoir a connaitre la structure interne des sous-modules.
 */

export {
  AS24_URL_PATTERNS, AD_PAGE_PATTERN,
  TLD_TO_COUNTRY, TLD_TO_CURRENCY, TLD_TO_COUNTRY_CODE,
  SWISS_ZIP_TO_CANTON, MIN_PRICES,
  FUEL_MAP, TRANSMISSION_MAP, AS24_GEAR_MAP, AS24_FUEL_CODE_MAP,
  CANTON_CENTER_ZIP, SMG_TLDS,
} from './constants.js';

export {
  getCantonFromZip, mapFuelType, mapTransmission,
  getAs24GearCode, getAs24FuelCode,
  getAs24PowerParams, getAs24KmParams,
  getHpRangeString, parseHpRange, getCantonCenterZip,
} from './helpers.js';

export {
  normalizeToAdData, buildBonusSignals,
  _yearFromDate, _daysOnline, _daysSinceRefresh, _isRepublished,
} from './normalize.js';

export {
  extractTld, extractLang, toAs24Slug, extractAs24SlugsFromSearchUrl,
  buildSearchUrl, brandMatchesAs24, parseSearchPrices,
} from './search.js';

export {
  parseRSCPayload, parseJsonLd,
  extractMakeModelFromUrl,
  _extractImageCountFromNextData, _extractDatesFromDom,
  _extractDescriptionFromDom, _extractColorFromDom, fallbackAdDataFromDom,
  _findJsonLdByMake,
} from './parser.js';

export { AutoScout24Extractor } from './extractor.js';
