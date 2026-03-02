/**
 * SiteExtractor - Interface commune pour l'extraction de donnees vehicule.
 *
 * Chaque site (LeBonCoin, AutoScout24, etc.) implemente cette interface.
 * Le contrat de sortie de extract() doit produire un objet compatible
 * avec le backend /api/analyze.
 */
export class SiteExtractor {
  /** Identifiant du site ('leboncoin', 'autoscout24'). */
  static SITE_ID = '';

  /** Patterns regex pour detecter le site depuis l'URL. */
  static URL_PATTERNS = [];

  /** @type {Function|null} Backend fetch proxy (injected by content.js) */
  _fetch = null;
  /** @type {string|null} API base URL (injected by content.js) */
  _apiUrl = null;

  /**
   * Injecte les dependances communes (backendFetch, apiUrl).
   * Appele par content.js apres construction de l'extracteur.
   * @param {{fetch: Function, apiUrl: string}} deps
   */
  initDeps(deps) {
    this._fetch = deps.fetch;
    this._apiUrl = deps.apiUrl;
  }

  /**
   * Detecte si l'URL courante est une page d'annonce.
   * @param {string} url
   * @returns {boolean}
   */
  isAdPage(url) {
    throw new Error('isAdPage() must be implemented');
  }

  /**
   * Extrait les donnees vehicule de la page.
   *
   * Retourne un objet avec:
   * - type: 'raw' (envoyer next_data brut) ou 'normalized' (ad_data pre-digere)
   * - next_data: payload brut (si type='raw')
   * - ad_data: dict normalise au format extract_ad_data() (si type='normalized')
   * - source: identifiant du site
   *
   * @returns {Promise<{type: string, source: string, next_data?: object, ad_data?: object}|null>}
   */
  async extract() {
    throw new Error('extract() must be implemented');
  }

  /**
   * Revele le numero de telephone du vendeur si possible.
   * @returns {Promise<string|null>}
   */
  async revealPhone() {
    return null;
  }

  /**
   * Detecte un rapport gratuit (Autoviza, etc.) sur la page.
   * @returns {Promise<string|null>}
   */
  async detectFreeReport() {
    return null;
  }

  /**
   * Verifie si l'utilisateur est connecte sur le site.
   * @returns {boolean}
   */
  isLoggedIn() {
    return false;
  }

  /**
   * Indique si l'annonce a un telephone revelable.
   * @returns {boolean}
   */
  hasPhone() {
    return false;
  }

  /**
   * Collecte les prix du marche pour le vehicule courant.
   * @param {object} progress - Progress tracker pour l'UI
   * @returns {Promise<{submitted: boolean}>}
   */
  async collectMarketPrices(progress) {
    return { submitted: false };
  }

  /**
   * Retourne les signaux bonus specifiques au site.
   * Affiches dans une section popup dediee, pas envoyes au backend.
   *
   * @returns {Array<{label: string, value: string, status: string}>}
   */
  getBonusSignals() {
    return [];
  }

  /**
   * Extrait un resume vehicule court pour le header du progress tracker.
   * @returns {{make: string, model: string, year: string}|null}
   */
  getVehicleSummary() {
    return null;
  }
}
