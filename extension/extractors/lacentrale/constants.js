"use strict";

/**
 * La Centrale — URL patterns and mapping constants.
 */

// Detection patterns for lacentrale.fr ad pages
export const LC_URL_PATTERNS = [
  /lacentrale\.fr/,
];

// Ad page detection (annonce individuelle)
// La Centrale utilise plusieurs préfixes de verticales (`auto`, `utilitaire`, ...)
// pour des pages qui gardent la même structure d'annonce exploitable.
export const LC_AD_PAGE_PATTERN = /lacentrale\.fr\/(?:auto|utilitaire)-occasion-annonce-\d+\.html/;

// Fuel normalization: La Centrale energy values → standard fuel tokens
export const LC_FUEL_MAP = {
  'DIESEL': 'diesel',
  'ESSENCE': 'essence',
  'ELECTRIQUE': 'electric',
  'HYBRIDE': 'hybrid',
  'HYBRIDE_RECHARGEABLE': 'hybrid',
  'GPL': 'lpg',
  'GNV': 'cng',
};

// Gearbox normalization
export const LC_GEARBOX_MAP = {
  'MECANIQUE': 'manual',
  'MANUELLE': 'manual',
  'AUTOMATIQUE': 'automatic',
  'SEMI_AUTOMATIQUE': 'semi-automatic',
  'SEMI-AUTOMATIQUE': 'semi-automatic',
};

// ── Search URL parameters (reverse-engineered from lacentrale.fr/listing) ──

// Base URL for listing searches
export const LC_LISTING_BASE = 'https://www.lacentrale.fr/listing';

// Fuel codes for search URL ?energies= param
export const LC_SEARCH_FUEL_CODES = {
  'diesel': 'dies',
  'essence': 'ess',
  'electric': 'elec',
  'electrique': 'elec',
  'électrique': 'elec',
  'hybrid': 'hyb',
  'hybride': 'hyb',
  'hybrid rechargeable': 'hybRech',
  'hybride rechargeable': 'hybRech',
  'lpg': 'gpl',
  'gpl': 'gpl',
  'cng': 'gnv',
  'gnv': 'gnv',
};

// Gearbox codes for search URL ?gearbox= param
// Verified 2026-03-09: LC uses uppercase full words (MANUAL, AUTO), NOT abbreviations.
// "man"/"auto" are silently ignored by the site = 0 results with gearbox filter.
export const LC_SEARCH_GEARBOX_CODES = {
  'manual': 'MANUAL',
  'manuelle': 'MANUAL',
  'automatic': 'AUTO',
  'automatique': 'AUTO',
};

// Region codes for search URL ?regions= param
// Verified 2026-03-09: LC supports regional filtering via ISO-like codes.
// Multiple regions: comma-separated (e.g. "FR-ARA,FR-BFC").
export const LC_SEARCH_REGION_CODES = {
  'Île-de-France': 'FR-IDF',
  'Auvergne-Rhône-Alpes': 'FR-ARA',
  'Provence-Alpes-Côte d\'Azur': 'FR-PAC',
  'Occitanie': 'FR-OCC',
  'Nouvelle-Aquitaine': 'FR-NAQ',
  'Hauts-de-France': 'FR-HDF',
  'Grand Est': 'FR-GES',
  'Bretagne': 'FR-BRE',
  'Pays de la Loire': 'FR-PDL',
  'Normandie': 'FR-NOR',
  'Bourgogne-Franche-Comté': 'FR-BFC',
  'Centre-Val de Loire': 'FR-CVL',
  'Corse': 'FR-COR',
};

// Min prices to consider a collection successful
export const LC_MIN_PRICES = 20;

// Max prices cap
export const LC_MAX_PRICES = 100;
