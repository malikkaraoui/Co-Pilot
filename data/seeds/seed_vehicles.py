#!/usr/bin/env python3
"""Seed du referentiel vehicules -- 20 modeles les plus vendus en France (2010-2025).

Script idempotent : ne cree pas de doublons si relance.
Usage : python data/seeds/seed_vehicles.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.vehicle import Vehicle, VehicleSpec  # noqa: E402

# Les 20 modeles les plus vendus / recherches en France (2010-2025)
VEHICLES = [
    # (marque, modele, generation, annee_debut, annee_fin)
    ("Peugeot", "208", "II", 2019, 2025),
    ("Peugeot", "3008", "II", 2016, 2023),
    ("Peugeot", "308", "III", 2021, 2025),
    ("Peugeot", "2008", "II", 2019, 2025),
    ("Renault", "Clio V", "V", 2019, 2025),
    ("Renault", "Captur", "II", 2019, 2025),
    ("Renault", "Megane", "IV", 2015, 2023),
    ("Renault", "Scenic", "IV", 2016, 2022),
    ("Citroen", "C3", "III", 2016, 2025),
    ("Citroen", "C3 Aircross", "I", 2017, 2025),
    ("Citroen", "C5 Aircross", "I", 2018, 2025),
    ("Dacia", "Sandero", "III", 2020, 2025),
    ("Dacia", "Duster", "II", 2017, 2025),
    ("Volkswagen", "Golf", "VII/VIII", 2012, 2025),
    ("Volkswagen", "Polo", "VI", 2017, 2025),
    ("Toyota", "Yaris", "IV", 2020, 2025),
    ("Toyota", "C-HR", "I/II", 2016, 2025),
    ("Fiat", "500", "II", 2007, 2025),
    ("Ford", "Fiesta", "VII", 2017, 2023),
    ("BMW", "Serie 3", "G20", 2018, 2025),
]

# Specs de base pour chaque modele (fuel, transmission, puissance)
# Format: (marque, modele, fuel_type, transmission, engine, power_hp,
#           reliability_rating, known_issues, expected_costs)
SPECS = [
    ("Peugeot", "208", "Essence", "Manuelle", "1.2 PureTech 100", 100,
     4.0, "Courroie de distribution, turbo PureTech 1.2 (rappel)", "Courroie ~600 EUR, revision ~250 EUR"),
    ("Peugeot", "208", "Diesel", "Manuelle", "1.5 BlueHDi 100", 100,
     4.2, "FAP a surveiller sur trajets courts", "FAP ~800 EUR si encrasse"),
    ("Peugeot", "3008", "Diesel", "Automatique", "1.5 BlueHDi 130 EAT8", 130,
     3.8, "Boite EAT8 parfois hesitante, ecran tactile fragile", "Boite ~2000 EUR, ecran ~500 EUR"),
    ("Peugeot", "3008", "Essence", "Automatique", "1.2 PureTech 130 EAT8", 130,
     3.5, "Turbo PureTech, consommation essence elevee", "Turbo ~1200 EUR"),
    ("Renault", "Clio V", "Essence", "Manuelle", "1.0 TCe 100", 100,
     4.3, "Peu de problemes signales, modele fiable", "Revision ~200 EUR"),
    ("Renault", "Clio V", "Hybride", "Automatique", "1.6 E-Tech 145", 145,
     4.0, "Systeme hybride complexe, batterie a surveiller", "Batterie hybride ~1500 EUR"),
    ("Renault", "Captur", "Essence", "Manuelle", "1.0 TCe 100", 100,
     4.0, "Boite parfois dure a froid", "Embrayage ~800 EUR"),
    ("Renault", "Megane", "Diesel", "Manuelle", "1.5 dCi 115", 115,
     3.7, "Injecteurs, turbo, vanne EGR", "Injecteurs ~300 EUR/piece, turbo ~1500 EUR"),
    ("Citroen", "C3", "Essence", "Manuelle", "1.2 PureTech 83", 83,
     4.1, "Suspension ferme, PureTech fragile sur anciennes versions", "Suspension ~400 EUR"),
    ("Citroen", "C3 Aircross", "Essence", "Manuelle", "1.2 PureTech 110", 110,
     3.9, "Memes soucis PureTech que le C3", "Courroie ~600 EUR"),
    ("Dacia", "Sandero", "Essence", "Manuelle", "1.0 TCe 90", 90,
     4.5, "Tres fiable, peu de problemes. Finitions basiques.", "Revision ~150 EUR, tres peu de frais"),
    ("Dacia", "Duster", "Diesel", "Manuelle", "1.5 dCi 115", 115,
     4.2, "Robuste mais finitions fragiles (plastiques, sellerie)", "Revision ~200 EUR"),
    ("Volkswagen", "Golf", "Diesel", "Automatique", "2.0 TDI 150 DSG", 150,
     3.5, "Boite DSG (embrayage), AdBlue, electronique complexe", "Embrayage DSG ~2500 EUR, AdBlue ~100 EUR"),
    ("Volkswagen", "Golf", "Essence", "Manuelle", "1.5 TSI 150", 150,
     3.8, "Fiable en essence, turbo solide", "Revision ~300 EUR"),
    ("Volkswagen", "Polo", "Essence", "Manuelle", "1.0 TSI 95", 95,
     4.2, "Peu de problemes, bon rapport fiabilite", "Revision ~250 EUR"),
    ("Toyota", "Yaris", "Hybride", "Automatique", "1.5 Hybrid 116", 116,
     4.8, "Reference fiabilite, hybride eprouve, quasi aucun probleme", "Quasiment rien, revision ~200 EUR"),
    ("Toyota", "C-HR", "Hybride", "Automatique", "1.8 Hybrid 122", 122,
     4.6, "Tres fiable, systeme hybride Toyota mature", "Revision ~250 EUR"),
    ("Fiat", "500", "Essence", "Manuelle", "1.2 69ch / 1.0 Hybrid 70", 70,
     3.5, "Embrayage, demarreur, alternateur sur anciennes versions", "Embrayage ~700 EUR"),
    ("Ford", "Fiesta", "Essence", "Manuelle", "1.0 EcoBoost 100", 100,
     4.0, "Moteur EcoBoost fiable, suspension parfois bruyante", "Revision ~220 EUR"),
    ("BMW", "Serie 3", "Diesel", "Automatique", "320d 190 BVA", 190,
     3.6, "Chaine distribution, turbo, electronique couteuse", "Chaine ~1500 EUR, entretien ~500 EUR/an"),
]


def seed():
    """Insere les vehicules et specs en base. Idempotent."""
    app = create_app()

    with app.app_context():
        db.create_all()
        created_vehicles = 0
        created_specs = 0

        for brand, model, generation, year_start, year_end in VEHICLES:
            existing = Vehicle.query.filter_by(brand=brand, model=model).first()
            if existing:
                print(f"  [skip] {brand} {model} existe deja")
                continue

            v = Vehicle(
                brand=brand,
                model=model,
                generation=generation,
                year_start=year_start,
                year_end=year_end,
            )
            db.session.add(v)
            db.session.flush()
            created_vehicles += 1
            print(f"  [+] {brand} {model} ({generation})")

        db.session.commit()

        # Ajout des specs
        for (brand, model, fuel, trans, engine, power,
             reliability, issues, costs) in SPECS:
            vehicle = Vehicle.query.filter_by(brand=brand, model=model).first()
            if not vehicle:
                continue

            existing_spec = VehicleSpec.query.filter_by(
                vehicle_id=vehicle.id, fuel_type=fuel, engine=engine
            ).first()
            if existing_spec:
                continue

            spec = VehicleSpec(
                vehicle_id=vehicle.id,
                fuel_type=fuel,
                transmission=trans,
                engine=engine,
                power_hp=power,
                reliability_rating=reliability,
                known_issues=issues,
                expected_costs=costs,
            )
            db.session.add(spec)
            created_specs += 1

        db.session.commit()

        total_v = Vehicle.query.count()
        total_s = VehicleSpec.query.count()
        print(f"\nResultat : {created_vehicles} vehicules crees, {created_specs} specs creees")
        print(f"Total en base : {total_v} vehicules, {total_s} specs")


if __name__ == "__main__":
    seed()
