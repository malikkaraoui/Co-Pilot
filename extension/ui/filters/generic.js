"use strict";

import { escapeHTML } from '../../utils/format.js';
import { buildDetailsHTML } from '../../utils/format.js';

export function buildGenericBody(f) {
  const msgHTML = `<p class="okazcar-filter-message">${escapeHTML(f.message)}</p>`;
  const detailsHTML = f.details ? buildDetailsHTML(f.details) : "";
  return msgHTML + detailsHTML;
}
