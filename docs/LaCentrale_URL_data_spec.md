# La Centrale — URL Data Spec

Reverse-engineered 2026-03-09 depuis lacentrale.fr/listing.

## Base URL

```
https://www.lacentrale.fr/listing?<params>
```

## Parametres

### Marque + Modele (`makesModelsCommercialNames`)

Format : `BRAND::MODEL` (double colon !)

```
?makesModelsCommercialNames=VOLKSWAGEN          # marque seule
?makesModelsCommercialNames=VOLKSWAGEN%3A%3AGOLF  # marque::modele
```

**ATTENTION** : un seul colon (`VOLKSWAGEN:GOLF`) ne fonctionne PAS correctement.

### Annee (`yearMin`, `yearMax`)

```
?yearMin=2003&yearMax=2005
```

**Convention LC** : quand on veut inclure l'annee courante, on omet `yearMax` :
```
?yearMin=2023          # = de 2023 a aujourd'hui
```

### Kilometrage (`mileageMin`, `mileageMax`)

```
?mileageMin=100000&mileageMax=999999
```

### Carburant (`energies`)

| Carburant | Code |
|-----------|------|
| Diesel | `dies` |
| Essence | `ess` |
| Electrique | `elec` |
| Hybride | `hyb` |
| Hybride rechargeable | `hybRech,plug_hyb` |
| GPL | `gpl` |

**Verifie manuellement 2026-03-09** : tous les codes ci-dessus sont confirmes fonctionnels.
GNV (`gnv`) ne fonctionne PAS comme filtre sur LC — retire.
Hybride rechargeable necessite les DEUX codes `hybRech` ET `plug_hyb` separes par virgule.

```
?energies=dies
?energies=hybRech%2Cplug_hyb    # hybride rechargeable (deux codes)
```

### Boite de vitesse (`gearbox`)

| Boite | Code |
|-------|------|
| Manuelle | `MANUAL` |
| Automatique | `AUTO` |

```
?gearbox=MANUAL
```

**ATTENTION** : les codes sont en MAJUSCULES. `man` et `auto` sont silencieusement ignores par le site (le filtre apparait vide dans l'interface = aucun filtrage reel).

### Regions (`regions`)

Format ISO-like. Multiples separees par virgule.

| Region | Code |
|--------|------|
| Ile-de-France | `FR-IDF` |
| Auvergne-Rhone-Alpes | `FR-ARA` |
| Provence-Alpes-Cote d'Azur | `FR-PAC` |
| Occitanie | `FR-OCC` |
| Nouvelle-Aquitaine | `FR-NAQ` |
| Hauts-de-France | `FR-HDF` |
| Grand Est | `FR-GES` |
| Bretagne | `FR-BRE` |
| Pays de la Loire | `FR-PDL` |
| Normandie | `FR-NOR` |
| Bourgogne-Franche-Comte | `FR-BFC` |
| Centre-Val de Loire | `FR-CVL` |
| Corse | `FR-COR` |

**Verifie manuellement 2026-03-09** : les 13 codes region ci-dessus sont confirmes fonctionnels.

```
?regions=FR-ARA                  # une region
?regions=FR-ARA%2CFR-BFC         # deux regions (virgule encodee)
```

### Localisation par code postal ou departement (`dptCp`, `distance`)

**Verifie manuellement 2026-03-09** : `dptCp` accepte un code postal complet OU un numero de departement seul.

```
?dptCp=74000&distance=2          # 20 km autour de 74000
?dptCp=74000&distance=4          # 100 km autour de 74000
?dptCp=74                        # departement 74 (Haute-Savoie)
```

Codes distance connus :
- `2` = 20 km
- `4` = 100 km
- (autres a verifier)

### Puissance DIN (`powerDINMin`, `powerDINMax`)

```
?powerDINMin=100&powerDINMax=250   # entre 100 et 250 ch DIN
```

### Puissance fiscale (`ratedHorsePowerMin`, `ratedHorsePowerMax`)

**Verifie manuellement 2026-03-09** : `taxHorsepowerMin`/`taxHorsepowerMax` ne fonctionnent PAS.

```
?ratedHorsePowerMin=5&ratedHorsePowerMax=10   # entre 5 et 10 CV fiscaux
```

### Categories / Carrosserie (`categories`)

> **Verifie manuellement 2026-03-11** : `bodyType=` est IGNORE par LC.
> Seul `categories=` fonctionne, avec des codes numeriques.

| Code | Carrosserie |
|------|-------------|
| `47` | 4x4, SUV & Crossover |
| `41_42` | Berline (2 sous-codes) |
| `43` | Break |
| `44` | Monospace |
| `45` | Coupe |

**Multi-select** : virgule encodee `%2C`
```
?categories=41_42%2C43          # Berline + Break
?categories=47                   # SUV uniquement
```

### Prix (`priceMin`, `priceMax`)

> **Verifie manuellement 2026-03-11**.

```
?priceMin=15000&priceMax=30000   # entre 15k et 30k EUR
```

### Type de vendeur (`customerFamilyCodes`)

> **Verifie manuellement 2026-03-11** : `sellerType=` est IGNORE par LC.
> Seul `customerFamilyCodes=` fonctionne.

| Valeur | Type |
|--------|------|
| `PART` | Particulier |
| `PROFESSIONNEL%2CCOURTIER_AUTOMOBILE%2CINTERMEDIAIRE` | Professionnel (3 codes) |

```
?customerFamilyCodes=PART
?customerFamilyCodes=PROFESSIONNEL%2CCOURTIER_AUTOMOBILE%2CINTERMEDIAIRE
```

---

## Exemples complets

Diesel, manuelle, VW Golf, 2003-2005, >100k km :
```
https://www.lacentrale.fr/listing?energies=dies&gearbox=MANUAL&makesModelsCommercialNames=VOLKSWAGEN%3A%3AGOLF&mileageMax=999999&mileageMin=100000&yearMax=2005&yearMin=2003
```

Electrique, VW Golf, depuis 2023, regions ARA+BFC :
```
https://www.lacentrale.fr/listing?energies=elec&makesModelsCommercialNames=VOLKSWAGEN%3A%3AGOLF&regions=FR-ARA%2CFR-BFC&yearMin=2023
```

Localisation 74000, rayon 20km, 100-250ch :
```
https://www.lacentrale.fr/listing?distance=2&dptCp=74000&energies=elec&makesModelsCommercialNames=VOLKSWAGEN%3A%3AGOLF&powerDINMax=250&powerDINMin=100&yearMin=2003
```
