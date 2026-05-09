"""
app.py — Flask backend for AI Roof Estimator
Pipeline:
  1. Geocode address
  2. Try Google Solar API → real roof segment data with measured pitch
  3. If Solar API unavailable (404/error) → fall back to Claude vision analysis
  4. Calculate materials estimate
  5. Generate PDF
"""

import os
import tempfile
import requests
import uuid
from flask import Flask, request, jsonify, send_file, render_template, session
from dotenv import load_dotenv
import io

load_dotenv()

from solar_api import fetch_solar_data, solar_to_analysis
from roof_analyzer import analyze_roof
from calculator import calculate
from pdf_generator import build_pdf

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "roofquote-hackathon-2026")

GOOGLE_MAPS_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
SATELLITE_ZOOM_CLOSE = 20
SATELLITE_ZOOM_WIDE  = 18
IMAGE_SIZE = "640x640"

_quote_store = {}


def geocode_address(address: str) -> tuple[float, float]:
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    resp = requests.get(url, params={"address": address, "key": GOOGLE_MAPS_KEY}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data["status"] != "OK":
        raise ValueError(f"Geocoding failed: {data['status']}")
    loc = data["results"][0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def fetch_satellite_image(lat: float, lng: float, zoom: int) -> bytes:
    url = "https://maps.googleapis.com/maps/api/staticmap"
    params = {
        "center": f"{lat},{lng}",
        "zoom": zoom,
        "size": IMAGE_SIZE,
        "scale": 2,
        "format": "png32",
        "maptype": "satellite",
        "key": GOOGLE_MAPS_KEY,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.content


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/quote", methods=["POST"])
def quote():
    data = request.get_json()
    address = (data or {}).get("address", "").strip()

    if not address:
        return jsonify({"error": "Address is required"}), 400
    if not GOOGLE_MAPS_KEY:
        return jsonify({"error": "Google Maps API key not configured"}), 500

    try:
        lat, lng = geocode_address(address)

        # Always fetch satellite image for PDF page 2
        image_close = fetch_satellite_image(lat, lng, SATELLITE_ZOOM_CLOSE)

        # ── Step 1: Try Solar API ─────────────────────────────────────────
        solar_data = fetch_solar_data(lat, lng, GOOGLE_MAPS_KEY)

        if solar_data:
            analysis = solar_to_analysis(solar_data)
            app.logger.info(f"Solar API success for {address}")
        else:
            # ── Step 2: Fall back to Claude vision ────────────────────────
            app.logger.info(f"Solar API unavailable for {address}, falling back to vision")
            image_wide = fetch_satellite_image(lat, lng, SATELLITE_ZOOM_WIDE)
            analysis = analyze_roof(
                image_close, image_wide,
                SATELLITE_ZOOM_CLOSE, SATELLITE_ZOOM_WIDE,
                lat, address
            )

        estimate = calculate(analysis)

        # Save close image for PDF
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        tmp.write(image_close)
        tmp.close()

        token = str(uuid.uuid4())
        _quote_store[token] = {
            "address": address,
            "analysis": analysis,
            "estimate": estimate,
            "image_path": tmp.name,
            "lat": lat,
            "zoom": SATELLITE_ZOOM_CLOSE,
        }
        session["quote_token"] = token

        return jsonify({
            "success": True,
            "address": address,
            "analysis": analysis,
            "estimate": estimate,
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except requests.RequestException as e:
        return jsonify({"error": f"Maps API error: {str(e)}"}), 502
    except Exception as e:
        app.logger.exception("Quote generation failed")
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500


@app.route("/download")
def download():
    token = session.get("quote_token")
    quote_data = _quote_store.get(token) if token else None
    if not quote_data:
        return "No quote generated yet.", 404

    image_bytes = None
    image_path = quote_data.get("image_path")
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            image_bytes = f.read()

    pdf_bytes = build_pdf(
        address=quote_data["address"],
        analysis=quote_data["analysis"],
        estimate=quote_data["estimate"],
        image_bytes=image_bytes,
        zoom=quote_data.get("zoom", 20),
        lat=quote_data.get("lat", 40.0),
    )

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="roofing-estimate.pdf",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
