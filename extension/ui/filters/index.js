"use strict";

import { escapeHTML } from '../../utils/format.js';
import { statusColor, statusIcon, filterLabel } from '../../utils/styles.js';
import { buildScoreBar } from '../components.js';
import { buildL1Body } from './l1.js';
import { buildL2Body } from './l2.js';
import { buildL3Body } from './l3.js';
import { buildPriceBarHTML } from './l4.js';
import { buildL5Body } from './l5.js';
import { buildL6Body } from './l6.js';
import { buildL7Body } from './l7.js';
import { buildL8Body } from './l8.js';
import { buildL9Body } from './l9.js';
import { buildL10Body } from './l10.js';
import { buildGenericBody } from './generic.js';

export const SIMULATED_FILTERS = ["L4", "L5"];
export const FILTER_DISPLAY_ORDER = ["L4", "L10", "L1", "L3", "L5", "L8", "L6", "L7", "L2", "L9"];

export function buildFilterBody(f, vehicle, allFilters) {
  const d = f.details || {};
  switch (f.filter_id) {
    case "L1":  return buildL1Body(f, d);
    case "L3":  return buildL3Body(f, d);
    case "L4":  return buildPriceBarHTML(d, vehicle);
    case "L2":  return buildL2Body(f, d);
    case "L5":  return buildL5Body(f, d);
    case "L6":  return buildL6Body(f, d);
    case "L7":  return buildL7Body(f, d);
    case "L8":  return buildL8Body(f, d);
    case "L9":  return buildL9Body(f, d, allFilters);
    case "L10": return buildL10Body(f, d);
    default:    return buildGenericBody(f);
  }
}

export function buildFiltersList(filters, vehicle) {
  if (!filters || !filters.length) return "";

  const sorted = [...filters].sort((a, b) => {
    const ia = FILTER_DISPLAY_ORDER.indexOf(a.filter_id);
    const ib = FILTER_DISPLAY_ORDER.indexOf(b.filter_id);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });

  return sorted
    .map((f) => {
      const color = statusColor(f.status);
      const icon = statusIcon(f.status);
      const label = filterLabel(f.filter_id, f.status);
      const simulatedBadge = SIMULATED_FILTERS.includes(f.filter_id) && f.filter_id !== "L4"
        ? '<span class="copilot-badge-simulated">Données simulées</span>'
        : "";
      const scoreBarHTML = buildScoreBar(f);
      const bodyHTML = buildFilterBody(f, vehicle, sorted);
      return `
        <div class="copilot-filter-item" data-status="${escapeHTML(f.status)}">
          <div class="copilot-filter-header">
            <span class="copilot-filter-icon" style="color:${color}">${icon}</span>
            <span class="copilot-filter-label">${escapeHTML(label)}${simulatedBadge}</span>
            ${scoreBarHTML}
          </div>
          ${bodyHTML}
        </div>
      `;
    })
    .join("");
}
