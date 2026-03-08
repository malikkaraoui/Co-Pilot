"use strict";

/**
 * La Centrale — DOM/JS data extraction.
 *
 * Sources (in priority order):
 * 1. window.CLASSIFIED_GALLERY — main structured data (~9 KB)
 * 2. window.tc_vars — tracking variables (complements)
 * 3. Cote URL — quotation from DOM link
 * 4. JSON-LD — schema.org/Car (basic fallback)
 */

/**
 * Extract CLASSIFIED_GALLERY from the page.
 * Tolerates both `gallery.data.classified` and `gallery.classified` shapes.
 *
 * @param {Window} win
 * @returns {{classified: object, vehicle: object, images: object, config: object}|null}
 */
export function extractGallery(win) {
  const raw = win.CLASSIFIED_GALLERY;
  if (!raw || typeof raw !== 'object') return null;

  // Shape 1: gallery.data.{classified, vehicle, images}
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

  // Shape 2: gallery.{classified, vehicle, images} (no wrapper)
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
 * Extract tc_vars tracking variables.
 *
 * @param {Window} win
 * @returns {object}
 */
export function extractTcVars(win) {
  return (win.tc_vars && typeof win.tc_vars === 'object') ? win.tc_vars : {};
}

/**
 * Extract the "La Cote" quotation from DOM link.
 * Looks for <a href="...cote-auto...?quotation=12380&trustIndex=2...">
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
 * Extract JSON-LD (schema.org/Car) from the page.
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
      // Sometimes wrapped in @graph
      if (Array.isArray(data['@graph'])) {
        const car = data['@graph'].find((item) => item['@type'] === 'Car' || item['@type'] === 'Vehicle');
        if (car) return car;
      }
    } catch { /* ignore malformed JSON-LD */ }
  }
  return null;
}

/**
 * Extract Autoviza report URL from the DOM.
 *
 * @param {Document} doc
 * @returns {string|null}
 */
export function extractAutovizaUrl(doc) {
  const link = doc.querySelector('a[href*="autoviza.fr"]');
  return link ? link.href : null;
}
