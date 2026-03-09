"use strict";

/**
 * Loi Montagne — alerte pneus hiver.
 *
 * Source: securite-routiere.gouv.fr + arretes prefectoraux 2021-2022
 * Fichier de reference: docs/221022_liste_communes_equipements_hivernaux.xlsx
 *
 * Obligation: 1er novembre — 31 mars, 34 departements concernes.
 * On alerte si on est a ±30 jours de la saison.
 */

// 34 departements concernes par la Loi Montagne (codes 2 chiffres)
const LOI_MONTAGNE_DEPTS = new Set([
  '01', '03', '04', '05', '06', '07', '09', '11', '12',
  '15', '25', '26', '31', '38', '39', '42', '43', '48',
  '57', '63', '64', '65', '66', '67', '68', '69', '70',
  '73', '74', '81', '83', '84', '88', '90',
]);

// Departements "sud" — pneus hiver en fin de saison = vigilance
const SOUTH_DEPTS = new Set([
  '04', '05', '06', '11', '12', '13', '30', '31', '34',
  '48', '64', '65', '66', '81', '83', '84',
]);

/**
 * Extrait le code departement (2 chiffres) depuis un zipcode ou un department brut.
 */
function extractDeptCode(zipcode, department) {
  if (zipcode && /^\d{5}$/.test(String(zipcode))) {
    return String(zipcode).slice(0, 2);
  }
  if (department && /^\d{1,3}$/.test(String(department))) {
    return String(department).padStart(2, '0');
  }
  if (typeof department === 'string') {
    const m = department.match(/\d{2,3}/);
    if (m) return m[0].slice(0, 2);
  }
  return null;
}

/**
 * Genere les signaux pneus hiver si pertinent.
 *
 * @param {{zipcode?: string, department?: string, city?: string}} location
 * @param {Date} [now] - date courante (pour les tests)
 * @returns {Array<{label: string, value: string, status: string}>}
 */
export function getWinterTireSignals(location, now) {
  if (!location) return [];

  const dept = extractDeptCode(location.zipcode, location.department);
  if (!dept) return [];

  const today = now || new Date();
  const month = today.getMonth() + 1; // 1-12
  const day = today.getDate();

  // Saison: 1er novembre (11/1) — 31 mars (3/31)
  // Alerte etendue ±30j: 1er octobre (10/1) — 30 avril (4/30)
  const inSeason = (month >= 11) || (month <= 3);
  const nearBeforeSeason = (month === 10); // octobre = 30j avant
  const nearAfterSeason = (month === 4);   // avril = 30j apres

  const isLoiMontagneDept = LOI_MONTAGNE_DEPTS.has(dept);
  const isSouth = SOUTH_DEPTS.has(dept);

  const signals = [];

  if (nearBeforeSeason && isLoiMontagneDept) {
    // Avant la saison → levier de negociation
    signals.push({
      label: 'Pneus hiver (Loi Montagne)',
      value: 'Obligation dès le 1er nov. — verifier l\'equipement ou negocier',
      status: 'warning',
    });
  } else if (inSeason && isLoiMontagneDept) {
    // Pendant la saison → le vehicule DOIT etre equipe
    signals.push({
      label: 'Pneus hiver (Loi Montagne)',
      value: 'Obligatoire jusqu\'au 31 mars — verifier pneus hiver/4 saisons ou chaines',
      status: 'warning',
    });
  } else if (nearAfterSeason && isSouth) {
    // Fin de saison dans le sud → vigilance pneus hiver encore montes
    signals.push({
      label: 'Pneus hiver en fin de saison',
      value: 'Verifier que les pneus ne sont pas des pneus hiver (usure acceleree en été)',
      status: 'warning',
    });
  }

  // Rappel dimensions pneus (toujours, si departement montagne)
  if (isLoiMontagneDept && (inSeason || nearBeforeSeason || nearAfterSeason)) {
    signals.push({
      label: 'Dimensions pneus',
      value: 'Verifier la compatibilite des pneus avec la carte grise (expert sinistre)',
      status: 'info',
    });
  }

  return signals;
}
