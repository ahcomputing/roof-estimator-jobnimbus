import anthropic
import base64
import json
import math
import re

client = anthropic.Anthropic()

SANITY_MIN_SQFT = 600
SANITY_MAX_SQFT = 4000  # tightened from 6000 — catches Humble TX overcount

# Climate zone pitch floors by state and latitude
# Returns (min_pitch_str, min_multiplier, climate_note)
def get_climate_pitch_floor(state: str, lat: float) -> tuple[str, float, str]:
    state = state.upper().strip()
    # Hot/flat climate states — very low pitch common
    if state in ("FL", "AZ", "NM", "HI", "PR"):
        return "4/12", 1.054, f"Florida/desert climate at lat {lat:.1f} — low pitch is standard"
    # Southern TX / Gulf Coast
    if state in ("TX", "LA", "MS", "AL", "GA", "SC") and lat < 30.5:
        return "4/12", 1.054, f"Gulf Coast region (lat {lat:.1f}) — low pitch common"
    # Mid-South and Central
    if state in ("TX", "OK", "AR", "TN", "NC", "VA", "MD", "DE", "KY"):
        return "5/12", 1.083, f"Mid-South region — moderate pitch typical"
    if state in ("CA", "OR", "WA", "NV", "UT", "CO", "ID", "MT", "WY"):
        return "5/12", 1.083, f"Western US — variable pitch, defaulting moderate"
    # Midwest / Great Lakes
    if state in ("IL", "IN", "OH", "MI", "WI", "MN", "IA", "MO", "KS", "NE", "SD", "ND"):
        return "6/12", 1.118, f"Midwest (lat {lat:.1f}) — moderate to steep pitch for snow load"
    # Northeast / New England
    if state in ("NY", "PA", "NJ", "CT", "RI", "MA", "VT", "NH", "ME", "WV"):
        return "6/12", 1.118, f"Northeast — moderate to steep pitch for snow/ice load"
    # Default
    return "4/12", 1.054, f"Default conservative pitch floor"


def extract_state_from_address(address: str) -> str:
    """Best-effort state extraction from address string."""
    # Try two-letter state code before zip or at end
    import re as _re
    # Match ", ST 12345" or ", ST" at end
    m = _re.search(r',\s*([A-Z]{2})\s*(?:\d{5})?(?:\s*[-\d]*)?$', address, _re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Try spelled out common states as fallback
    state_map = {
        "texas": "TX", "florida": "FL", "illinois": "IL", "missouri": "MO",
        "california": "CA", "new york": "NY", "ohio": "OH", "georgia": "GA",
    }
    low = address.lower()
    for name, code in state_map.items():
        if name in low:
            return code
    return ""


ANALYSIS_PROMPT_TEMPLATE = """You are a professional roofing estimator. You are looking at TWO satellite images of the same property:
- IMAGE 1: Close-up view (zoom 20, ~0.06 m/px) — use for detail: roof plane edges, ridges, valleys, eave lines
- IMAGE 2: Context view (zoom 18, ~0.24 m/px) — use for scale: overall structure footprint, shadow angles for pitch

Measure only the PRIMARY RESIDENTIAL STRUCTURE including attached garage. Do NOT include detached sheds, neighboring houses, or yard.

PITCH ESTIMATION — Climate context for this property:
{climate_note}
Minimum pitch floor for this region: {min_pitch}

Pitch rules:
- Only go ABOVE the regional floor if you see CLEAR evidence: dramatic shadow triangles at eave/hip edges
- 8/12+ pitch shows very dark, deep shadows at roof edges — obvious triangular shadows at hip corners
- 6/12 shows moderate shadows
- 4/12 or less shows very little shadow — roof appears nearly flat
- When shadows are ambiguous: stay at the regional floor, do not guess higher

FOOTPRINT SCALE CHECK — use IMAGE 2:
- A standard residential lane is ~12 ft wide
- A typical single-family home footprint is 1,000–2,500 sqft
- Count house widths vs road widths to sanity-check your estimate
- Total roof area for a single family home is almost always 1,200–3,800 sqft

Return ONLY a valid JSON object, no markdown, no explanation:
{{
  "roof_planes": [
    {{
      "id": "main_slope_1",
      "description": "Front-facing main slope",
      "estimated_area_sqft": 850,
      "pitch": "{min_pitch}",
      "pitch_multiplier": {min_mult}
    }}
  ],
  "total_footprint_sqft": 1400,
  "total_roof_area_sqft": 1476,
  "eave_linear_ft": 120,
  "ridge_linear_ft": 40,
  "hip_linear_ft": 0,
  "valley_linear_ft": 20,
  "roof_type": "gable",
  "stories": 1,
  "complexity": "simple",
  "pitch_description": "{pitch_desc}",
  "confidence": "medium",
  "notes": "Brief description of what you see."
}}

Pitch multipliers:
- 4/12: 1.054 | 5/12: 1.083 | 6/12: 1.118 | 7/12: 1.157 | 8/12: 1.202 | 9/12: 1.250 | 10/12: 1.302 | 12/12: 1.414

total_roof_area_sqft = sum of all (plane footprint * pitch_multiplier)
Roof types: gable, hip, flat, gambrel, mansard, shed, complex
Return ONLY the JSON object."""

REQUERY_PROMPT = """Your roof area estimate of {prev_sqft} sqft seems too {direction}.

For reference: a standard residential street lane is ~12 ft wide.
Look at IMAGE 2 and estimate the house width in lane-widths, then multiply to get approximate footprint.
A typical single-family home is 1,000–2,500 sqft footprint → 1,200–3,800 sqft roof area.

Return a corrected JSON estimate using the same format. Be conservative on footprint size."""


def meters_per_pixel(zoom: int, lat: float) -> float:
    return (156543.03392 * math.cos(math.radians(lat))) / (2 ** zoom)


def _build_image_content(image_bytes: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
        },
    }


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse roof analysis JSON: {raw[:300]}")


