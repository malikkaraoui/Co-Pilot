"use strict";

export const PV_URL_PATTERNS = [/paruvendu\.fr/i];

export const AD_PAGE_PATTERN = /paruvendu\.fr\/a\/voiture-occasion\/[^/]+\/[^/]+\/\d+A1KVVO/i;

export const JSONLD_SELECTOR = 'script[type="application/ld+json"]';

export const FUEL_MAP = {
  diesel: 'diesel',
  essence: 'essence',
  hybride: 'hybride',
  'hybride rechargeable': 'hybride rechargeable',
  electrique: 'electrique',
  électrique: 'electrique',
  gpl: 'gpl',
  gnv: 'gnv',
  automatic: 'automatique',
};

export const TRANSMISSION_MAP = {
  automatic: 'automatique',
  automatique: 'automatique',
  manual: 'manuelle',
  manuelle: 'manuelle',
};

export const OWNER_TYPE_PATTERNS = {
  pro: [/\bprofessionnel\b/i, /\bconcessionnaire\b/i],
  private: [/vendeur particulier/i, /contacter le vendeur particulier/i],
};
