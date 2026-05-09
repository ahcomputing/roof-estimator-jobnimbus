# AI Roof Estimator — JobNimbus AI Builder Day 2026

Address → roof measurements → PDF estimate in seconds.

## Live Demo
https://jobnimbus.ahcomputing.com

## How it works

Built a Flask app that takes any US address and returns a full roofing estimate with PDF output in seconds. Initially used Claude Sonnet vision to analyze Google Maps satellite imagery, experimenting with dual zoom levels (zoom 20 for detail, zoom 18 for context) and regional pitch floors by climate zone — this got accuracy from ~53% average error down to ~16%. However, I discovered Google's Solar API (`buildingInsights:findClosest`), which returns directly measured pitch in degrees and area in square meters per roof segment from Google's own ML-enhanced aerial imagery. Rather than asking Claude to guess pitch from shadows when Google had already done the hard work with better data, I made Solar API the primary measurement source and kept Claude vision as a fallback for addresses outside Solar coverage. Final result: 2.1% average error across 5 calibration properties vs commercial reference measurements.

## Stack
- **Google Solar API** — primary measurement source (measured pitchDegrees + areaMeters2 per segment)
- **Claude Sonnet vision** — fallback when Solar API unavailable
- **Google Maps Static API** — satellite imagery (zoom 20 close + zoom 18 context)
- **Google Geocoding API** — address → lat/lng
- **Flask** — backend
- **ReportLab** — PDF generation

## Accuracy
Average error: 2.1% across 5 calibration properties vs commercial reference measurements

| Address | Reference | Our Result | Error |
|---|---|---|---|
| 21106 Kenswick Meadows Ct, Humble TX | 2,393 sqft | 2,389 sqft | -0.2% |
| 5914 Copper Lilly Lane, Spring TX | 4,344 sqft | 4,369 sqft | +0.6% |
| 122 NW 13th Ave, Cape Coral FL | 2,884 sqft | 2,924 sqft | +1.4% |
| 14132 Trenton Ave, Orland Park IL | 2,963 sqft | 3,170 sqft | +7.0% |
| 835 S Cobble Creek, Nixa MO | 3,044 sqft | 3,070 sqft | +0.9% |

## PDF Output
Two-page PDF per quote:
- **Page 1** — customer-facing estimate with line items, materials, labor, tax
- **Page 2** — satellite image, roof plane breakdown, full calculation detail, data source

## Run locally
\```bash
cp .env.example .env  # add your API keys
pip install -r requirements.txt
python app.py
\```

## API Keys needed
- `GOOGLE_MAPS_API_KEY` — enables Maps Static, Geocoding, and Solar APIs
- `ANTHROPIC_API_KEY` — Claude Sonnet vision fallback
