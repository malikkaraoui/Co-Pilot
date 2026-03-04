"use strict";

// ── URL patterns ────────────────────────────────────────────────────

export const AS24_URL_PATTERNS = [
  /autoscout24\.\w+\/(?:fr|de|it|en|nl|es)?\/?d\//,
  /autoscout24\.\w+\/angebote\//,
  /autoscout24\.\w+\/offerte\//,
  /autoscout24\.\w+\/ofertas\//,
  /autoscout24\.\w+\/aanbod\//,
];

export const AD_PAGE_PATTERN = /autoscout24\.\w+\/(?:(?:fr|de|it|en|nl|es)\/)?(?:d|angebote|offerte|ofertas|aanbod)\/\S+-[a-f0-9-]+/;

// TLD → country mapping for region field
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

// TLD → currency (omitted = EUR by default)
export const TLD_TO_CURRENCY = {
  ch: 'CHF',
  pl: 'PLN',
  se: 'SEK',
};

// TLD → ISO country code (for backend MarketPrice.country)
export const TLD_TO_COUNTRY_CODE = {
  ch: 'CH', de: 'DE', fr: 'FR', it: 'IT',
  at: 'AT', be: 'BE', nl: 'NL', es: 'ES',
  pl: 'PL', lu: 'LU', se: 'SE', com: 'INT',
};

// Swiss ZIP prefix (2 digits) → canton name (French, matching backend SWISS_CANTONS)
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

// Minimum prices to submit
export const MIN_PRICES = 10;

export const FUEL_MAP = {
  gasoline: 'Essence',
  diesel: 'Diesel',
  electric: 'Electrique',
  'mhev-diesel': 'Diesel',
  'mhev-gasoline': 'Essence',
  'phev-diesel': 'Hybride Rechargeable',
  'phev-gasoline': 'Hybride Rechargeable',
  cng: 'GNV',
  lpg: 'GPL',
  hydrogen: 'Hydrogene',
  hybrid: 'Hybride',
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

export const TRANSMISSION_MAP = {
  automatic: 'Automatique',
  manual: 'Manuelle',
  'semi-automatic': 'Automatique',
};

export const AS24_GEAR_MAP = {
  automatic: 'A',
  automatique: 'A',
  'semi-automatic': 'A',
  manual: 'M',
  manuelle: 'M',
};

export const AS24_FUEL_CODE_MAP = {
  gasoline: 'B', diesel: 'D', electric: 'E',
  cng: 'C', lpg: 'L', hydrogen: 'H',
  'mhev-diesel': 'D', 'mhev-gasoline': 'B',
  'phev-diesel': '2', 'phev-gasoline': '2',
  essence: 'B', electrique: 'E',
  gnv: 'C', gpl: 'L', hydrogene: 'H',
  'hybride rechargeable': '2',
};

// Canton center ZIP codes for geo-targeted searches (chef-lieu)
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

// TLDs using the Swiss Marketplace Group platform (different URL structure)
export const SMG_TLDS = new Set(['ch']);
