"use strict";

import { LC_FUEL_MAP, LC_GEARBOX_MAP } from './constants.js';

/**
 * Normalize La Centrale data into the ad_data contract expected by the backend.
 *
 * @param {object} gallery  — parsed CLASSIFIED_GALLERY (from extractGallery)
 * @param {object} tcVars   — parsed tc_vars
 * @param {object} cote     — {quotation, trustIndex} from extractCoteFromDom
 * @param {object} jsonLd   — JSON-LD Car object (fallback)
 * @returns {object} ad_data compatible with /api/analyze
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

    // La Centrale specifics (passed through ad_data for potential L4 use)
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
 * Build bonus signals from La Centrale data for the popup display.
 */
export function buildBonusSignals(gallery, tcVars, cote) {
  const signals = [];
  const classified = gallery?.classified || {};
  const vehicle = gallery?.vehicle || {};
  const tc = tcVars || {};

  // Good deal badge
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

  // Mileage badge
  if (classified.mileageBadge) {
    signals.push({
      label: 'Kilométrage',
      value: classified.mileageBadge === 'OVER_MILEAGE' ? 'Au-dessus de la moyenne' : 'En-dessous de la moyenne',
      status: classified.mileageBadge === 'OVER_MILEAGE' ? 'warning' : 'pass',
    });
  }

  // Number of owners
  if (vehicle.nbOfOwners != null) {
    signals.push({
      label: 'Propriétaires',
      value: String(vehicle.nbOfOwners),
      status: vehicle.nbOfOwners <= 1 ? 'pass' : vehicle.nbOfOwners <= 2 ? 'info' : 'warning',
    });
  }

  // La Cote quotation
  if (cote?.quotation) {
    signals.push({
      label: 'Cote La Centrale',
      value: `${cote.quotation.toLocaleString('fr-FR')} €`,
      status: 'info',
    });
  }

  // Price variation
  if (classified.priceVariation?.prices?.isDropping) {
    signals.push({
      label: 'Prix',
      value: 'En baisse',
      status: 'pass',
    });
  }

  // Import flag
  if (vehicle.international === true) {
    signals.push({
      label: 'Import',
      value: 'Véhicule importé',
      status: 'warning',
    });
  }

  // Warranty
  if (tc.warranty_duration) {
    signals.push({
      label: 'Garantie',
      value: `${tc.warranty_duration} mois`,
      status: 'pass',
    });
  }

  // Maintenance badge
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

  // Crit'Air
  if (vehicle.critair?.critairLevel) {
    signals.push({
      label: "Crit'Air",
      value: `${vehicle.critair.critairLevel} (${vehicle.critair.standardMet || '?'})`,
      status: 'info',
    });
  }

  // Seller rating
  if (tc.rating_satisfaction && tc.rating_count) {
    signals.push({
      label: 'Avis vendeur',
      value: `${tc.rating_satisfaction}/5 (${tc.rating_count} avis)`,
      status: 'info',
    });
  }

  return signals;
}

// ── Internal helpers ─────────────────────────────────────────

function _normalizeFuel(energy) {
  if (!energy) return null;
  return LC_FUEL_MAP[energy.toUpperCase()] || energy.toLowerCase();
}

function _normalizeGearbox(gearbox) {
  if (!gearbox) return null;
  return LC_GEARBOX_MAP[gearbox.toUpperCase()] || gearbox.toLowerCase();
}

function _resolveOwnerType(classified, tc) {
  if (classified.customerType === 'PRO') return 'pro';
  if (classified.customerType === 'PART' || classified.customerType === 'PARTICULIER') return 'private';
  if (tc.owner_category === 'professionnel') return 'pro';
  if (tc.owner_category === 'particulier') return 'private';
  // Default: if isPro flag in config
  return 'private';
}

function _resolveYear(classified, vehicle, ld) {
  if (classified.year) return String(classified.year);
  if (vehicle.firstTrafficDate) {
    const m = vehicle.firstTrafficDate.match(/^(\d{4})/);
    if (m) return m[1];
  }
  if (ld.dateVehicleFirstRegistered) return String(ld.dateVehicleFirstRegistered);
  return null;
}

function _resolveImageCount(images) {
  // images can be {v1: {pictures: [...]}} or {pictures: [...]}
  const pics = images?.v1?.pictures || images?.pictures;
  if (Array.isArray(pics)) return pics.length;
  return 0;
}

function _resolveDescription(classified, vehicle) {
  // 1. Real text description if available
  if (classified.description?.content) return classified.description.content;
  if (typeof classified.description === 'string' && classified.description.length > 0) return classified.description;

  // 2. Build a synthetic description from structured vehicle data
  // LC often has no free-text description — characteristics are structured
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

function _resolveDisplayedAge(classified) {
  // priceVariation.displayedAge = days online on La Centrale
  const age = classified.priceVariation?.displayedAge;
  if (typeof age === 'number' && age >= 0) return age;
  return null;
}

function _cleanPhone(phone) {
  if (!phone) return null;
  const raw = String(phone).trim();
  const compact = raw.replace(/[^\d+]/g, '');
  if (/^\+33\d{9}$/.test(compact) || /^0\d{9}$/.test(compact)) return compact;
  return null;
}

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
 * Very basic department→region mapping for French departments.
 * La Centrale provides the department number (e.g., "88" for Vosges).
 */
function _departmentToRegion(dept) {
  if (!dept) return null;
  // Return the department as-is — the backend handles region mapping
  return dept;
}
