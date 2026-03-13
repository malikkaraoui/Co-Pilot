"use strict";

/**
 * La Centrale — normalisation des donnees vers le format ad_data du backend.
 *
 * Fusionne quatre sources :
 * - CLASSIFIED_GALLERY (gallery) : donnees principales du vehicule
 * - tc_vars : variables de tracking avec complements (garantie, badges)
 * - cote : cotation La Centrale extraite du DOM
 * - JSON-LD : fallback schema.org/Car
 *
 * Produit aussi les bonus signals specifiques a LC :
 * badge bonne affaire, kilometrage, nombre de proprietaires, etc.
 */

import { LC_FUEL_MAP, LC_GEARBOX_MAP } from './constants.js';

/**
 * Normalise les donnees La Centrale en un objet ad_data unifie.
 *
 * Les champs prefixes lc_ sont specifiques a La Centrale et passes
 * au backend pour un eventuel usage L4 (cotation, badges, etc.).
 *
 * @param {object} gallery - Donnees CLASSIFIED_GALLERY parsees
 * @param {object} tcVars - Variables tc_vars
 * @param {object} cote - {quotation, trustIndex} depuis le DOM
 * @param {object} jsonLd - JSON-LD Car en fallback
 * @returns {object} ad_data normalise pour /api/analyze
 */
export function normalizeToAdData(gallery, tcVars, cote, jsonLd) {
  const classified = gallery?.classified || {};
  const vehicle = gallery?.vehicle || {};
  const images = gallery?.images || {};
  const tc = tcVars || {};
  const ld = jsonLd || {};

  const fuel = _normalizeFuel(vehicle.energy);
  const gearbox = _normalizeGearbox(vehicle.gearbox);
  const ownerType = _resolveOwnerType(classified, tc);
  const year = _resolveYear(classified, vehicle, ld);
  const imageCount = _resolveImageCount(images);
  const description = _resolveDescription(classified, vehicle);
  const department = classified.visitPlace || tc.department_list?.[0] || null;
  const zipcode = classified.zipCode || tc.zip_code || null;
  const phone = _resolvePhone(classified, ld, tc);

  return {
    title: classified.title || ld.name || null,
    price_eur: classified.price ?? ld.offers?.price ?? null,
    currency: 'EUR',
    make: vehicle.make || ld.brand || null,
    model: vehicle.model || vehicle.commercialModel || ld.model || null,
    year_model: year,
    mileage_km: classified.mileage ?? ld.mileageFromOdometer?.value ?? null,
    fuel,
    gearbox,
    doors: vehicle.nbOfDoors ?? ld.numberOfDoors ?? null,
    seats: vehicle.seatingCapacity ?? null,
    first_registration: vehicle.firstTrafficDate || ld.dateVehicleFirstRegistered || null,
    color: vehicle.externalColor || ld.color || null,
    power_fiscal_cv: vehicle.fiscalHorsePower ?? null,
    power_din_hp: vehicle.powerDin ?? ld.vehicleEngine?.enginePower?.value ?? null,
    country: 'FR',
    location: {
      city: null,
      zipcode,
      department,
      region: _departmentToRegion(department),
      lat: null,
      lng: null,
    },
    phone,
    description,
    owner_type: ownerType,
    owner_name: classified.sellerName || tc.dealer_name || null,
    siret: null,
    dealer_rating: tc.rating_satisfaction ?? null,
    dealer_review_count: tc.rating_count ?? null,
    raw_attributes: {},
    image_count: imageCount,
    has_phone: Boolean(phone),
    has_urgent: false,
    has_highlight: false,
    has_boost: false,
    publication_date: null,
    days_online: _resolveDisplayedAge(classified),
    index_date: null,
    days_since_refresh: null,
    republished: false,
    lbc_estimation: null,

    // Champs specifiques La Centrale — transmis au backend pour usage potentiel
    lc_quotation: cote?.quotation ?? null,
    lc_trust_index: cote?.trustIndex ?? null,
    lc_good_deal_badge: classified.goodDealBadge || null,
    lc_mileage_badge: classified.mileageBadge || null,
    lc_average_mileage: classified.averageMileage ?? null,
    lc_nb_owners: vehicle.nbOfOwners ?? null,
    lc_is_international: vehicle.international ?? null,
    lc_price_variation: classified.priceVariation || null,
    lc_first_hand: classified.firstHand ?? null,
    lc_warranty_duration: tc.warranty_duration ?? null,
    lc_badge_maintenance: tc.badge_maintenance ?? null,
    lc_owner_sub_category: tc.owner_sub_category ?? null,
    lc_critair: vehicle.critair?.critairLevel ?? null,
    lc_euro_standard: vehicle.critair?.standardMet ?? null,
    lc_model_raw: vehicle.model || null,
    lc_commercial_model: vehicle.commercialModel || null,
    lc_family: vehicle.family || null,
    lc_version: vehicle.version || null,
  };
}

