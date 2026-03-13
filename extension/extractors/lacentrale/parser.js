"use strict";

/**
 * La Centrale — extraction des donnees depuis le DOM et les scripts JS.
 *
 * Sources de donnees (par ordre de priorite) :
 * 1. window.CLASSIFIED_GALLERY — donnees structurees principales (~9 KB)
 *    Contient le vehicule complet, les images, le vendeur, les badges LC.
 * 2. window.tc_vars — variables de tracking (complements : garantie, badges, etc.)
 * 3. Lien cote-auto dans le DOM — cotation et indice de confiance
 * 4. JSON-LD (schema.org/Car) — fallback basique si les sources JS sont absentes
 */

/**
 * Extrait le CLASSIFIED_GALLERY depuis la page.
 * Tolere deux structures differentes :
 * - gallery.data.{classified, vehicle, images} (avec wrapper)
 * - gallery.{classified, vehicle, images} (sans wrapper)
 *
 * @param {Window} win
 * @returns {{classified: object, vehicle: object, images: object, config: object}|null}
 */
export function extractGallery(win) {
  const raw = win.CLASSIFIED_GALLERY;
  if (!raw || typeof raw !== 'object') return null;

  // Shape 1 : gallery.data.{classified, vehicle, images}
  if (raw.data && typeof raw.data === 'object') {
    const d = raw.data;
    if (d.classified || d.vehicle) {
      return {
        classified: d.classified || {},
        vehicle: d.vehicle || {},
        images: d.images || {},
        config: raw.config || raw,
      };
    }
  }

  // Shape 2 : gallery.{classified, vehicle, images} (pas de wrapper data)
  if (raw.classified || raw.vehicle) {
    return {
      classified: raw.classified || {},
      vehicle: raw.vehicle || {},
      images: raw.images || {},
      config: raw.config || {},
    };
  }

  return null;
}

/**
 * Extrait les variables de tracking tc_vars.
 * Contient des complements utiles : garantie, badges entretien, note vendeur.
 *
 * @param {Window} win
 * @returns {object}
 */
export function extractTcVars(win) {
  return (win.tc_vars && typeof win.tc_vars === 'object') ? win.tc_vars : {};
}

/**
 * Extrait la cotation "La Cote" depuis un lien dans le DOM.
 * Cherche un lien vers cote-auto avec les parametres quotation et trustIndex.
 * Ex: <a href="...cote-auto...?quotation=12380&trustIndex=2...">
 *
 * @param {Document} doc
 * @returns {{quotation: number|null, trustIndex: number|null}}
 */
export function extractCoteFromDom(doc) {
  const link = doc.querySelector('a[href*="cote-auto"]');
  if (!link) return { quotation: null, trustIndex: null };

  try {
    const url = new URL(link.href, 'https://www.lacentrale.fr');
    const quotation = parseInt(url.searchParams.get('quotation'), 10);
    const trustIndex = parseInt(url.searchParams.get('trustIndex'), 10);
    return {
      quotation: Number.isFinite(quotation) ? quotation : null,
      trustIndex: Number.isFinite(trustIndex) ? trustIndex : null,
    };
  } catch {
    return { quotation: null, trustIndex: null };
  }
}

/**
 * Extrait le JSON-LD de type Car ou Vehicle depuis la page.
 * Gere aussi le cas ou le JSON-LD est enveloppe dans un @graph.
 *
 * @param {Document} doc
 * @returns {object|null}
 */
export function extractJsonLd(doc) {
  const scripts = doc.querySelectorAll('script[type="application/ld+json"]');
  for (const s of scripts) {
    try {
      const data = JSON.parse(s.textContent);
      if (data['@type'] === 'Car' || data['@type'] === 'Vehicle') return data;
      if (Array.isArray(data['@graph'])) {
        const car = data['@graph'].find((item) => item['@type'] === 'Car' || item['@type'] === 'Vehicle');
        if (car) return car;
      }
    } catch { /* JSON-LD malformed, on passe */ }
  }
  return null;
}

/**
 * Detecte un lien vers un rapport Autoviza gratuit dans le DOM.
 *
 * @param {Document} doc
 * @returns {string|null} URL du rapport ou null
 */
export function extractAutovizaUrl(doc) {
  const link = doc.querySelector('a[href*="autoviza.fr"]');
  return link ? link.href : null;
}
