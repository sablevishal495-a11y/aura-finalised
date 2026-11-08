"""Risk-based lending policy: LTV checks and valuation routing.

The routing decides how much physical valuation work a case needs. It supports a human
credit decision; it never approves or declines a loan by itself.
"""
from __future__ import annotations

# RBI LTV ceilings for individual housing loans (loan amount slab -> max LTV).
RESIDENTIAL_LTV_SLABS = [
    (3_000_000, 0.90),     # up to Rs 30 lakh
    (7_500_000, 0.80),     # Rs 30 lakh - 75 lakh
    (float("inf"), 0.75),  # above Rs 75 lakh
]
# Illustrative lender policy for loans against commercial property (configure per lender).
COMMERCIAL_MAX_LTV = 0.60
COMMERCIAL_TYPES = {"office space", "retail shop"}

# Routing policy (illustrative defaults; a lender would tune these in a pilot).
MIN_COMPARABLES_FOR_DESK = 3
HIGH_VALUE_THRESHOLD_INR = 50_000_000  # Rs 5 crore and above always gets a site visit

AUTO_DESK = "AUTO_DESK_VALUATION"
DESKTOP_REVIEW = "DESKTOP_REVIEW"
PHYSICAL = "PHYSICAL_INSPECTION"

ROUTING_LABELS = {
    AUTO_DESK: "Desk valuation - no site visit",
    DESKTOP_REVIEW: "Desktop review by valuer",
    PHYSICAL: "Physical inspection required",
}


def is_commercial(property_type: str) -> bool:
    return property_type.casefold() in COMMERCIAL_TYPES


def max_ltv_for(loan_amount: float, property_type: str) -> float:
    if is_commercial(property_type):
        return COMMERCIAL_MAX_LTV
    for upper, ltv in RESIDENTIAL_LTV_SLABS:
        if loan_amount <= upper:
            return ltv
    return RESIDENTIAL_LTV_SLABS[-1][1]


def max_eligible_loan(collateral_value: float, property_type: str) -> float:
    if is_commercial(property_type):
        return COMMERCIAL_MAX_LTV * collateral_value
    best, lower = 0.0, 0.0
    for upper, ltv in RESIDENTIAL_LTV_SLABS:
        candidate = min(upper, ltv * collateral_value)
        if candidate > lower:
            best = max(best, candidate)
        lower = upper
    return best


def route(valuation: dict, comparable_count: int, property_type: str, loan_amount: float | None) -> dict:
    """Decide the valuation route and, when a loan amount is given, the LTV risk band."""
    confidence = valuation["confidence"]["label"]
    warnings = valuation["coverage_warnings"]
    # Lenders lend against the conservative end of the range.
    collateral = valuation["low_estimate_inr"]
    reasons = []

    if warnings:
        routing = PHYSICAL
        reasons.append("Property is outside the model's coverage.")
    elif confidence == "Low":
        routing = PHYSICAL
        reasons.append("Model confidence is low (wide valuation range).")
    elif valuation["estimated_value_inr"] >= HIGH_VALUE_THRESHOLD_INR:
        routing = PHYSICAL
        reasons.append("High-value property (Rs 5 crore or more) always gets a site visit.")
    elif comparable_count < MIN_COMPARABLES_FOR_DESK:
        routing = DESKTOP_REVIEW
        reasons.append(f"Fewer than {MIN_COMPARABLES_FOR_DESK} comparable transactions nearby.")
    elif confidence == "Medium":
        routing = DESKTOP_REVIEW
        reasons.append("Medium confidence: a valuer should check documents and photos.")
    else:
        routing = AUTO_DESK
        reasons.append("High confidence, enough comparables and within coverage.")

    lending = None
    if loan_amount:
        cap = max_ltv_for(loan_amount, property_type)
        ltv = loan_amount / collateral if collateral > 0 else float("inf")
        if ltv > cap:
            risk_band = "High"
            reasons.append(f"Requested LTV {ltv:.0%} is above the {cap:.0%} cap.")
            if routing == AUTO_DESK:
                routing = DESKTOP_REVIEW
        elif ltv > cap - 0.10 or confidence != "High":
            risk_band = "Medium"
        else:
            risk_band = "Low"
        lending = {
            "loan_amount_inr": round(loan_amount, 2),
            "collateral_value_inr": round(collateral, 2),
            "collateral_basis": "Low end of the calibrated valuation range",
            "ltv_pct": round(ltv * 100, 1),
            "max_ltv_pct": round(cap * 100, 1),
            "ltv_policy": ("Illustrative lender policy for commercial property" if is_commercial(property_type)
                           else "RBI LTV ceiling for individual housing loans"),
            "max_eligible_loan_inr": round(max_eligible_loan(collateral, property_type), 0),
            "risk_band": risk_band,
        }

    return {
        "routing": routing,
        "routing_label": ROUTING_LABELS[routing],
        "reasons": reasons,
        "physical_visit_avoided": routing != PHYSICAL,
        "human_review_required": True,
        "lending": lending,
        "notice": "Decision support only. A credit officer makes the lending decision.",
    }
