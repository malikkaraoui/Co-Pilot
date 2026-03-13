"use strict";

/**
 * ParuVendu — normalisation des donnees vers le format ad_data du backend.
 *
 * Fusionne deux sources :
 * - JSON-LD (schema.org/Vehicle) : donnees structurees du vehicule
 * - domData (parseAdPage) : complement scrape depuis le DOM
 *   (titre, description, type vendeur, localisation, etc.)
 */

import { FUEL_MAP, TRANSMISSION_MAP } from './constants.js';

/** Normalise les espaces et trim */
function normalizeSpace(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

/** Convertit en cle de lookup minuscule */
function toKey(value) {
  return normalizeSpace(value).toLowerCase();
}

/** Extrait un entier depuis une valeur (supprime tout sauf les chiffres) */
function toInt(value) {
  if (value == null) return null;
  const digits = String(value).replace(/[^\d]/g, '');
  return digits ? parseInt(digits, 10) : null;
}

/** Extrait l'annee (4 chiffres) depuis le debut d'une date */
function yearFromDate(value) {
  const match = String(value || '').match(/^(\d{4})/);
  return match ? match[1] : null;
}

/** Resout la marque depuis le JSON-LD (peut etre string ou objet {name}) */
function resolveBrand(vehicle) {
  if (!vehicle) return null;
  if (typeof vehicle.brand === 'string') return vehicle.brand;
  return vehicle.brand?.name || null;
}

/** Normalise le carburant via le FUEL_MAP */
function resolveFuel(vehicle) {
  const raw = vehicle?.fuelType || vehicle?.vehicleEngine?.fuelType || null;
  const key = toKey(raw);
  return FUEL_MAP[key] || normalizeSpace(raw) || null;
}

/** Normalise la boite de vitesses via le TRANSMISSION_MAP */
function resolveTransmission(vehicle) {
  const raw = vehicle?.vehicleTransmission || null;
  const key = toKey(raw);
  return TRANSMISSION_MAP[key] || normalizeSpace(raw) || null;
}

/** Compte les images depuis le JSON-LD ou le DOM */
function resolveImageCount(vehicle, domData) {
  if (Array.isArray(vehicle?.image)) return vehicle.image.length;
  return domData?.photo_count || 0;
}

/** Construit les attributs bruts supplementaires (non normalises) */
function buildRawAttributes(vehicle, domData) {
  return {
    body_type: vehicle?.bodyType || null,
    color: vehicle?.color || null,
    reference: domData?.reference || null,
    cote_links: domData?.cote_links || [],
    fiche_links: domData?.fiche_links || [],
  };
}

/**
 * Construit les signaux bonus depuis les donnees DOM de ParuVendu.
 * PV a peu de donnees structurees — on affiche les liens cote/fiche
 * et les infos vendeur quand elles sont disponibles.
 *
 * @param {object} domData - Donnees extraites du DOM
 * @returns {Array<{label: string, value: string, status: string}>}
 */
export function buildBonusSignals(domData = {}) {
  const signals = [];

  if (domData.reference) {
    signals.push({ label: 'Référence', value: domData.reference, status: 'info' });
  }
  if (domData.cote_links?.length) {
    signals.push({ label: 'Cote native', value: 'Disponible', status: 'info' });
  }
  if (domData.fiche_links?.length) {
    signals.push({ label: 'Fiche technique', value: 'Disponible', status: 'info' });
  }
  if (domData.owner_type === 'private' && domData.seller_name) {
    signals.push({ label: 'Vendeur', value: domData.seller_name, status: 'info' });
  }

  return signals;
}

/**
 * Normalise les donnees ParuVendu en un objet ad_data unifie.
 *
 * @param {object} vehicle - JSON-LD parse (schema.org/Vehicle)
 * @param {object} domData - Donnees extraites du DOM
 * @param {string} url - URL de l'annonce
 * @returns {object|null} ad_data normalise pour /api/analyze
 */
export function normalizeToAdData(vehicle, domData, url) {
  if (!vehicle && !domData) return null;

  const offers = vehicle?.offers || {};
  const seller = offers?.seller || offers?.offeredBy || {};
  const sellerAddress = seller?.address || {};
  const price = offers?.price ?? vehicle?.price ?? null;
  const mileage = vehicle?.mileageFromOdometer?.value ?? null;

  return {
    title: domData?.title || vehicle?.name || null,
    price_eur: toInt(price),
    currency: offers?.priceCurrency || 'EUR',
    make: resolveBrand(vehicle),
    model: vehicle?.model || null,
    year_model: yearFromDate(vehicle?.dateVehicleFirstRegistered || vehicle?.productionDate),
    mileage_km: toInt(mileage),
    fuel: resolveFuel(vehicle),
    gearbox: resolveTransmission(vehicle),
    doors: toInt(vehicle?.numberOfDoors),
    seats: toInt(vehicle?.vehicleSeatingCapacity || vehicle?.seatingCapacity),
    first_registration: yearFromDate(vehicle?.dateVehicleFirstRegistered || vehicle?.productionDate),
    color: vehicle?.color || null,
    power_fiscal_cv: null,
    power_din_hp: null,
    country: 'FR',
    location: {
      city: domData?.city || sellerAddress?.addressLocality || null,
      zipcode: domData?.zipcode || sellerAddress?.postalCode || null,
      department: null,
      region: null,
      lat: null,
      lng: null,
    },
    phone: null,
    description: domData?.description || normalizeSpace(vehicle?.description || ''),
    owner_type: domData?.owner_type || null,
    owner_name: domData?.seller_name || seller?.name || null,
    siret: null,
    dealer_rating: null,
    dealer_review_count: null,
    raw_attributes: buildRawAttributes(vehicle, domData),
    image_count: resolveImageCount(vehicle, domData),
    has_phone: Boolean(domData?.has_phone_cta),
    has_urgent: false,
    has_highlight: false,
    has_boost: false,
    publication_date: null,
    days_online: null,
    index_date: null,
    days_since_refresh: null,
    republished: false,
    lbc_estimation: null,
    source: 'paruvendu',
    url,
  };
}
