"use strict";

import { escapeHTML } from '../utils/format.js';

export function buildPremiumSection() {
  return `<div class="copilot-premium-section"><div class="copilot-premium-blur"><div class="copilot-premium-fake"><p><strong>Rapport détaillé du véhicule</strong></p><p>Fiche fiabilité complète avec problèmes connus, coûts d'entretien prévus, historique des rappels constructeur et comparaison avec les alternatives du segment.</p><p>Estimation de la valeur réelle basée sur 12 critères régionaux.</p><p>Recommandation d'achat personnalisée avec score de confiance.</p></div></div><div class="copilot-premium-overlay"><div class="copilot-premium-glass"><p class="copilot-premium-title">Analyse complète</p><p class="copilot-premium-subtitle">Débloquez le rapport détaillé avec fiabilité, coûts et recommandations.</p><button class="copilot-premium-cta" id="copilot-premium-btn">Débloquer – 9,90 €</div></div></div>`;
}

export function buildYouTubeBanner(featuredVideo) {
  if (!featuredVideo || !featuredVideo.url) return "";
  const title = featuredVideo.title || "Découvrir ce modèle en vidéo";
  const channel = featuredVideo.channel || "";
  return `<div class="copilot-youtube-banner"><a href="${escapeHTML(featuredVideo.url)}" target="_blank" rel="noopener noreferrer" class="copilot-youtube-link"><span class="copilot-youtube-icon">&#x25B6;&#xFE0F;</span><span class="copilot-youtube-text"><strong>Découvrir ce modèle en vidéo</strong><small>${escapeHTML(channel)}${channel ? " · " : ""}${escapeHTML(title).substring(0, 50)}</small></span><span class="copilot-youtube-arrow">&rsaquo;</span></a></div>`;
}

export function buildAutovizaBanner(autovizaUrl) {
  if (!autovizaUrl) return "";
  return `<div class="copilot-autoviza-banner"><a href="${escapeHTML(autovizaUrl)}" target="_blank" rel="noopener noreferrer" class="copilot-autoviza-link"><span class="copilot-autoviza-icon">&#x1F4CB;</span><span class="copilot-autoviza-text"><strong>Rapport d'historique gratuit</strong><small>Offert par LeBonCoin via Autoviza (valeur 25 €)</small></span><span class="copilot-autoviza-arrow">&rsaquo;</span></a></div>`;
}

export function buildEmailBanner() {
  return `<div class="copilot-email-banner" id="copilot-email-section"><button class="copilot-email-btn" id="copilot-email-btn">&#x2709; Rédiger un email au vendeur</button><div class="copilot-email-result" id="copilot-email-result" style="display:none;"><textarea class="copilot-email-textarea" id="copilot-email-text" rows="8" readonly></textarea><div class="copilot-email-actions"><button class="copilot-email-copy" id="copilot-email-copy">&#x1F4CB; Copier</button><span class="copilot-email-copied" id="copilot-email-copied" style="display:none;">Copié !</span></div></div><div class="copilot-email-loading" id="copilot-email-loading" style="display:none;"><span class="copilot-mini-spinner"></span> Génération en cours...</div><div class="copilot-email-error" id="copilot-email-error" style="display:none;"></div></div>`;
}
