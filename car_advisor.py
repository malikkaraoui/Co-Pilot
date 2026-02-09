#!/usr/bin/env python3
"""
Used Car Buying Assistant - Co-Pilot
A tool to help buyers make informed decisions about used car purchases
based on their usage, budget, and known model weaknesses.
"""

import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from enum import Enum


class UsageType(Enum):
    """Types of car usage patterns"""
    DAILY_COMMUTE = "daily_commute"
    FAMILY_TRANSPORT = "family_transport"
    WEEKEND_DRIVER = "weekend_driver"
    BUSINESS_TRAVEL = "business_travel"
    MIXED_USE = "mixed_use"


@dataclass
class UserRequirements:
    """User requirements for car purchase"""
    budget_min: float
    budget_max: float
    usage_type: UsageType
    annual_mileage: int
    priority_factors: List[str]  # e.g., ["reliability", "fuel_economy", "safety"]
    
    def to_dict(self):
        return {
            "budget_min": self.budget_min,
            "budget_max": self.budget_max,
            "usage_type": self.usage_type.value,
            "annual_mileage": self.annual_mileage,
            "priority_factors": self.priority_factors
        }


@dataclass
class CarModel:
    """Information about a specific car model"""
    make: str
    model: str
    year_range: str
    common_issues: List[str]
    strengths: List[str]
    typical_price_range: Dict[str, float]
    reliability_rating: float  # 0-10 scale
    fuel_economy: str
    maintenance_cost: str  # "low", "medium", "high"
    
    def to_dict(self):
        return asdict(self)


@dataclass
class Advice:
    """Advice generated for a specific car"""
    car_model: CarModel
    fit_score: float  # 0-100 scale
    budget_analysis: str
    usage_fit: str
    key_concerns: List[str]
    recommendations: List[str]
    overall_verdict: str
    
    def to_dict(self):
        result = asdict(self)
        result['car_model'] = self.car_model.to_dict()
        return result


class CarDatabase:
    """Database of car models and their characteristics"""
    
    def __init__(self):
        self.cars = self._initialize_database()
    
    def _initialize_database(self) -> List[CarModel]:
        """Initialize with sample car data"""
        return [
            CarModel(
                make="Honda",
                model="Civic",
                year_range="2016-2020",
                common_issues=[
                    "CVT transmission issues in some years",
                    "Air conditioning compressor failures",
                    "Infotainment system glitches"
                ],
                strengths=[
                    "Excellent reliability rating",
                    "Good fuel economy",
                    "Strong resale value",
                    "Low maintenance costs"
                ],
                typical_price_range={"min": 12000, "max": 18000},
                reliability_rating=8.5,
                fuel_economy="30-35 MPG combined",
                maintenance_cost="low"
            ),
            CarModel(
                make="Toyota",
                model="Camry",
                year_range="2015-2019",
                common_issues=[
                    "Some models have excessive oil consumption",
                    "Dashboard rattle in certain years",
                    "Brake actuator recalls"
                ],
                strengths=[
                    "Outstanding reliability",
                    "Spacious interior",
                    "Comfortable ride",
                    "Widely available parts"
                ],
                typical_price_range={"min": 14000, "max": 22000},
                reliability_rating=9.0,
                fuel_economy="28-32 MPG combined",
                maintenance_cost="low"
            ),
            CarModel(
                make="Ford",
                model="Focus",
                year_range="2014-2018",
                common_issues=[
                    "Dual-clutch transmission problems (major concern)",
                    "Power steering electronic failures",
                    "Clutch shuddering and overheating"
                ],
                strengths=[
                    "Fun to drive",
                    "Good handling",
                    "Available as hatchback",
                    "Affordable pricing"
                ],
                typical_price_range={"min": 8000, "max": 14000},
                reliability_rating=5.0,
                fuel_economy="28-30 MPG combined",
                maintenance_cost="medium"
            ),
            CarModel(
                make="Mazda",
                model="CX-5",
                year_range="2016-2020",
                common_issues=[
                    "Windshield prone to cracking",
                    "Bluetooth connectivity issues",
                    "Some reports of engine stalling"
                ],
                strengths=[
                    "Premium interior feel",
                    "Engaging driving dynamics",
                    "Good reliability",
                    "Strong safety ratings"
                ],
                typical_price_range={"min": 16000, "max": 24000},
                reliability_rating=8.0,
                fuel_economy="25-28 MPG combined",
                maintenance_cost="medium"
            ),
            CarModel(
                make="Volkswagen",
                model="Jetta",
                year_range="2015-2018",
                common_issues=[
                    "Water pump failures",
                    "Electrical system problems",
                    "Sunroof drainage issues leading to leaks"
                ],
                strengths=[
                    "Refined ride quality",
                    "Good fuel economy",
                    "European driving feel",
                    "Spacious trunk"
                ],
                typical_price_range={"min": 10000, "max": 16000},
                reliability_rating=6.5,
                fuel_economy="30-33 MPG combined",
                maintenance_cost="high"
            ),
            CarModel(
                make="Subaru",
                model="Outback",
                year_range="2015-2019",
                common_issues=[
                    "CVT transmission issues",
                    "Oil consumption in some engines",
                    "Head gasket problems in older models"
                ],
                strengths=[
                    "Excellent AWD system",
                    "Great for outdoors/adventure",
                    "Good ground clearance",
                    "Strong safety record"
                ],
                typical_price_range={"min": 15000, "max": 23000},
                reliability_rating=7.5,
                fuel_economy="25-27 MPG combined",
                maintenance_cost="medium"
            )
        ]
    
    def get_all_cars(self) -> List[CarModel]:
        """Get all cars in database"""
        return self.cars
    
    def find_car(self, make: str, model: str) -> Optional[CarModel]:
        """Find a specific car by make and model"""
        for car in self.cars:
            if car.make.lower() == make.lower() and car.model.lower() == model.lower():
                return car
        return None


