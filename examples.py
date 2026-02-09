#!/usr/bin/env python3
"""
Example scenarios demonstrating Co-Pilot usage for different situations
"""

from car_advisor import CarAdvisor, UserRequirements, UsageType, format_advice


def scenario_1_budget_conscious_student():
    """Scenario: Budget-conscious college student"""
    print("\n" + "=" * 80)
    print("SCENARIO 1: Budget-Conscious College Student")
    print("=" * 80)
    print("Profile: College student, limited budget, occasional weekend use")
    print("-" * 80)
    
    requirements = UserRequirements(
        budget_min=6000,
        budget_max=10000,
        usage_type=UsageType.WEEKEND_DRIVER,
        annual_mileage=5000,
        priority_factors=["low_maintenance", "fuel_economy", "reliability"]
    )
    
    advisor = CarAdvisor()
    
    # Check specific affordable car
    car = advisor.database.find_car("Ford", "Focus")
    if car:
        advice = advisor.assess_car(car, requirements)
        print(format_advice(advice))


def scenario_2_growing_family():
    """Scenario: Growing family needs reliable transportation"""
    print("\n" + "=" * 80)
    print("SCENARIO 2: Growing Family")
    print("=" * 80)
    print("Profile: Family with kids, needs space and reliability, moderate budget")
    print("-" * 80)
    
    requirements = UserRequirements(
        budget_min=18000,
        budget_max=25000,
        usage_type=UsageType.FAMILY_TRANSPORT,
        annual_mileage=12000,
        priority_factors=["reliability", "safety", "comfort"]
    )
    
    advisor = CarAdvisor()
    assessments = advisor.find_suitable_cars(requirements)
    
    # Show top 2 for families
    print("\nBest options for your family:\n")
    for i, advice in enumerate(assessments[:2], 1):
        print(format_advice(advice))


def scenario_3_long_commuter():
    """Scenario: Long daily commute"""
    print("\n" + "=" * 80)
    print("SCENARIO 3: Long Daily Commuter")
    print("=" * 80)
    print("Profile: 80-mile daily commute, needs reliability and fuel efficiency")
    print("-" * 80)
    
    requirements = UserRequirements(
        budget_min=12000,
        budget_max=18000,
        usage_type=UsageType.DAILY_COMMUTE,
        annual_mileage=20000,  # High mileage
        priority_factors=["reliability", "fuel_economy", "low_maintenance"]
    )
    
    advisor = CarAdvisor()
    
    # Compare two popular commuter cars
    civic = advisor.database.find_car("Honda", "Civic")
    camry = advisor.database.find_car("Toyota", "Camry")
    
    print("\nComparing top commuter choices:\n")
    if civic:
        advice = advisor.assess_car(civic, requirements)
        print(format_advice(advice))
    
    if camry:
        advice = advisor.assess_car(camry, requirements)
        print(format_advice(advice))


def scenario_4_first_time_buyer():
    """Scenario: First-time used car buyer, wants guidance"""
    print("\n" + "=" * 80)
    print("SCENARIO 4: First-Time Used Car Buyer")
    print("=" * 80)
    print("Profile: New to used cars, wants reliable and worry-free option")
    print("-" * 80)
    
    requirements = UserRequirements(
        budget_min=15000,
        budget_max=20000,
        usage_type=UsageType.MIXED_USE,
        annual_mileage=10000,
        priority_factors=["reliability", "low_maintenance"]
    )
    
    advisor = CarAdvisor()
    assessments = advisor.find_suitable_cars(requirements)
    
    # Show best overall choice
    print("\nRecommended for first-time buyers (worry-free options):\n")
    best = assessments[0]
    print(format_advice(best))


def scenario_5_adventure_seeker():
    """Scenario: Outdoor enthusiast needs capable vehicle"""
    print("\n" + "=" * 80)
    print("SCENARIO 5: Adventure Seeker")
    print("=" * 80)
    print("Profile: Weekend outdoor adventures, needs AWD and reliability")
    print("-" * 80)
    
    requirements = UserRequirements(
        budget_min=16000,
        budget_max=24000,
        usage_type=UsageType.WEEKEND_DRIVER,
        annual_mileage=8000,
        priority_factors=["reliability", "performance"]
    )
    
    advisor = CarAdvisor()
    
    # Check AWD options
    outback = advisor.database.find_car("Subaru", "Outback")
    cx5 = advisor.database.find_car("Mazda", "CX-5")
    
    print("\nAWD/SUV options for outdoor adventures:\n")
    if outback:
        advice = advisor.assess_car(outback, requirements)
        print(format_advice(advice))
    
    if cx5:
        advice = advisor.assess_car(cx5, requirements)
        print(format_advice(advice))


def main():
    """Run all example scenarios"""
    print("=" * 80)
    print("CO-PILOT EXAMPLE SCENARIOS")
    print("=" * 80)
    print("Demonstrating personalized advice for different buyer situations")
    print("=" * 80)
    
    scenarios = [
        scenario_1_budget_conscious_student,
        scenario_2_growing_family,
        scenario_3_long_commuter,
        scenario_4_first_time_buyer,
        scenario_5_adventure_seeker
    ]
    
    for scenario in scenarios:
        scenario()
        input("\nPress Enter to continue to next scenario...")
    
    print("\n" + "=" * 80)
    print("End of example scenarios")
    print("=" * 80)


if __name__ == "__main__":
    main()
