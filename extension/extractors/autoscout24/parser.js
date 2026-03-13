"use strict";

/**
 * Parsing des donnees AutoScout24.
 *
 * AS24 est une SPA Next.js qui stocke les donnees vehicule dans deux endroits :
 * 1. RSC (React Server Components) — payload JS dans les <script> de la page,
 *    contenant le maximum d'infos (dates, images, description, etc.)
 * 2. JSON-LD (schema.org) — donnees structurees pour le SEO
 *
 * La difficulte principale est le SPA : quand l'utilisateur navigue entre
 * annonces, les scripts peuvent contenir les donnees de PLUSIEURS vehicules.
 * On utilise un systeme de scoring pour choisir le bon vehicule en comparant
 * marque/modele avec le slug de l'URL courante.
 *
 * Contient aussi des extracteurs DOM fallback pour quand ni RSC ni JSON-LD
 * ne sont exploitables (dates, images, description, carburant, couleur).
 */

import { toAs24Slug } from './search.js';
import { _daysOnline, _daysSinceRefresh, _isRepublished } from './normalize.js';

// ── RSC payload parsing ─────────────────────────────────────────────

/**
 * Generateur qui extrait les objets JSON top-level d'un texte brut.
 * Parcourt le texte caractere par caractere en comptant les accolades
 * pour isoler chaque objet JSON valide. Necessaire car le RSC de AS24
 * contient plusieurs blobs JSON concatenes dans un meme <script>.
 *
 * @param {string} text - Texte brut contenant des objets JSON
 * @yields {string} Chaque objet JSON sous forme de string
 */
function* extractJsonObjects(text) {
  let i = 0;
  while (i < text.length) {
    if (text[i] !== '{') { i++; continue; }
    let depth = 0;
    let inString = false;
    let escape = false;
    const start = i;
    for (let j = i; j < text.length; j++) {
      const ch = text[j];
      if (escape) { escape = false; continue; }
      if (ch === '\\' && inString) { escape = true; continue; }
      if (ch === '"') { inString = !inString; continue; }
      if (inString) continue;
      if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        if (depth === 0) {
          yield text.slice(start, j + 1);
          i = j + 1;
          break;
        }
      }
      if (j === text.length - 1) i = j + 1;
    }
    if (depth !== 0) break;
  }
}

/**
 * Recherche recursive d'un noeud vehicule dans un objet JSON.
 * Un "vehicule" est un objet avec make + model + au moins un signal
 * supplementaire (vehicleCategory, price, firstRegistrationDate, mileage).
 *
 * @param {*} input - Objet a explorer
 * @param {number} depth - Profondeur courante (securite anti-boucle infinie)
 * @returns {object|null} Noeud vehicule trouve ou null
 */
function findVehicleNode(input, depth = 0) {
  if (!input || depth > 12) return null;

  if (Array.isArray(input)) {
    for (const item of input) {
      const found = findVehicleNode(item, depth + 1);
      if (found) return found;
    }
    return null;
  }

  if (typeof input !== 'object') return null;

  const obj = input;
  const hasMake = !!(typeof obj.make === 'string' || obj.make?.name);
  const hasModel = !!(typeof obj.model === 'string' || obj.model?.name);
  const isRealVehicle = (
    typeof obj.vehicleCategory === 'string'
    || typeof obj.price === 'number'
    || typeof obj.firstRegistrationDate === 'string'
    || typeof obj.mileage === 'number'
  );
  if (hasMake && hasModel && isRealVehicle) return obj;

  for (const value of Object.values(obj)) {
    const found = findVehicleNode(value, depth + 1);
    if (found) return found;
  }
  return null;
}

/**
 * Recherche les dates createdDate/lastModifiedDate dans un objet RSC.
 * Les dates peuvent etre dans un noeud different du vehicule lui-meme.
 */
function _findListingDates(input, depth = 0) {
  if (!input || depth > 12) return null;

  if (Array.isArray(input)) {
    for (const item of input) {
      const found = _findListingDates(item, depth + 1);
      if (found) return found;
    }
    return null;
  }

  if (typeof input !== 'object') return null;

  if (typeof input.createdDate === 'string' && input.createdDate.includes('T')) {
    return {
      createdDate: input.createdDate,
      lastModifiedDate: typeof input.lastModifiedDate === 'string' ? input.lastModifiedDate : null,
    };
  }

  for (const value of Object.values(input)) {
    const found = _findListingDates(value, depth + 1);
    if (found) return found;
  }
  return null;
}

