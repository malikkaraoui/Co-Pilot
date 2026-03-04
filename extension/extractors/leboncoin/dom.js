"use strict";

import { lbcDeps } from './_deps.js';

export function isUserLoggedIn() {
  const header = document.querySelector("header");
  if (!header) return false;
  const text = header.textContent.toLowerCase();
  return !text.includes("se connecter") && !text.includes("s'identifier");
}

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

    if (attempt < 3) await lbcDeps.sleep(800);
  }

  if (nextData) {
    const json = JSON.stringify(nextData);
    const match = json.match(/(https?:\/\/[^\s"]*autoviza\.fr[^\s"]*)/);
    if (match) return match[1];
  }

  return null;
}

export async function revealPhoneNumber() {
  const existingTelLinks = document.querySelectorAll('a[href^="tel:"]');
  for (const link of existingTelLinks) {
    const phone = link.href.replace("tel:", "").trim();
    if (phone && phone.length >= 10) return phone;
  }

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

  for (let attempt = 0; attempt < 5; attempt++) {
    await lbcDeps.sleep(500);

    const telLinks = document.querySelectorAll('a[href^="tel:"]');
    for (const link of telLinks) {
      const phone = link.href.replace("tel:", "").trim();
      if (phone && phone.length >= 10) return phone;
    }

    const container = phoneBtn.closest("div") || phoneBtn.parentElement;
    if (container) {
      const match = container.textContent.match(/(?:\+33|0)\s*[1-9](?:[\s.-]*\d{2}){4}/);
      if (match) return match[0].replace(/[\s.-]/g, "");
    }
  }

  return null;
}

export function isAdPageLBC() {
  const url = window.location.href;
  return url.includes("leboncoin.fr/ad/") || url.includes("leboncoin.fr/voitures/");
}