/**
 * Construit les signaux bonus affiches dans la popup pour La Centrale.
 * Ces signaux exploitent les donnees riches de LC (badges, cotation, Crit'Air).
 *
 * @param {object} gallery - Donnees CLASSIFIED_GALLERY parsees
 * @param {object} tcVars - Variables tc_vars
 * @param {object} cote - {quotation, trustIndex}
 * @returns {Array<{label: string, value: string, status: string}>}
 */
export function buildBonusSignals(gallery, tcVars, cote) {
  const signals = [];
  const classified = gallery?.classified || {};
  const vehicle = gallery?.vehicle || {};
  const tc = tcVars || {};

  // Badge "bonne affaire" de La Centrale
  if (classified.goodDealBadge) {
    const badgeLabels = {
      'VERY_GOOD_DEAL': 'Très bonne affaire',
      'GOOD_DEAL': 'Bonne affaire',
      'FAIR_PRICE': 'Prix correct',
    };
    const label = badgeLabels[classified.goodDealBadge] || classified.goodDealBadge;
    signals.push({
      label: 'Badge La Centrale',
      value: label,
      status: classified.goodDealBadge.includes('GOOD') ? 'pass' : 'info',
    });
  }

  // Badge kilometrage (au-dessus ou en-dessous de la moyenne)
  if (classified.mileageBadge) {
    signals.push({
      label: 'Kilométrage',
      value: classified.mileageBadge === 'OVER_MILEAGE' ? 'Au-dessus de la moyenne' : 'En-dessous de la moyenne',
      status: classified.mileageBadge === 'OVER_MILEAGE' ? 'warning' : 'pass',
    });
  }

  // Nombre de proprietaires
  if (vehicle.nbOfOwners != null) {
    signals.push({
      label: 'Propriétaires',
      value: String(vehicle.nbOfOwners),
      status: vehicle.nbOfOwners <= 1 ? 'pass' : vehicle.nbOfOwners <= 2 ? 'info' : 'warning',
    });
  }

  // Cotation La Centrale
  if (cote?.quotation) {
    signals.push({
      label: 'Cote La Centrale',
      value: `${cote.quotation.toLocaleString('fr-FR')} €`,
      status: 'info',
    });
  }

  // Tendance de prix (en baisse = bon signe pour l'acheteur)
  if (classified.priceVariation?.prices?.isDropping) {
    signals.push({
      label: 'Prix',
      value: 'En baisse',
      status: 'pass',
    });
  }

  // Vehicule importe
  if (vehicle.international === true) {
    signals.push({
      label: 'Import',
      value: 'Véhicule importé',
      status: 'warning',
    });
  }

  // Garantie
  if (tc.warranty_duration) {
    signals.push({
      label: 'Garantie',
      value: `${tc.warranty_duration} mois`,
      status: 'pass',
    });
  }

  // Badge entretien
  if (tc.badge_maintenance) {
    const labels = Array.isArray(tc.badge_maintenance) ? tc.badge_maintenance : [tc.badge_maintenance];
    for (const badge of labels) {
      if (badge === 'entretienAVerifier') {
        signals.push({ label: 'Entretien', value: 'À vérifier', status: 'warning' });
      } else if (badge === 'entretienOk') {
        signals.push({ label: 'Entretien', value: 'OK', status: 'pass' });
      }
    }
  }

  // Vignette Crit'Air
  if (vehicle.critair?.critairLevel) {
    signals.push({
      label: "Crit'Air",
      value: `${vehicle.critair.critairLevel} (${vehicle.critair.standardMet || '?'})`,
      status: 'info',
    });
  }

  // Note vendeur
  if (tc.rating_satisfaction && tc.rating_count) {
    signals.push({
      label: 'Avis vendeur',
      value: `${tc.rating_satisfaction}/5 (${tc.rating_count} avis)`,
      status: 'info',
    });
  }

  return signals;
}

