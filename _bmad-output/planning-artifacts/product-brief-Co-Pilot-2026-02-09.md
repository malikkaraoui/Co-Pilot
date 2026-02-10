---
stepsCompleted: [1, 2, 3, 4, 5, 6]
workflow_completed: true
inputDocuments: ['_bmad-output/brainstorming/brainstorming-session-2026-02-09.md']
date: 2026-02-09
author: Malik
---

# Product Brief: Co-Pilot

## Executive Summary

Co-Pilot est un copilote d'achat automobile intelligent qui se presente sous la forme d'une extension Chrome. En un clic sur une annonce Leboncoin, il analyse instantanement l'annonce et delivre un score de confiance, les red flags detectes et une fiche de connaissance sur le vehicule -- transformant un acheteur non-expert en acheteur eclaire.

**Le pitch :** "Tu cliques sur l'annonce, et en 10 secondes tu sais si c'est fiable ou pas."

Le marche du vehicule d'occasion en France est un terrain mine : brouteurs nigerians, compteurs trafiques, imports douteux, reventes avant entretien lourd, et une explosion technologique (hybrides, electriques, marques chinoises) qui depasse meme les passionnes. Aujourd'hui, les acheteurs paient une "taxe de reassurance" -- mandataires, concessionnaires, LOA -- faute d'outil leur donnant confiance pour acheter en direct.

Co-Pilot elimine cette taxe en democratisant l'expertise automobile derriere un simple clic.

---

## Core Vision

### Problem Statement

L'acheteur de vehicule d'occasion fait face a un double mur :

1. **Un marche infeste d'arnaques sophistiquees** : brouteurs nigerians, compteurs trafiques, imports maquilles d'Allemagne ou d'ailleurs, reventes strategiques avant entretien lourd, voitures d'auto-ecole deguisees en "premiere main soigneuse"
2. **Une explosion de complexite technologique** : hybride leger/lourd/rechargeable, diesel FAP/sans FAP/AdBlue, electrique, marques chinoises -- une deferlante de nouveautes qui rend impossible une evaluation eclairee sans expertise pointue, meme pour les passionnes

### Problem Impact

- **Financier :** Perte de plusieurs milliers d'euros sur une mauvaise affaire, ou surcout de 15-30% via mandataire/concessionnaire pour "acheter la paix"
- **Temporel :** Des jours/semaines de recherche fragmentee entre forums, argus, HistoVec, avis -- pour un acheteur qui est a pied et sous pression
- **Emotionnel :** Stress, angoisse de se faire arnaquer, tensions familiales quand on demande conseil a des proches qui engagent leur parole
- **Cognitif :** Meme avec les donnees disponibles, les profils non-experts ne peuvent pas les interpreter ("oui mais elle est belle" face a un argus depasse de 16%)

### Why Existing Solutions Fall Short

Les outils existent mais sont **eparpilles, passifs et inintelligibles** :

- **HistoVec** (gouvernemental, gratuit) : regarde dans le retroviseur (historique administratif), pas vers l'avenir du vehicule -- ne dit rien sur les couts a venir, la fiabilite, les red flags prospectifs
- **LaCentrale / AutoVisual** : un prix argus sans contexte ni verdict, approche avec friction
- **Forums (Caradisiac, etc.)** : des centaines de messages a trier, expertise requise pour filtrer le signal du bruit
- **Mandataires** : solution par delegation couteuse (commission), pas par autonomisation
- **Concessionnaires / LOA** : "la carotte du siecle" -- les gens preferent payer plus pour etre rassures car c'est souvent adosse a un credit bancaire
- **Appel a un ami** : engage la parole de l'autre, cree des tensions, et l'ami non plus n'est plus a la page

**Aucun outil ne combine detection d'arnaques + education marche + verdict instantane.** Tous demandent du temps, des connaissances prealables, et une demarche active. Aucun ne donne un verdict actionnable a un non-expert.

### Proposed Solution

Co-Pilot est une extension Chrome qui, en un clic sur une annonce Leboncoin, declenche un pipeline d'analyse multi-couches :