class CarAdvisor:
    """Main advisor that generates personalized advice"""
    
    def __init__(self):
        self.database = CarDatabase()
    
    def assess_car(self, car: CarModel, requirements: UserRequirements) -> Advice:
        """Assess a car against user requirements"""
        
        # Calculate fit score
        fit_score = self._calculate_fit_score(car, requirements)
        
        # Generate budget analysis
        budget_analysis = self._analyze_budget(car, requirements)
        
        # Analyze usage fit
        usage_fit = self._analyze_usage_fit(car, requirements)
        
        # Identify key concerns
        key_concerns = self._identify_key_concerns(car, requirements)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(car, requirements)
        
        # Overall verdict
        overall_verdict = self._generate_verdict(car, requirements, fit_score)
        
        return Advice(
            car_model=car,
            fit_score=fit_score,
            budget_analysis=budget_analysis,
            usage_fit=usage_fit,
            key_concerns=key_concerns,
            recommendations=recommendations,
            overall_verdict=overall_verdict
        )
    
    def _calculate_fit_score(self, car: CarModel, requirements: UserRequirements) -> float:
        """Calculate how well the car fits user requirements (0-100)"""
        score = 0.0
        
        # Budget fit (30 points)
        price_mid = (car.typical_price_range["min"] + car.typical_price_range["max"]) / 2
        if requirements.budget_min <= price_mid <= requirements.budget_max:
            score += 30
        elif price_mid < requirements.budget_min:
            score += 20  # Below budget is okay
        elif price_mid > requirements.budget_max:
            # Proportional penalty
            overage = (price_mid - requirements.budget_max) / requirements.budget_max
            score += max(0, 30 - overage * 30)
        
        # Reliability (30 points)
        score += car.reliability_rating * 3
        
        # Maintenance cost (20 points)
        if car.maintenance_cost == "low":
            score += 20
        elif car.maintenance_cost == "medium":
            score += 12
        else:
            score += 5
        
        # Usage type fit (20 points)
        usage_score = self._calculate_usage_score(car, requirements.usage_type)
        score += usage_score
        
        return min(100, score)
    
    def _calculate_usage_score(self, car: CarModel, usage_type: UsageType) -> float:
        """Calculate usage fit score"""
        # Different cars suit different usage patterns
        if usage_type == UsageType.DAILY_COMMUTE:
            if car.maintenance_cost == "low" and car.reliability_rating > 7:
                return 20
            return 10
        elif usage_type == UsageType.FAMILY_TRANSPORT:
            if "Camry" in car.model or "Outback" in car.model or "CX-5" in car.model:
                return 20
            return 12
        elif usage_type == UsageType.WEEKEND_DRIVER:
            return 15  # Most cars work fine for weekend use
        elif usage_type == UsageType.BUSINESS_TRAVEL:
            if car.reliability_rating > 7.5 and car.maintenance_cost != "high":
                return 20
            return 8
        return 10
    
    def _analyze_budget(self, car: CarModel, requirements: UserRequirements) -> str:
        """Analyze budget fit"""
        price_min = car.typical_price_range["min"]
        price_max = car.typical_price_range["max"]
        price_mid = (price_min + price_max) / 2
        
        if price_max < requirements.budget_min:
            return f"This car (${price_min:,}-${price_max:,}) is well below your budget (${requirements.budget_min:,}-${requirements.budget_max:,}). You have room to consider newer models or better conditions."
        elif price_min > requirements.budget_max:
            return f"This car (${price_min:,}-${price_max:,}) exceeds your budget (${requirements.budget_min:,}-${requirements.budget_max:,}). Consider older years or higher mileage examples to bring it into budget."
        elif requirements.budget_min <= price_mid <= requirements.budget_max:
            return f"This car (${price_min:,}-${price_max:,}) fits well within your budget (${requirements.budget_min:,}-${requirements.budget_max:,}). Good value for the money."
        else:
            return f"This car (${price_min:,}-${price_max:,}) is at the edge of your budget (${requirements.budget_min:,}-${requirements.budget_max:,}). Carefully evaluate condition and negotiate price."
    
    def _analyze_usage_fit(self, car: CarModel, requirements: UserRequirements) -> str:
        """Analyze how well the car fits the usage pattern"""
        usage = requirements.usage_type
        mileage = requirements.annual_mileage
        
        fit_text = []
        
        if usage == UsageType.DAILY_COMMUTE:
            fit_text.append(f"For daily commuting ({mileage:,} miles/year):")
            if car.reliability_rating > 7.5:
                fit_text.append(f"✓ High reliability rating ({car.reliability_rating}/10) is excellent for daily use")
            else:
                fit_text.append(f"⚠ Moderate reliability ({car.reliability_rating}/10) may cause occasional issues")
            
            if car.maintenance_cost == "low":
                fit_text.append(f"✓ Low maintenance costs will keep your total ownership costs down")
            elif car.maintenance_cost == "high":
                fit_text.append(f"⚠ High maintenance costs will add up with daily driving")
            
            fit_text.append(f"✓ Fuel economy: {car.fuel_economy}")
        
        elif usage == UsageType.FAMILY_TRANSPORT:
            fit_text.append(f"For family transportation ({mileage:,} miles/year):")
            if "Outback" in car.model or "CX-5" in car.model:
                fit_text.append(f"✓ SUV/wagon body style provides good space and versatility")
            elif "Camry" in car.model:
                fit_text.append(f"✓ Sedan with spacious interior, good for families")
            else:
                fit_text.append(f"○ Check interior space meets your family's needs")
            
            fit_text.append(f"○ Safety ratings and reliability ({car.reliability_rating}/10) are important for family use")
        
        elif usage == UsageType.WEEKEND_DRIVER:
            fit_text.append(f"For weekend/occasional use ({mileage:,} miles/year):")
            fit_text.append(f"✓ Lower annual mileage reduces wear and maintenance frequency")
            if car.reliability_rating > 6:
                fit_text.append(f"✓ Should be reliable when you need it")
        
        elif usage == UsageType.BUSINESS_TRAVEL:
            fit_text.append(f"For business travel ({mileage:,} miles/year):")
            if car.reliability_rating > 8:
                fit_text.append(f"✓ Excellent reliability critical for business use")
            else:
                fit_text.append(f"⚠ Consider higher reliability for business needs")
            
            fit_text.append(f"○ Fuel economy: {car.fuel_economy}")
            fit_text.append(f"○ Maintenance: {car.maintenance_cost} cost")
        
        return "\n".join(fit_text)
    
    def _identify_key_concerns(self, car: CarModel, requirements: UserRequirements) -> List[str]:
        """Identify key concerns for this specific car and usage"""
        concerns = []
        
        # Critical reliability issues
        if car.reliability_rating < 6:
            concerns.append(f"LOW RELIABILITY: This model has below-average reliability ({car.reliability_rating}/10). Expect more frequent repairs.")
        
        # Known critical issues
        critical_keywords = ["transmission", "engine", "major", "recall"]
        for issue in car.common_issues:
            if any(keyword in issue.lower() for keyword in critical_keywords):
                concerns.append(f"CRITICAL ISSUE: {issue}")
        
        # High maintenance with high mileage
        if car.maintenance_cost == "high" and requirements.annual_mileage > 12000:
            concerns.append("HIGH MAINTENANCE + HIGH MILEAGE: This combination will be expensive over time.")
        
        # Budget concerns
        if car.typical_price_range["min"] > requirements.budget_max:
            concerns.append(f"OVER BUDGET: Typical prices exceed your maximum budget.")
        
        # Add top common issues
        if not concerns:  # If no critical concerns, add top issues as awareness
            concerns.extend([f"Known issue: {issue}" for issue in car.common_issues[:2]])
        
        return concerns
    
    def _generate_recommendations(self, car: CarModel, requirements: UserRequirements) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Pre-purchase inspection recommendations
        if car.reliability_rating < 7:
            recommendations.append("MUST DO: Get a comprehensive pre-purchase inspection from an independent mechanic")
        else:
            recommendations.append("Get a pre-purchase inspection focusing on common issues listed above")
        
        # Specific checks based on common issues
        for issue in car.common_issues[:3]:
            if "transmission" in issue.lower():
                recommendations.append("Have a transmission specialist inspect the transmission - test drive in various conditions")
            elif "oil" in issue.lower():
                recommendations.append("Check for oil consumption - look for oil residue, check service records")
            elif "electrical" in issue.lower() or "electronic" in issue.lower():
                recommendations.append("Test all electrical systems thoroughly during inspection")
        
        # Warranty recommendations
        if car.maintenance_cost == "high" or car.reliability_rating < 7:
            recommendations.append("Consider purchasing an extended warranty given the potential for costly repairs")
        
        # Service history
        recommendations.append("Request complete service history - regular maintenance is critical for used cars")
        
        # Budget planning
        if car.maintenance_cost == "medium" or car.maintenance_cost == "high":
            recommendations.append(f"Budget for {car.maintenance_cost} maintenance costs - set aside emergency repair fund")
        
        # Year-specific advice
        recommendations.append(f"Research the specific year within {car.year_range} - some years are more problematic than others")
        
        return recommendations
    
    def _generate_verdict(self, car: CarModel, requirements: UserRequirements, fit_score: float) -> str:
        """Generate overall verdict"""
        if fit_score >= 75:
            verdict = f"✓ GOOD CHOICE: This {car.make} {car.model} is a strong match for your needs."
        elif fit_score >= 60:
            verdict = f"○ ACCEPTABLE: This {car.make} {car.model} could work but has some considerations."
        elif fit_score >= 45:
            verdict = f"⚠ PROCEED WITH CAUTION: This {car.make} {car.model} has notable concerns for your situation."
        else:
            verdict = f"✗ NOT RECOMMENDED: This {car.make} {car.model} is not a good fit for your requirements."
        
        # Add specific reasoning
        if car.reliability_rating > 8 and fit_score >= 70:
            verdict += " The excellent reliability makes it a safe bet."
        elif car.reliability_rating < 6:
            verdict += " Poor reliability is a significant risk."
        
        if car.maintenance_cost == "high" and requirements.annual_mileage > 12000:
            verdict += " High maintenance costs with your driving needs will be expensive."
        
        return verdict
    
    def find_suitable_cars(self, requirements: UserRequirements) -> List[Advice]:
        """Find and assess all cars that might fit requirements"""
        all_cars = self.database.get_all_cars()
        assessments = []
        
        for car in all_cars:
            advice = self.assess_car(car, requirements)
            assessments.append(advice)
        
        # Sort by fit score
        assessments.sort(key=lambda x: x.fit_score, reverse=True)
        return assessments


