"""Moteur de filtres et filtres individuels (L1-L11).

Package principal d'analyse OKazCar. Chaque filtre (L1 a L11) examine
un aspect precis de l'annonce auto et retourne un FilterResult normalise.

L1  - Qualite d'extraction (completude des champs)
L2  - Referentiel vehicule (marque/modele connu en base)
L3  - Coherence croisee (km/age/prix)
L4  - Prix vs argus geolocalise
L5  - Analyse statistique z-score
L6  - Telephone vendeur (indicatif, demarchage, virtuel)
L7  - Entreprise vendeur (SIRET/UID)
L8  - Detection d'import
L9  - Evaluation globale (qualite annonce)
L10 - Anciennete annonce (stagnation)
L11 - Rappels constructeur

Le FilterEngine orchestre l'execution de tous les filtres en parallele.
"""
