"use strict";

/**
 * ParuVendu — patterns URL et constantes de mapping.
 *
 * ParuVendu est un site d'annonces generaliste avec une section vehicules.
 * Les URL d'annonces suivent le format /a/voiture-occasion/<ville>/<dept>/<id>A1KVVO.
 */

/** Patterns de detection du domaine ParuVendu */
export const PV_URL_PATTERNS = [/paruvendu\.fr/i];

/** Detection d'une page d'annonce individuelle */
export const AD_PAGE_PATTERN = /paruvendu\.fr\/a\/voiture-occasion\/[^/]+\/[^/]+\/\d+A1KVVO/i;

/** Selecteur pour les blocs JSON-LD dans le DOM */
export const JSONLD_SELECTOR = 'script[type="application/ld+json"]';

/** Normalisation carburant : tokens ParuVendu → tokens standards */
export const FUEL_MAP = {
  diesel: 'diesel',
  essence: 'essence',
  hybride: 'hybride',
  'hybride rechargeable': 'hybride rechargeable',
  electrique: 'electrique',
  '\u00e9lectrique': 'electrique',
  gpl: 'gpl',
  gnv: 'gnv',
  automatic: 'automatique',
};

/** Normalisation boite de vitesses */
export const TRANSMISSION_MAP = {
  automatic: 'automatique',
  automatique: 'automatique',
  manual: 'manuelle',
  manuelle: 'manuelle',
};

/**
 * Patterns de detection du type de vendeur dans le texte de la page.
 * PV n'a pas de champ structure pour ca — on se base sur le wording.
 */
export const OWNER_TYPE_PATTERNS = {
  pro: [/\bprofessionnel\b/i, /\bconcessionnaire\b/i],
  private: [/vendeur particulier/i, /contacter le vendeur particulier/i],
};
