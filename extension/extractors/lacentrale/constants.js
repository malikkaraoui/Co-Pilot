"use strict";

/**
 * La Centrale — URL patterns and mapping constants.
 */

// Detection patterns for lacentrale.fr ad pages
export const LC_URL_PATTERNS = [
  /lacentrale\.fr/,
];

// Ad page detection (annonce individuelle)
export const LC_AD_PAGE_PATTERN = /lacentrale\.fr\/auto-occasion-annonce-\d+\.html/;

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