def format_advice(advice: Advice) -> str:
    """Format advice for display"""
    car = advice.car_model
    lines = []
    
    lines.append("=" * 80)
    lines.append(f"{car.make} {car.model} ({car.year_range})")
    lines.append("=" * 80)
    lines.append(f"FIT SCORE: {advice.fit_score:.1f}/100")
    lines.append("")
    
    lines.append("OVERALL VERDICT:")
    lines.append(advice.overall_verdict)
    lines.append("")
    
    lines.append("BUDGET ANALYSIS:")
    lines.append(advice.budget_analysis)
    lines.append("")
    
    lines.append("USAGE FIT:")
    lines.append(advice.usage_fit)
    lines.append("")
    
    lines.append("KEY STRENGTHS:")
    for strength in car.strengths:
        lines.append(f"  ✓ {strength}")
    lines.append("")
    
    lines.append("KEY CONCERNS:")
    if advice.key_concerns:
        for concern in advice.key_concerns:
            lines.append(f"  ⚠ {concern}")
    else:
        lines.append("  No major concerns identified")
    lines.append("")
    
    lines.append("RECOMMENDATIONS:")
    for i, rec in enumerate(advice.recommendations, 1):
        lines.append(f"  {i}. {rec}")
    lines.append("")
    
    lines.append("TECHNICAL DETAILS:")
    lines.append(f"  Reliability Rating: {car.reliability_rating}/10")
    lines.append(f"  Fuel Economy: {car.fuel_economy}")
    lines.append(f"  Maintenance Cost: {car.maintenance_cost.upper()}")
    lines.append(f"  Typical Price Range: ${car.typical_price_range['min']:,} - ${car.typical_price_range['max']:,}")
    lines.append("")
    
    return "\n".join(lines)


