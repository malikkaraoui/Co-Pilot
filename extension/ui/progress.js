"use strict";

// NOTE: innerHTML usage below is intentional — all content is either
// hardcoded static HTML or escaped via escapeHTML(). No user input
// is injected raw. This is the same pattern as the original content.js.

import { scoreColor, statusColor, statusIcon, filterLabel } from '../utils/styles.js';
import { showPopup, removePopup } from './dom.js';

export function createProgressTracker() {
  function stepIconHTML(status) {
    switch (status) {
      case "running": return '<div class="copilot-mini-spinner"></div>';
      case "done":    return "\u2713";
      case "warning": return "\u26A0";
      case "error":   return "\u2717";
      case "skip":    return "\u2014";
      default:        return "\u25CB";
    }
  }

  function update(stepId, status, detail) {
    const el = document.getElementById("copilot-step-" + stepId);
    if (!el) return;
    el.setAttribute("data-status", status);
    const iconEl = el.querySelector(".copilot-step-icon");
    if (iconEl) {
      iconEl.className = "copilot-step-icon " + status;
      if (status === "running") { iconEl.innerHTML = '<div class="copilot-mini-spinner"></div>'; }
      else { iconEl.textContent = stepIconHTML(status); }
    }
    if (detail !== undefined) {
      let detailEl = el.querySelector(".copilot-step-detail");
      if (!detailEl) { detailEl = document.createElement("div"); detailEl.className = "copilot-step-detail"; el.querySelector(".copilot-step-text").appendChild(detailEl); }
      detailEl.textContent = detail;
    }
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function addSubStep(parentId, text, status, detail) {
    const parentEl = document.getElementById("copilot-step-" + parentId);
    if (!parentEl) return;
    let container = parentEl.querySelector(".copilot-substeps");
    if (!container) { container = document.createElement("div"); container.className = "copilot-substeps"; parentEl.appendChild(container); }
    const subEl = document.createElement("div");
    subEl.className = "copilot-substep";
    const iconSpan = document.createElement("span");
    iconSpan.className = "copilot-substep-icon";
    iconSpan.textContent = stepIconHTML(status);
    subEl.appendChild(iconSpan);
    const textSpan = document.createElement("span");
    let fullText = text;
    if (detail) fullText += " \u2014 " + detail;
    textSpan.textContent = fullText;
    subEl.appendChild(textSpan);
    container.appendChild(subEl);
    subEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function showFilters(filters) {
    const container = document.getElementById("copilot-progress-filters");
    if (!container || !filters) return;
    filters.forEach(function (f) {
      const color = statusColor(f.status);
      const icon = statusIcon(f.status);
      const label = filterLabel(f.filter_id, f.status);
      const scoreText = f.status === "skip" ? "skip" : Math.round(f.score * 100) + "%";
      const filterDiv = document.createElement("div"); filterDiv.className = "copilot-progress-filter";
      const iconSpan = document.createElement("span"); iconSpan.className = "copilot-progress-filter-icon"; iconSpan.style.color = color; iconSpan.textContent = icon; filterDiv.appendChild(iconSpan);
      const idSpan = document.createElement("span"); idSpan.className = "copilot-progress-filter-id"; idSpan.textContent = f.filter_id; filterDiv.appendChild(idSpan);
      const labelSpan = document.createElement("span"); labelSpan.className = "copilot-progress-filter-label"; labelSpan.textContent = label; filterDiv.appendChild(labelSpan);
      const scoreSpan = document.createElement("span"); scoreSpan.className = "copilot-progress-filter-score"; scoreSpan.style.color = color; scoreSpan.textContent = scoreText; filterDiv.appendChild(scoreSpan);
      container.appendChild(filterDiv);
      const msgDiv = document.createElement("div"); msgDiv.className = "copilot-progress-filter-msg"; msgDiv.textContent = f.message; container.appendChild(msgDiv);
      if (f.filter_id === "L4" && f.details) { appendCascadeDetails(container, f.details); }
    });
    container.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function appendCascadeDetails(container, details) {
    var lines = [];
    if (details.source === "marche_leboncoin" || details.source === "marche_autoscout24") {
      var srcLabel = details.source === "marche_autoscout24" ? "AS24" : "LBC";
      lines.push("Source : march\u00e9 " + srcLabel + " (" + (details.sample_count || "?") + " annonces" + (details.precision ? ", pr\u00e9cision " + details.precision : "") + ")");
    }
    else if (details.source === "argus_seed") { lines.push("Source : Argus (donn\u00e9es seed)"); }
    if (details.cascade_tried) {
      details.cascade_tried.forEach(function (tier) {
        var result = details["cascade_" + tier + "_result"] || "non essay\u00e9";
        var tierLabel = tier === "market_price" ? "March\u00e9 crowdsourc\u00e9" : "Argus Seed";
        var tierIcon = result === "found" ? "\u2713" : result === "insufficient" ? "\u26A0" : "\u2014";
        lines.push(tierIcon + " " + tierLabel + " : " + result);
      });
    }
    lines.forEach(function (line) { var div = document.createElement("div"); div.className = "copilot-cascade-detail"; div.textContent = line; container.appendChild(div); });
  }

  function showScore(score, verdict) {
    const container = document.getElementById("copilot-progress-score");
    if (!container) return;
    const color = scoreColor(score);
    const labelDiv = document.createElement("div"); labelDiv.className = "copilot-progress-score-label"; labelDiv.textContent = "Score global"; container.appendChild(labelDiv);
    const valueDiv = document.createElement("div"); valueDiv.className = "copilot-progress-score-value"; valueDiv.style.color = color; valueDiv.textContent = String(score); container.appendChild(valueDiv);
    const verdictDiv = document.createElement("div"); verdictDiv.className = "copilot-progress-score-verdict"; verdictDiv.style.color = color; verdictDiv.textContent = verdict; container.appendChild(verdictDiv);
    container.style.display = "block";
    container.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  return { update, addSubStep, showFilters, showScore };
}

export function showLoading() {
  removePopup();
  showPopup('<div class="copilot-popup copilot-popup-loading" id="copilot-popup"><div class="copilot-loading-body"><div class="copilot-spinner"></div><p>Analyse en cours...</p></div></div>');
}

export function showProgress() {
  removePopup();
  const html = [
    '<div class="copilot-popup" id="copilot-popup">',
    '  <div class="copilot-popup-header">',
    '    <div class="copilot-popup-title-row">',
    '      <span class="copilot-popup-title">Co-Pilot</span>',
    '      <button class="copilot-popup-close" id="copilot-close">&times;</button>',
    '    </div>',
    '    <p class="copilot-popup-vehicle" id="copilot-progress-vehicle">Analyse en cours...</p>',
    '  </div>',
    '  <div class="copilot-progress-body">',
    '    <div class="copilot-progress-phase">',
    '      <div class="copilot-progress-phase-title">1. Extraction</div>',
    '      <div class="copilot-step" id="copilot-step-extract" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Extraction des donn\u00e9es de l\'annonce</div></div>',
    '      <div class="copilot-step" id="copilot-step-phone" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">R\u00e9v\u00e9lation du num\u00e9ro de t\u00e9l\u00e9phone</div></div>',
    '    </div>',
    '    <div class="copilot-progress-phase">',
    '      <div class="copilot-progress-phase-title">2. Collecte prix march\u00e9</div>',
    '      <div class="copilot-step" id="copilot-step-job" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Demande au serveur : quel v\u00e9hicule collecter ?</div></div>',
    '      <div class="copilot-step" id="copilot-step-collect" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Collecte des prix (cascade recherche)</div></div>',
    '      <div class="copilot-step" id="copilot-step-submit" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Envoi des prix au serveur</div></div>',
    '      <div class="copilot-step" id="copilot-step-bonus" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Collecte bonus multi-r\u00e9gion</div></div>',
    '    </div>',
    '    <div class="copilot-progress-phase">',
    '      <div class="copilot-progress-phase-title">3. Analyse serveur</div>',
    '      <div class="copilot-step" id="copilot-step-analyze" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Analyse des 10 filtres (L1 \u2013 L10)</div></div>',
    '      <div id="copilot-progress-filters" class="copilot-progress-filters"></div>',
    '      <div class="copilot-step" id="copilot-step-autoviza" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">D\u00e9tection rapport Autoviza</div></div>',
    '    </div>',
    '    <hr class="copilot-progress-separator">',
    '    <div id="copilot-progress-score" class="copilot-progress-score" style="display:none"></div>',
    '    <div style="text-align:center; padding: 12px 0;">',
    '      <button class="copilot-btn copilot-btn-retry" id="copilot-progress-details-btn" style="display:none">Voir l\'analyse compl\u00e8te</button>',
    '    </div>',
    '  </div>',
    '  <div class="copilot-popup-footer"><p>Co-Pilot v1.0 &middot; Analyse en temps r\u00e9el</p></div>',
    '</div>',
  ].join("\n");
  showPopup(html);
  return createProgressTracker();
}
