"use strict";

import { escapeHTML } from '../../utils/format.js';

export function buildL8Body(f, d) {
  const signals = d.signals || [];
  const strongCount = d.strong_count || 0;

  if (f.status === "pass" || signals.length === 0) {
    return `<div class="copilot-l8-body">
      <div class="copilot-l8-clean">
        <span class="copilot-l8-clean-icon">\u2705</span>
        <span>Aucun signal d'import d\u00E9tect\u00E9</span>
      </div>
    </div>`;
  }

  let headerText = strongCount >= 2
    ? "Import probable"
    : strongCount === 1
      ? "Signal d'import d\u00E9tect\u00E9"
      : "Signal faible d'import";
  const headerClass = f.status === "fail" ? "copilot-l8-alert-fail" : "copilot-l8-alert-warn";

  let html = `<div class="copilot-l8-body">`;
  html += `<div class="copilot-l8-alert ${headerClass}">`;
  html += `<span class="copilot-l8-alert-icon">${f.status === "fail" ? "\uD83D\uDEA8" : "\u26A0\uFE0F"}</span>`;
  html += `<span class="copilot-l8-alert-text">${escapeHTML(headerText)} (${signals.length} indice${signals.length > 1 ? "s" : ""})</span>`;
  html += `</div>`;

  html += `<ul class="copilot-l8-signals">`;
  for (const sig of signals) {
    html += `<li class="copilot-l8-signal">${escapeHTML(sig)}</li>`;
  }
  html += `</ul></div>`;
  return html;
}
