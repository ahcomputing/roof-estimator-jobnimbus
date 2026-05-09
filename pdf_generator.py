"""
pdf_generator.py — Professional 2-page roofing estimate PDF.
Page 1: Customer-facing quote with line items.
Page 2: Satellite image + calculation methodology (show your work).
"""

import io
import math
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, Image, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

# Brand colors
NAVY  = colors.HexColor("#1B2A4A")
BLUE  = colors.HexColor("#2563EB")
LBLUE = colors.HexColor("#EFF6FF")
GOLD  = colors.HexColor("#F59E0B")
GRAY  = colors.HexColor("#6B7280")
LGRAY = colors.HexColor("#F3F4F6")
GREEN = colors.HexColor("#10B981")
WHITE = colors.white
BLACK = colors.black

PAGE_W, PAGE_H = letter
MARGIN = 0.65 * inch

SHINGLE_SQFT_PER_BUNDLE = 33.0
UNDERLAYMENT_SQFT_PER_ROLL = 400.0
NAILS_LBS_PER_SQUARE = 2.5
WASTE_FACTOR = 0.12
TAX_RATE = 0.08


def _fmt(n):
    return f"${n:,.2f}"

def _est_number():
    from random import randint
    return f"RE-{datetime.now().strftime('%Y%m')}-{randint(1000,9999)}"

def _mpp(zoom, lat):
    return (156543.03392 * math.cos(math.radians(lat))) / (2 ** zoom)

def _pitch_mult(description: str) -> float:
    low = description.lower()
    if "12/12" in low: return 1.414
    if "10/12" in low: return 1.302
    if "9/12"  in low: return 1.250
    if "8/12"  in low: return 1.202
    if "7/12"  in low: return 1.157
    if "6/12"  in low: return 1.118
    if "5/12"  in low: return 1.083
    if "steep" in low: return 1.302
    if "medium" in low: return 1.118
    if "low"   in low: return 1.054
    return 1.118


def _styles():
    def s(name, **kw):
        return ParagraphStyle(name, **kw)
    return {
        "co_name":   s("CoName",  fontSize=14, textColor=NAVY,  fontName="Helvetica-Bold", leading=18),
        "co_sub":    s("CoSub",   fontSize=9,  textColor=GRAY,  fontName="Helvetica",      leading=13),
        "big_title": s("BigT",    fontSize=28, textColor=NAVY,  fontName="Helvetica-Bold", alignment=TA_RIGHT, leading=32),
        "lbl":       s("Lbl",     fontSize=8,  textColor=BLUE,  fontName="Helvetica-Bold", leading=12),
        "val":       s("Val",     fontSize=10, textColor=BLACK, fontName="Helvetica",      leading=14),
        "bt_lbl":    s("BtLbl",   fontSize=8,  textColor=BLUE,  fontName="Helvetica-Bold", leading=12),
        "bt_name":   s("BtName",  fontSize=12, textColor=NAVY,  fontName="Helvetica-Bold", leading=16),
        "bt_addr":   s("BtAddr",  fontSize=9,  textColor=GRAY,  fontName="Helvetica",      leading=13),
        "th":        s("Th",      fontSize=9,  textColor=WHITE, fontName="Helvetica-Bold", alignment=TA_LEFT),
        "td":        s("Td",      fontSize=9,  textColor=BLACK, fontName="Helvetica",      leading=13),
        "td_r":      s("TdR",     fontSize=9,  textColor=BLACK, fontName="Helvetica",      alignment=TA_RIGHT, leading=13),
        "tot_lbl":   s("TotLbl",  fontSize=10, textColor=NAVY,  fontName="Helvetica-Bold", alignment=TA_RIGHT),
        "tot_big":   s("TotBig",  fontSize=13, textColor=WHITE, fontName="Helvetica-Bold", alignment=TA_RIGHT),
        "footer":    s("Ftr",     fontSize=8,  textColor=GRAY,  fontName="Helvetica",      alignment=TA_CENTER),
        "notes":     s("Notes",   fontSize=8,  textColor=GRAY,  fontName="Helvetica",      leading=12),
        "roof_stat": s("RfStat",  fontSize=8,  textColor=NAVY,  fontName="Helvetica-Bold", leading=12, alignment=TA_CENTER),
        "p2_h1":     s("P2H1",    fontSize=18, textColor=NAVY,  fontName="Helvetica-Bold", leading=22),
        "p2_h2":     s("P2H2",    fontSize=11, textColor=BLUE,  fontName="Helvetica-Bold", leading=15),
        "p2_body":   s("P2Body",  fontSize=9,  textColor=BLACK, fontName="Helvetica",      leading=14),
        "p2_note":   s("P2Note",  fontSize=7,  textColor=GRAY,  fontName="Helvetica-Oblique", leading=11),
        "p2_th":     s("P2Th",    fontSize=8,  textColor=WHITE, fontName="Helvetica-Bold", alignment=TA_CENTER),
        "p2_td":     s("P2Td",    fontSize=8,  textColor=BLACK, fontName="Helvetica",      leading=12, alignment=TA_CENTER),
        "p2_td_l":   s("P2TdL",   fontSize=8,  textColor=BLACK, fontName="Helvetica",      leading=12),
        "p2_formula":s("P2Form",  fontSize=8,  textColor=colors.HexColor("#1e40af"),
                        fontName="Courier-Bold", leading=13, leftIndent=8),
    }


