/**
 * L4 — Analyse du prix par rapport au marche.
 * C'est le filtre le plus complexe cote UI : barre visuelle prix annonce vs reference,
 * verdict textuel, source de prix (marche LBC/AS24, Argus, cote LC), references
 * secondaires, et detection des annonces stagnantes a prix bas.
 */

"use strict";

import { escapeHTML } from '../../utils/format.js';

/**
 * Detecte si on est sur LBC ou AS24 pour adapter le label "marche externe".
 * @returns {string|null} 'autoscout24', 'leboncoin' ou null
 */
function _detectCurrentSite() {
  try {
    const host = String(window.location.hostname || '').toLowerCase();
    if (host.includes('autoscout24.')) return 'autoscout24';
    if (host.includes('leboncoin.')) return 'leboncoin';
  } catch { /* ignore */ }
  return null;
}

/**
 * Mappe un identifiant de source vers ses metadonnees d'affichage.
 * @param {string} src - Identifiant source (ex: "marche_leboncoin", "argus_seed")
 * @returns {{label: string, className: string, marker: string}} Metadonnees
 */
function _mapReferenceSourceMeta(src) {
  if (src === "marche_leboncoin") return { label: "LBC", className: "okazcar-l4-src-lbc", marker: "Marché" };
  if (src === "marche_autoscout24") return { label: "AS24", className: "okazcar-l4-src-as24", marker: "Marché" };
  if (src === "argus_seed") return { label: "Argus Base", className: "okazcar-l4-src-seed", marker: "Argus" };
  if (src === "estimation_lbc") return { label: "Estimation LBC", className: "okazcar-l4-src-est", marker: "Est. LBC" };
  if (src === "cote_lacentrale") return { label: "Cote LC", className: "okazcar-l4-src-lc", marker: "Cote LC" };
  return { label: "Référence", className: "okazcar-l4-src-default", marker: "Réf." };
}

/**
 * Barre de prix visuelle avec verdict, source, et references secondaires.
 * Gere la conversion devise pour les annonces hors zone euro.
 * @param {Object} details - Details L4 {price_annonce, price_reference, delta_eur, source, ...}
 * @param {Object} vehicle - Donnees vehicule {currency, price, price_original}
 * @returns {string} HTML du composant prix ou chaine vide
 */