def main():
    """Main entry point for the car advisor"""
    print("=" * 80)
    print("USED CAR BUYING ASSISTANT - Co-Pilot")
    print("=" * 80)
    print("Get personalized advice based on your usage, budget, and known model issues")
    print("=" * 80)
    print()
    
    # Example usage with predefined requirements
    print("Example Analysis: Daily Commuter with $15,000-$20,000 budget")
    print("-" * 80)
    
    requirements = UserRequirements(
        budget_min=15000,
        budget_max=20000,
        usage_type=UsageType.DAILY_COMMUTE,
        annual_mileage=15000,
        priority_factors=["reliability", "fuel_economy", "low_maintenance"]
    )
    
    advisor = CarAdvisor()
    assessments = advisor.find_suitable_cars(requirements)
    
    # Show top 3 recommendations
    print("\nTOP 3 RECOMMENDATIONS FOR YOUR NEEDS:\n")
    for i, advice in enumerate(assessments[:3], 1):
        print(f"\n{'#' * 80}")
        print(f"RECOMMENDATION #{i}")
        print(format_advice(advice))
    
    # Show one to avoid
    if len(assessments) > 3:
        print(f"\n{'#' * 80}")
        print("CARS TO AVOID:")
        worst = assessments[-1]
        print(format_advice(worst))


if __name__ == "__main__":
    main()
