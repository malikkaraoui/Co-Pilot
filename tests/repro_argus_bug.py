from app.extensions import db
from app.models.market_price import MarketPrice
from app.services.market_service import get_market_stats, store_market_prices


def test_reproduce_argus_pollution(app):
    """Reproduces the bug where asking for Diesel returns Essence price."""
    with app.app_context():
        # Clean DB
        db.session.query(MarketPrice).delete()

        # Insert Essence data only (using service to ensure valid record)
        store_market_prices(
            make="Renault",
            model="Clio",
            year=2020,
            region="Ile-de-France",
            fuel="essence",
            prices=[10000, 10000, 10000],  # Simplest way to get median=10000
        )

        # Ask for Diesel
        result = get_market_stats(
            make="Renault", model="Clio", year=2020, region="Ile-de-France", fuel="diesel"
        )

        # Bug: result is NOT None (it returns the essence record!)
        # Fix: result should be None if no Diesel data exists
        if result:
            print(
                f"BUG REPRODUCED: Asked for diesel, got {result.fuel} price {result.price_median}"
            )
            assert result.fuel == "diesel", "Returned wrong fuel type!"
        else:
            print("Correct behavior: returned None")