export function buildPriceBarHTML(details, vehicle) {
  const priceAnnonce = details.price_annonce;
  const priceRef = details.price_reference;
  if (!priceAnnonce || !priceRef) return "";

  const deltaEur = details.delta_eur || (priceAnnonce - priceRef);
  const deltaPct = details.delta_pct != null
    ? details.delta_pct
    : Math.round(((priceAnnonce - priceRef) / priceRef) * 100);

  // Conversion devise : si l'annonce est en CHF/GBP/etc., on affiche en devise locale
  const isLocal = vehicle?.currency && vehicle.currency !== "EUR";
  const eurToLocal = isLocal && vehicle.price_original && vehicle.price
    ? vehicle.price_original / vehicle.price : 1;
  const sym = isLocal ? vehicle.currency : "\u20AC";
  const displayDelta = Math.round(Math.abs(deltaEur) * eurToLocal);
  const displayAnnonce = Math.round(priceAnnonce * eurToLocal);
  const displayRef = Math.round(priceRef * eurToLocal);

  const absPct = Math.abs(Math.round(deltaPct));
  const fmtD = displayDelta.toLocaleString("fr-FR");

  // Verdict textuel selon l'ecart au marche :
  // <= 10% : prix marche / 10-25% : bonne affaire ou a negocier / > 25% : suspect ou trop cher
  let verdictClass, verdictEmoji, line1, line2;
  if (absPct <= 10) {
    verdictClass = "verdict-fair";
    verdictEmoji = "\u2705";
    line1 = "Prix march\u00E9";
    line2 = `Dans la fourchette du march\u00E9 (${deltaPct > 0 ? "+" : ""}${Math.round(deltaPct)}%) \u2014 n\u00E9gociez sereinement`;
  } else if (absPct <= 25) {
    if (deltaPct < 0) {
      verdictClass = "verdict-below";
      verdictEmoji = "\uD83D\uDFE2";
      line1 = `${fmtD} ${sym} en dessous du march\u00E9`;
      line2 = `Bonne affaire potentielle \u2014 ${absPct}% moins cher`;
    } else {
      verdictClass = "verdict-above-warning";
      verdictEmoji = "\uD83D\uDFE0";
      line1 = `${fmtD} ${sym} au-dessus du march\u00E9`;
      line2 = `N\u00E9gociez serr\u00E9 \u2014 ${absPct}% plus cher que le march\u00E9`;
    }
  } else {
    if (deltaPct < 0) {
      verdictClass = "verdict-below-suspect";
      verdictEmoji = "\u26A0\uFE0F";
      line1 = `${fmtD} ${sym} en dessous du march\u00E9`;
      line2 = `Prix tr\u00E8s bas \u2014 m\u00E9fiez-vous, \u00E7a peut cacher quelque chose`;
    } else {
      verdictClass = "verdict-above-fail";
      verdictEmoji = "\uD83D\uDD34";
      line1 = `${fmtD} ${sym} au-dessus du march\u00E9`;
      line2 = `Trop cher \u2014 ${absPct}% plus cher, ce n'est pas une affaire`;
    }
  }

  const statusColors = { "verdict-below": "#16a34a", "verdict-below-suspect": "#ea580c", "verdict-fair": "#16a34a", "verdict-above-warning": "#ea580c", "verdict-above-fail": "#dc2626" };
  const fillOpacities = { "verdict-below": "rgba(22,163,74,0.15)", "verdict-below-suspect": "rgba(234,88,12,0.2)", "verdict-fair": "rgba(22,163,74,0.15)", "verdict-above-warning": "rgba(234,88,12,0.2)", "verdict-above-fail": "rgba(220,38,38,0.2)" };
  const color = statusColors[verdictClass] || "#16a34a";
  const fillBg = fillOpacities[verdictClass] || "rgba(22,163,74,0.15)";

  // Calcul de l'echelle de la barre : on centre les deux prix avec du padding
  const minP = Math.min(displayAnnonce, displayRef);
  const maxP = Math.max(displayAnnonce, displayRef);
  const gap = (maxP - minP) || maxP * 0.1;
  const scaleMin = Math.max(0, minP - gap * 0.8);
  const scaleMax = maxP + gap * 0.8;
  const range = scaleMax - scaleMin;
  const pct = (p) => ((p - scaleMin) / range) * 100;

  const annoncePct = pct(displayAnnonce);
  const argusPct = pct(displayRef);
  const fillLeft = Math.min(annoncePct, argusPct);
  const fillWidth = Math.abs(annoncePct - argusPct);
  const fmtP = (n) => escapeHTML(n.toLocaleString("fr-FR")) + " " + escapeHTML(sym);

  const src = details.source || "";
  const sourceMeta = _mapReferenceSourceMeta(src);
  let srcLabel = sourceMeta.label;
  let srcClass = sourceMeta.className;

  // Si la source de prix vient d'un autre site que celui ou on est, on le signale
  const currentSite = _detectCurrentSite();
  const marketSite = src === 'marche_leboncoin'
    ? 'leboncoin'
    : src === 'marche_autoscout24'
      ? 'autoscout24'
      : null;
  const isCrossSource = Boolean(currentSite && marketSite && currentSite !== marketSite);
  if (srcLabel && isCrossSource) {
    srcLabel += ' · marché externe';
  }

  const sampleCount = details.sample_count;
  const precision = details.precision;
  let precisionStars = "";
  if (precision != null) {
    const full = Math.floor(precision);
    const half = precision - full >= 0.5 ? 1 : 0;
    const empty = 5 - full - half;
    precisionStars = "\u2605".repeat(full) + (half ? "\u00BD" : "") + "\u2606".repeat(empty);
  }

  // References secondaires : cote LC, estimation LBC, etc. pour croiser les sources
  let secondaryRefs = Array.isArray(details.reference_secondary)
    ? details.reference_secondary.filter((entry) => entry && entry.price)
    : [];
  if (secondaryRefs.length === 0 && src !== "cote_lacentrale" && details.lc_quotation) {
    secondaryRefs = [{
      source: "cote_lacentrale",
      price: details.lc_quotation,
      trust_index: details.lc_trust_index,
    }];
  }

  let footerHTML = "";
  if (srcLabel || secondaryRefs.length > 0) {
    footerHTML = `<div class="okazcar-l4-footer">`;
    if (srcLabel) {
      footerHTML += `<span class="okazcar-l4-source ${escapeHTML(srcClass)}">${escapeHTML(srcLabel)}</span>`;
    }
    if (sampleCount != null) {
      footerHTML += `<span class="okazcar-l4-samples">Bas\u00E9 sur ${sampleCount} annonce${sampleCount > 1 ? "s" : ""}${isCrossSource ? " (source externe au site)" : ""}</span>`;
    }
    if (precisionStars) footerHTML += `<span class="okazcar-l4-precision" title="Pr\u00E9cision de l'\u00E9chantillon">${precisionStars}</span>`;
    secondaryRefs.forEach((entry) => {
      const meta = _mapReferenceSourceMeta(entry.source || "");
      const priceText = `${Math.round(Number(entry.price)).toLocaleString("fr-FR")} ${sym}`;
      const trustText = entry.trust_index ? ` · indice ${entry.trust_index}` : "";
      footerHTML += `<span class="okazcar-l4-secondary-ref"><span class="okazcar-l4-source ${escapeHTML(meta.className)}">${escapeHTML(meta.label)}</span><span class="okazcar-l4-secondary-value">${escapeHTML(priceText + trustText)}</span></span>`;
    });
    footerHTML += `</div>`;
  }

  let staleHTML = "";
  if (details.stale_below_market) {
    const staleDays = details.days_online || "30+";
    staleHTML = `<div class="okazcar-l4-stale">
      <span class="okazcar-l4-stale-icon">\uD83D\uDC40</span>
      <div>
        <div class="okazcar-l4-stale-title">Prix bas + ${staleDays} jours en ligne</div>
        <div class="okazcar-l4-stale-text">Les acheteurs n'ont pas franchi le pas \u2014 il y a peut-\u00EAtre anguille sous roche</div>
      </div>
    </div>`;
  }

  return `
    <div class="okazcar-price-bar-container">
      <div class="okazcar-price-verdict ${escapeHTML(verdictClass)}">
        <span class="okazcar-price-verdict-emoji">${verdictEmoji}</span>
        <div>
          <div class="okazcar-price-verdict-text">${escapeHTML(line1)}</div>
          <div class="okazcar-price-verdict-pct">${escapeHTML(line2)}</div>
        </div>
      </div>
      <div class="okazcar-price-bar-track">
        <div class="okazcar-price-bar-fill" style="left:${fillLeft}%;width:${fillWidth}%;background:${fillBg}"></div>
        <div class="okazcar-price-arrow-zone" style="left:${fillLeft}%;width:${fillWidth}%;border-color:${color}"></div>
        <div class="okazcar-price-market-ref" style="left:${argusPct}%">
          <div class="okazcar-price-market-line"></div>
          <div class="okazcar-price-market-label">${escapeHTML(sourceMeta.marker)}</div>
          <div class="okazcar-price-market-price">${fmtP(displayRef)}</div>
        </div>
        <div class="okazcar-price-car" style="left:${annoncePct}%">
          <span class="okazcar-price-car-emoji">\uD83D\uDE97</span>
          <div class="okazcar-price-car-price" style="color:${color}">${fmtP(displayAnnonce)}</div>
        </div>
      </div>
      <div class="okazcar-price-bar-spacer"></div>
      ${footerHTML}
      ${staleHTML}
    </div>
  `;
}
