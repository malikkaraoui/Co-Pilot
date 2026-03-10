"use strict";

import { escapeHTML } from '../utils/format.js';

function formatTireSize(raw) {
  const s = String(raw || '').trim();
  if (!s) return '';
  // Ex: 205/55R16 -> 205/55 R16
  return s.replace(/(\d{3}\/\d{2})R(\d{2})/i, '$1 R$2');
}

function formatDimLine(dim) {
  if (!dim) return '';
  const size = formatTireSize(dim.size || dim.tire_full || dim.tire || '');
  if (!size) return '';

  const li = dim.load_index != null && dim.load_index !== '' ? String(dim.load_index) : '';
  const si = dim.speed_index != null && dim.speed_index !== '' ? String(dim.speed_index) : '';
  const suffix = (li || si) ? ` ${li}${si}`.trimEnd() : '';
  return `${size}${suffix}`.trim();
}

export function buildTiresPanel(tireSizes) {
  if (!tireSizes || !Array.isArray(tireSizes.dimensions) || tireSizes.dimensions.length === 0) {
    return '';
  }

  const dims = tireSizes.dimensions
    .map(formatDimLine)
    .filter((x) => x);

  if (dims.length === 0) return '';

  const warn = dims.length > 1
    ? '<div class="okazcar-tire-warning">\u26A0 Plusieurs dimensions correspondent \u00E0 ce v\u00E9hicule. V\u00E9rifiez sur le pneu !</div>'
    : '<div class="okazcar-tire-warning">\u2139 Dimension indicative : v\u00E9rifiez sur le pneu</div>';

  const source = tireSizes.source ? escapeHTML(String(tireSizes.source)) : '';
  const sourceUrl = tireSizes.source_url ? String(tireSizes.source_url) : '';
  const sourceLink = sourceUrl
    ? `<a class="okazcar-tire-source-link" href="${escapeHTML(sourceUrl)}" target="_blank" rel="noopener noreferrer">${source || 'Source'}</a>`
    : (source ? `<span class="okazcar-tire-source">${source}</span>` : '');

  const generation = tireSizes.generation ? escapeHTML(String(tireSizes.generation)) : '';
  const yearRange = tireSizes.year_range ? escapeHTML(String(tireSizes.year_range)) : '';
  const meta = (generation || yearRange)
    ? `<div class="okazcar-tire-meta">${generation}${generation && yearRange ? ' \u00B7 ' : ''}${yearRange}</div>`
    : '';

  const listHtml = dims
    .slice(0, 12)
    .map((d) => `<li class="okazcar-tire-dim">${escapeHTML(d)}</li>`)
    .join('');

  const more = dims.length > 12
    ? `<div class="okazcar-tire-more">+ ${dims.length - 12} autres</div>`
    : '';

  return `
    <div class="okazcar-tire-section">
      <h3 class="okazcar-section-title">Dimensions pneus possibles</h3>
      ${warn}
      ${meta}
      <ul class="okazcar-tire-dims">${listHtml}</ul>
      ${more}
      ${sourceLink ? `<div class="okazcar-tire-footer">Source : ${sourceLink}</div>` : ''}
    </div>
  `;
}
