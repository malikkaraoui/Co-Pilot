# Co-Pilot - Used Car Buying Assistant

An intelligent assistant designed to help people buy used cars with confidence. Instead of just showing you a vehicle's history, Co-Pilot helps you determine whether a specific car is the right choice for **your** needs, based on:

- **Your usage patterns** (daily commute, family transport, weekend driving, etc.)
- **Your budget** (not just if you can afford it, but if it's a good value)
- **Known model weaknesses** (turning scattered technical information into clear, actionable advice)

## What Makes Co-Pilot Different?

Unlike typical car history services, Co-Pilot:
- ✓ Focuses on **helping you decide**, not just reporting facts
- ✓ Considers **your specific situation** - budget, driving needs, and priorities
- ✓ Provides **practical, actionable advice** before you make the purchase
- ✓ Warns you about **model-specific issues** to check during inspection
- ✓ Generates **personalized recommendations** for each car you're considering

## Features

### Comprehensive Assessment
- **Budget Analysis**: Determines if the car fits your budget and if it's good value
- **Usage Fit Analysis**: Evaluates how well the car matches your driving patterns
- **Reliability Scoring**: Rates cars on a 0-10 scale based on known issues
- **Maintenance Cost Estimates**: Helps you understand long-term ownership costs

### Practical Advice
- **Key Concerns**: Highlights critical issues to be aware of
- **Actionable Recommendations**: Specific things to check during inspection
- **Model Strengths**: What this car does well
- **Overall Verdict**: Clear guidance on whether this car is right for you

### Built-in Knowledge Base
Includes detailed information on popular models:
- Honda Civic (2016-2020)
- Toyota Camry (2015-2019)
- Ford Focus (2014-2018)
- Mazda CX-5 (2016-2020)
- Volkswagen Jetta (2015-2018)
- Subaru Outback (2015-2019)

## Installation

```bash
# Clone the repository
git clone https://github.com/malikkaraoui/Co-Pilot.git
cd Co-Pilot

# No dependencies needed! Uses Python 3.7+ standard library only
python car_advisor.py
```

## Usage

### Quick Start - Run Example Analysis

The simplest way to see Co-Pilot in action:

```bash
python car_advisor.py
```

This runs an example scenario (daily commuter with $15,000-$20,000 budget) and shows recommendations.

### Custom Analysis (Python API)

You can use Co-Pilot programmatically to assess cars for your specific needs:

```python
from car_advisor import CarAdvisor, UserRequirements, UsageType

# Define your requirements
requirements = UserRequirements(
    budget_min=15000,
    budget_max=20000,
    usage_type=UsageType.DAILY_COMMUTE,
    annual_mileage=15000,
    priority_factors=["reliability", "fuel_economy", "low_maintenance"]
)

# Create advisor and get recommendations
advisor = CarAdvisor()
assessments = advisor.find_suitable_cars(requirements)

# Get advice for specific car
car = advisor.database.find_car("Honda", "Civic")
if car:
    advice = advisor.assess_car(car, requirements)
    print(f"Fit Score: {advice.fit_score}/100")
    print(f"Verdict: {advice.overall_verdict}")
```

### Usage Types

Co-Pilot supports different usage patterns:

- `DAILY_COMMUTE`: Regular weekday driving, prioritizes reliability and fuel economy
- `FAMILY_TRANSPORT`: Family vehicle needs, considers space and safety
- `WEEKEND_DRIVER`: Occasional use, lower annual mileage
- `BUSINESS_TRAVEL`: Professional use, emphasizes reliability and presentability
- `MIXED_USE`: Combination of various uses

## Example Output

```
================================================================================
Honda Civic (2016-2020)
================================================================================
FIT SCORE: 85.0/100

OVERALL VERDICT:
✓ GOOD CHOICE: This Honda Civic is a strong match for your needs. The excellent 
reliability makes it a safe bet.

BUDGET ANALYSIS:
This car ($12,000-$18,000) fits well within your budget ($15,000-$20,000). 
Good value for the money.

USAGE FIT:
For daily commuting (15,000 miles/year):
✓ High reliability rating (8.5/10) is excellent for daily use
✓ Low maintenance costs will keep your total ownership costs down
✓ Fuel economy: 30-35 MPG combined

KEY STRENGTHS:
  ✓ Excellent reliability rating
  ✓ Good fuel economy
  ✓ Strong resale value
  ✓ Low maintenance costs

KEY CONCERNS:
  ⚠ Known issue: CVT transmission issues in some years
  ⚠ Known issue: Air conditioning compressor failures

RECOMMENDATIONS:
  1. Get a pre-purchase inspection focusing on common issues listed above
  2. Have a transmission specialist inspect the transmission - test drive in 
     various conditions
  3. Request complete service history - regular maintenance is critical for 
     used cars
  4. Research the specific year within 2016-2020 - some years are more 
     problematic than others
```

## How It Works

### 1. Define Your Requirements
Tell Co-Pilot about your budget, how you'll use the car, and your priorities.

### 2. Get Personalized Assessment
Co-Pilot analyzes each car model against your specific needs, considering:
- Price fit within your budget
- Reliability for your usage pattern
- Maintenance costs over time
- Known model-specific issues

### 3. Receive Actionable Advice
Get clear guidance including:
- Whether this car is a good choice for YOU
- What to check during inspection
- Potential concerns to be aware of
- Overall verdict and reasoning

### 4. Make Informed Decision
Armed with practical, personalized advice, you can confidently move forward or walk away.

## Architecture

The system is designed with clean separation of concerns:

- **Data Models** (`UserRequirements`, `CarModel`, `Advice`): Structured data representation
- **CarDatabase**: Knowledge base of car models and their characteristics
- **CarAdvisor**: Core logic for assessing fit and generating advice
- **Formatting**: Clean presentation of advice to users

## Extending the Knowledge Base

To add more car models, edit the `_initialize_database()` method in `CarDatabase`:

```python
CarModel(
    make="Your Make",
    model="Your Model",
    year_range="2015-2020",
    common_issues=["Issue 1", "Issue 2"],
    strengths=["Strength 1", "Strength 2"],
    typical_price_range={"min": 10000, "max": 15000},
    reliability_rating=7.5,
    fuel_economy="28-32 MPG combined",
    maintenance_cost="medium"
)
```

## Design Philosophy

Co-Pilot is built on these principles:

1. **User-Centric**: Every recommendation is personalized to the user's specific situation
2. **Practical**: Focus on actionable advice, not just data
3. **Honest**: Clearly communicate both strengths and concerns
4. **Educational**: Help users understand WHY a car is or isn't a good fit
5. **Comprehensive**: Consider budget, usage, reliability, and maintenance together

## Future Enhancements

Potential additions:
- Web interface for easier interaction
- Integration with real-time pricing data
- More car models in the knowledge base
- Insurance cost estimates
- Comparison view for multiple cars side-by-side
- Import from VIN or listing URL

## Contributing

Contributions are welcome! Areas where help is needed:
- Adding more car models to the knowledge base
- Improving assessment algorithms
- Adding new usage patterns
- UI/UX improvements

## License

See LICENSE file for details.

## Contact

For questions or suggestions, please open an issue on GitHub.