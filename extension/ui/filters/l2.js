"use strict";

import { escapeHTML } from '../../utils/format.js';

export function buildL2Body(f, d) {
  if (f.status === "skip") {
    return `<div class="copilot-l2-body"><span class="copilot-l2-na">${escapeHTML(f.message)}</span></div>`;
  }

  if (f.status === "pass") {
    const brand = d.brand || "";
    const model = d.model || "";
    const gen = d.generation ? ` \u00B7 ${d.generation}` : "";
    return `<div class="copilot-l2-body">
      <span class="copilot-l2-badge copilot-l2-badge-ok">\u2713 ${escapeHTML(brand)} ${escapeHTML(model)}${escapeHTML(gen)}</span>
    </div>`;
  }

  return `<div class="copilot-l2-body">
    <span class="copilot-l2-msg">${escapeHTML(f.message)}</span>
  </div>`;
}