- **Verification vendeur** (SIRET, telephone, patterns d'arnaque)
- **Coherence annonce** (modele/annee/motorisation/prix vs referentiel)
- **Prix vs argus geolocalise** (prix moyen du meme modele dans la zone)
- **Analyse visuelle** (coherence entre les photos de l'annonce)
- **Fiche reputation vehicule** (points faibles connus, entretien, pronostic)
- **Score de confiance global** avec rapport detaille des red flags
- **Generation d'email calibre** : si des doutes sont detectes, Co-Pilot genere un email technique cible que l'acheteur envoie au vendeur, forcant celui-ci a se positionner par ecrit hors plateforme

L'intelligence est cachee derriere un clic. L'utilisateur voit un verdict, pas des donnees.

### Key Differentiators

- **Verdict, pas donnees** : Co-Pilot interprete pour l'utilisateur au lieu de lui donner des tableaux bruts
- **Pronostic, pas historique** : Co-Pilot ne dit pas d'ou vient la voiture, il dit ou elle va -- couts a prevoir, problemes connus, risques a anticiper
- **Zero friction** : extension Chrome, un clic, pas de site a visiter ni de formulaire a remplir
- **Triple couverture** : detection d'arnaques + education technologique + protection juridique en un seul outil
- **Bouclier juridique integre** : generation d'emails techniques cibles qui forcent le vendeur a se positionner par ecrit, hors plateforme -- creant une trace exploitable en cas de litige (contrairement aux messages Leboncoin qui disparaissent avec l'annonce)
- **Remplace l'ecosysteme entier** : le pote mecano + le mandataire + Google + les forums en un geste
- **Architecture intelligente** : pipeline amont (pre-calcul) + pipeline live (instantaneite) pour un temps de reponse en secondes
- **Marche gigantesque** : des millions de transactions VO/an en France, aucun concurrent direct sur ce positionnement

---

## Target Users

### Primary Users

**Persona 1 : "Le Responsable Prudent" -- Jean-Pierre, 58 ans**
Beau-pere type. Il porte le poids de l'achat familial -- c'est aussi l'argent de sa femme, il ne peut pas faire le con. Aujourd'hui il va en concession ou chez un mandataire parce qu'il a trop peur de se faire arnaquer en C2C. Il prefere payer plus pour etre rassure. Il pourrait demander a un proche mais il ne veut pas deranger. Co-Pilot lui donne la confiance d'acheter seul, sans intermediaire couteux, avec un verdict clair qu'il comprend.

**Persona 2 : "La Mefiante du Circuit Traditionnel" -- Sophie, 34 ans**
Elle sait qu'elle se fait plumer en LOA/concession mais n'ose pas aller sur le marche C2C. Elle cherche des preuves sociales avant de faire confiance a un outil. Elle consulte les avis des autres utilisateurs Co-Pilot, se rassure, puis ose. Co-Pilot est sa porte de sortie du circuit traditionnel.

**Persona 3 : "Le Brule" -- Kevin, 24 ans**
Il a achete une C3 Pluriel en pensant tout savoir. Problemes electriques, faisceau cabriolet identique au non-cabriolet -- il a appris la douleur. Son prochain achat, il le fera avec Co-Pilot. Pas la cible du premier achat (ils pensent tout savoir), mais celle du deuxieme.

### Secondary Users

**Persona 4 : "Le Revendeur Malin" -- Karim, 41 ans**
Petit revendeur qui connait les voitures mais veut gagner du temps et de la marge. Co-Pilot est son outil de productivite : scan rapide des annonces, red flags instantanes, estimation de marge. Utilisateur power, potentiellement abonne premium.

### User Journey

**Decouverte :**
Bouche-a-oreille, YouTube (reviews/demos), partenaires cles (assurances), Chrome Web Store

**Premier contact (Gratuit -- zero cout serveur) :**
1. L'utilisateur est sur Leboncoin, navigue une annonce
2. L'extension detecte la page, une fenetre contextuelle s'ouvre
3. Un assistant se presente
4. En un clic → extraction JSON de la page + analyse locale
5. En quelques secondes → **jauge circulaire sur 100** avec retours texte (warnings, red flags, checks valides)
6. Premiere impression de valeur, zero friction, zero cout pour Co-Pilot

**Conversion (Payant -- artillerie lourde) :**
7. S'il veut creuser → paiement
8. Pipeline complet : verification vendeur, argus geolocalise, fiche vehicule, analyse photos, pronostic
9. Generation d'email calibre si doutes detectes

**Moment "aha" :** La jauge circulaire s'affiche avec un score clair. En 10 secondes, il sait.

**Long terme :** L'utilisateur gagne en autonomie. Il n'a plus besoin du mandataire, de la concession, ni du pote mecano. Outil simple et efficace qui devient reflexe.

---

## Success Metrics

### User Success Metrics

- **Score de confiance compris** : l'utilisateur comprend la jauge sur 100 et les red flags sans avoir besoin d'explication
- **Confiance C2C acquise** : l'utilisateur ose acheter en direct particulier-a-particulier au lieu de passer par mandataire/concession
- **Temps de decision reduit** : de jours/semaines de recherche a quelques secondes de scan + lecture du rapport
- **Autonomie gagnee** : l'utilisateur ne sollicite plus son entourage pour valider un achat

### Business Objectives

**Milestone 0 -- 16 mars 2026 : Validation jury**
Premier essai a transformer. Le MVP doit demontrer la maitrise technique (grille Python SE) ET la viabilite produit. Apres ca, tout est benefice.

**3 mois post-lancement :**
- 1 000+ installations de l'extension Chrome (levier : partenariats YouTubeurs auto)
- Taux de conversion gratuit → premium : 5%
- Premiers revenus recurrents via abonnements pro

**12 mois :**
- Bouche-a-oreille organique mesurable (installations sans campagne active)
- Revenu recurrent stable (one-shot + abonnements pro)
- Partenariats cles actifs (assurances, YouTubeurs)

### Key Performance Indicators

| KPI | Cible | Mesure |
|-----|-------|--------|
| Installations extension | 1 000+ (3 mois) | Chrome Web Store analytics |
| Scans gratuits / jour | A definir post-lancement | Logs extension locale |
| Conversion gratuit → premium | 5% annee 1 | Paiements / scans gratuits |
| Prix premium one-shot | 9,90€ (4,95€ avec code promo) | Stripe/payment processor |
| Revenu par analyse premium | 9,90€ (PDF + rapport + email + demarches) | Paiement unitaire |
| Abonnement pro mensuel | A calibrer sur cout des requetes | Abonnement recurrent |
| Partenariats YouTubeurs actifs | 4+ (Terry Gollow, Choco Cars, Pilotes du Dimanche, Fred Cars) | Codes promo distribues |
| NPS / avis Chrome Store | 4.5+ etoiles | Avis utilisateurs |

### Modele de revenus

- **Gratuit** : scan local zero cout serveur → acquisition et viralite
- **Premium one-shot** (9,90€) : rapport PDF complet, points a verifier, email calibre, demarches localisees (carte grise, plaques, partenaires), prix cheval fiscal
- **Abonnement pro mensuel** : pour revendeurs, prix indexe sur le cout reel des requetes
- **Levier acquisition** : codes promo -50% via YouTubeurs auto

---

## MVP Scope

### Core Features (IN -- 16 mars 2026)

**Extension Chrome :**
- Detection automatique des pages annonces Leboncoin
- Extraction JSON des donnees de l'annonce
- Fenetre contextuelle avec assistant
- Jauge circulaire score de confiance sur 100
- Retours texte : warnings, red flags, checks valides

**Pipeline AMONT :**
- Referentiel vehicules SQLite (top 20 modeles les plus vendus en France)
- Import et structuration des datasets existants (car-list.json, CSVs allemands, Teoalida)
- Argus geolocalise (scraping prix Leboncoin par modele/zone)
- Pipeline YouTube scope : 10 chaines cibles → extraction audio → Whisper → digestion LLM → fiches synthetiques par modele

**Pipeline LIVE (filtres au clic) :**
- L1 : Extraction donnees annonce Leboncoin
- L2 : Vehicule existe dans le referentiel ?
- L3 : Coherence modele/annee/motorisation
- L4 : Prix vs argus geolocalise
- L5 : Analyse visuelle NumPy (ordonnancement visuel des donnees existantes)
- L6 : Numero de telephone suspect (regex, indicatif etranger)
- L7 : SIRET vendeur pro (API gouv.fr)
- L8 : Fiche reputation modele (lookup SQL)
- L9 : Score global + rapport red flags

**Flask Admin :**
- Dashboard Plotly (etat des pipelines, stats SQL, monitoring)
- API REST
- Bootstrap, formulaires, usabilite

**Infrastructure :**
- Docker obligatoire
- Repo GitHub public (en parallele pour la suite post-jury)
- SQLite comme SGBD
- Git, structure modulaire

### Out of Scope for MVP (V2+)

- **Stripe / paiement integre** : maitrise acquise, sera ajoute apres validation du moteur (LLM, BDD)
- **Email calibre au vendeur** : bouclier juridique reporte en V2
- **PDF rapport detaille premium** : concept presente au jury, pas implemente
- **Referentiel exhaustif** : au-dela des 20 top modeles FR
- **Pipeline YouTube etendu** : au-dela de 10 chaines
- **Abonnement pro mensuel** : apres calibrage des couts reels
- **Autres plateformes** : AutoScout24 (IT/CH/DE), La Centrale, Facebook Marketplace

### MVP Success Criteria

**Critere binaire : le jury valide le 16 mars 2026**

Le MVP doit demontrer :
- **Couverture de la grille Python SE** : les 10 criteres coches (Flask, NumPy, Pandas, SQL, API, Docker, etc.)
- **Produit credible** : le score sur 100 s'affiche en live devant le jury sur une vraie annonce Leboncoin
- **Architecture solide** : pipeline amont/live, separation des responsabilites, classes, modules
- **Vision commerciale** : le jury comprend le modele freemium et le potentiel marche

**Signaux de validation post-jury :**
- Le jury pose des questions sur le business model (= ils y croient)
- La demo live fonctionne sans accroc
- Le score est pertinent sur plusieurs annonces test

### Future Vision (2-3 ans)

**Extension multi-plateformes :**
- AutoScout24 (Italie, Suisse, Allemagne)
- La Centrale, Facebook Marketplace
- Adaptation par marche (reglementations, habitudes, langues)

**Monetisation complete :**
- Stripe integre, paiement one-shot 9,90€ + abonnement pro
- PDF rapport detaille premium avec demarches localisees
- Partenariats B2B (assurances, banques, courtiers credit)

**Intelligence augmentee :**
- Email calibre au vendeur (bouclier juridique)
- Referentiel exhaustif (parc complet 2010-2025+)
- Pipeline YouTube industrialise (centaines de chaines, mise a jour continue)
- Analyse visuelle avancee (detection anomalies inter-photos par LLM multimodal)

**Expansion :**
- App mobile native
- API ouverte pour partenaires
- Communaute utilisateurs (avis, retours, scoring participatif)
