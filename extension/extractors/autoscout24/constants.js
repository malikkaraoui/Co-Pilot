"use strict";

/**
 * Constantes specifiques a AutoScout24.
 *
 * AS24 est un site multi-pays (CH, DE, FR, IT...) avec des structures d'URL
 * differentes selon le TLD et la plateforme (SMG pour .ch, GmbH pour les autres).
 * D'ou la profusion de mappings TLD → pays, devises, codes canton, etc.
 */

// ── Patterns de detection d'URL ─────────────────────────────────
// Couvre tous les TLD et toutes les langues d'interface d'AS24
export const AS24_URL_PATTERNS = [
  /autoscout24\.\w+\/(?:(?:fr|de|it|en|nl|es|pl|sv)\/)?(?:d|angebote|offerte|ofertas|aanbod|offres|annunci|anuncios|oferta|erbjudanden)\//i,
];

// Pattern plus strict pour identifier une page d'annonce individuelle
// (vs une page de listing de resultats)
export const AD_PAGE_PATTERN = /autoscout24\.\w+\/(?:(?:fr|de|it|en|nl|es|pl|sv)\/)?(?:d|angebote|offerte|ofertas|aanbod|offres|annunci|anuncios|oferta|erbjudanden)\/[a-z0-9][\w-]*?[-–](?:\d+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9]{6,})(?:[/?#]|$)/i;

// ── Mappings TLD → metadonnees pays ─────────────────────────────
// Chaque TLD d'AS24 correspond a un pays, une devise, un code ISO
export const TLD_TO_COUNTRY = {
  ch: 'Suisse',
  de: 'Allemagne',
  fr: 'France',
  it: 'Italie',
  at: 'Autriche',
  be: 'Belgique',
  nl: 'Pays-Bas',
  es: 'Espagne',
  pl: 'Pologne',
  lu: 'Luxembourg',
  se: 'Suede',
  com: 'International',
};

// TLD → devise (omit = EUR par defaut)
export const TLD_TO_CURRENCY = {
  ch: 'CHF',
  pl: 'PLN',
  se: 'SEK',
};

// TLD → code ISO pays (pour le backend MarketPrice.country)
export const TLD_TO_COUNTRY_CODE = {
  ch: 'CH', de: 'DE', fr: 'FR', it: 'IT',
  at: 'AT', be: 'BE', nl: 'NL', es: 'ES',
  pl: 'PL', lu: 'LU', se: 'SE', com: 'INT',
};

// ── Suisse : mapping code postal → canton ───────────────────────
// Les 2 premiers chiffres du NPA suisse determinent le canton.
// On utilise ca pour la granularite regionale de la collecte de prix.
export const SWISS_ZIP_TO_CANTON = {
  '10': 'Vaud', '11': 'Vaud', '12': 'Geneve', '13': 'Vaud',
  '14': 'Vaud', '15': 'Vaud', '16': 'Fribourg', '17': 'Fribourg',
  '18': 'Vaud', '19': 'Valais',
  '20': 'Neuchatel', '21': 'Neuchatel', '22': 'Neuchatel', '23': 'Neuchatel',
  '24': 'Jura', '25': 'Berne', '26': 'Berne', '27': 'Jura',
  '28': 'Jura', '29': 'Jura',
  '30': 'Berne', '31': 'Berne', '32': 'Berne', '33': 'Berne',
  '34': 'Berne', '35': 'Berne', '36': 'Berne', '37': 'Berne',
  '38': 'Berne', '39': 'Valais',
  '40': 'Bale-Ville', '41': 'Bale-Campagne', '42': 'Bale-Campagne',
  '43': 'Argovie', '44': 'Bale-Campagne', '45': 'Soleure', '46': 'Soleure',
  '47': 'Soleure', '48': 'Argovie', '49': 'Berne',
  '50': 'Argovie', '51': 'Argovie', '52': 'Argovie', '53': 'Argovie',
  '54': 'Argovie', '55': 'Argovie', '56': 'Argovie', '57': 'Argovie',
  '58': 'Argovie', '59': 'Argovie',
  '60': 'Lucerne', '61': 'Lucerne', '62': 'Lucerne',
  '63': 'Zoug', '64': 'Schwyz', '65': 'Obwald',
  '66': 'Tessin', '67': 'Tessin', '68': 'Tessin', '69': 'Tessin',
  '70': 'Grisons', '71': 'Grisons', '72': 'Grisons', '73': 'Grisons',
  '74': 'Grisons', '75': 'Grisons', '76': 'Grisons', '77': 'Grisons',
  '78': 'Grisons', '79': 'Grisons',
  '80': 'Zurich', '81': 'Zurich', '82': 'Schaffhouse', '83': 'Zurich',
  '84': 'Zurich', '85': 'Thurgovie', '86': 'Zurich', '87': 'Saint-Gall',
  '88': 'Zurich', '89': 'Saint-Gall',
  '90': 'Saint-Gall', '91': 'Appenzell Rhodes-Exterieures', '92': 'Saint-Gall',
  '93': 'Saint-Gall', '94': 'Saint-Gall', '95': 'Thurgovie', '96': 'Saint-Gall',
  '97': 'Saint-Gall',
};

// Nombre minimum de prix pour considerer la collecte exploitable
export const MIN_PRICES = 10;

// ── Normalisation carburant ─────────────────────────────────────
// AS24 utilise des labels multilingues qu'on normalise en francais
export const FUEL_MAP = {
  gasoline: 'Essence',
  benzin: 'Essence',
  benzine: 'Essence',
  benzyna: 'Essence',
  petrol: 'Essence',
  gasolina: 'Essence',
  diesel: 'Diesel',
  gazole: 'Diesel',
  'olej napedowy': 'Diesel',
  electric: 'Electrique',
  elektryczny: 'Electrique',
  elektryczna: 'Electrique',
  electricity: 'Electrique',
  'mhev-diesel': 'Diesel',
  'mhev-gasoline': 'Essence',
  'phev-diesel': 'Hybride Rechargeable',
  'phev-gasoline': 'Hybride Rechargeable',
  cng: 'GNV',
  lpg: 'GPL',
  hydrogen: 'Hydrogene',
  hybrid: 'Hybride',
  hybride: 'Hybride',
  hybryda: 'Hybride',
  'hybrid-diesel': 'Hybride',
  'hybrid-gasoline': 'Hybride',
  'mild-hybrid': 'Hybride',
  'mild-hybrid-diesel': 'Diesel',
  'mild-hybrid-gasoline': 'Essence',
  'plug-in-hybrid': 'Hybride Rechargeable',
  'plug-in-hybrid-diesel': 'Hybride Rechargeable',
  'plug-in-hybrid-gasoline': 'Hybride Rechargeable',
  ethanol: 'Ethanol',
  'e85': 'Ethanol',
  bifuel: 'Bicarburation',
};

// Normalisation transmission
export const TRANSMISSION_MAP = {
  automatic: 'Automatique',
  manual: 'Manuelle',
  'semi-automatic': 'Automatique',
};

// ── Codes de filtre pour les URL de recherche AS24 ──────────────
// Utilisés pour construire les URLs de recherche de prix
export const AS24_GEAR_MAP = {
  automatic: 'A',
  automatique: 'A',
  'semi-automatic': 'A',
  manual: 'M',
  manuelle: 'M',
};

// Codes carburant AS24 : B=Benzin, D=Diesel, E=Electric, etc.
export const AS24_FUEL_CODE_MAP = {
  gasoline: 'B', diesel: 'D', electric: 'E',
  benzin: 'B', benzine: 'B', benzyna: 'B', petrol: 'B', gasolina: 'B',
  gazole: 'D', 'olej napedowy': 'D',
  cng: 'C', lpg: 'L', hydrogen: 'H',
  'mhev-diesel': 'D', 'mhev-gasoline': 'B',
  'phev-diesel': '3', 'phev-gasoline': '2',
  essence: 'B', electrique: 'E',
  gnv: 'C', gpl: 'L', hydrogene: 'H',
  'electrique/essence': '2',
  'electrique/diesel': '3',
  'hybride rechargeable': '2',
};

// Code postal du chef-lieu de chaque canton suisse
// pour les recherches geolocalisees sur AS24.ch
export const CANTON_CENTER_ZIP = {
  'Zurich': '8000', 'Berne': '3000', 'Lucerne': '6000', 'Uri': '6460',
  'Schwyz': '6430', 'Obwald': '6060', 'Nidwald': '6370', 'Glaris': '8750',
  'Zoug': '6300', 'Fribourg': '1700', 'Soleure': '4500', 'Bale-Ville': '4000',
  'Bale-Campagne': '4410', 'Schaffhouse': '8200',
  'Appenzell Rhodes-Exterieures': '9100', 'Appenzell Rhodes-Interieures': '9050',
  'Saint-Gall': '9000', 'Grisons': '7000', 'Argovie': '5000', 'Thurgovie': '8500',
  'Tessin': '6500', 'Vaud': '1000', 'Valais': '1950', 'Neuchatel': '2000',
  'Geneve': '1200', 'Jura': '2800',
};

// TLDs qui utilisent la plateforme Swiss Marketplace Group (structure d'URL differente)
export const SMG_TLDS = new Set(['ch']);