def analyze_roof(image_close: bytes, image_wide: bytes,
                 zoom_close: int, zoom_wide: int,
                 lat: float, address: str = "") -> dict:
    mpp_close = meters_per_pixel(zoom_close, lat) / 2
    mpp_wide  = meters_per_pixel(zoom_wide,  lat) / 2

    # Get climate-based pitch floor
    state = extract_state_from_address(address)
    min_pitch, min_mult, climate_note = get_climate_pitch_floor(state, lat)
    pitch_desc = {"4/12": "low (4/12)", "5/12": "low-medium (5/12)",
                  "6/12": "medium (6/12)", "7/12": "medium-steep (7/12)"}.get(min_pitch, min_pitch)

    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        climate_note=climate_note,
        min_pitch=min_pitch,
        min_mult=min_mult,
        pitch_desc=pitch_desc,
    )

    scale_info = (
        f"IMAGE 1 scale: {mpp_close:.4f} m/px (zoom {zoom_close}, 1280x1280px)\n"
        f"IMAGE 2 scale: {mpp_wide:.4f} m/px (zoom {zoom_wide}, 1280x1280px)\n"
        f"Latitude: {lat:.4f} | State: {state or 'unknown'}"
    )

    content = [
        _build_image_content(image_close),
        {"type": "text", "text": "IMAGE 1 — Close view (zoom 20)"},
        _build_image_content(image_wide),
        {"type": "text", "text": f"IMAGE 2 — Context view (zoom 18)\n\n{scale_info}\n\n{prompt}"},
    ]

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": content}],
    )

    analysis = _parse_json(message.content[0].text)

    # Sanity check
    total = analysis.get("total_roof_area_sqft", 0)
    if total > SANITY_MAX_SQFT or total < SANITY_MIN_SQFT:
        direction = "high" if total > SANITY_MAX_SQFT else "low"
        retry = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            messages=[
                {"role": "user",      "content": content},
                {"role": "assistant", "content": message.content[0].text},
                {"role": "user",      "content": REQUERY_PROMPT.format(
                    prev_sqft=total, direction=direction)},
            ],
        )
        analysis = _parse_json(retry.content[0].text)
        analysis["sanity_check_triggered"] = True
        analysis["original_sqft"] = total

    return analysis
