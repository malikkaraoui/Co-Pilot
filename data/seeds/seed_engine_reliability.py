#!/usr/bin/env python3
"""Seed fiabilite moteurs diesel + essence. Idempotent.

Scores bases sur agregation de sources web (12 sources diesel, 8 sources essence).
score = sources_citant / sources_max * 5, arrondi au 0.5 pres.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app import create_app
from app.extensions import db
from app.models.engine_reliability import EngineReliability
from app.services.pipeline_tracker import track_pipeline

# fmt: off
# ── Moteurs DIESEL (9 sources exploitables) ────────────────────────────────
DIESEL_ENGINES = [
    # (engine_code, brand, score, source_count, note, weaknesses, match_patterns)
    (
        "1.9 TDI", "VAG", 4.5, 7,
        "Moteur diesel de reference, souvent qualifie d'indestructible. "
        "Nombreux exemplaires > 500 000 km. Injection mecanique (ALH) ou "
        "pompe-injecteur (PD). Fiabilite exceptionnelle avec entretien regulier.",
        "Courroie de distribution a respecter imperativement. "
        "Version PD : injecteurs pompe couteux.",
        "1.9 TDI,1.9TDI,ALH,PD TDI",
    ),
    (
        "2.0 HDi / BlueHDi", "PSA", 4.5, 6,
        "Reference fiabilite chez Peugeot/Citroen. Version 90ch particulierement "
        "robuste. BlueHDi 130/150 egalement recommande. Tres repandu, pieces "
        "disponibles et abordables.",
        "FAP et injecteurs a surveiller. Vanne EGR sujette aux encrassements "
        "en usage urbain.",
        "2.0 HDi,2.0HDi,BlueHDi,DW10,HDi 90,HDi 110,HDi 130,HDi 150,BlueHDi 130,BlueHDi 150,BlueHDi 180",
    ),
    (
        "1.5 dCi (K9K)", "Renault-Nissan", 4.5, 6,
        "Moteur diesel le plus produit d'Europe. Tres solide avec vidanges "
        "regulieres. Equipe Clio, Megane, Duster, Kangoo, Qashqai et beaucoup "
        "d'autres. Longévite prouvee > 300 000 km.",
        "Chaine de distribution et EGR vulnerables en usage 100% urbain. "
        "Vidange a 10 000 km max recommandee.",
        "1.5 dCi,1.5dCi,K9K,dCi 85,dCi 90,dCi 105,dCi 110,dCi 115",
    ),
    (
        "D-4D Toyota", "Toyota", 4.5, 6,
        "Fiabilite quasi legendaire. Le 2.0 et 2.2 D-4D sont les plus "
        "recommandes. Present sur Corolla, Avensis, Yaris, RAV4, Hilux. "
        "Robustesse reconnue meme en usage intensif.",
        "Turbo 1.4 D-4D historiquement fragile (resolu sur versions recentes). "
        "Embrayage bimasse a surveiller.",
        "D-4D,1CD,2AD,2.0 D-4D,2.2 D-4D,1.4 D-4D",
    ),
    (
        "CDI Mercedes", "Mercedes", 4.5, 6,
        "Parmi les meilleurs diesels selon consensus des sources. L'OM654 "
        "(2016+) est moderne et fiable. OM651 egalement tres bien cote. "
        "Architecture robuste sur longue distance.",
        "Injecteurs common rail couteux a remplacer. "
        "Entretien plus onéreux que la moyenne.",
        "CDI,OM651,OM654,200d,220d,250d,C220d,E220d",
    ),
    (
        "3.0 TDI V6", "VAG", 4.0, 5,
        "Fiabilite sans precedent pour un V6 diesel. Longévite elevee sur "
        "Audi A6, Q5, Passat. Couple genereux et silencieux. "
        "Meilleur choix pour les longs trajets.",
        "Cout de reparation eleve en cas de defaillance. "
        "Consommation d'huile a surveiller sur versions > 200 000 km.",
        "3.0 TDI,V6 TDI,CAPA,CRC,3.0TDI,TDI V6,TDI 204,TDI 245,TDI 272",
    ),
    (
        "2.0d BMW (M57/B47)", "BMW", 4.0, 5,
        "M57 (6-cyl 3.0d) extremement fiable. B47 (2014+) corrige les defauts "
        "du N47. Le 320d M57 est l'un des diesels les plus fiables de sa "
        "categorie, capable de depasser 500 000 km.",
        "N47 2.0d avant 2014 : courroie de distribution dans le bain d'huile "
        "(defaut majeur). B47 post-2014 corrige ce probleme.",
        "M57,B47,N47,320d,330d,520d,525d,530d,xDrive20d",
    ),
    (
        "2.0 TDI EA288", "VAG", 4.0, 5,
        "Successeur de l'EA189 (Dieselgate), le EA288 est reconnu robuste "
        "et sobre. Fiabilite confirmee sur Golf VII/VIII et Octavia III. "
        "Version biturbo 240ch egalement solide.",
        "Vanne EGR a surveiller. Adblue requis sur versions SCR.",
        "2.0 TDI,2.0TDI,EA288,TDI 115,TDI 150,TDI 190,TDI 240",
    ),
    (
        "2.0 dCi M9R", "Renault-Nissan", 3.5, 4,
        "Excellente endurance (> 400 000 km cites). Moins connu que le K9K "
        "mais tres cote pour la robustesse. Presente sur Laguna, Espace, "
        "Vel Satis, Qashqai 2.0, Trafic.",
        "Bielle et vilebrequin sensibles si vidange negligee. "
        "Particule (DPF) a entretenir.",
        "2.0 dCi,M9R,dCi 130,dCi 150,dCi 175",
    ),
    (
        "1.6 HDi / BlueHDi DV6", "PSA", 3.5, 4,
        "Belle maturite apres quelques annees de production. Repandu et "
        "economique sur 208, C3, C4. Version e-HDi avec micro-hybridation "
        "egalement recommandee.",
        "Injecteurs et vanne EGR : points de vigilance recurrents. "
        "FAP a regenerer en usage urbain.",
        "1.6 HDi,1.6 BlueHDi,1.6 e-HDi,DV6,HDi 92,HDi 100,HDi 110,HDi 120,BlueHDi 100,BlueHDi 120",
    ),
    (
        "CRDi Hyundai-Kia", "Hyundai-Kia", 3.5, 4,
        "Fiabilite en progression constante. Le 1.6 CRDi et 2.2 CRDi sont "
        "recommandes. Entretien plus abordable que les marques europeennes. "
        "Garantie constructeur longue (7 ans).",
        "Premiere generation (pre-2010) moins robuste. "
        "DPF sensible au courte distances.",
        "CRDi,1.6 CRDi,2.0 CRDi,2.2 CRDi,1.4 CRDi,CRDI",
    ),
    (
        "Multijet / JTD Fiat", "Fiat-Alfa", 3.0, 3,
        "Fiables et bien toleres mecaniquement. Le 2.0 Multijet est "
        "particulierement solide. Equipe Giulietta, 500X, Punto, 159.",
        "Injecteurs common rail sensibles. "
        "Courroie de distribution a respecter.",
        "Multijet,JTD,1.6 Multijet,2.0 Multijet,1.3 Multijet,JTDM",
    ),
    (
        "SkyActiv-D Mazda", "Mazda", 3.0, 3,
        "Conception moderne a faible taux de compression (14:1). "
        "Fiabilite impressionnante sur unites recentes. "
        "Tres sobre a la consommation.",
        "DPF delicat en usage urbain exclusif. "
        "Demarrage froid parfois hesitant.",
        "SkyActiv-D,Skyactiv-D,SKYACTIV-D,2.2 SKYACTIV-D,1.5 SKYACTIV-D",
    ),
    (
        "1.7 CDTI Opel", "Opel", 3.0, 3,
        "Version 130ch particulierement durable selon les sources. "
        "Equipe Astra, Zafira, Meriva, Combo. "
        "Bon rapport fiabilite/cout.",
        "Boite de vitesses comme point faible potentiel. "
        "Courroie de distribution a 120 000 km.",
        "1.7 CDTI,1.7CDTI,CDTI 100,CDTI 110,CDTI 125,CDTI 130,Z17DTH",
    ),
    (
        "1.6 iDTEC Honda", "Honda", 3.0, 3,
        "Valeur sure, l'un des diesels les plus sobres de sa categorie. "
        "Fiabilite reconnue sur Civic et CR-V.",
        "Distribution par chaine a controler. "
        "EGR a nettoyer.",
        "1.6 iDTEC,iDTEC,i-DTEC,DTEC 120,DTEC 160",
    ),
]

# ── Moteurs ESSENCE (8 sources exploitables) ──────────────────────────────
ESSENCE_ENGINES = [
    (
        "1.8 VVT-i Toyota", "Toyota", 5.0, 6,
        "Fiabilite legendaire, > 300 000 km reguliers. La version hybride "
        "(2ZR-FXE) reduit encore le stress thermique. Reference absolue en "
        "moteur essence atmospherique. Equipe Corolla, Auris, Prius, RAV4.",
        "Legere consommation d'huile sur 1ZZ-FE anciens. "
        "Roulement de roue parfois fragile.",
        "1.8 VVT-i,1ZZ-FE,2ZR-FXE,VVT-i 140,VVT-i 132,Hybrid 122",
    ),
    (
        "SkyActiv-G 2.0 Mazda", "Mazda", 5.0, 6,
        "Taux de compression eleve (13:1-14:1), sans turbo. Note 9.5/10 "
        "fiabilite, > 350 000 km estimes. Aucune faiblesse documentee. "
        "Ideal pour longue duree.",
        "Consommation legerement superieure aux turbos equivalents. "
        "Puissance moderee sans turbo.",
        "SkyActiv-G,Skyactiv-G,SKYACTIV-G,2.0 SKYACTIV-G,2.5 SKYACTIV-G",
    ),
    (
        "i-VTEC Honda", "Honda", 5.0, 6,
        "Distribution par chaine, > 300 000 km sans broncher. Entretien "
        "abordable. Architecture simple et robuste. Equipe Jazz, HR-V, "
        "Civic, CR-V sur 10+ ans.",
        "Chaine a surveiller sur K20/K24 vers 200 000 km. "
        "Pompe a huile en fin de vie si vidange negligee.",
        "i-VTEC,VTEC,1.5 i-VTEC,1.8 i-VTEC,L15,R18A,i-VTEC 130,i-VTEC 140",
    ),
    (
        "1.5 TSI EA211 VW", "VAG", 4.5, 5,
        "Desactivation cylindres (ACT), > 200 000 km sans probleme majeur. "
        "Fiabilite confirmee sur Golf 7/8, Octavia III, Leon. "
        "Reference moderne du segment.",
        "Premieres versions (pre-2018) : mises a jour logicielles necessaires. "
        "Chaine de distribution a surveiller.",
        "1.5 TSI,1.5TSI,EA211,TSI 130,TSI 150,eTSI 150",
    ),
    (
        "1.4 TSI EA211 VW", "VAG", 4.5, 5,
        "Fiabilite largement confirmee apres refonte 2012. Equipe Golf 6/7, "
        "Polo, T-Roc, Audi A3. Excellent compromis performance/fiabilite.",
        "Avant 2012 (EA111) : problemes chaine distribution et pompe a eau. "
        "Nettoyage soupapes recommande tous les 60 000 km.",
        "1.4 TSI,1.4TSI,CZEA,TSI 122,TSI 125,TSI 140,TSI 150",
    ),
    (
        "1.6 K4M Renault", "Renault-Dacia", 4.5, 5,
        "Atmospherique sans turbo, > 300 000-400 000 km courants. "
        "Architecture simple et robuste. Equipe Clio II/III, Megane II/III, "
        "Scenic, Logan, Sandero, Duster. Aucune faiblesse majeure.",
        "Distribution par courroie a respecter. "
        "Consommation un peu elevee vs turbos modernes.",
        "1.6 K4M,K4M,1.6 16V,1.6 8V,1.6 essence",
    ),
    (
        "1.0 VVT-i Toyota", "Toyota", 4.0, 4,
        "Extremement simple, sans injection directe ni turbo. "
        "> 250 000 km reguliers. Monte sur Aygo/Yaris/iQ et les PSA gemels "
        "(Peugeot 107, Citroen C1). Architecture ultra-simple.",
        "Legere consommation d'huile sur exemplaires ages. "
        "Puissance tres limitee (68-72ch).",
        "1.0 VVT-i,1KR-FE,VVT-i 68,VVT-i 72",
    ),
    (
        "1.0 TSI VW", "VAG", 4.0, 4,
        "Fiabilite solide malgre la petite cylindree turbo. "
        "Tres repandu sur Polo, Golf, Up!, Fabia, Ibiza. "
        "Architecture 3-cyl bien maitrisee.",
        "Fuites d'eau signalees sur quelques versions > 100ch (pre-2019). "
        "Distribution chaine a surveiller.",
        "1.0 TSI,1.0TSI,TSI 75,TSI 95,TSI 110,TSI 115,CHYA,DKLA",
    ),
    (
        "1.0 EcoBoost Ford", "Ford", 4.0, 4,
        "Moteur downsizing primé, bien concu. Fiesta, Focus, Puma. "
        "Excellent couple a bas regime. Referénce de la classe si entretien rigoureux.",
        "Fuites eau frequentes sur versions 100-125ch. "
        "Vidange imperativement a 10 000 km (pas 15 000).",
        "1.0 EcoBoost,EcoBoost,M1JA,EcoBoost 100,EcoBoost 125,EcoBoost 140",
    ),
    (
        "2.0 BMW (B48)", "BMW", 4.0, 4,
        "Robustesse confirmee apres refonte B48. Excellent moteur sur "
        "Serie 3/5 post-2016. Performant et sobre. Fiabilite 8.5/10 "
        "selon les sources.",
        "N20 ancien (pre-2016) : chaine distribution et pompe a eau fragiles. "
        "B48 post-2016 corrige ces defauts.",
        "B48,N20,2.0 TwinPower,320i,330i,520i,528i,TwinPower Turbo 184",
    ),
    (
        "0.9 TCe Renault", "Renault-Dacia", 3.5, 3,
        "Bon compagnon sur long terme malgre 3 cylindres. Equipe Clio IV, "
        "Captur, Twingo III, Sandero, Duster. Fiabilite acceptable.",
        "Fuites d'eau recurrentes autour du boitier thermostat. "
        "Vibrations 3-cyl perceptibles a froid.",
        "0.9 TCe,TCe 90,TCe 100,TCe 110,H4Bt",
    ),
    (
        "1.3 VVT-i Toyota", "Toyota", 3.5, 3,
        "Fiabilite elevee, longévite prouvee. Equipe Yaris, Auris, Corolla. "
        "Architecture simple et eprouvee.",
        "Embrayage sujet a fatigue sous usage intensif.",
        "1.3 VVT-i,2NZ-FE,VVT-i 87,VVT-i 99",
    ),
    (
        "1.6 PureTech 225", "PSA", 3.0, 2,
        "Version haute performance surprenante par sa fiabilite. "
        "Peugeot 508 II, DS4, DS7. "
        "Meilleur choix PSA en terme de fiabilite essence.",
        "Versions PureTech 1.2 (3-cyl) a eviter absolument "
        "(courroie humide, conso huile). Seul le 1.6 est recommande.",
        "1.6 PureTech 225,PureTech 225,EP6 CDTx,THP 225",
    ),
    (
        "1.6 K4M Dacia", "Renault-Dacia", 3.0, 2,
        "Meme bloc que le K4M Renault, fiabilite identique. "
        "Repandu sur Logan, Sandero, Duster 1.6. "
        "Aucune faiblesse majeure documentee.",
        "Distribution par courroie a respecter. "
        "Consommation un peu elevee.",
        "Dacia 1.6,1.6 SCe,SCe 115",
    ),
    (
        "2.0 F4R Renault", "Renault", 3.0, 2,
        "Concu pour encaisser les sollicitations sportives. "
        "Megane RS, Clio RS, Laguna, Espace. "
        "Fiabilite reconnue meme en usage performance.",
        "Consommation elevee. "
        "Courroie de distribution a respecter.",
        "2.0 F4R,F4R,2.0 16V,2.0 essence 135,2.0 essence 175",
    ),
    (
        "1.0 T-GDi Hyundai-Kia", "Hyundai-Kia", 3.0, 2,
        "Garantie constructeur 7 ans / 150 000 km. "
        "Fiabilite en amelioration constante. "
        "Equipe i20, i30, Kona, Rio, Stonic, Ceed.",
        "Eviter accelerations brutales a froid. "
        "Vidanges rigoureuses requises (10 000 km max).",
        "1.0 T-GDi,T-GDi,T-GDI,G3LC,GDi 100,GDi 120",
    ),
    (
        "1.0 SCe Renault", "Renault-Dacia", 3.0, 2,
        "Atmospherique, distribution chaine, tres convaincant en robustesse. "
        "Clio V, Sandero III, Jogger. "
        "Aucune faiblesse documentee.",
        "Puissance modeste (65-75ch). "
        "Adapte a la ville uniquement.",
        "1.0 SCe,SCe 65,SCe 75,H4D",
    ),
    (
        "1.2 DualJet Suzuki", "Suzuki", 3.0, 2,
        "Bloc sans mauvaise surprise, longévite prouvee. "
        "Swift, Ignis, Baleno. Fiabilite Suzuki reconnue.",
        "Legeres vibrations sur versions pre-2021. "
        "Puissance limitee.",
        "1.2 DualJet,DualJet,K12C,DualJet 83,DualJet 90",
    ),
]
# fmt: on


def score_to_stars(score: float) -> str:
    """Convertit un score en representation etoiles."""
    full = int(score)
    half = 1 if (score - full) >= 0.5 else 0
    empty = 5 - full - half
    return "★" * full + ("½" if half else "") + "☆" * empty


def seed() -> None:
    app = create_app()
    with app.app_context():
        db.create_all()
        with track_pipeline("seed_engine_reliability") as tracker:
            created = 0
            all_engines = [
                (fuel, row)
                for fuel, rows in [("Diesel", DIESEL_ENGINES), ("Essence", ESSENCE_ENGINES)]
                for row in rows
            ]
            for fuel_type, row in all_engines:
                engine_code, brand, score, source_count, note, weaknesses, patterns = row
                existing = EngineReliability.query.filter_by(
                    engine_code=engine_code, brand=brand
                ).first()
                if existing:
                    continue
                obj = EngineReliability(
                    engine_code=engine_code,
                    brand=brand,
                    fuel_type=fuel_type,
                    score=score,
                    source_count=source_count,
                    note=note,
                    weaknesses=weaknesses,
                    match_patterns=patterns,
                )
                db.session.add(obj)
                created += 1

            db.session.commit()
            tracker.count = created

        total = EngineReliability.query.count()
        print(f"Seed engine_reliability : {created} crees, {total} total en base.")
        print("\nResume par carburant :")
        for fuel in ("Diesel", "Essence"):
            count = EngineReliability.query.filter_by(fuel_type=fuel).count()
            print(f"  {fuel}: {count} moteurs")
            for r in (
                EngineReliability.query.filter_by(fuel_type=fuel)
                .order_by(EngineReliability.score.desc())
                .all()
            ):
                print(f"    {score_to_stars(r.score)} {r.engine_code} ({r.brand})")


if __name__ == "__main__":
    seed()
