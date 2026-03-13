"use strict";

/**
 * Constantes specifiques a LeBonCoin.
 *
 * Contient les mappings necessaires a la collecte de prix sur LBC :
 * - Codes carburant/boite pour les filtres de recherche
 * - Identifiants region LBC (rn_XX)
 * - Aliases de marques (ex: MERCEDES -> MERCEDES-BENZ)
 * - Seuils et parametres de la collecte
 *
 * Les re-exports depuis shared/ assurent la retrocompatibilite
 * pour les modules qui importaient ces fonctions depuis constants.js.
 */

import { COLLECT_COOLDOWN_MS as _COOLDOWN } from '../../shared/cooldown.js';
import { brandsMatch as _brandsMatch } from '../../shared/brand.js';
import { getHpRange, getMileageRange as _getMileageRange } from '../../shared/ranges.js';

/** Modeles generiques a ignorer pour la recherche par modele */
export const GENERIC_MODELS = ["autres", "autre", "other", "divers"];

/** Categories d'annonces a exclure de la collecte (pas des voitures) */
export const EXCLUDED_CATEGORIES = ["motos", "equipement_moto", "caravaning", "nautisme"];

/** Aliases de marques : le nom courant vers le token LBC officiel */
export const LBC_BRAND_ALIASES = {
  MERCEDES: "MERCEDES-BENZ",
};

/**
 * Marques "duales" : une marque qui peut aussi etre listee sous une autre.
 * Ex: DS est une marque autonome mais certaines annonces restent sous Citroen.
 */
export const DUAL_BRAND_ALIASES = {
  DS: "CITROEN",
};

/**
 * Mapping region -> code LBC (rn_XX).
 * Inclut les anciennes regions (avant la reforme 2016) qui sont mappees
 * vers leur nouvelle region pour retrocompatibilite.
 */
export const LBC_REGIONS = {
  "Île-de-France": "rn_12",
  "Auvergne-Rhône-Alpes": "rn_22",
  "Provence-Alpes-Côte d'Azur": "rn_21",
  "Occitanie": "rn_16",
  "Nouvelle-Aquitaine": "rn_20",
  "Hauts-de-France": "rn_17",
  "Grand Est": "rn_8",
  "Bretagne": "rn_6",
  "Pays de la Loire": "rn_18",
  "Normandie": "rn_4",
  "Bourgogne-Franche-Comté": "rn_5",
  "Centre-Val de Loire": "rn_7",
  "Corse": "rn_9",
  "Nord-Pas-de-Calais": "rn_17",
  "Picardie": "rn_17",
  "Rhône-Alpes": "rn_22",
  "Auvergne": "rn_22",
  "Midi-Pyrénées": "rn_16",
  "Languedoc-Roussillon": "rn_16",
  "Aquitaine": "rn_20",
  "Poitou-Charentes": "rn_20",
  "Limousin": "rn_20",
  "Alsace": "rn_8",
  "Lorraine": "rn_8",
  "Champagne-Ardenne": "rn_8",
  "Basse-Normandie": "rn_4",
  "Haute-Normandie": "rn_4",
  "Bourgogne": "rn_5",
  "Franche-Comté": "rn_5",
};

/** Codes carburant pour le filtre &fuel= des URL de recherche LBC */
export const LBC_FUEL_CODES = {
  "essence": 1,
  "diesel": 2,
  "gpl": 3,
  "electrique": 4,
  "électrique": 4,
  "autre": 5,
  "hybride": 6,
  "gnv": 7,
  "gaz naturel": 7,
  "hybride rechargeable": 8,
  "électrique & essence": 6,
  "electrique & essence": 6,
  "électrique & diesel": 6,
  "electrique & diesel": 6,
};

/** Codes boite de vitesses pour le filtre &gearbox= */
export const LBC_GEARBOX_CODES = {
  "manuelle": 1,
  "automatique": 2,
};

export const COLLECT_COOLDOWN_MS = _COOLDOWN;
/** Rayon de recherche geolocalisee en metres (30 km) */
export const DEFAULT_SEARCH_RADIUS = 30000;
/** Nombre minimum de prix pour considerer la collecte exploitable */
export const MIN_PRICES_FOR_ARGUS = 20;

// Re-exports from shared/ for backward compatibility
export const getHorsePowerRange = getHpRange;
export const getMileageRange = _getMileageRange;
export const brandMatches = _brandsMatch;
