#!/usr/bin/env python3
"""
Interactive CLI for the Used Car Buying Assistant
Allows users to input their own requirements and get personalized advice
"""

from car_advisor import (
    CarAdvisor, UserRequirements, UsageType, format_advice
)


def get_budget():
    """Get budget information from user"""
    print("\n💰 BUDGET")
    print("-" * 40)
    while True:
        try:
            min_budget = float(input("Minimum budget ($): "))
            max_budget = float(input("Maximum budget ($): "))
            if min_budget > 0 and max_budget >= min_budget:
                return min_budget, max_budget
            print("Invalid budget. Max must be >= min, and both must be positive.")
        except ValueError:
            print("Please enter valid numbers.")


def get_usage_type():
    """Get usage type from user"""
    print("\n🚗 USAGE TYPE")
    print("-" * 40)
    print("How will you primarily use this car?")
    print("1. Daily Commute (regular weekday driving)")
    print("2. Family Transport (family vehicle needs)")
    print("3. Weekend Driver (occasional use)")
    print("4. Business Travel (professional use)")
    print("5. Mixed Use (combination of various uses)")
    
    usage_map = {
        "1": UsageType.DAILY_COMMUTE,
        "2": UsageType.FAMILY_TRANSPORT,
        "3": UsageType.WEEKEND_DRIVER,
        "4": UsageType.BUSINESS_TRAVEL,
        "5": UsageType.MIXED_USE
    }
    
    while True:
        choice = input("\nSelect (1-5): ").strip()
        if choice in usage_map:
            return usage_map[choice]
        print("Invalid choice. Please select 1-5.")


def get_annual_mileage():
    """Get annual mileage from user"""
    print("\n📏 ANNUAL MILEAGE")
    print("-" * 40)
    while True:
        try:
            mileage = int(input("Expected annual mileage (miles/year): "))
            if mileage > 0:
                return mileage
            print("Mileage must be positive.")
        except ValueError:
            print("Please enter a valid number.")


def get_priorities():
    """Get priority factors from user"""
    print("\n⭐ PRIORITIES")
    print("-" * 40)
    print("What's most important to you? (select multiple, comma-separated)")
    print("1. Reliability")
    print("2. Fuel Economy")
    print("3. Low Maintenance")
    print("4. Safety")
    print("5. Comfort")
    print("6. Performance")
    
    priority_map = {
        "1": "reliability",
        "2": "fuel_economy",
        "3": "low_maintenance",
        "4": "safety",
        "5": "comfort",
        "6": "performance"
    }
    
    while True:
        choices = input("\nSelect priorities (e.g., 1,2,3): ").strip()
        try:
            selected = [c.strip() for c in choices.split(",")]
            priorities = [priority_map[c] for c in selected if c in priority_map]
            if priorities:
                return priorities
            print("Please select at least one priority.")
        except:
            print("Invalid input. Use comma-separated numbers (e.g., 1,2,3).")


def select_car_to_assess(advisor):
    """Let user select a specific car to assess"""
    print("\n🚙 SELECT CAR TO ASSESS")
    print("-" * 40)
    cars = advisor.database.get_all_cars()
    
    for i, car in enumerate(cars, 1):
        print(f"{i}. {car.make} {car.model} ({car.year_range})")
    print(f"{len(cars) + 1}. Assess all cars and show recommendations")
    
    while True:
        try:
            choice = int(input(f"\nSelect (1-{len(cars) + 1}): "))
            if 1 <= choice <= len(cars):
                return cars[choice - 1]
            elif choice == len(cars) + 1:
                return None  # Assess all
            print(f"Please select 1-{len(cars) + 1}.")
        except ValueError:
            print("Please enter a valid number.")


def main():
    """Main interactive CLI"""
    print("=" * 80)
    print("USED CAR BUYING ASSISTANT - Co-Pilot (Interactive Mode)")
    print("=" * 80)
    print("Answer a few questions to get personalized car buying advice")
    print("=" * 80)
    
    # Collect user requirements
    min_budget, max_budget = get_budget()
    usage_type = get_usage_type()
    annual_mileage = get_annual_mileage()
    priorities = get_priorities()
    
    requirements = UserRequirements(
        budget_min=min_budget,
        budget_max=max_budget,
        usage_type=usage_type,
        annual_mileage=annual_mileage,
        priority_factors=priorities
    )
    
    # Create advisor
    advisor = CarAdvisor()
    
    # Let user choose specific car or get recommendations
    selected_car = select_car_to_assess(advisor)
    
    print("\n" + "=" * 80)
    print("GENERATING PERSONALIZED ADVICE...")
    print("=" * 80)
    
    if selected_car:
        # Assess specific car
        advice = advisor.assess_car(selected_car, requirements)
        print(format_advice(advice))
    else:
        # Show top recommendations
        assessments = advisor.find_suitable_cars(requirements)
        
        print("\n🏆 TOP RECOMMENDATIONS FOR YOUR NEEDS:\n")
        for i, advice in enumerate(assessments[:3], 1):
            print(f"\n{'#' * 80}")
            print(f"RECOMMENDATION #{i}")
            print(format_advice(advice))
        
        # Show cars to consider with caution
        moderate_scores = [a for a in assessments if 45 <= a.fit_score < 60]
        if moderate_scores:
            print(f"\n{'#' * 80}")
            print("⚠️  PROCEED WITH CAUTION:")
            for advice in moderate_scores[:2]:
                print(format_advice(advice))
        
        # Show cars to avoid
        low_scores = [a for a in assessments if a.fit_score < 45]
        if low_scores:
            print(f"\n{'#' * 80}")
            print("❌ NOT RECOMMENDED:")
            for advice in low_scores:
                print(format_advice(advice))
    
    print("\n" + "=" * 80)
    print("Thank you for using Co-Pilot! Make an informed decision.")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting... Good luck with your car search!")
    except ValueError as e:
        print(f"\nInput error: {e}")
        print("Please try again with valid inputs.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        print("Please try again or report this issue on GitHub.")