/**
 * Parse du JSON-LD de maniere tolerante (gere les commentaires HTML autour).
 */
function parseLooselyJsonLd(text) {
  const cleaned = String(text || '')
    .trim()
    .replace(/^<!--\s*/, '')
    .replace(/\s*-->$/, '')
    .trim();

  if (!cleaned) return null;
  try {
    return JSON.parse(cleaned);
  } catch {
    return null;
  }
}

/**
 * Verifie si un noeud JSON-LD ressemble a un vehicule.
 * Criteres : @type=Car, ou Vehicle+marque+modele, ou marque+modele+signaux.
 */
function isVehicleLikeLdNode(node) {
  if (!node || typeof node !== 'object') return false;

  const type = String(node['@type'] || '').toLowerCase();
  if (type === 'car') return true;

  const hasMake = !!(node.brand?.name || node.brand);
  const hasModel = !!node.model;
  if (type === 'vehicle') return hasMake && hasModel;

  const hasSignals = !!(node.offers || node.vehicleModelDate || node.mileageFromOdometer || node.vehicleEngine);
  return hasMake && hasModel && hasSignals;
}

/**
 * Recherche recursive d'un noeud vehicule dans le JSON-LD.
 * Gere aussi les cas ou le vehicule est dans offers.itemOffered ou @graph.
 */
function findVehicleLikeLdNode(input, depth = 0) {
  if (!input || depth > 12) return null;

  if (Array.isArray(input)) {
    for (const item of input) {
      const found = findVehicleLikeLdNode(item, depth + 1);
      if (found) return found;
    }
    return null;
  }

  if (typeof input !== 'object') return null;
  if (isVehicleLikeLdNode(input)) return input;

  // Le vehicule peut etre dans offers.itemOffered (structure OfferCatalog)
  const itemOffered = input.offers?.itemOffered;
  if (itemOffered && isVehicleLikeLdNode(itemOffered)) {
    return {
      ...itemOffered,
      offers: input.offers,
      brand: itemOffered.brand || input.brand,
      name: itemOffered.name || input.name,
      image: itemOffered.image || input.image,
      description: itemOffered.description || input.description,
    };
  }

  if (Array.isArray(input['@graph'])) {
    for (const item of input['@graph']) {
      const found = findVehicleLikeLdNode(item, depth + 1);
      if (found) return found;
    }
  }

  for (const value of Object.values(input)) {
    const found = findVehicleLikeLdNode(value, depth + 1);
    if (found) return found;
  }
  return null;
}

/**
 * Extrait marque et modele depuis le slug de l'URL AS24.
 * Le slug a le format "marque-modele-XXXXX" (ex: "peugeot-308-12345678").
 *
 * @param {string} url - URL complete de l'annonce
 * @returns {{make: string|null, model: string|null}}
 */
