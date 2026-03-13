"use strict";

// NOTE: innerHTML usage below is intentional — all content is either
// hardcoded static HTML or escaped via escapeHTML(). No user input
// is injected raw. This is the same pattern as the original content.js.

import { scoreColor, statusColor, statusIcon, filterLabel } from '../utils/styles.js';
import { showPopup, removePopup } from './dom.js';

function detectCurrentSite() {
  try {
    const host = String(window.location.hostname || '').toLowerCase();
    if (host.includes('autoscout24.')) return 'autoscout24';
    if (host.includes('leboncoin.')) return 'leboncoin';
  } catch {
    /* ignore */
  }
  return null;
}

export function createProgressTracker() {
  function stepIconHTML(status) {
    switch (status) {
      case 'running': return '<div class="okazcar-mini-spinner"></div>';
      case 'done': return '✓';
      case 'warning': return '⚠';
      case 'error': return '✗';
      case 'skip': return '—';
      default: return '○';
    }
  }

  function update(stepId, status, detail) {
    const el = document.getElementById(`okazcar-step-${stepId}`);
    if (!el) return;
    el.setAttribute('data-status', status);
    const iconEl = el.querySelector('.okazcar-step-icon');
    if (iconEl) {
      iconEl.className = `okazcar-step-icon ${status}`;
      if (status === 'running') {
        iconEl.innerHTML = '<div class="okazcar-mini-spinner"></div>';
      } else {
        iconEl.textContent = stepIconHTML(status);
      }
    }
    if (detail !== undefined) {
      let detailEl = el.querySelector('.okazcar-step-detail');
      if (!detailEl) {
        detailEl = document.createElement('div');
        detailEl.className = 'okazcar-step-detail';
        el.querySelector('.okazcar-step-text').appendChild(detailEl);
      }
      detailEl.textContent = detail;
    }
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function addSubStep(parentId, text, status, detail) {
    const parentEl = document.getElementById(`okazcar-step-${parentId}`);
    if (!parentEl) return;
    let container = parentEl.querySelector('.okazcar-substeps');
    if (!container) {
      container = document.createElement('div');
      container.className = 'okazcar-substeps';
      parentEl.appendChild(container);
    }
    const subEl = document.createElement('div');
    subEl.className = 'okazcar-substep';
    const iconSpan = document.createElement('span');
    iconSpan.className = 'okazcar-substep-icon';
    iconSpan.textContent = stepIconHTML(status);
    subEl.appendChild(iconSpan);
    const textSpan = document.createElement('span');
    let fullText = text;
    if (detail) fullText += ` — ${detail}`;
    textSpan.textContent = fullText;
    subEl.appendChild(textSpan);
    container.appendChild(subEl);
    subEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function showFilters(filters) {
    const container = document.getElementById('okazcar-progress-filters');
    if (!container || !filters) return;
    filters.forEach((f) => {
      const color = statusColor(f.status);
      const icon = statusIcon(f.status);
      const label = filterLabel(f.filter_id, f.status);
      const scoreText = f.status === 'skip' ? 'skip' : `${Math.round(f.score * 100)}%`;
      const filterDiv = document.createElement('div');
      filterDiv.className = 'okazcar-progress-filter';
      const iconSpan = document.createElement('span');
      iconSpan.className = 'okazcar-progress-filter-icon';
      iconSpan.style.color = color;
      iconSpan.textContent = icon;
      filterDiv.appendChild(iconSpan);
      const idSpan = document.createElement('span');
      idSpan.className = 'okazcar-progress-filter-id';
      idSpan.textContent = f.filter_id;
      filterDiv.appendChild(idSpan);
      const labelSpan = document.createElement('span');
      labelSpan.className = 'okazcar-progress-filter-label';
      labelSpan.textContent = label;
      filterDiv.appendChild(labelSpan);
      const scoreSpan = document.createElement('span');
      scoreSpan.className = 'okazcar-progress-filter-score';
      scoreSpan.style.color = color;
      scoreSpan.textContent = scoreText;
      filterDiv.appendChild(scoreSpan);
      container.appendChild(filterDiv);
      const msgDiv = document.createElement('div');
      msgDiv.className = 'okazcar-progress-filter-msg';
      msgDiv.textContent = f.message;
      container.appendChild(msgDiv);
      if (f.filter_id === 'L4' && f.details) {
        appendCascadeDetails(container, f.details);
      }
    });
    container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function appendCascadeDetails(container, details) {
    const lines = [];
    if (details.source === 'marche_leboncoin' || details.source === 'marche_autoscout24') {
      const srcLabel = details.source === 'marche_autoscout24' ? 'AS24' : 'LBC';
      const currentSite = detectCurrentSite();
      const marketSite = details.source === 'marche_autoscout24' ? 'autoscout24' : 'leboncoin';
      const cross = currentSite && currentSite !== marketSite;
      lines.push(`Source : marché ${srcLabel}${cross ? ' (externe au site courant)' : ''} (${details.sample_count || '?'} annonces${details.precision ? `, précision ${details.precision}` : ''})`);
    } else if (details.source === 'argus_seed') {
      lines.push('Source : Argus base interne');
    } else if (details.source === 'estimation_lbc') {
      lines.push('Source : estimation LeBonCoin');
    } else if (details.source === 'cote_lacentrale') {
      lines.push('Source : cote La Centrale');
    }

    let secondaryRefs = Array.isArray(details.reference_secondary) ? details.reference_secondary : [];
    if (secondaryRefs.length === 0 && details.source !== 'cote_lacentrale' && details.lc_quotation) {
      secondaryRefs = [{ source: 'cote_lacentrale', price: details.lc_quotation, trust_index: details.lc_trust_index }];
    }
    secondaryRefs.forEach((ref) => {
      if (!ref || !ref.price) return;
      if (ref.source === 'cote_lacentrale') {
        lines.push(`Info complémentaire : cote LC ${Number(ref.price).toLocaleString('fr-FR')} €${ref.trust_index ? ` · indice ${ref.trust_index}` : ''}`);
      }
    });

    if (details.cascade_tried) {
      details.cascade_tried.forEach((tier) => {
        const result = details[`cascade_${tier}_result`] || 'non essayé';
        const tierLabel = tier === 'market_price'
          ? 'Marché crowdsourcé'
          : tier === 'argus_seed'
            ? 'Argus base interne'
            : tier === 'lbc_estimation'
              ? 'Estimation LeBonCoin'
              : tier === 'lc_quotation'
                ? 'Cote La Centrale'
                : tier;
        const tierIcon = result === 'found' ? '✓' : result === 'insufficient' ? '⚠' : '—';
        lines.push(`${tierIcon} ${tierLabel} : ${result}`);
      });
    }
    lines.forEach((line) => {
      const div = document.createElement('div');
      div.className = 'okazcar-cascade-detail';
      div.textContent = line;
      container.appendChild(div);
    });
  }

  function showScore(score, verdict) {
    const container = document.getElementById('okazcar-progress-score');
    if (!container) return;
    const color = scoreColor(score);
    const labelDiv = document.createElement('div');
    labelDiv.className = 'okazcar-progress-score-label';
    labelDiv.textContent = 'Score global';
    container.appendChild(labelDiv);
    const valueDiv = document.createElement('div');
    valueDiv.className = 'okazcar-progress-score-value';
    valueDiv.style.color = color;
    valueDiv.textContent = String(score);
    container.appendChild(valueDiv);
    const verdictDiv = document.createElement('div');
    verdictDiv.className = 'okazcar-progress-score-verdict';
    verdictDiv.style.color = color;
    verdictDiv.textContent = verdict;
    container.appendChild(verdictDiv);
    container.style.display = 'block';
    container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  return { update, addSubStep, showFilters, showScore };
}

export function showLoading() {
  removePopup();
  showPopup('<div class="okazcar-popup okazcar-popup-loading" id="okazcar-popup"><div class="okazcar-loading-body"><div class="okazcar-spinner"></div><p>Analyse en cours...</p></div></div>');
}

export function showProgress() {
  removePopup();
  const html = [
    '<div class="okazcar-popup" id="okazcar-popup">',
    '  <div class="okazcar-popup-header">',
    '    <div class="okazcar-popup-title-row">',
    '      <span class="okazcar-popup-title">OKazCar</span>',
    '      <button class="okazcar-popup-close" id="okazcar-close">&times;</button>',
    '    </div>',
    '    <p class="okazcar-popup-vehicle" id="okazcar-progress-vehicle">Analyse en cours...</p>',
    '  </div>',
    '  <div class="okazcar-progress-body">',
    '    <div class="okazcar-progress-phase">',
    '      <div class="okazcar-progress-phase-title">1. Extraction</div>',
    '      <div class="okazcar-step" id="okazcar-step-extract" data-status="pending"><span class="okazcar-step-icon pending">○</span><div class="okazcar-step-text">Extraction des données de l\'annonce</div></div>',
    '      <div class="okazcar-step" id="okazcar-step-phone" data-status="pending"><span class="okazcar-step-icon pending">○</span><div class="okazcar-step-text">Révélation du numéro de téléphone</div></div>',
    '    </div>',
    '    <div class="okazcar-progress-phase">',
    '      <div class="okazcar-progress-phase-title">2. Collecte prix marché</div>',
    '      <div class="okazcar-step" id="okazcar-step-job" data-status="pending"><span class="okazcar-step-icon pending">○</span><div class="okazcar-step-text">Demande au serveur : quel véhicule collecter ?</div></div>',
    '      <div class="okazcar-step" id="okazcar-step-collect" data-status="pending"><span class="okazcar-step-icon pending">○</span><div class="okazcar-step-text">Collecte des prix (cascade recherche)</div></div>',
    '      <div class="okazcar-step" id="okazcar-step-submit" data-status="pending"><span class="okazcar-step-icon pending">○</span><div class="okazcar-step-text">Envoi des prix au serveur</div></div>',
    '      <div class="okazcar-step" id="okazcar-step-bonus" data-status="pending"><span class="okazcar-step-icon pending">○</span><div class="okazcar-step-text">Collecte bonus multi-région</div></div>',
    '    </div>',
    '    <div class="okazcar-progress-phase">',
    '      <div class="okazcar-progress-phase-title">3. Analyse serveur</div>',
    '      <div class="okazcar-step" id="okazcar-step-analyze" data-status="pending"><span class="okazcar-step-icon pending">○</span><div class="okazcar-step-text">Analyse des 11 filtres (L1 – L11)</div></div>',
    '      <div id="okazcar-progress-filters" class="okazcar-progress-filters"></div>',
    '      <div class="okazcar-step" id="okazcar-step-autoviza" data-status="pending"><span class="okazcar-step-icon pending">○</span><div class="okazcar-step-text">Détection rapport Autoviza</div></div>',
    '    </div>',
    '    <hr class="okazcar-progress-separator">',
    '    <div id="okazcar-progress-score" class="okazcar-progress-score" style="display:none"></div>',
    '    <div class="okazcar-progress-actions">',
    '      <div class="okazcar-report-banner" id="okazcar-progress-report-section" style="display:none;">',
    '        <button class="okazcar-report-btn" id="okazcar-progress-report-btn">&#x1F4C4; T&eacute;l&eacute;charger le rapport PDF</button>',
    '        <div class="okazcar-report-loading" id="okazcar-progress-report-loading" style="display:none;"><span class="okazcar-mini-spinner"></span> Pr&eacute;paration du PDF...</div>',
    '        <div class="okazcar-report-error" id="okazcar-progress-report-error" style="display:none;"></div>',
    '      </div>',
    '      <button class="okazcar-btn okazcar-btn-retry" id="okazcar-progress-details-btn" style="display:none">Voir l\'analyse complète</button>',
    '    </div>',
    '  </div>',
    '  <div class="okazcar-popup-footer"><p>OKazCar v1.2 &middot; Analyse en temps réel</p></div>',
    '</div>',
  ].join('\n');
  showPopup(html);
  return createProgressTracker();
}
