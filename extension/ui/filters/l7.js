"use strict";

import { escapeHTML } from '../../utils/format.js';

export function buildL7Body(f, d) {
  const ownerType = (d.owner_type || "").toLowerCase();

  if (f.status === "neutral" || ownerType === "private" || ownerType === "particulier") {
    return `<div class="okazcar-l7-body"><span class="okazcar-l7-badge okazcar-l7-badge-neutral">Particulier</span></div>`;
  }

  if (f.status === "skip") {
    return `<div class="okazcar-l7-body"><span class="okazcar-l7-na">${escapeHTML(f.message)}</span></div>`;
  }

  let html = `<div class="okazcar-l7-body">`;

  if (d.platform_verified) {
    html += `<span class="okazcar-l7-badge okazcar-l7-badge-verified">Pro v\u00E9rifi\u00E9</span>`;
    if (d.dealer_rating != null && d.dealer_review_count != null) {
      const stars = "\u2605".repeat(Math.round(Number(d.dealer_rating)));
      html += `<span class="okazcar-l7-rating">${stars} ${d.dealer_rating}/5 (${d.dealer_review_count} avis)</span>`;
    }
    html += `</div>`;
    return html;
  }

  if (f.status === "pass") {
    const denom = d.denomination || d.name || "";
    const siretOrUid = d.formatted || d.siret || d.uid || "";
    html += `<span class="okazcar-l7-badge okazcar-l7-badge-pro">Pro</span>`;
    if (denom) html += `<span class="okazcar-l7-denom">${escapeHTML(denom)}</span>`;
    if (siretOrUid) html += `<span class="okazcar-l7-id">${escapeHTML(siretOrUid)}</span>`;
    if (d.dealer_rating != null && d.dealer_review_count != null) {
      const stars = "\u2605".repeat(Math.round(Number(d.dealer_rating)));
      html += `<span class="okazcar-l7-rating">${stars} ${d.dealer_rating}/5 (${d.dealer_review_count} avis)</span>`;
    }
    html += `</div>`;
    return html;
  }

  if (f.status === "warning") {
    html += `<span class="okazcar-l7-badge okazcar-l7-badge-warn">Pro non identifi\u00E9</span>`;
    html += `<span class="okazcar-l7-msg">${escapeHTML(f.message)}</span>`;
    html += `</div>`;
    return html;
  }

  html += `<span class="okazcar-l7-badge okazcar-l7-badge-fail">Pro suspect</span>`;
  html += `<span class="okazcar-l7-msg">${escapeHTML(f.message)}</span>`;
  html += `</div>`;
  return html;
}
