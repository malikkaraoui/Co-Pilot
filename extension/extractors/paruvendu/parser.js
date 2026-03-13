"use strict";

/**
 * ParuVendu — extraction des donnees depuis le DOM et le JSON-LD.
 *
 * PV fournit un JSON-LD de type Vehicle dans la page, mais les donnees
 * complementaires (description, vendeur, localisation, liens cote/fiche)
 * doivent etre scrapees depuis le DOM car elles ne sont pas structurees.
 */

import { JSONLD_SELECTOR, OWNER_TYPE_PATTERNS } from './constants.js';

/** Normalise les espaces et trim */
function normalizeSpace(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

/** Parse JSON en securite (retourne null si malformed) */
function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * Iterateur sur les items JSON-LD de la page.
 * Gere les blocs qui contiennent un seul objet ou un tableau.
 */
function* iterJsonLdItems(doc) {
  const nodes = doc.querySelectorAll(JSONLD_SELECTOR);
  for (const node of nodes) {
    const raw = node.textContent || '';
    const data = safeJsonParse(raw);
    if (!data) continue;
    const items = Array.isArray(data) ? data : [data];
    for (const item of items) {
      if (item && typeof item === 'object') {
        yield item;
      }
    }
  }
}

/**
 * Descend recursivement dans une structure JSON-LD pour trouver un noeud vehicule.
 * PV peut imbriquer le vehicule dans offers.itemOffered, @graph, ou directement.
 *
 * @param {*} input - Structure JSON-LD a explorer
 * @param {number} depth - Profondeur courante (securite anti-boucle)
 * @returns {object|null} Noeud vehicule ou null
 */
function findVehicleLikeNode(input, depth = 0) {
  if (!input || depth > 8) return null;
  if (Array.isArray(input)) {
    for (const item of input) {
      const found = findVehicleLikeNode(item, depth + 1);
      if (found) return found;
    }
    return null;
  }
  if (typeof input !== 'object') return null;

  const type = input['@type'];
  const types = Array.isArray(type) ? type : [type].filter(Boolean);
  const hasVehicleType = types.some((value) => /vehicle|car/i.test(String(value)));
  const hasVehicleSignals = Boolean(
    input.brand || input.model || input.vehicleTransmission || input.mileageFromOdometer || input.offers
  );

  if (hasVehicleType && hasVehicleSignals) return input;

  // Chercher dans offers.itemOffered (structure Offer > Vehicle)
  if (input.offers?.itemOffered) {
    const offered = findVehicleLikeNode(input.offers.itemOffered, depth + 1);
    if (offered) {
      // Fusionner les champs de l'offre parente (offers, description, image)
      return {
        ...offered,
        offers: offered.offers || input.offers,
        description: offered.description || input.description,
        image: offered.image || input.image,
      };
    }
  }

  // Chercher dans @graph
  if (Array.isArray(input['@graph'])) {
    for (const item of input['@graph']) {
      const found = findVehicleLikeNode(item, depth + 1);
      if (found) return found;
    }
  }

  // Dernier recours : explorer toutes les valeurs
  for (const value of Object.values(input)) {
    const found = findVehicleLikeNode(value, depth + 1);
    if (found) return found;
  }

  return null;
}

/** Extrait le texte complet de la page */
function textContent(doc) {
  return normalizeSpace(doc.body?.textContent || '');
}

/**
 * Cherche une localisation dans les headings de la page.
 * PV met souvent la ville + code postal dans un h2 ou h3.
 */
function extractHeadingLocation(doc) {
  const headings = doc.querySelectorAll('h2, h3');
  for (const node of headings) {
    const text = normalizeSpace(node.textContent);
    if (/\b\d{5}\b/.test(text)) return text;
  }
  return null;
}

/**
 * Extrait la description du vehicule.
 * Cherche d'abord un bloc "Description du vehicule" dans le DOM,
 * puis fallback sur la meta description.
 */
function extractDescription(doc) {
  const headings = Array.from(doc.querySelectorAll('h2, h3, h4, strong, span, div'));
  for (const heading of headings) {
    const title = normalizeSpace(heading.textContent).toLowerCase();
    if (!title.includes('description du v\u00e9hicule')) continue;
    const container = heading.closest('section, article, div') || heading.parentElement;
    const text = normalizeSpace(container?.textContent || '');
    if (text.length >= 50) return text.slice(0, 3000);
  }

  const metaDescription = doc.querySelector('meta[name="description"]')?.getAttribute('content');
  return normalizeSpace(metaDescription || '') || null;
}

/**
 * Detecte le type de vendeur (pro ou particulier) depuis le texte de la page.
 * PV n'a pas de champ structure — on se base sur des mots-cles.
 */
function extractOwnerType(doc) {
  const fullText = textContent(doc);
  if (OWNER_TYPE_PATTERNS.private.some((re) => re.test(fullText))) return 'private';
  if (OWNER_TYPE_PATTERNS.pro.some((re) => re.test(fullText))) return 'pro';
  return null;
}

/** Extrait la reference de l'annonce depuis le texte de la page */
function extractReference(doc) {
  const fullText = textContent(doc);
  const match = fullText.match(/R\u00e9f\. annonce\s*:\s*([^\n]+?)\s*-\s*Le/i);
  return match ? normalizeSpace(match[1]) : null;
}

/** Extrait le nombre de photos depuis le texte de la page */
function extractPhotoCount(doc) {
  const fullText = textContent(doc);
  const match = fullText.match(/(\d+)\s*photos disponibles/i);
  return match ? parseInt(match[1], 10) : 0;
}

/** Extrait le nom du vendeur depuis le texte de la page */
function extractSellerName(doc) {
  const fullText = textContent(doc);
  const match = fullText.match(/Annonce de\s+([^\-]+?)\s*-\s*[^\n]+membre depuis/i);
  if (match) return normalizeSpace(match[1]);
  return null;
}

/** Extrait un code postal 5 chiffres depuis un texte de localisation */
function extractPostalCode(locationText) {
  const match = String(locationText || '').match(/\b(\d{5})\b/);
  return match ? match[1] : null;
}

/** Extrait le nom de la ville depuis un texte de localisation */
function extractCity(locationText) {
  const value = normalizeSpace(locationText || '').replace(/^\d{5}\s+/, '');
  const cityBeforePostal = normalizeSpace(String(locationText || '').replace(/\s*\(\d{5}\).*$/, ''));
  return cityBeforePostal || value || null;
}

/**
 * Parse le JSON-LD pour trouver le noeud vehicule.
 *
 * @param {Document} doc
 * @returns {object|null} Noeud vehicule JSON-LD ou null
 */
export function parseJsonLd(doc) {
  for (const item of iterJsonLdItems(doc)) {
    const vehicle = findVehicleLikeNode(item);
    if (vehicle) return vehicle;
  }
  return null;
}

/**
 * Scrape les donnees complementaires depuis le DOM de la page d'annonce.
 * Extrait titre, localisation, description, type vendeur, references, etc.
 *
 * @param {Document} doc
 * @param {string} url - URL de l'annonce
 * @returns {object} Donnees extraites du DOM
 */
export function parseAdPage(doc, url) {
  const title = normalizeSpace(doc.querySelector('h1')?.textContent || doc.title || '') || null;
  const locationText = extractHeadingLocation(doc);
  const coteLinks = [];
  const ficheLinks = [];

  // Collecter les liens vers la cote et les fiches techniques
  for (const node of doc.querySelectorAll('a[href]')) {
    const href = node.href;
    if (href.includes('/cote-auto-gratuite/') && !coteLinks.includes(href)) coteLinks.push(href);
    if (href.includes('/fiches-techniques-auto/') && !ficheLinks.includes(href)) ficheLinks.push(href);
  }

  return {
    url,
    title,
    location_text: locationText,
    city: extractCity(locationText),
    zipcode: extractPostalCode(locationText),
    description: extractDescription(doc),
    owner_type: extractOwnerType(doc),
    seller_name: extractSellerName(doc),
    reference: extractReference(doc),
    photo_count: extractPhotoCount(doc),
    cote_links: coteLinks,
    fiche_links: ficheLinks,
    has_phone_cta: /voir le num\u00e9ro|contacter par t\u00e9l\u00e9phone/i.test(textContent(doc)),
    has_message_cta: /envoyer un message|contacter le vendeur/i.test(textContent(doc)),
  };
}
