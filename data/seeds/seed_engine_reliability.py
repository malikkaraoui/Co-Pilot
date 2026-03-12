#!/usr/bin/env python3
"""Seed fiabilite moteurs diesel + essence. Idempotent.

Scores basés sur agrégation de sources web (12 sources diesel, 8 sources essence).
score = sources_citant / sources_max * 5, arrondi au 0.5 près.
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
        "Un classique increvable. Beaucoup dépassent 500 000 km. "
        "Simple à entretenir, pièces disponibles partout et pas chères. "
        "Entretien régulier = longévité garantie.",
        "Courroie de distribution à respecter (kilométrage et âge). "
        "Version pompe-injecteur (PD) : injecteurs coûteux à remplacer.",
        "1.9 TDI,1.9TDI,ALH,PD TDI",
    ),
    (
        "2.0 HDi / BlueHDi", "PSA", 4.5, 6,
        "Solide et très répandu chez Peugeot et Citroën. "
        "La version 90ch est quasi indestructible. "
        "BlueHDi 130/150 également très bien. Pièces disponibles partout et abordables.",
        "Filtre à particules (FAP) à surveiller. "
        "Vanne EGR qui s'encrasse en usage urbain.",
        "2.0 HDi,2.0HDi,BlueHDi,DW10,HDi 90,HDi 110,HDi 130,HDi 150,BlueHDi 130,BlueHDi 150,BlueHDi 180",
    ),
    (
        "1.5 dCi (K9K)", "Renault-Nissan", 4.5, 6,
        "Le diesel le plus fabriqué d'Europe, et pour cause : il tient la route. "
        "Plus de 300 000 km régulièrement atteints. "
        "Monte sur presque tout chez Renault et Nissan (Clio, Mégane, Qashqai, Duster…).",
        "Mauvais en usage 100% urbain (chaîne de distribution et EGR). "
        "Vidange tous les 10 000 km maximum recommandée.",
        "1.5 dCi,1.5dCi,K9K,dCi 85,dCi 90,dCi 105,dCi 110,dCi 115",
    ),
    (
        "D-4D Toyota", "Toyota", 4.5, 6,
        "Fiabilité Toyota au rendez-vous. Le 2.0 et 2.2 D-4D sont des valeurs sûres. "
        "Corolla, Avensis, RAV4, Hilux — ça tourne et ça tourne encore, "
        "même en usage intensif.",
        "Ancien 1.4 D-4D fragile (problème corrigé sur les versions récentes). "
        "Embrayage à double masse à surveiller.",
        "D-4D,1CD,2AD,2.0 D-4D,2.2 D-4D,1.4 D-4D",
    ),
    (
        "CDI Mercedes", "Mercedes", 4.5, 6,
        "Parmi les meilleurs diesels du marché. "
        "L'OM654 (depuis 2016) est moderne et fiable. "
        "Très à l'aise sur les longs trajets. Architecture robuste dans la durée.",
        "Injecteurs coûteux à remplacer. "
        "Entretien plus cher que la moyenne.",
        "CDI,OM651,OM654,200d,220d,250d,C220d,E220d",
    ),
    (
        "3.0 TDI V6", "VAG", 4.0, 5,
        "Un V6 diesel rare et fiable. Longévité élevée sur Audi A6, Q5, Passat. "
        "Silencieux, couple généreux, idéal pour la grande route.",
        "Réparations onéreuses en cas de panne. "
        "Consommation d'huile à surveiller au-delà de 200 000 km.",
        "3.0 TDI,V6 TDI,CAPA,CRC,3.0TDI,TDI V6,TDI 204,TDI 245,TDI 272",
    ),
    (
        "2.0d BMW (M57/B47)", "BMW", 4.0, 5,
        "Le M57 (6 cylindres 3.0d) est légendaire : certains dépassent 500 000 km. "
        "Le B47 (depuis 2014) corrige les défauts du N47 et est très recommandé.",
        "N47 avant 2014 : courroie de distribution dans le bain d'huile, "
        "défaut majeur connu — à éviter absolument. "
        "B47 post-2014 corrige ce problème.",
        "M57,B47,N47,320d,330d,520d,525d,530d,xDrive20d",
    ),
    (
        "2.0 TDI EA288", "VAG", 4.0, 5,
        "Successeur du moteur impliqué dans le Dieselgate, et bien meilleur que lui. "
        "Reconnu fiable et économique sur Golf VII/VIII et Octavia III. "
        "Version biturbo 240ch également solide.",
        "Vanne EGR à surveiller. "
        "Versions SCR : Adblue requis (à ne pas laisser tomber à zéro).",
        "2.0 TDI,2.0TDI,EA288,TDI 115,TDI 150,TDI 190,TDI 240",
    ),
    (
        "2.0 dCi M9R", "Renault-Nissan", 3.5, 4,
        "Moins connu que le K9K mais costaud. "
        "Plus de 400 000 km cités sur certains exemplaires. "
        "Sur Laguna, Espace, Vel Satis, Qashqai 2.0, Trafic.",
        "Sensible si les vidanges sont négligées (bielle et vilebrequin). "
        "Filtre à particules (FAP) à entretenir.",
        "2.0 dCi,M9R,dCi 130,dCi 150,dCi 175",
    ),
    (
        "1.6 HDi / BlueHDi DV6", "PSA", 3.5, 4,
        "Fiable une fois rodé, économique au quotidien. "
        "Répandu sur 208, C3, C4. "
        "Version e-HDi avec micro-hybridation également bien vue.",
        "Injecteurs et vanne EGR : points récurrents à surveiller. "
        "FAP à régénérer en usage urbain.",
        "1.6 HDi,1.6 BlueHDi,1.6 e-HDi,DV6,HDi 92,HDi 100,HDi 110,HDi 120,BlueHDi 100,BlueHDi 120",
    ),
    (
        "CRDi Hyundai-Kia", "Hyundai-Kia", 3.5, 4,
        "Fiabilité en progrès constant. Le 1.6 CRDi et 2.2 CRDi sont recommandés. "
        "Entretien moins cher que les marques européennes. "
        "Garantie constructeur longue (7 ans chez Hyundai-Kia).",
        "Première génération (avant 2010) moins fiable. "
        "FAP sensible aux courts trajets en ville.",
        "CRDi,1.6 CRDi,2.0 CRDi,2.2 CRDi,1.4 CRDi,CRDI",
    ),
    (
        "Multijet / JTD Fiat", "Fiat-Alfa", 3.0, 3,
        "Fiables dans l'ensemble. Le 2.0 Multijet est le plus solide. "
        "Sur Giulietta, 500X, Punto, 159.",
        "Injecteurs common rail fragiles. "
        "Courroie de distribution à respecter impérativement.",
        "Multijet,JTD,1.6 Multijet,2.0 Multijet,1.3 Multijet,JTDM",
    ),
    (
        "SkyActiv-D Mazda", "Mazda", 3.0, 3,
        "Conception moderne et sobre. "
        "Fiabilité convaincante sur les unités récentes.",
        "FAP délicat si vous roulez essentiellement en ville. "
        "Démarrage froid parfois capricieux.",
        "SkyActiv-D,Skyactiv-D,SKYACTIV-D,2.2 SKYACTIV-D,1.5 SKYACTIV-D",
    ),
    (
        "1.7 CDTI Opel", "Opel", 3.0, 3,
        "La version 130ch est particulièrement durable. "
        "Sur Astra, Zafira, Meriva, Combo. Bon rapport fiabilité/coût.",
        "Boîte de vitesses peut être un point faible. "
        "Courroie de distribution à changer à 120 000 km.",
        "1.7 CDTI,1.7CDTI,CDTI 100,CDTI 110,CDTI 125,CDTI 130,Z17DTH",
    ),
    (
        "1.6 iDTEC Honda", "Honda", 3.0, 3,
        "Un des diesels les plus sobres de sa catégorie. "
        "Fiabilité reconnue sur Civic et CR-V.",
        "Distribution par chaîne à contrôler. "
        "EGR à nettoyer régulièrement.",
        "1.6 iDTEC,iDTEC,i-DTEC,DTEC 120,DTEC 160",
    ),
]

# ── Moteurs ESSENCE (8 sources exploitables) ──────────────────────────────
ESSENCE_ENGINES = [
    (
        "1.8 VVT-i Toyota", "Toyota", 5.0, 6,
        "La référence absolue en fiabilité. Plus de 300 000 km sans problème, "
        "c'est la norme. Sur Corolla, Auris, Prius, RAV4. "
        "Fiabilité légendaire Toyota au maximum.",
        "Légère consommation d'huile sur les anciens 1ZZ-FE. "
        "Roulement de roue parfois à refaire.",
        "1.8 VVT-i,1ZZ-FE,2ZR-FXE,VVT-i 140,VVT-i 132,Hybrid 122",
    ),
    (
        "SkyActiv-G 2.0 Mazda", "Mazda", 5.0, 6,
        "Sans turbo, sobre, fiable, durable. "
        "Estimé à plus de 350 000 km, aucune faiblesse connue. "
        "Le choix idéal si vous visez la longue durée.",
        "Légèrement plus gourmand que les turbos équivalents. "
        "Puissance modérée sans turbo.",
        "SkyActiv-G,Skyactiv-G,SKYACTIV-G,2.0 SKYACTIV-G,2.5 SKYACTIV-G",
    ),
    (
        "i-VTEC Honda", "Honda", 5.0, 6,
        "Distribution par chaîne, plus de 300 000 km sans broncher. "
        "Entretien abordable. Sur Jazz, HR-V, Civic, CR-V — "
        "solide depuis plus de 10 ans de production.",
        "Chaîne à surveiller sur K20/K24 vers 200 000 km. "
        "Pompe à huile à risque si vidanges négligées.",
        "i-VTEC,VTEC,1.5 i-VTEC,1.8 i-VTEC,L15,R18A,i-VTEC 130,i-VTEC 140",
    ),
    (
        "1.5 TSI EA211 VW", "VAG", 4.5, 5,
        "La référence moderne chez Volkswagen. "
        "Désactivation des cylindres, économique, fiable. "
        "Plus de 200 000 km sans problème majeur sur Golf 7/8, Octavia, Leon.",
        "Premières versions avant 2018 : mises à jour logicielles parfois nécessaires. "
        "Chaîne de distribution à surveiller.",
        "1.5 TSI,1.5TSI,EA211,TSI 130,TSI 150,eTSI 150",
    ),
    (
        "1.4 TSI EA211 VW", "VAG", 4.5, 5,
        "Très fiable depuis la refonte de 2012. "
        "Sur Golf 6/7, Polo, T-Roc, Audi A3. Bon compromis puissance/fiabilité.",
        "Avant 2012 (EA111) : problèmes chaîne et pompe à eau à éviter. "
        "Nettoyage des soupapes recommandé tous les 60 000 km.",
        "1.4 TSI,1.4TSI,CZEA,TSI 122,TSI 125,TSI 140,TSI 150",
    ),
    (
        "1.6 K4M Renault", "Renault-Dacia", 4.5, 5,
        "Sans turbo, simple, robuste. Plus de 300 000 à 400 000 km courants. "
        "Sur Clio II/III, Mégane II/III, Scénic, Logan, Sandero, Duster. "
        "Aucune faiblesse majeure.",
        "Courroie de distribution à changer aux intervalles prévus. "
        "Un peu plus gourmand que les turbos modernes.",
        "1.6 K4M,K4M,1.6 16V,1.6 8V,1.6 essence",
    ),
    (
        "1.0 VVT-i Toyota", "Toyota", 4.0, 4,
        "Ultra simple : sans turbo ni injection directe. "
        "Plus de 250 000 km régulièrement atteints. "
        "Sur Aygo, Yaris, et les jumeaux Peugeot 107 / Citroën C1.",
        "Légère consommation d'huile sur les exemplaires âgés. "
        "Puissance très limitée (68-72ch).",
        "1.0 VVT-i,1KR-FE,VVT-i 68,VVT-i 72",
    ),
    (
        "1.0 TSI VW", "VAG", 4.0, 4,
        "Petit moteur 3 cylindres turbo bien maîtrisé. "
        "Fiable sur Polo, Golf, Fabia, Ibiza. Architecture bien rodée.",
        "Fuites d'eau signalées sur certaines versions +100ch avant 2019. "
        "Distribution par chaîne à surveiller.",
        "1.0 TSI,1.0TSI,TSI 75,TSI 95,TSI 110,TSI 115,CHYA,DKLA",
    ),
    (
        "1.0 EcoBoost Ford", "Ford", 4.0, 4,
        "Moteur primé, bien conçu. Sur Fiesta, Focus, Puma. "
        "Bon couple à bas régime. Fiable si l'entretien est rigoureux.",
        "Fuites d'eau fréquentes sur les versions 100-125ch. "
        "Vidange impérativement à 10 000 km — pas à 15 000 comme indiqué parfois.",
        "1.0 EcoBoost,EcoBoost,M1JA,EcoBoost 100,EcoBoost 125,EcoBoost 140",
    ),
    (
        "2.0 BMW (B48)", "BMW", 4.0, 4,
        "Solide depuis la refonte B48 (2016). "
        "Performant et économique sur Série 3/5. Fiabilité bien notée.",
        "N20 avant 2016 : chaîne de distribution et pompe à eau fragiles — à éviter. "
        "B48 post-2016 corrige ces défauts.",
        "B48,N20,2.0 TwinPower,320i,330i,520i,528i,TwinPower Turbo 184",
    ),
    (
        "0.9 TCe Renault", "Renault-Dacia", 3.5, 3,
        "Fiabilité acceptable sur le long terme malgré ses 3 cylindres. "
        "Sur Clio IV, Captur, Twingo III, Sandero, Duster.",
        "Fuites d'eau récurrentes au niveau du boîtier thermostat. "
        "Vibrations 3 cylindres perceptibles à froid.",
        "0.9 TCe,TCe 90,TCe 100,TCe 110,H4Bt",
    ),
    (
        "1.3 VVT-i Toyota", "Toyota", 3.5, 3,
        "Fiable et éprouvé. Sur Yaris, Auris, Corolla. "
        "Architecture simple qui a fait ses preuves.",
        "Embrayage sujet à fatigue en usage intensif.",
        "1.3 VVT-i,2NZ-FE,VVT-i 87,VVT-i 99",
    ),
    (
        "1.6 PureTech 225", "PSA", 3.0, 2,
        "La version 225ch est étonnamment fiable. "
        "Sur Peugeot 508 II, DS4, DS7. Meilleur choix PSA en essence.",
        "Attention : le 1.2 PureTech 3 cylindres est à éviter absolument "
        "(courroie humide, consommation d'huile). Seul le 1.6 est recommandé.",
        "1.6 PureTech 225,PureTech 225,EP6 CDTx,THP 225",
    ),
    (
        "1.6 K4M Dacia", "Renault-Dacia", 3.0, 2,
        "Même bloc que le K4M Renault, même fiabilité. "
        "Sur Logan, Sandero, Duster 1.6. Aucune faiblesse majeure connue.",
        "Courroie de distribution à respecter. "
        "Un peu gourmand au quotidien.",
        "Dacia 1.6,1.6 SCe,SCe 115",
    ),
    (
        "2.0 F4R Renault", "Renault", 3.0, 2,
        "Conçu pour encaisser les sollicitations sportives (Mégane RS, Clio RS). "
        "Tient bien ses promesses même en usage poussé. Sur Laguna et Espace aussi.",
        "Consommation élevée. "
        "Courroie de distribution à respecter.",
        "2.0 F4R,F4R,2.0 16V,2.0 essence 135,2.0 essence 175",
    ),
    (
        "1.0 T-GDi Hyundai-Kia", "Hyundai-Kia", 3.0, 2,
        "Garanti 7 ans / 150 000 km par Hyundai-Kia. "
        "Fiabilité en progression. Sur i20, i30, Kona, Rio, Stonic, Ceed.",
        "Éviter les accélérations brutales à froid. "
        "Vidanges à 10 000 km maximum.",
        "1.0 T-GDi,T-GDi,T-GDI,G3LC,GDi 100,GDi 120",
    ),
    (
        "1.0 SCe Renault", "Renault-Dacia", 3.0, 2,
        "Atmosphérique, distribution par chaîne, très convaincant en robustesse. "
        "Sur Clio V, Sandero III, Jogger. Aucune faiblesse connue.",
        "Puissance modeste (65-75ch). "
        "Adapté à la ville uniquement.",
        "1.0 SCe,SCe 65,SCe 75,H4D",
    ),
    (
        "1.2 DualJet Suzuki", "Suzuki", 3.0, 2,
        "Fiable et sans mauvaise surprise. "
        "Sur Swift, Ignis, Baleno. La fiabilité Suzuki en petit format.",
        "Légères vibrations sur les versions avant 2021. "
        "Puissance limitée.",
        "1.2 DualJet,DualJet,K12C,DualJet 83,DualJet 90",
    ),
]
# fmt: on


def score_to_stars(score: float) -> str:
    """Convertit un score en représentation étoiles."""
    full = int(score)
    half = 1 if (score - full) >= 0.5 else 0
    empty = 5 - full - half
    return "★" * full + ("½" if half else "") + "☆" * empty


def seed() -> None:
    app = create_app()
    with app.app_context():
        db.create_all()
        with track_pipeline("seed_engine_reliability") as tracker:
            created = updated = 0
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
                    existing.note = note
                    existing.weaknesses = weaknesses
                    updated += 1
                else:
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
            tracker.count = created + updated

        total = EngineReliability.query.count()
        print(
            f"Seed engine_reliability : {created} créés, {updated} mis à jour, {total} total en base."
        )
        print("\nRésumé par carburant :")
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