// ── Helpers internes ─────────────────────────────────────────

/** Normalise le carburant LC vers un token standard */
function _normalizeFuel(energy) {
  if (!energy) return null;
  return LC_FUEL_MAP[energy.toUpperCase()] || energy.toLowerCase();
}

/** Normalise la boite de vitesses LC vers un token standard */
function _normalizeGearbox(gearbox) {
  if (!gearbox) return null;
  return LC_GEARBOX_MAP[gearbox.toUpperCase()] || gearbox.toLowerCase();
}

/**
 * Determine si le vendeur est pro ou particulier.
 * Priorite : classified.customerType > tc_vars.owner_category > defaut.
 */
function _resolveOwnerType(classified, tc) {
  if (classified.customerType === 'PRO') return 'pro';
  if (classified.customerType === 'PART' || classified.customerType === 'PARTICULIER') return 'private';
  if (tc.owner_category === 'professionnel') return 'pro';
  if (tc.owner_category === 'particulier') return 'private';
  return 'private';
}

/** Extrait l'annee depuis les differentes sources disponibles */
function _resolveYear(classified, vehicle, ld) {
  if (classified.year) return String(classified.year);
  if (vehicle.firstTrafficDate) {
    const m = vehicle.firstTrafficDate.match(/^(\d{4})/);
    if (m) return m[1];
  }
  if (ld.dateVehicleFirstRegistered) return String(ld.dateVehicleFirstRegistered);
  return null;
}

/** Compte les images — gere les deux structures possibles de l'objet images */
function _resolveImageCount(images) {
  const pics = images?.v1?.pictures || images?.pictures;
  if (Array.isArray(pics)) return pics.length;
  return 0;
}

/**
 * Resout la description du vehicule.
 * LC a souvent pas de description libre — on synthetise une description
 * depuis les caracteristiques structurees quand c'est le cas.
 */
function _resolveDescription(classified, vehicle) {
  if (classified.description?.content) return classified.description.content;
  if (typeof classified.description === 'string' && classified.description.length > 0) return classified.description;

  // Description synthetique depuis les donnees structurees
  const parts = [];
  if (vehicle?.make && vehicle?.model) parts.push(`${vehicle.make} ${vehicle.model}`);
  if (vehicle?.energy) parts.push(vehicle.energy);
  if (vehicle?.gearbox) parts.push(vehicle.gearbox);
  if (vehicle?.powerDin) parts.push(`${vehicle.powerDin} ch`);
  if (vehicle?.fiscalHorsePower) parts.push(`${vehicle.fiscalHorsePower} CV`);
  if (vehicle?.externalColor) parts.push(vehicle.externalColor);
  if (vehicle?.nbOfDoors) parts.push(`${vehicle.nbOfDoors} portes`);
  if (classified.mileage) parts.push(`${classified.mileage.toLocaleString('fr-FR')} km`);

  return parts.length > 0 ? parts.join(' — ') : null;
}

/** Extrait le nombre de jours en ligne depuis priceVariation.displayedAge */
function _resolveDisplayedAge(classified) {
  const age = classified.priceVariation?.displayedAge;
  if (typeof age === 'number' && age >= 0) return age;
  return null;
}

/** Nettoie et valide un numero de telephone francais */
function _cleanPhone(phone) {
  if (!phone) return null;
  const raw = String(phone).trim();
  const compact = raw.replace(/[^\d+]/g, '');
  if (/^\+33\d{9}$/.test(compact) || /^0\d{9}$/.test(compact)) return compact;
  return null;
}

/**
 * Resout le telephone depuis toutes les sources possibles.
 * LC stocke le telephone sous des cles differentes selon la version du payload.
 */
function _resolvePhone(classified, ld, tc) {
  const candidates = [
    classified?.contactPhone,
    classified?.phone,
    classified?.telephone,
    Array.isArray(classified?.phones) ? classified.phones[0] : classified?.phones,
    ld?.telephone,
    tc?.phone,
    tc?.telephone,
  ];

  for (const candidate of candidates) {
    const cleaned = _cleanPhone(candidate);
    if (cleaned) return cleaned;
  }
  return null;
}

/**
 * Mapping departement → region.
 * Ici on passe directement le departement — le backend gere le mapping complet.
 */
function _departmentToRegion(dept) {
  if (!dept) return null;
  return dept;
}