def _page1(story, address, analysis, estimate, st, est_num, today, due_date):
    # Header
    left = [
        Paragraph("AHComputing Roofing Estimates", st["co_name"]),
        Paragraph("Powered by AI Roof Analysis", st["co_sub"]),
        Paragraph("hire.ahcomputing.com", st["co_sub"]),
    ]
    hdr = Table([[left, [Paragraph("ROOFING<br/>ESTIMATE", st["big_title"])]],],
                colWidths=[3.5*inch, 3.5*inch])
    hdr.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(1,0),(1,0),"RIGHT")]))
    story.append(hdr)
    story.append(Spacer(1, 0.15*inch))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE))
    story.append(Spacer(1, 0.15*inch))

    parts = address.split(",")
    street = parts[0].strip()
    city_state = ", ".join(p.strip() for p in parts[1:]) if len(parts) > 1 else ""

    bill = [
        Paragraph("BILL TO", st["bt_lbl"]),
        Paragraph("Property Owner", st["bt_name"]),
        Paragraph(street, st["bt_addr"]),
        Paragraph(city_state, st["bt_addr"]),
    ]
    est_info = Table([
        [Paragraph("Estimate #",    st["lbl"]), Paragraph(est_num, st["val"])],
        [Paragraph("Estimate Date", st["lbl"]), Paragraph(today.strftime("%m-%d-%Y"), st["val"])],
        [Paragraph("Valid Until",   st["lbl"]), Paragraph(due_date.strftime("%m-%d-%Y"), st["val"])],
    ], colWidths=[1.1*inch, 1.7*inch])
    est_info.setStyle(TableStyle([
        ("ALIGN",(0,0),(0,-1),"RIGHT"),
        ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)
    ]))
    bill_row = Table([[bill, est_info]], colWidths=[3.8*inch, 3.2*inch])
    bill_row.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(1,0),(1,0),"RIGHT")]))
    story.append(bill_row)
    story.append(Spacer(1, 0.2*inch))

    summary = estimate.get("summary", {})
    bar_data = [[
        Paragraph(f"Roof Area\n{summary.get('total_roof_area_sqft',0)} sqft", st["roof_stat"]),
        Paragraph(f"Squares\n{summary.get('total_squares',0)}", st["roof_stat"]),
        Paragraph(f"Eave Length\n{summary.get('eave_linear_ft',0)} lnft", st["roof_stat"]),
        Paragraph(f"Ridge/Hip\n{summary.get('ridge_linear_ft',0)} lnft", st["roof_stat"]),
        Paragraph(f"Roof Type\n{analysis.get('roof_type','N/A').title()}", st["roof_stat"]),
        Paragraph(f"Pitch\n{analysis.get('pitch_description','N/A')}", st["roof_stat"]),
        Paragraph(f"AI Confidence\n{analysis.get('confidence','N/A').title()}", st["roof_stat"]),
    ]]
    bar = Table(bar_data, colWidths=[1.0*inch]*7)
    bar.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),LBLUE),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#DBEAFE")),
    ]))
    story.append(bar)
    story.append(Spacer(1, 0.2*inch))

    cw = [0.7*inch, 0.6*inch, 3.5*inch, 1.0*inch, 1.2*inch]
    tdata = [[
        Paragraph("QTY",         st["th"]),
        Paragraph("UNIT",        st["th"]),
        Paragraph("DESCRIPTION", st["th"]),
        Paragraph("UNIT PRICE",  st["th"]),
        Paragraph("AMOUNT",      st["th"]),
    ]]
    for i, item in enumerate(estimate.get("line_items", [])):
        tdata.append([
            Paragraph(str(item["qty"]),         st["td"]),
            Paragraph(item["unit"],             st["td"]),
            Paragraph(item["description"],      st["td"]),
            Paragraph(_fmt(item["unit_price"]), st["td_r"]),
            Paragraph(_fmt(item["amount"]),     st["td_r"]),
        ])
    items_tbl = Table(tdata, colWidths=cw, repeatRows=1)
    row_bgs = [("BACKGROUND",(0,i+1),(-1,i+1), LGRAY if i%2==0 else WHITE)
               for i in range(len(estimate.get("line_items",[])))]
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),BLUE),
        ("TOPPADDING",(0,0),(-1,0),8),("BOTTOMPADDING",(0,0),(-1,0),8),
        ("TOPPADDING",(0,1),(-1,-1),6),("BOTTOMPADDING",(0,1),(-1,-1),6),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("ALIGN",(3,0),(4,-1),"RIGHT"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LINEBELOW",(0,-1),(-1,-1),1.5,BLUE),
        *row_bgs,
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 0.1*inch))

    subtotal = estimate.get("subtotal", 0)
    tax      = estimate.get("tax", 0)
    tax_rate = estimate.get("tax_rate_pct", 8)
    total    = estimate.get("total", 0)
    tot_wht  = ParagraphStyle("TW", fontSize=13, fontName="Helvetica-Bold",
                               textColor=WHITE, alignment=TA_RIGHT)
    totals = Table([
        ["", Paragraph("Subtotal",                   st["tot_lbl"]), Paragraph(_fmt(subtotal), st["tot_lbl"])],
        ["", Paragraph(f"Sales Tax ({tax_rate:.0f}%)",st["tot_lbl"]), Paragraph(_fmt(tax),      st["tot_lbl"])],
        ["", Paragraph("TOTAL (USD)",                tot_wht),       Paragraph(_fmt(total),     tot_wht)],
    ], colWidths=[4.1*inch, 1.5*inch, 1.4*inch])
    totals.setStyle(TableStyle([
        ("ALIGN",(1,0),(2,-1),"RIGHT"),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("RIGHTPADDING",(2,0),(2,-1),8),
        ("LINEABOVE",(1,2),(2,2),1,NAVY),
        ("BACKGROUND",(0,2),(-1,2),NAVY),
    ]))
    story.append(totals)
    story.append(Spacer(1, 0.2*inch))

    notes = analysis.get("notes", "")
    if notes:
        story.append(Paragraph(f"<b>Estimator Notes:</b> {notes}", st["notes"]))
        story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        "<b>Terms &amp; Conditions:</b> This estimate is valid for 30 days. "
        "A 50% deposit is required to begin work. Final invoice may vary +/-10% based on field conditions. "
        "All work performed to local building code. Permit costs not included.",
        st["notes"]
    ))
    story.append(Spacer(1, 0.2*inch))
    story.append(Table([[
        Paragraph("Contractor Signature: _______________________________", st["notes"]),
        Paragraph("Customer Signature: _______________________________",  st["notes"]),
    ]], colWidths=[3.5*inch, 3.5*inch]))

    story.append(Spacer(1, 0.15*inch))
    story.append(HRFlowable(width="100%", thickness=1, color=LGRAY))
    story.append(Spacer(1, 0.05*inch))
    story.append(Paragraph(
        f"Generated by AI Roof Estimator  |  hire.ahcomputing.com  |  {today.strftime('%B %d, %Y')}  |  Page 1 of 2",
        st["footer"]
    ))