export function extractMakeModelFromUrl(url) {
  try {
    const u = new URL(url);
    const match = u.pathname.match(
      /\/(?:d|angebote|offerte|ofertas|aanbod|offres|annunci|anuncios|oferta|erbjudanden)\/([a-z0-9][\w-]*?)[-–](?:\d+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9]{6,})(?:[/?#]|$)/i
    );
    if (!match) return { make: null, model: null };

    const slug = decodeURIComponent(match[1] || '');
    const tokens = slug.split('-').filter(Boolean);
    if (!tokens.length) return { make: null, model: null };

    return {
      make: tokens[0] ? tokens[0].toUpperCase() : null,
      model: tokens[1] ? tokens[1].toUpperCase() : null,
    };
  } catch {
    return { make: null, model: null };
  }
}

// ── DOM extraction helpers ──────────────────────────────────────────
// Fallbacks quand RSC et JSON-LD ne contiennent pas certaines infos.

/**
 * Extrait le nombre d'images depuis le __NEXT_DATA__ du DOM.
 * @param {Document} doc
 * @returns {number}
 */
export function _extractImageCountFromNextData(doc) {
  const el = doc.getElementById('__NEXT_DATA__');
  if (!el) return 0;
  try {
    const data = JSON.parse(el.textContent);
    const images = data?.props?.pageProps?.listingDetails?.images;
    return Array.isArray(images) ? images.length : 0;
  } catch (_) { return 0; }
}

/**
 * Extrait les dates de creation/modification depuis les scripts du DOM.
 * Cherche d'abord dans les scripts RSC (self.__next_f), puis dans __NEXT_DATA__.
 *
 * @param {Document} doc
 * @returns {{createdDate: string|null, lastModifiedDate: string|null}}
 */
export function _extractDatesFromDom(doc) {
  const scripts = doc.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    if (!text.includes('createdDate')) continue;

    // Les scripts RSC echappent les guillemets differemment
    const searchText = text.includes('self.__next_f')
      ? text.replace(/\\+"/g, '"')
      : text;

    const createdMatch = searchText.match(/"createdDate"\s*:\s*"([^"]+T[^"]+)"/);
    if (createdMatch) {
      const modifiedMatch = searchText.match(/"lastModifiedDate"\s*:\s*"([^"]+T[^"]+)"/);
      return {
        createdDate: createdMatch[1],
        lastModifiedDate: modifiedMatch ? modifiedMatch[1] : null,
      };
    }
  }

  const nextDataEl = doc.getElementById('__NEXT_DATA__');
  if (nextDataEl) {
    try {
      const nd = JSON.parse(nextDataEl.textContent);
      const ts = nd?.props?.pageProps?.listingDetails?.createdTimestampWithOffset;
      if (ts) return { createdDate: ts, lastModifiedDate: null };
    } catch (_) { /* ignore parse errors */ }
  }

  return { createdDate: null, lastModifiedDate: null };
}

function _normalizeText(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

/**
 * Extrait le type de carburant depuis le DOM visible de la page.
 * Utilise quand le RSC et le JSON-LD ne fournissent pas cette info.
 * Supporte les labels multilingues (Carburant, Kraftstoff, Fuel, etc.).
 *
 * @param {Document} doc
 * @returns {string|null}
 */
export function _extractFuelFromDom(doc) {
  // Chercher d'abord dans les scripts (fuelType en JSON)
  const scripts = doc.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    if (!text.includes('fuelType') && !text.includes('Kraftstoff') && !text.includes('Carburant')) continue;

    const fuelTypeMatch = text.match(/"fuelType"\s*:\s*"([^"]{2,40})"/i);
    if (fuelTypeMatch && fuelTypeMatch[1]) return _normalizeText(fuelTypeMatch[1]);
  }

  // Fallback : texte visible de la page (multi-locale)
  const fullText = _normalizeText(doc.body?.textContent || '');
  if (!fullText) return null;

  const re = /(?:carburant|kraftstoff|paliwo|combustible|carburante|brandstof|fuel)\s*[:\-]?\s*([A-Za-zÀ-ÿ0-9\- ]{2,48})/i;
  const m = fullText.match(re);
  if (!m || !m[1]) return null;

  const cleaned = _normalizeText(m[1])
    .replace(/[;,|].*$/, '')
    .split(/\s{2,}/)[0]
    .trim();

  if (!cleaned) return null;
  return cleaned.split(' ').slice(0, 3).join(' ').trim();
}

/**
 * Extrait la couleur du vehicule depuis le DOM visible.
 * Cherche les labels multilingues (Couleur, Farbe, Color, etc.)
 * d'abord dans les elements structurels, puis en fallback dans le texte complet.
 *
 * @param {Document} doc
 * @returns {string|null}
 */
export function _extractColorFromDom(doc) {
  const candidates = Array.from(doc.querySelectorAll('li, dt, dd, div, span'));
  const labelRe = /(couleur originale|couleur|farbe|lackierung|color|colore)/i;

  for (const node of candidates) {
    const txt = _normalizeText(node.textContent);
    if (!txt || txt.length < 6 || txt.length > 200) continue;
    if (!labelRe.test(txt)) continue;

    const inline = txt.match(/(?:couleur originale|couleur|farbe|lackierung|color|colore)\s*[:\-]?\s*(.{2,120})$/i);
    if (inline?.[1]) {
      const c = _normalizeText(inline[1]).replace(/[;,|].*$/, '').trim();
      if (c && c.length >= 2) return c;
    }

    const parent = node.closest('li, dl, div, section, article') || node.parentElement;
    if (parent) {
      const ptxt = _normalizeText(parent.textContent || '');
      const m = ptxt.match(/(?:couleur originale|couleur|farbe|lackierung|color|colore)\b\s*[:\-]?\s*(.{2,120})/i);
      if (m?.[1]) {
        const c = _normalizeText(m[1]).replace(/[;,|].*$/, '').trim();
        if (c && c.length >= 2) return c;
      }
    }
  }

  // Fallback texte complet
  const fullText = _normalizeText(doc.body?.textContent || '');
  if (!fullText) return null;
  const m = fullText.match(/(?:couleur originale|couleur|farbe|lackierung|color|colore)\b\s*[:\-]?\s*([A-Za-zÀ-ÿ0-9+\- ]{2,80})/i);
  if (!m?.[1]) return null;
  const color = _normalizeText(m[1]).replace(/[;,|].*$/, '').trim();
  return color || null;
}

