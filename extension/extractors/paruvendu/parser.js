"use strict";

import { JSONLD_SELECTOR, OWNER_TYPE_PATTERNS } from './constants.js';

function normalizeSpace(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

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

  if (input.offers?.itemOffered) {
    const offered = findVehicleLikeNode(input.offers.itemOffered, depth + 1);
    if (offered) {
      return {
        ...offered,
        offers: offered.offers || input.offers,
        description: offered.description || input.description,
        image: offered.image || input.image,
      };
    }
  }

  if (Array.isArray(input['@graph'])) {
    for (const item of input['@graph']) {
      const found = findVehicleLikeNode(item, depth + 1);
      if (found) return found;
    }
  }

  for (const value of Object.values(input)) {
    const found = findVehicleLikeNode(value, depth + 1);
    if (found) return found;
  }

  return null;
}

function textContent(doc) {
  return normalizeSpace(doc.body?.textContent || '');
}

function extractHeadingLocation(doc) {
  const headings = doc.querySelectorAll('h2, h3');
  for (const node of headings) {
    const text = normalizeSpace(node.textContent);
    if (/\b\d{5}\b/.test(text)) return text;
  }
  return null;
}

function extractDescription(doc) {
  const headings = Array.from(doc.querySelectorAll('h2, h3, h4, strong, span, div'));
  for (const heading of headings) {
    const title = normalizeSpace(heading.textContent).toLowerCase();
    if (!title.includes('description du véhicule')) continue;
    const container = heading.closest('section, article, div') || heading.parentElement;
    const text = normalizeSpace(container?.textContent || '');
    if (text.length >= 50) return text.slice(0, 3000);
  }

  const metaDescription = doc.querySelector('meta[name="description"]')?.getAttribute('content');
  return normalizeSpace(metaDescription || '') || null;
}

function extractOwnerType(doc) {
  const fullText = textContent(doc);
  if (OWNER_TYPE_PATTERNS.private.some((re) => re.test(fullText))) return 'private';
  if (OWNER_TYPE_PATTERNS.pro.some((re) => re.test(fullText))) return 'pro';
  return null;
}

function extractReference(doc) {
  const fullText = textContent(doc);
  const match = fullText.match(/Réf\. annonce\s*:\s*([^\n]+?)\s*-\s*Le/i);
  return match ? normalizeSpace(match[1]) : null;
}

function extractPhotoCount(doc) {
  const fullText = textContent(doc);
  const match = fullText.match(/(\d+)\s*photos disponibles/i);
  return match ? parseInt(match[1], 10) : 0;
}

function extractSellerName(doc) {
  const fullText = textContent(doc);
  const match = fullText.match(/Annonce de\s+([^\-]+?)\s*-\s*[^\n]+membre depuis/i);
  if (match) return normalizeSpace(match[1]);
  return null;
}

function extractPostalCode(locationText) {
  const match = String(locationText || '').match(/\b(\d{5})\b/);
  return match ? match[1] : null;
}

function extractCity(locationText) {
  const value = normalizeSpace(locationText || '').replace(/^\d{5}\s+/, '');
  const cityBeforePostal = normalizeSpace(String(locationText || '').replace(/\s*\(\d{5}\).*$/, ''));
  return cityBeforePostal || value || null;
}

export function parseJsonLd(doc) {
  for (const item of iterJsonLdItems(doc)) {
    const vehicle = findVehicleLikeNode(item);
    if (vehicle) return vehicle;
  }
  return null;
}

export function parseAdPage(doc, url) {
  const title = normalizeSpace(doc.querySelector('h1')?.textContent || doc.title || '') || null;
  const locationText = extractHeadingLocation(doc);
  const coteLinks = [];
  const ficheLinks = [];

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
    has_phone_cta: /voir le numéro|contacter par téléphone/i.test(textContent(doc)),
    has_message_cta: /envoyer un message|contacter le vendeur/i.test(textContent(doc)),
  };
}
