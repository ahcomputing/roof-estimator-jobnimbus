"""
calculator.py — Materials and labor estimator from roof analysis JSON.
All prices are national averages; adjust in PRICING dict for local rates.
"""

import math

PRICING = {
    # Materials
    "shingles_per_bundle": 32.00,       # 3-tab, per bundle (covers ~33 sqft)
    "architectural_shingles_per_bundle": 48.00,  # architectural, per bundle
    "underlayment_per_roll": 75.00,      # 15lb felt, 400 sqft per roll
    "ice_water_shield_per_sqft": 0.75,
    "drip_edge_per_lnft": 1.50,         # per linear foot
    "ridge_cap_per_lnft": 3.50,         # per linear foot
    "valley_flashing_per_lnft": 4.00,
    "roofing_nails_per_lb": 3.50,
    "plywood_per_sheet": 55.00,         # 4x8, if deck replacement needed

    # Labor (per square = 100 sqft)
    "tearoff_per_square": 65.00,
    "install_per_square": 150.00,

    # Other
    "waste_factor": 0.12,               # 12% waste
    "tax_rate": 0.08,                   # 8% sales tax
}

SHINGLE_SQFT_PER_BUNDLE = 33.0
UNDERLAYMENT_SQFT_PER_ROLL = 400.0
NAILS_LBS_PER_SQUARE = 2.5


def calculate(analysis: dict, shingle_type: str = "architectural") -> dict:
    """
    Takes roof analysis dict, returns full materials + labor breakdown.
    """
    total_area = analysis.get("total_roof_area_sqft", 0)
    eave_lnft = analysis.get("eave_linear_ft", 0)
    ridge_lnft = analysis.get("ridge_linear_ft", 0)
    hip_lnft = analysis.get("hip_linear_ft", 0)
    valley_lnft = analysis.get("valley_linear_ft", 0)

    ridge_total = ridge_lnft + hip_lnft  # Both use ridge cap
    area_with_waste = total_area * (1 + PRICING["waste_factor"])
    squares = total_area / 100.0

    # --- Shingles ---
    bundles_needed = math.ceil(area_with_waste / SHINGLE_SQFT_PER_BUNDLE)
    shingle_price = (
        PRICING["architectural_shingles_per_bundle"]
        if shingle_type == "architectural"
        else PRICING["shingles_per_bundle"]
    )
    shingles_cost = bundles_needed * shingle_price

    # --- Underlayment ---
    rolls_needed = math.ceil(area_with_waste / UNDERLAYMENT_SQFT_PER_ROLL)
    underlayment_cost = rolls_needed * PRICING["underlayment_per_roll"]

    # --- Ice & water shield (eaves: first 3ft up from eave edge) ---
    ice_shield_sqft = eave_lnft * 3
    ice_shield_cost = ice_shield_sqft * PRICING["ice_water_shield_per_sqft"]

    # --- Drip edge ---
    drip_edge_cost = eave_lnft * PRICING["drip_edge_per_lnft"]

    # --- Ridge cap ---
    ridge_cap_cost = ridge_total * PRICING["ridge_cap_per_lnft"]

    # --- Valley flashing ---
    valley_cost = valley_lnft * PRICING["valley_flashing_per_lnft"]

    # --- Nails ---
    nails_lbs = math.ceil(squares * NAILS_LBS_PER_SQUARE)
    nails_cost = nails_lbs * PRICING["roofing_nails_per_lb"]

    # --- Labor ---
    tearoff_cost = squares * PRICING["tearoff_per_square"]
    install_cost = squares * PRICING["install_per_square"]

    # --- Build line items ---
    line_items = []

    def add_item(qty, unit, description, unit_price):
        amount = round(qty * unit_price, 2)
        line_items.append({
            "qty": qty,
            "unit": unit,
            "description": description,
            "unit_price": round(unit_price, 2),
            "amount": amount,
        })
        return amount

    subtotal = 0
    subtotal += add_item(bundles_needed, "bundles",
                         f"{'Architectural' if shingle_type == 'architectural' else '3-Tab'} Roofing Shingles",
                         shingle_price)
    subtotal += add_item(rolls_needed, "rolls",
                         "Roofing Underlayment (15lb felt, 400 sqft/roll)",
                         PRICING["underlayment_per_roll"])
    if ice_shield_sqft > 0:
        subtotal += add_item(round(ice_shield_sqft), "sqft",
                             "Ice & Water Shield (eave protection)",
                             PRICING["ice_water_shield_per_sqft"])
    subtotal += add_item(round(eave_lnft), "lnft",
                         "Drip Edge / Eave Trim",
                         PRICING["drip_edge_per_lnft"])
    if ridge_total > 0:
        subtotal += add_item(round(ridge_total), "lnft",
                             "Ridge Cap Shingles (ridge + hips)",
                             PRICING["ridge_cap_per_lnft"])
    if valley_lnft > 0:
        subtotal += add_item(round(valley_lnft), "lnft",
                             "Valley Flashing",
                             PRICING["valley_flashing_per_lnft"])
    subtotal += add_item(nails_lbs, "lbs",
                         "Roofing Nails",
                         PRICING["roofing_nails_per_lb"])
    subtotal += add_item(round(squares, 1), "squares",
                         "Tear-Off & Disposal (existing roof removal)",
                         PRICING["tearoff_per_square"])
    subtotal += add_item(round(squares, 1), "squares",
                         "Installation Labor",
                         PRICING["install_per_square"])

    subtotal = round(subtotal, 2)
    tax = round(subtotal * PRICING["tax_rate"], 2)
    total = round(subtotal + tax, 2)

    return {
        "line_items": line_items,
        "subtotal": subtotal,
        "tax_rate_pct": PRICING["tax_rate"] * 100,
        "tax": tax,
        "total": total,
        "summary": {
            "total_roof_area_sqft": round(total_area, 1),
            "total_squares": round(squares, 1),
            "shingle_bundles": bundles_needed,
            "eave_linear_ft": round(eave_lnft, 1),
            "ridge_linear_ft": round(ridge_total, 1),
            "valley_linear_ft": round(valley_lnft, 1),
        }
    }