/**
 * Extrait la description du vehicule depuis le DOM.
 * Essaie les selecteurs data-cy/data-testid, puis les sections "equipement",
 * puis les meta tags og:description et description.
 *
 * @param {Document} doc
 * @returns {string|null}
 */
export function _extractDescriptionFromDom(doc) {
  const directSelectors = [
    '[data-cy*="description"]',
    '[data-testid*="description"]',
    '#description',
    '[class*="description"]',
  ];

  for (const sel of directSelectors) {
    const nodes = doc.querySelectorAll(sel);
    for (const node of nodes) {
      const txt = _normalizeText(node.textContent);
      if (txt.length >= 50) return txt.slice(0, 2000);
    }
  }

  // Chercher la section equipements et lister les items
  const equipmentHeadingRe = /(équipement|equipement|ausstattung|equipment|dotazione|equipaggiamento|opzioni|options?)/i;
  const headings = doc.querySelectorAll('h1,h2,h3,h4,strong,span,div');
  for (const h of headings) {
    const title = _normalizeText(h.textContent);
    if (!title || title.length > 60 || !equipmentHeadingRe.test(title)) continue;

    const container = h.closest('section,article,div') || h.parentElement;
    if (!container) continue;

    const lis = Array.from(container.querySelectorAll('li'))
      .map((li) => _normalizeText(li.textContent))
      .filter((t) => t.length >= 3 && t.length <= 180);

    const uniq = [...new Set(lis)];
    if (uniq.length >= 3) {
      return uniq.join(' • ').slice(0, 2000);
    }
  }

  // Meta tags en dernier recours
  const ogDesc = _normalizeText(doc.querySelector('meta[property="og:description"]')?.getAttribute('content'));
  if (ogDesc.length >= 50) return ogDesc.slice(0, 2000);

  const metaDesc = _normalizeText(doc.querySelector('meta[name="description"]')?.getAttribute('content'));
  if (metaDesc.length >= 50) return metaDesc.slice(0, 2000);

  return null;
}

/**
 * Construit un ad_data minimal a partir du DOM quand RSC et JSON-LD sont absents.
 * Utilise comme dernier recours — ne recupere que le titre, prix, et marque/modele
 * depuis l'URL + les meta tags.
 *
 * @param {Document} doc
 * @param {string} url - URL de l'annonce
 * @returns {object} ad_data minimal
 */
export function fallbackAdDataFromDom(doc, url) {
  const h1 = doc.querySelector('h1')?.textContent?.trim() || null;
  const title = h1 || doc.querySelector('meta[property="og:title"]')?.getAttribute('content') || doc.title || null;
  const priceMeta = doc.querySelector('meta[property="product:price:amount"]')?.getAttribute('content');
  const price = priceMeta ? Number(String(priceMeta).replace(/[^\d.]/g, '')) : null;
  const currency = doc.querySelector('meta[property="product:price:currency"]')?.getAttribute('content') || null;
  const fromUrl = extractMakeModelFromUrl(url);
  const domDates = _extractDatesFromDom(doc);

  return {
    title,
    price_eur: Number.isFinite(price) ? price : null,
    currency,
    make: fromUrl.make,
    model: fromUrl.model,
    year_model: null,
    mileage_km: null,
    fuel: null,
    gearbox: null,
    doors: null,
    seats: null,
    first_registration: null,
    color: _extractColorFromDom(doc),
    power_fiscal_cv: null,
    power_din_hp: null,
    location: {
      city: null,
      zipcode: null,
      department: null,
      region: null,
      lat: null,
      lng: null,
    },
    phone: null,
    description: _extractDescriptionFromDom(doc),
    owner_type: 'private',
    owner_name: null,
    siret: null,
    raw_attributes: {},
    image_count: 0,
    has_phone: false,
    has_urgent: false,
    has_highlight: false,
    has_boost: false,
    publication_date: domDates.createdDate || null,
    days_online: _daysOnline(domDates.createdDate),
    index_date: domDates.lastModifiedDate || null,
    days_since_refresh: _daysSinceRefresh(domDates.createdDate, domDates.lastModifiedDate),
    republished: _isRepublished(domDates.createdDate, domDates.lastModifiedDate),
    lbc_estimation: null,
  };
}

