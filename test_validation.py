#!/usr/bin/env python3
"""
Simple validation tests for the Used Car Buying Assistant
Tests core functionality to ensure advice is generated correctly
"""

from car_advisor import (
    CarAdvisor, UserRequirements, UsageType, CarModel
)


def test_car_database():
    """Test that car database is properly initialized"""
    print("Testing car database initialization...")
    advisor = CarAdvisor()
    cars = advisor.database.get_all_cars()
    
    assert len(cars) > 0, "Database should contain cars"
    assert all(isinstance(car, CarModel) for car in cars), "All entries should be CarModel instances"
    
    # Test find_car method
    civic = advisor.database.find_car("Honda", "Civic")
    assert civic is not None, "Should find Honda Civic"
    assert civic.make == "Honda", "Make should match"
    assert civic.model == "Civic", "Model should match"
    
    print("✓ Car database tests passed")


def test_basic_assessment():
    """Test basic car assessment"""
    print("\nTesting basic car assessment...")
    
    requirements = UserRequirements(
        budget_min=15000,
        budget_max=20000,
        usage_type=UsageType.DAILY_COMMUTE,
        annual_mileage=15000,
        priority_factors=["reliability", "fuel_economy"]
    )
    
    advisor = CarAdvisor()
    car = advisor.database.find_car("Honda", "Civic")
    
    assert car is not None, "Test car should exist"
    
    advice = advisor.assess_car(car, requirements)
    
    # Validate advice structure
    assert advice.fit_score >= 0 and advice.fit_score <= 100, "Fit score should be 0-100"
    assert len(advice.budget_analysis) > 0, "Budget analysis should not be empty"
    assert len(advice.usage_fit) > 0, "Usage fit should not be empty"
    assert isinstance(advice.key_concerns, list), "Key concerns should be a list"
    assert isinstance(advice.recommendations, list), "Recommendations should be a list"
    assert len(advice.recommendations) > 0, "Should have recommendations"
    assert len(advice.overall_verdict) > 0, "Should have verdict"
    
    print("✓ Basic assessment tests passed")


def test_fit_score_calculation():
    """Test that fit scores are calculated reasonably"""
    print("\nTesting fit score calculation...")
    
    advisor = CarAdvisor()
    
    # High budget, reliable car - should score well
    high_budget_reqs = UserRequirements(
        budget_min=20000,
        budget_max=30000,
        usage_type=UsageType.DAILY_COMMUTE,
        annual_mileage=15000,
        priority_factors=["reliability"]
    )
    
    camry = advisor.database.find_car("Toyota", "Camry")
    advice = advisor.assess_car(camry, high_budget_reqs)
    high_score = advice.fit_score
    
    # Low budget, less reliable car
    low_budget_reqs = UserRequirements(
        budget_min=5000,
        budget_max=8000,
        usage_type=UsageType.DAILY_COMMUTE,
        annual_mileage=20000,  # High mileage
        priority_factors=["low_maintenance"]
    )
    
    focus = advisor.database.find_car("Ford", "Focus")
    advice = advisor.assess_car(focus, low_budget_reqs)
    low_score = advice.fit_score
    
    # High reliability, good budget match should score higher than
    # low reliability with budget mismatch
    print(f"  High reliability + good budget: {high_score:.1f}/100")
    print(f"  Low reliability + budget mismatch: {low_score:.1f}/100")
    
    assert high_score > 70, "Good match should score well"
    assert low_score < high_score, "Better match should score higher"
    
    print("✓ Fit score calculation tests passed")


def test_find_suitable_cars():
    """Test finding suitable cars for requirements"""
    print("\nTesting find_suitable_cars...")
    
    requirements = UserRequirements(
        budget_min=15000,
        budget_max=20000,
        usage_type=UsageType.FAMILY_TRANSPORT,
        annual_mileage=12000,
        priority_factors=["reliability", "safety"]
    )
    
    advisor = CarAdvisor()
    assessments = advisor.find_suitable_cars(requirements)
    
    assert len(assessments) > 0, "Should return assessments"
    assert all(hasattr(a, 'fit_score') for a in assessments), "All should have fit scores"
    
    # Check sorting (highest score first)
    scores = [a.fit_score for a in assessments]
    assert scores == sorted(scores, reverse=True), "Should be sorted by fit score (high to low)"
    
    print(f"  Found {len(assessments)} cars")
    print(f"  Top recommendation: {assessments[0].car_model.make} {assessments[0].car_model.model} ({assessments[0].fit_score:.1f}/100)")
    
    print("✓ Find suitable cars tests passed")


def test_usage_types():
    """Test different usage types produce different advice"""
    print("\nTesting different usage types...")
    
    advisor = CarAdvisor()
    car = advisor.database.find_car("Toyota", "Camry")
    
    usage_types = [
        UsageType.DAILY_COMMUTE,
        UsageType.FAMILY_TRANSPORT,
        UsageType.WEEKEND_DRIVER,
        UsageType.BUSINESS_TRAVEL
    ]
    
    for usage in usage_types:
        requirements = UserRequirements(
            budget_min=15000,
            budget_max=20000,
            usage_type=usage,
            annual_mileage=10000,
            priority_factors=["reliability"]
        )
        
        advice = advisor.assess_car(car, requirements)
        assert len(advice.usage_fit) > 0, f"Should generate usage fit for {usage.value}"
        print(f"  ✓ {usage.value}: {advice.fit_score:.1f}/100")
    
    print("✓ Usage type tests passed")


def test_data_serialization():
    """Test that data can be serialized to dict"""
    print("\nTesting data serialization...")
    
    requirements = UserRequirements(
        budget_min=15000,
        budget_max=20000,
        usage_type=UsageType.DAILY_COMMUTE,
        annual_mileage=15000,
        priority_factors=["reliability"]
    )
    
    req_dict = requirements.to_dict()
    assert isinstance(req_dict, dict), "Should serialize to dict"
    assert "budget_min" in req_dict, "Should include budget_min"
    assert "usage_type" in req_dict, "Should include usage_type"
    
    advisor = CarAdvisor()
    car = advisor.database.find_car("Honda", "Civic")
    
    car_dict = car.to_dict()
    assert isinstance(car_dict, dict), "Car should serialize to dict"
    assert "make" in car_dict, "Should include make"
    
    advice = advisor.assess_car(car, requirements)
    advice_dict = advice.to_dict()
    assert isinstance(advice_dict, dict), "Advice should serialize to dict"
    assert "fit_score" in advice_dict, "Should include fit_score"
    
    print("✓ Data serialization tests passed")


def run_all_tests():
    """Run all validation tests"""
    print("=" * 80)
    print("RUNNING VALIDATION TESTS")
    print("=" * 80)
    
    tests = [
        test_car_database,
        test_basic_assessment,
        test_fit_score_calculation,
        test_find_suitable_cars,
        test_usage_types,
        test_data_serialization
    ]
    
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"✗ Test failed: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ Test error: {e}")
            failed += 1
    
    print("\n" + "=" * 80)
    if failed == 0:
        print("✓ ALL TESTS PASSED")
    else:
        print(f"✗ {failed} TEST(S) FAILED")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
