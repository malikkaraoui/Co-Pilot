"use strict";

/**
 * La Centrale — patterns URL et constantes de mapping.
 *
 * Contient les codes de filtre reverse-engineered depuis lacentrale.fr/listing
 * pour construire les URL de recherche (carburant, boite, regions).
 */

/** Patterns de detection du domaine La Centrale */
export const LC_URL_PATTERNS = [
  /lacentrale\.fr/,
];

/**
 * Detection d'une page d'annonce individuelle.
 * LC utilise plusieurs prefixes de verticales (auto, utilitaire, ...)
 * qui partagent la meme structure exploitable.
 */
export const LC_AD_PAGE_PATTERN = /lacentrale\.fr\/(?:auto|utilitaire)-occasion-annonce-\d+\.html/;

/** Normalisation carburant : valeurs LC → tokens standards */
export const LC_FUEL_MAP = {
  'DIESEL': 'diesel',
  'ESSENCE': 'essence',
  'ELECTRIQUE': 'electric',
  'HYBRIDE': 'hybrid',
  'HYBRIDE_RECHARGEABLE': 'hybrid',
  'GPL': 'lpg',
};

/** Normalisation boite de vitesses : valeurs LC → tokens standards */
export const LC_GEARBOX_MAP = {
  'MECANIQUE': 'manual',
  'MANUELLE': 'manual',
  'AUTOMATIQUE': 'automatic',
  'SEMI_AUTOMATIQUE': 'semi-automatic',
  'SEMI-AUTOMATIQUE': 'semi-automatic',
};

// ── Parametres URL de recherche (reverse-engineered depuis lacentrale.fr/listing) ──

/** URL de base pour les recherches listing */
export const LC_LISTING_BASE = 'https://www.lacentrale.fr/listing';

/**
 * Codes carburant pour le parametre URL ?energies=.
 * Verifie le 2026-03-09 sur lacentrale.fr.
 * GNV supprime : pas un vrai filtre sur LC.
 * Hybride rechargeable : necessite les deux codes hybRech ET plug_hyb.
 */
export const LC_SEARCH_FUEL_CODES = {
  'diesel': 'dies',
  'essence': 'ess',
  'electric': 'elec',
  'electrique': 'elec',
  'électrique': 'elec',
  'hybrid': 'hyb',
  'hybride': 'hyb',
  'hybrid rechargeable': 'hybRech,plug_hyb',
  'hybride rechargeable': 'hybRech,plug_hyb',
  'lpg': 'gpl',
  'gpl': 'gpl',
};

/**
 * Codes boite de vitesses pour le parametre URL ?gearbox=.
 * Verifie le 2026-03-09 : LC utilise des mots complets en majuscules (MANUAL, AUTO).
 * Les abreviations "man"/"auto" sont ignorees par le site = 0 resultat.
 */
export const LC_SEARCH_GEARBOX_CODES = {
  'manual': 'MANUAL',
  'manuelle': 'MANUAL',
  'automatic': 'AUTO',
  'automatique': 'AUTO',
};

/**
 * Codes region pour le parametre URL ?regions=.
 * Verifie le 2026-03-09 : LC supporte le filtrage regional via codes ISO-like.
 * Regions multiples : separees par virgules (ex: "FR-ARA,FR-BFC").
 */
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

/** Nombre minimum de prix pour considerer une collecte exploitable */
export const LC_MIN_PRICES = 20;

/** Plafond de prix a collecter (au-dela on arrete) */
export const LC_MAX_PRICES = 100;