def _page2(story, address, analysis, estimate, st, est_num, today,
           image_bytes, zoom, lat):

    story.append(PageBreak())

    # Header
    p2pg = ParagraphStyle("P2Pg", fontSize=9, textColor=GRAY, fontName="Helvetica", alignment=TA_RIGHT)
    p2_hdr = Table([[
        [Paragraph("Roof Analysis &amp; Calculation Detail", st["p2_h1"]),
         Paragraph(f"Estimate {est_num}  |  {address}", st["p2_note"])],
        [Paragraph("Page 2 of 2", p2pg)],
    ]], colWidths=[5.5*inch, 1.5*inch])
    p2_hdr.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"BOTTOM")]))
    story.append(p2_hdr)
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE))
    story.append(Spacer(1, 0.2*inch))

    content_width = PAGE_W - 2 * MARGIN
    mpp = _mpp(zoom, lat) / 2  # scale=2 halves meters-per-pixel

    # Left: satellite image
    if image_bytes:
        img_io = io.BytesIO(image_bytes)
        sat_img = Image(img_io, width=3.0*inch, height=3.0*inch)
        img_col = [
            Paragraph("SATELLITE IMAGE", ParagraphStyle("ImgHdr", fontSize=7,
                       fontName="Helvetica-Bold", textColor=BLUE, leading=10, alignment=TA_CENTER)),
            Spacer(1, 4),
            sat_img,
            Spacer(1, 5),
            Paragraph(f"Zoom {zoom}  |  {mpp:.4f} m/px", st["p2_note"]),
            Paragraph(f"640x640px  |  Google Maps Static API", st["p2_note"]),
            Paragraph(f"Lat {lat:.5f}", st["p2_note"]),
        ]
    else:
        img_col = [Paragraph("(Satellite image unavailable)", st["p2_note"])]

    # Right: roof planes table
    planes = analysis.get("roof_planes", [])
    if planes:
        plane_rows = [[
            Paragraph("PLANE", st["p2_th"]),
            Paragraph("FOOTPRINT", st["p2_th"]),
            Paragraph("PITCH", st["p2_th"]),
            Paragraph("MULT", st["p2_th"]),
            Paragraph("ADJ AREA", st["p2_th"]),
        ]]
        fp_total = 0
        for i, p in enumerate(planes):
            fp = p.get("estimated_area_sqft", 0)
            fp_total += fp
            pitch = p.get("pitch", "6/12")
            mult  = p.get("pitch_multiplier", 1.118)
            adj   = round(fp * mult, 1)
            plane_rows.append([
                Paragraph(p.get("description", f"Plane {i+1}"), st["p2_td_l"]),
                Paragraph(f"{fp:,.0f} sqft", st["p2_td"]),
                Paragraph(pitch, st["p2_td"]),
                Paragraph(f"x{mult}", st["p2_td"]),
                Paragraph(f"{adj:,.1f} sqft", st["p2_td"]),
            ])
        plane_tbl = Table(plane_rows, colWidths=[1.5*inch, 0.85*inch, 0.6*inch, 0.65*inch, 0.85*inch])
        plane_tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),NAVY),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
            ("ALIGN",(1,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            *[("BACKGROUND",(0,i+1),(-1,i+1), LGRAY if i%2==0 else WHITE)
              for i in range(len(planes))],
        ]))
        total_adj = analysis.get("total_roof_area_sqft", 0)
        avg_mult  = round(total_adj / fp_total, 3) if fp_total else 1.0
        planes_col = [
            Paragraph("ROOF PLANE BREAKDOWN", ParagraphStyle("PlHdr", fontSize=7,
                       fontName="Helvetica-Bold", textColor=BLUE, leading=10)),
            Spacer(1, 4),
            plane_tbl,
            Spacer(1, 5),
            Paragraph(
                f"Footprint total: {fp_total:,.0f} sqft  |  Avg multiplier: {avg_mult}  |  "
                f"Adjusted area: {total_adj:,.0f} sqft",
                st["p2_note"]
            ),
        ]
    else:
        planes_col = [Paragraph("No plane detail available.", st["p2_note"])]

    right_w = content_width - 3.2*inch
    two_col = Table([[img_col, planes_col]], colWidths=[3.2*inch, right_w])
    two_col.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(1,0),(1,0),14)]))
    story.append(two_col)
    story.append(Spacer(1, 0.2*inch))
    story.append(HRFlowable(width="100%", thickness=1, color=LGRAY))
    story.append(Spacer(1, 0.15*inch))

    # Calculation table
    story.append(Paragraph("Calculation Detail — Show Your Work", st["p2_h2"]))
    story.append(Spacer(1, 0.1*inch))

    s       = estimate.get("summary", {})
    area    = s.get("total_roof_area_sqft", 0)
    squares = s.get("total_squares", 0)
    eave    = s.get("eave_linear_ft", 0)
    ridge   = s.get("ridge_linear_ft", 0)
    valley  = s.get("valley_linear_ft", 0)
    bundles = s.get("shingle_bundles", 0)
    area_w  = round(area * (1 + WASTE_FACTOR), 1)
    wp      = int(WASTE_FACTOR * 100)

    calcs = [
        ("Adjusted area (waste)",
         f"{area:,.0f} sqft  x  (1 + {wp}% waste)  =  {area_w:,.1f} sqft"),
        ("Shingle bundles",
         f"{area_w:,.1f} sqft  /  {SHINGLE_SQFT_PER_BUNDLE:.0f} sqft/bundle  =  "
         f"{area_w/SHINGLE_SQFT_PER_BUNDLE:.1f}  ->  {bundles} bundles (ceiling)"),
        ("Underlayment rolls",
         f"{area_w:,.1f} sqft  /  {UNDERLAYMENT_SQFT_PER_ROLL:.0f} sqft/roll  =  "
         f"{area_w/UNDERLAYMENT_SQFT_PER_ROLL:.2f}  ->  {math.ceil(area_w/UNDERLAYMENT_SQFT_PER_ROLL)} rolls (ceiling)"),
        ("Ice & water shield",
         f"Eave {eave:.0f} lnft  x  3 ft protection band  =  {eave*3:.0f} sqft"),
        ("Drip edge",
         f"Eave perimeter  =  {eave:.0f} lnft"),
        ("Ridge cap",
         f"Ridge + hips  =  {ridge:.0f} lnft"),
        ("Valley flashing",
         f"Valley length  =  {valley:.0f} lnft"),
        ("Roofing nails",
         f"{squares:.1f} squares  x  {NAILS_LBS_PER_SQUARE} lbs/sq  =  "
         f"{squares*NAILS_LBS_PER_SQUARE:.1f}  ->  {math.ceil(squares*NAILS_LBS_PER_SQUARE)} lbs (ceiling)"),
        ("Labor (squares)",
         f"{area:,.0f} sqft  /  100  =  {squares:.1f} squares"),
        ("Sales tax",
         f"Subtotal {_fmt(estimate.get('subtotal',0))}  x  {int(TAX_RATE*100)}%  =  {_fmt(estimate.get('tax',0))}"),
    ]

    calc_rows = [[Paragraph("ITEM", st["p2_th"]), Paragraph("FORMULA", st["p2_th"])]]
    for i, (label, formula) in enumerate(calcs):
        calc_rows.append([
            Paragraph(label, st["p2_td_l"]),
            Paragraph(formula, st["p2_formula"]),
        ])
    calc_tbl = Table(calc_rows, colWidths=[1.7*inch, content_width - 1.7*inch], repeatRows=1)
    calc_tbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),NAVY),
        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LINEBELOW",(0,-1),(-1,-1),1,BLUE),
        *[("BACKGROUND",(0,i+1),(-1,i+1), LGRAY if i%2==0 else WHITE)
          for i in range(len(calcs))],
    ]))
    story.append(calc_tbl)
    story.append(Spacer(1, 0.15*inch))

    # AI method note
    pitch_mult = _pitch_mult(analysis.get("pitch_description", "medium"))
    footprint  = analysis.get("total_footprint_sqft", round(area / pitch_mult, 0))
    n_planes   = len(analysis.get("roof_planes", []))
    data_source = analysis.get("data_source", "Claude Vision")
    is_solar = data_source == "Google Solar API"
    imagery_date = analysis.get("imagery_date", "unknown")
    imagery_quality = analysis.get("imagery_quality", "unknown")

    if is_solar:
        method_title = "Google Solar API — Measurement Method"
        method_body = (
            f"Roof measurements provided by the Google Solar API (buildingInsights endpoint). "
            f"Google's Solar API uses high-resolution aerial imagery and machine learning to map "
            f"individual roof segments with measured pitch, area, and orientation. "
            f"Data covers {n_planes} roof segment(s). Imagery date: {imagery_date}. "
            f"Imagery quality: {imagery_quality}. "
            f"Total roof area {area:,.0f} sqft and pitch data are directly measured values, "
            f"not estimates — no shadow inference required."
        )
        disclaimer = (
            "Note: Solar API data reflects the most recent available aerial imagery for this property. "
            "Linear measurements (eave, ridge, valley) are estimated from segment geometry. "
            "A licensed contractor should verify quantities during physical inspection."
        )
    else:
        method_title = "AI Vision Analysis Method"
        method_body = (
            f"The satellite image was submitted to Claude Sonnet via the Anthropic Vision API. "
            f"Claude identified {n_planes} roof plane(s), estimated eave / ridge / valley linear footage "
            f"from pixel geometry, and inferred pitch from shadow angles and plane proportions. "
            f"Scale was derived from zoom level {zoom} at lat {lat:.4f} using the Web Mercator formula: "
            f"m/px = (156,543 x cos(lat)) / 2^zoom = {mpp:.4f} m/px. "
            f"Footprint ({footprint:,.0f} sqft) was multiplied by pitch factor ({pitch_mult}) "
            f"to yield sloped surface area ({area:,.0f} sqft)."
        )
        disclaimer = (
            "Disclaimer: AI measurements are estimates. A licensed contractor should verify quantities "
            "during physical inspection. Typical accuracy: +/-10-15% for standard residential roofs."
        )

    story.append(KeepTogether([
        HRFlowable(width="100%", thickness=1, color=LGRAY),
        Spacer(1, 0.1*inch),
        Paragraph(method_title, st["p2_h2"]),
        Spacer(1, 0.06*inch),
        Paragraph(method_body, st["p2_body"]),
        Spacer(1, 0.07*inch),
        Paragraph(disclaimer, st["p2_note"]),
    ]))

    story.append(Spacer(1, 0.15*inch))
    story.append(HRFlowable(width="100%", thickness=1, color=LGRAY))
    story.append(Spacer(1, 0.05*inch))
    story.append(Paragraph(
        f"Generated by AI Roof Estimator  |  hire.ahcomputing.com  |  {today.strftime('%B %d, %Y')}  |  Page 2 of 2",
        st["footer"]
    ))


def build_pdf(address: str, analysis: dict, estimate: dict,
              image_bytes: bytes = None, zoom: int = 19, lat: float = 40.0) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.5*inch, bottomMargin=0.75*inch,
    )
    st       = _styles()
    story    = []
    est_num  = _est_number()
    today    = datetime.now()
    due_date = today + timedelta(days=14)

    _page1(story, address, analysis, estimate, st, est_num, today, due_date)
    _page2(story, address, analysis, estimate, st, est_num, today,
           image_bytes, zoom, lat)

    doc.build(story)
    return buffer.getvalue()
