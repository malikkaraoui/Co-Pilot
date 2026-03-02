/**
 * Extractor Registry
 *
 * Retourne le bon SiteExtractor en fonction de l'URL courante.
 * Ajouter un nouveau site = ajouter un import + une entree dans EXTRACTORS.
 */

import { LeBonCoinExtractor } from './leboncoin.js';
import { AutoScout24Extractor } from './autoscout24.js';

const EXTRACTORS = [LeBonCoinExtractor, AutoScout24Extractor];

/**
 * Retourne une instance du bon extracteur pour l'URL donnee,
 * ou null si aucun site n'est reconnu.
 *
 * @param {string} url
 * @returns {SiteExtractor|null}
 */
export function getExtractor(url) {
  for (const ExtractorClass of EXTRACTORS) {
    for (const pattern of ExtractorClass.URL_PATTERNS) {
      if (pattern.test(url)) {
        return new ExtractorClass();
      }
    }
  }
  return null;
}
