"use strict";

/**
 * Interactions DOM specifiques a LeBonCoin.
 *
 * Fonctions qui interrogent ou manipulent le DOM de la page LBC :
 * detection de connexion, revelation du telephone, detection Autoviza.
 * Separe de parser.js qui lui ne travaille que sur les donnees JSON.
 */

import { lbcDeps } from './_deps.js';

/**
 * Verifie si l'utilisateur est connecte sur LeBonCoin.
 * On regarde le header : si "se connecter" n'apparait pas, c'est qu'on est connecte.
 * @returns {boolean}
 */
export function isUserLoggedIn() {
  const header = document.querySelector("header");
  if (!header) return false;
  const text = header.textContent.toLowerCase();
  return !text.includes("se connecter") && !text.includes("s'identifier");
}

/**
 * Detecte l'URL d'un rapport Autoviza gratuit sur la page.
 * Plusieurs strategies car le lien peut etre injecte dynamiquement :
 * 1. Lien direct vers autoviza.fr
 * 2. Lien de redirection contenant "autoviza"
 * 3. Bouton/lien avec le texte "rapport historique" ou "autoviza"
 * 4. En dernier recours, on fouille le __NEXT_DATA__ brut
 *
 * On fait jusqu'a 4 tentatives avec un delai entre chaque, car le lien
 * peut apparaitre apres le chargement initial (rendu cote client).
 *
 * @param {object} nextData - Le __NEXT_DATA__ pour le fallback
 * @returns {Promise<string|null>} URL du rapport ou null
 */
export async function detectAutovizaUrl(nextData) {
  for (let attempt = 0; attempt < 4; attempt++) {
    const directLink = document.querySelector('a[href*="autoviza.fr"]');
    if (directLink) return directLink.href;

    const redirectLink = document.querySelector('a[href*="autoviza"]');
    if (redirectLink) {
      const href = redirectLink.href;
      const match = href.match(/(https?:\/\/[^\s&"]*autoviza\.fr[^\s&"]*)/);
      if (match) return match[1];
      return href;
    }

    const allLinks = document.querySelectorAll('a[href], button[data-href]');
    for (const el of allLinks) {
      const text = (el.textContent || "").toLowerCase();
      if ((text.includes("rapport") && text.includes("historique")) ||
          text.includes("autoviza")) {
        const href = el.href || el.dataset.href || "";
        if (href && href.includes("autoviza")) return href;
      }
    }

    // Attendre que le DOM se mette a jour (rendu dynamique)
    if (attempt < 3) await lbcDeps.sleep(800);
  }

  // Dernier recours : chercher dans le JSON brut du __NEXT_DATA__
  if (nextData) {
    const json = JSON.stringify(nextData);
    const match = json.match(/(https?:\/\/[^\s"]*autoviza\.fr[^\s"]*)/);
    if (match) return match[1];
  }

  return null;
}

/**
 * Revele le numero de telephone du vendeur sur LeBonCoin.
 *
 * LBC masque le telephone derriere un bouton "Voir le numero".
 * On verifie d'abord si un lien tel: existe deja (numero deja revele),
 * sinon on clique le bouton et on attend que le numero apparaisse.
 *
 * @returns {Promise<string|null>} Numero de telephone ou null
 */
export async function revealPhoneNumber() {
  // Verifier si le numero est deja visible dans un lien tel:
  const existingTelLinks = document.querySelectorAll('a[href^="tel:"]');
  for (const link of existingTelLinks) {
    const phone = link.href.replace("tel:", "").trim();
    if (phone && phone.length >= 10) return phone;
  }

  // Chercher le bouton de revelation du telephone
  const candidates = document.querySelectorAll('button, a, [role="button"]');
  let phoneBtn = null;

  for (const el of candidates) {
    const text = (el.textContent || "").toLowerCase().trim();
    if (text.includes("voir le numéro") || text.includes("voir le numero")
        || text.includes("afficher le numéro") || text.includes("afficher le numero")) {
      phoneBtn = el;
      break;
    }
  }

  if (!phoneBtn) return null;

  phoneBtn.click();

  // Attendre que le numero apparaisse dans le DOM apres le clic
  for (let attempt = 0; attempt < 5; attempt++) {
    await lbcDeps.sleep(500);

    // Strategie 1 : lien tel: apparu
    const telLinks = document.querySelectorAll('a[href^="tel:"]');
    for (const link of telLinks) {
      const phone = link.href.replace("tel:", "").trim();
      if (phone && phone.length >= 10) return phone;
    }

    // Strategie 2 : numero en texte brut pres du bouton
    const container = phoneBtn.closest("div") || phoneBtn.parentElement;
    if (container) {
      const match = container.textContent.match(/(?:\+33|0)\s*[1-9](?:[\s.-]*\d{2}){4}/);
      if (match) return match[0].replace(/[\s.-]/g, "");
    }
  }

  return null;
}

/**
 * Verifie si l'URL courante est une page d'annonce LeBonCoin.
 * @returns {boolean}
 */
export function isAdPageLBC() {
  const url = window.location.href;
  return url.includes("leboncoin.fr/ad/") || url.includes("leboncoin.fr/voitures/");
}