// ── SPA scoring ─────────────────────────────────────────────────────
// En SPA, plusieurs vehicules peuvent coexister dans les scripts.
// On score chaque candidat contre le slug de l'URL pour trouver le bon.

/**
 * Score un vehicule candidat par rapport au slug de l'URL courante.
 * Plus le score est eleve, plus le vehicule correspond a l'annonce affichee.
 *
 * @param {object} vehicle - Noeud vehicule candidat
 * @param {string} urlSlug - Slug de l'URL (ex: "peugeot-308")
 * @param {string|null} expectedMake - Marque attendue depuis l'URL
 * @returns {number} Score de correspondance
 */
function _scoreVehicleAgainstUrl(vehicle, urlSlug, expectedMake = null) {
  if (!vehicle || !urlSlug) return 0;

  const make = typeof vehicle.make === 'string' ? vehicle.make : vehicle.make?.name;
  const model = typeof vehicle.model === 'string' ? vehicle.model : vehicle.model?.name;
  const makeSlug = toAs24Slug(make || '');
  const modelSlug = toAs24Slug(model || '');

  let score = 0;
  if (makeSlug && urlSlug.startsWith(makeSlug)) score += 2;

  if (expectedMake) {
    const expMake = toAs24Slug(expectedMake);
    if (expMake && makeSlug === expMake) score += 1;
  }

  if (modelSlug) {
    if (urlSlug.includes(modelSlug)) {
      score += 4;
    } else {
      // Match partiel sur les tokens du modele (ex: "classe-a" dans "mercedes-classe-a")
      const tokenHit = modelSlug
        .split('-')
        .filter((t) => t.length >= 3)
        .some((t) => urlSlug.includes(t));
      if (tokenHit) score += 2;
    }
  }

  return score;
}

// ── Main parsing exports ────────────────────────────────────────────

/**
 * Parse le payload RSC (React Server Components) de la page AS24.
 * Parcourt tous les <script> de la page, extrait les objets JSON,
 * et cherche les noeuds vehicule. En contexte SPA, utilise le scoring
 * pour choisir le vehicule qui correspond a l'URL courante.
 *
 * @param {Document} doc - Le document DOM
 * @param {string|null} currentUrl - URL courante (pour le scoring SPA)
 * @returns {object|null} Noeud vehicule RSC ou null
 */
