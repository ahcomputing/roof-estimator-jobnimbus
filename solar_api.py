"""
solar_api.py — Google Solar API integration
Uses buildingInsights:findClosest to get real roof segment data.
Returns structured roof analysis compatible with the rest of the pipeline.
"""

import math
import requests


SQM_TO_SQFT = 10.7639

# Map pitch degrees to nearest standard roofing fraction and multiplier
def pitch_degrees_to_fraction(degrees: float) -> tuple[str, float]:
    # Convert degrees to rise/12 run
    # tan(pitch_angle) = rise/run, standard is rise per 12 inches of run
    rise = round(math.tan(math.radians(degrees)) * 12)
    rise = max(1, min(rise, 12))  # clamp 1-12
    multiplier = 1 / math.cos(math.radians(degrees))
    pitch_map = {
        1: ("2/12", 1.014), 2: ("2/12", 1.014), 3: ("3/12", 1.031),
        4: ("4/12", 1.054), 5: ("5/12", 1.083), 6: ("6/12", 1.118),
        7: ("7/12", 1.157), 8: ("8/12", 1.202), 9: ("9/12", 1.250),
        10: ("10/12", 1.302), 11: ("11/12", 1.357), 12: ("12/12", 1.414),
    }
    label, std_mult = pitch_map.get(rise, ("6/12", 1.118))
    return label, round(multiplier, 4)


def azimuth_to_direction(azimuth: float) -> str:
    directions = [
        (22.5, "North"), (67.5, "Northeast"), (112.5, "East"),
        (157.5, "Southeast"), (202.5, "South"), (247.5, "Southwest"),
        (292.5, "West"), (337.5, "Northwest"), (360, "North"),
    ]
    for threshold, name in directions:
        if azimuth < threshold:
            return name
    return "North"


def fetch_solar_data(lat: float, lng: float, api_key: str) -> dict | None:
    """
    Call Solar API buildingInsights. Returns None if not found or error.
    """
    url = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
    params = {
        "location.latitude": lat,
        "location.longitude": lng,
        "requiredQuality": "LOW",   # LOW = accept any quality, maximizes coverage
        "key": api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def solar_to_analysis(solar_data: dict) -> dict:
    """
    Convert Solar API buildingInsights response into our standard analysis dict.
    """
    sp = solar_data.get("solarPotential", {})

    whole = sp.get("wholeRoofStats", {})
    total_area_sqft = round(whole.get("areaMeters2", 0) * SQM_TO_SQFT)
    footprint_sqft  = round(whole.get("groundAreaMeters2", 0) * SQM_TO_SQFT)

    segments = sp.get("roofSegmentStats", [])

    # Filter out tiny segments (< 5% of total area) — gutters, dormers, noise
    min_area = whole.get("areaMeters2", 0) * 0.05
    significant = [s for s in segments if s.get("stats", {}).get("areaMeters2", 0) >= min_area]
    if not significant:
        significant = segments  # fallback: use all

    # Build roof planes
    roof_planes = []
    for i, seg in enumerate(significant):
        stats       = seg.get("stats", {})
        area_m2     = stats.get("areaMeters2", 0)
        ground_m2   = stats.get("groundAreaMeters2", 0)
        pitch_deg   = seg.get("pitchDegrees", 14.0)
        azimuth     = seg.get("azimuthDegrees", 180.0)

        pitch_label, pitch_mult = pitch_degrees_to_fraction(pitch_deg)
        direction = azimuth_to_direction(azimuth)
        area_sqft = round(area_m2 * SQM_TO_SQFT)

        roof_planes.append({
            "id": f"segment_{i}",
            "description": f"{direction}-facing slope",
            "estimated_area_sqft": area_sqft,
            "pitch": pitch_label,
            "pitch_degrees": round(pitch_deg, 1),
            "pitch_multiplier": pitch_mult,
            "azimuth_degrees": round(azimuth, 1),
        })

    # Weighted average pitch
    total_seg_area = sum(s.get("stats", {}).get("areaMeters2", 0) for s in significant)
    if total_seg_area > 0:
        weighted_pitch = sum(
            s.get("pitchDegrees", 14) * s.get("stats", {}).get("areaMeters2", 0)
            for s in significant
        ) / total_seg_area
    else:
        weighted_pitch = 14.0

    avg_pitch_label, _ = pitch_degrees_to_fraction(weighted_pitch)

    # Determine roof type from segment count and azimuths
    n = len(significant)
    azimuths = [s.get("azimuthDegrees", 0) for s in significant]
    unique_azimuths = len(set(round(a / 45) for a in azimuths))
    if n <= 2:
        roof_type = "gable"
    elif unique_azimuths >= 4 or n >= 4:
        roof_type = "hip"
    else:
        roof_type = "complex"

    # Eave/ridge/hip estimation from footprint geometry
    # For a rectangular footprint: eave = full perimeter, ridge = ~half the long side
    perimeter_ft = round(math.sqrt(footprint_sqft) * 4 * 0.9)  # rough square approx
    eave_ft      = round(perimeter_ft * 0.9)
    ridge_ft     = round(math.sqrt(footprint_sqft) * 0.4)
    hip_ft       = round(ridge_ft * 0.6) if roof_type == "hip" else 0
    valley_ft    = round(ridge_ft * 0.2) if n > 2 else 0

    # Build pitch description
    pitch_desc_map = {
        "2/12": "very low (2/12)", "3/12": "low (3/12)", "4/12": "low (4/12)",
        "5/12": "low-medium (5/12)", "6/12": "medium (6/12)", "7/12": "medium (7/12)",
        "8/12": "medium-steep (8/12)", "9/12": "steep (9/12)",
        "10/12": "steep (10/12)", "12/12": "very steep (12/12)",
    }
    pitch_desc = pitch_desc_map.get(avg_pitch_label, avg_pitch_label)

    imagery_date = solar_data.get("imageryDate", {})
    date_str = f"{imagery_date.get('year','?')}-{imagery_date.get('month','?'):02d}" if imagery_date else "unknown"

    return {
        "roof_planes": roof_planes,
        "total_footprint_sqft": footprint_sqft,
        "total_roof_area_sqft": total_area_sqft,
        "eave_linear_ft": eave_ft,
        "ridge_linear_ft": ridge_ft,
        "hip_linear_ft": hip_ft,
        "valley_linear_ft": valley_ft,
        "roof_type": roof_type,
        "stories": 1,
        "complexity": "simple" if n <= 2 else "moderate" if n <= 5 else "complex",
        "pitch_description": pitch_desc,
        "confidence": "high",
        "data_source": "Google Solar API",
        "imagery_date": date_str,
        "imagery_quality": solar_data.get("imageryQuality", "unknown"),
        "notes": (
            f"Solar API data: {n} roof segments, avg pitch {weighted_pitch:.1f}° "
            f"({avg_pitch_label}), imagery from {date_str}. "
            f"Quality: {solar_data.get('imageryQuality', 'unknown')}."
        ),
    }
