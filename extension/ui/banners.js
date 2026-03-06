"use strict";

import { escapeHTML } from '../utils/format.js';

export function buildPremiumSection() {
  return `<div class="okazcar-premium-section"><div class="okazcar-premium-blur"><div class="okazcar-premium-fake"><p><strong>Rapport détaillé du véhicule</strong></p><p>Fiche fiabilité complète avec problèmes connus, coûts d'entretien prévus, historique des rappels constructeur et comparaison avec les alternatives du segment.</p><p>Estimation de la valeur réelle basée sur 12 critères régionaux.</p><p>Recommandation d'achat personnalisée avec score de confiance.</p></div></div><div class="okazcar-premium-overlay"><div class="okazcar-premium-glass"><p class="okazcar-premium-title">Analyse complète</p><p class="okazcar-premium-subtitle">Débloquez le rapport détaillé avec fiabilité, coûts et recommandations.</p><button class="okazcar-premium-cta" id="okazcar-premium-btn">Débloquer – 9,90 €</div></div></div>`;
}

export function buildYouTubeBanner(featuredVideo) {
  if (!featuredVideo || !featuredVideo.url) return "";
  const title = featuredVideo.title || "Découvrir ce modèle en vidéo";
  const channel = featuredVideo.channel || "";
  return `<div class="okazcar-youtube-banner"><a href="${escapeHTML(featuredVideo.url)}" target="_blank" rel="noopener noreferrer" class="okazcar-youtube-link"><span class="okazcar-youtube-icon">&#x25B6;&#xFE0F;</span><span class="okazcar-youtube-text"><strong>Découvrir ce modèle en vidéo</strong><small>${escapeHTML(channel)}${channel ? " · " : ""}${escapeHTML(title).substring(0, 50)}</small></span><span class="okazcar-youtube-arrow">&rsaquo;</span></a></div>`;
}

export function buildAutovizaBanner(autovizaUrl) {
  if (!autovizaUrl) return "";
  return `<div class="okazcar-autoviza-banner"><a href="${escapeHTML(autovizaUrl)}" target="_blank" rel="noopener noreferrer" class="okazcar-autoviza-link"><span class="okazcar-autoviza-icon">&#x1F4CB;</span><span class="okazcar-autoviza-text"><strong>Rapport d'historique gratuit</strong><small>Offert par LeBonCoin via Autoviza (valeur 25 €)</small></span><span class="okazcar-autoviza-arrow">&rsaquo;</span></a></div>`;
}

export function buildEmailBanner() {
  return `<div class="okazcar-email-banner" id="okazcar-email-section"><button class="okazcar-email-btn" id="okazcar-email-btn">&#x2709; Rédiger un email au vendeur</button><div class="okazcar-email-result" id="okazcar-email-result" style="display:none;"><textarea class="okazcar-email-textarea" id="okazcar-email-text" rows="8" readonly></textarea><div class="okazcar-email-actions"><button class="okazcar-email-copy" id="okazcar-email-copy">&#x1F4CB; Copier</button><span class="okazcar-email-copied" id="okazcar-email-copied" style="display:none;">Copié !</span></div></div><div class="okazcar-email-loading" id="okazcar-email-loading" style="display:none;"><span class="okazcar-mini-spinner"></span> Génération en cours...</div><div class="okazcar-email-error" id="okazcar-email-error" style="display:none;"></div></div>`;
}