export function parseRSCPayload(doc, currentUrl = null) {
  const scripts = doc.querySelectorAll('script');
  let lastFound = null;
  const candidates = [];

  // Extraire le slug et la marque attendue depuis l'URL pour le scoring SPA
  let urlSlug = '';
  let expectedMake = null;
  const sourceUrl = currentUrl || (typeof window !== 'undefined' ? window.location?.href : null);
  if (sourceUrl) {
    const slugMatch = String(sourceUrl).match(
      /\/(?:d|angebote|offerte|ofertas|aanbod|offres|annunci|anuncios|oferta|erbjudanden)\/([a-z0-9][\w-]*?)[-–](?:\d+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9]{6,})(?:[/?#]|$)/i
    );
    urlSlug = slugMatch ? decodeURIComponent(slugMatch[1]).toLowerCase() : '';
    expectedMake = extractMakeModelFromUrl(String(sourceUrl)).make;
  }

  let order = 0;
  for (const script of scripts) {
    const text = script.textContent || '';
    if (!text.includes('vehicleCategory') && !text.includes('firstRegistrationDate')) {
      continue;
    }

    // Les scripts RSC utilisent un echappement specifique des guillemets
    // qu'il faut decoder avant de pouvoir parser le JSON
    const candidateSources = [];

    if (text.includes('self.__next_f')) {
      const sentinel = '__AS24_ESCAPED_QUOTE__';
      const decoded = text
        .replace(/\\\\\\"/g, sentinel)
        .replace(/\\\\"/g, '"')
        .replaceAll(sentinel, '\\"');
      candidateSources.push(decoded);
      candidateSources.push(text.replace(/\\"/g, '"'));
    } else {
      candidateSources.push(text);
    }

    for (const source of candidateSources) {
      for (const candidate of extractJsonObjects(source)) {
      if (!candidate.includes('"vehicleCategory"') && !candidate.includes('"firstRegistrationDate"')) {
        continue;
      }
      try {
        const parsed = JSON.parse(candidate);
        const vehicle = findVehicleNode(parsed);
        if (vehicle) {
          // Les dates peuvent etre dans un noeud parent du vehicule
          if (!vehicle.createdDate) {
            const dates = _findListingDates(parsed);
            if (dates) {
              vehicle.createdDate = dates.createdDate;
              if (!vehicle.lastModifiedDate) {
                vehicle.lastModifiedDate = dates.lastModifiedDate;
              }
            }
          }
          lastFound = vehicle;
          candidates.push({ vehicle, order: order++ });
        }
      } catch {
        // Not valid JSON, try next candidate
      }
      }
    }
  }

  if (!candidates.length) return null;

  // Sans slug d'URL, on prend le dernier vehicule trouve (le plus recent dans le DOM)
  if (!urlSlug) return lastFound;

  // Avec un slug, on score chaque candidat pour trouver le meilleur match
  let best = null;
  let bestScore = -1;
  for (const c of candidates) {
    const score = _scoreVehicleAgainstUrl(c.vehicle, urlSlug, expectedMake);
    if (score > bestScore || (score === bestScore && (!best || c.order > best.order))) {
      best = c;
      bestScore = score;
    }
  }

  return best?.vehicle || lastFound;
}

/**
 * Parse le JSON-LD (schema.org) de la page AS24.
 * Cherche le premier noeud vehicule valide dans tous les <script type="application/ld+json">.
 *
 * @param {Document} doc
 * @returns {object|null} Noeud vehicule JSON-LD ou null
 */
export function parseJsonLd(doc) {
  const scripts = doc.querySelectorAll('script[type="application/ld+json"]');
  for (const script of scripts) {
    const data = parseLooselyJsonLd(script.textContent || '');
    if (!data) continue;
    const vehicle = findVehicleLikeLdNode(data);
    if (vehicle) return vehicle;
  }
  return null;
}

/**
 * Cherche un JSON-LD correspondant a une marque specifique.
 * Utilise en fallback SPA quand le RSC contient des donnees obsoletes :
 * on cherche un JSON-LD qui matche la marque/modele de l'URL.
 *
 * @param {Document} doc
 * @param {string} expectedMake - Marque attendue
 * @param {string|null} expectedModel - Modele attendu
 * @param {string} urlSlug - Slug de l'URL pour le scoring
 * @returns {object|null} Noeud vehicule JSON-LD ou null
 */
export function _findJsonLdByMake(doc, expectedMake, expectedModel = null, urlSlug = '') {
  const target = (expectedMake || '').toLowerCase();
  if (!target) return null;
  const scripts = doc.querySelectorAll('script[type="application/ld+json"]');

  let best = null;
  let bestScore = -1;
  let order = 0;

  for (const script of scripts) {
    const data = parseLooselyJsonLd(script.textContent || '');
    if (!data) continue;
    const vehicle = findVehicleLikeLdNode(data);
    if (!vehicle) continue;

    const brand = String(vehicle.brand?.name || vehicle.brand || '').toLowerCase();
    if (brand !== target) continue;

    const model = typeof vehicle.model === 'string' ? vehicle.model : vehicle.model?.name;
    const modelSlug = toAs24Slug(model || '');
    const expectedModelSlug = toAs24Slug(expectedModel || '');

    let score = 2;
    if (expectedModelSlug && modelSlug && modelSlug === expectedModelSlug) {
      score += 3;
    }
    if (urlSlug && modelSlug && urlSlug.includes(modelSlug)) {
      score += 2;
    }

    const candidate = { vehicle, score, order: order++ };
    if (!best || candidate.score > bestScore || (candidate.score === bestScore && candidate.order > best.order)) {
      best = candidate;
      bestScore = candidate.score;
    }
  }
  return best?.vehicle || null;
}
