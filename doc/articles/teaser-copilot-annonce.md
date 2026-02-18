# Co-Pilot : L'oeil froid qui lit les annonces auto mieux que vous

**Et si un algorithme voyait ce que votre enthousiasme vous cache ?**

---

Vous connaissez cette sensation. Vous scrollez Leboncoin a 23h, un cafe froid a cote du clavier. Et la, vous la voyez. L'annonce parfaite. Le bon modele, le bon prix, les belles photos. Votre coeur accelere. Votre cerveau, lui, a deja decroche.

C'est exactement la que les arnaques se glissent. Pas dans l'ombre. En pleine lumiere, au milieu de votre enthousiasme.

**Co-Pilot est ne de ce constat : l'acheteur a besoin d'un regard froid. Pas d'un expert payant. Pas d'un site de plus. Juste un copilote silencieux, installe dans son navigateur, qui fait le travail ingrat pendant que vous, vous revez de votre prochaine voiture.**

---

## Un clic. Neuf verdicts. Zero bullshit.

Co-Pilot est une extension Chrome. Gratuite. Made in France.

Vous etes sur une annonce Leboncoin ? Un clic sur l'icone. En deux secondes, neuf filtres independants passent l'annonce au crible. Pas besoin de copier-coller un lien. Pas besoin de changer d'onglet. Pas besoin de creer un compte. L'analyse arrive la ou vous etes deja -- sur l'annonce.

**Le score tombe. Vert, orange, rouge. Vous savez.**

---

## Ce que Co-Pilot voit (et que vous ne voyez pas)

### Le prix est trop beau ? Il sait pourquoi.

Co-Pilot ne compare pas le prix a un vague "argus" statique. Il collecte en temps reel les vrais prix des annonces similaires sur Leboncoin -- meme modele, meme annee, meme region. Chaque utilisateur, sans le savoir, alimente une base de prix vivante. Plus on est nombreux, plus le prix de reference est juste.

Et quand un prix est anormalement bas **et** que l'annonce est en ligne depuis plus de 30 jours ? Co-Pilot le dit sans detour : *"Anguille sous roche -- les acheteurs n'ont pas franchi le pas."* Si personne n'a voulu de cette "bonne affaire" en un mois, posez-vous la question.

### Le compteur est credible ? Ca depend de la voiture.

Un moteur d'analyse qui applique la meme regle a une Dacia Sandero et a un BMW X5 n'a rien compris. Co-Pilot adapte le kilometrage attendu au type de vehicule. Une citadine roule 10 000 km/an. Un SUV familial, 17 000. Un utilitaire, 20 000. Les donnees viennent de l'INSEE, pas d'un doigt mouille.

150 000 km sur une Clio de 2015 ? Normal. Sur une Fiat 500 du meme age ? Suspect.

### L'annonce est "recente" ? Vraiment ?

Leboncoin permet aux vendeurs de supprimer et republier leur annonce pour remonter en tete des resultats. L'astuce est vieille comme le site. Co-Pilot lit les **vraies dates** enfouies dans le code de la page -- la date de premiere publication et la date d'indexation. Si elles ne collent pas, l'annonce est marquee **"republied"** et son age reel est affiche.

Pas de manipulation possible. La verite est dans le code source.

### Le vendeur pro est-il... reel ?

Un clic, et Co-Pilot interroge la base SIRENE de l'Etat francais. Le SIRET du vendeur professionnel est verifie en temps reel : entreprise active, fermee, radiee ? Vous le saurez avant meme de decrocher le telephone. Zero API payante. Juste les donnees publiques de la Republique.

### Le numero de telephone cache quelque chose ?

Numeros de teleprospection ficheus par l'ARCEP, prefixes etrangers, numeros virtuels OnOff... Co-Pilot croise le numero avec les listes officielles du regulateur des telecoms. Un numero de portable classique passe. Un numero de demarchage telemarketing ? Alerte rouge.

### Cette voiture vient-elle vraiment de France ?

Sept signaux independants traquent les importations deguisees : mots-cles d'import dans la description, pays d'origine mentionnes, indices fiscaux (TVA recuperable, malus), texte en allemand ou en espagnol copie-colle d'un site etranger, plaque WW, demande de COC...

**Oui, Co-Pilot detecte quand un vendeur a oublie de traduire la fiche technique allemande.** Parce que `Unfallwagen` dans une annonce francaise, ca ne trompe pas un algorithme.

### Un rapport d'historique gratuit ? On vous le montre.

Certaines annonces Leboncoin incluent un lien vers un rapport Autoviza gratuit (valeur 25 euros). Le probleme : ce lien est souvent invisible, noye dans la page. Co-Pilot le detecte automatiquement et l'affiche en banniere. Un cadeau que Leboncoin vous fait... et que vous ne voyez jamais sans nous.

---

## Derriere le rideau : du Python, du bon sens, et un soupcon d'IA

Co-Pilot n'est pas une usine a gaz. C'est un moteur Python propre, des donnees publiques croisees intelligemment, et bientot, de l'IA pour aller encore plus loin.

**Neuf filtres. Chacun avec son poids.**

Les filtres critiques (prix, referentiel vehicule) pesent double dans le score. Les signaux faibles (telephone) pesent moitie. Un filtre qui ne peut pas s'executer par manque de donnees ? Il penalise quand meme le score -- parce que l'absence d'information, c'est deja une information.

Le tout tourne sur un backend Flask lean, avec SQLAlchemy et NumPy pour les z-scores statistiques. Pas de machine learning obscur. Pas de boite noire. Du croisement de donnees verifiables, de la logique metier automobile, et des seuils calibres sur la realite du marche francais.

**Et l'IA dans tout ca ?** Elle arrive. Pour decupler ce que le bon sens a commence. Analyse semantique des descriptions, detection de patterns frauduleux a grande echelle, scoring predictif de fiabilite... Le moteur est pret. L'intelligence artificielle ne remplace pas la logique -- elle l'amplifie.

---

## Made in France. Gratuit. Et ce n'est que le debut.

Co-Pilot est francais. Concu pour le marche francais. Calibre sur les donnees francaises (INSEE, ARCEP, SIRENE, Argus). Les messages sont en francais. Les seuils sont francais. La reglementation est francaise.

**Et il est gratuit.** L'analyse complete, les neuf filtres, le score, les alertes -- tout ca, c'est cadeau.

Parce qu'on pense qu'un acheteur de voiture d'occasion en France merite un outil honnete, accessible, et qui ne lui demande rien en echange de la verite.

---

## Mais l'histoire ne s'arrete pas a l'achat...

On ne vous laisse pas seul avec les cles en main et un "bonne chance".

Co-Pilot a vocation a **accompagner l'acheteur au-dela de l'annonce**. Verification d'historique vehicule. Suivi post-achat. Fonctions inedites qu'aucun outil du marche ne propose aujourd'hui.

On ne peut pas tout dire. Pas encore.

**Mais ce qu'on peut vous dire, c'est que la version que vous voyez aujourd'hui -- aussi complete soit-elle -- n'est que le socle.**

---

## Installez-le. Testez-le. Parlez-en.

Un acheteur averti en vaut deux. Un acheteur avec Co-Pilot en vaut neuf.

**Extension Chrome. Un clic. Gratuit. Maintenant.**

---

*Co-Pilot -- L'analyse a froid des annonces auto. Made in France.*
