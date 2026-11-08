"""PDF valuation report a lender can file with the loan application."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def inr(value) -> str:
    if value is None:
        return "-"
    value = round(float(value))
    sign = "-" if value < 0 else ""
    digits = str(abs(value))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    return f"Rs {sign}{digits}"


def _table(rows, widths):
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ede9fe")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def build_report(r: dict) -> bytes:
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=8, leading=10, textColor=colors.HexColor("#475569"))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm,
                            title="AURA valuation report")
    p = r["property_input"]
    conf = r["confidence"]
    ds = r["decision_support"]
    story = [
        Paragraph("AURA - Digital Property Valuation Report", styles["Title"]),
        Paragraph(f"Valuation ID {r.get('valuation_id')} &middot; {r.get('valued_at', '')[:19]} UTC "
                  f"&middot; model {r['model_version']}", small),
        Paragraph("PROTOTYPE - trained on synthetic demo data. Not a certified valuation.", small),
        Spacer(1, 4 * mm),
        _table([
            ["Property", "Value"],
            ["Location", f"{p['locality']}, {p['city']}"],
            ["Type", p["property_type"]],
            ["Built-up area", f"{p['area_sqft']:g} sq.ft."],
            ["Bedrooms / bathrooms", f"{p['bedrooms']} / {p['bathrooms']}"],
            ["Age / floor", f"{p['property_age_years']} yrs / floor {p['floor_number']}"],
            ["Furnishing", p["furnishing_status"]],
        ], [55 * mm, 120 * mm]),
        Spacer(1, 3 * mm),
        _table([
            ["Valuation", ""],
            ["Estimated market value", inr(r["estimated_value_inr"])],
            [f"{conf['interval_level_pct']}% range", f"{inr(r['low_estimate_inr'])} - {inr(r['high_estimate_inr'])}"],
            ["Rate per sq.ft.", inr(r["rate_per_sqft_inr"])],
            ["Confidence", f"{conf['label']} ({conf['score']}/100, +/-{conf['relative_half_width_pct']}%)"],
            ["Route", ds["routing_label"]],
        ], [55 * mm, 120 * mm]),
        Spacer(1, 3 * mm),
        Paragraph("Main factors behind the value (SHAP)", styles["Heading3"]),
        _table(
            [["Factor", "Input", "Effect", "Source"]]
            + [[f["label"], str(f["value"]), f"{f['impact_pct']:+.1f}%", f["source"]]
               for f in r["explainability"]["top_factors"]],
            [50 * mm, 45 * mm, 25 * mm, 55 * mm],
        ),
    ]
    if ds.get("lending"):
        lend = ds["lending"]
        story += [
            Spacer(1, 3 * mm),
            Paragraph("Lending check", styles["Heading3"]),
            _table([
                ["Item", "Value"],
                ["Loan requested", inr(lend["loan_amount_inr"])],
                ["Collateral value (conservative)", inr(lend["collateral_value_inr"])],
                ["LTV / cap", f"{lend['ltv_pct']}% / {lend['max_ltv_pct']}% ({lend['ltv_policy']})"],
                ["Max eligible loan", inr(lend["max_eligible_loan_inr"])],
                ["Risk band", lend["risk_band"]],
            ], [55 * mm, 120 * mm]),
        ]
    comps = r["comparables"]
    story += [
        Spacer(1, 3 * mm),
        Paragraph("Comparable evidence", styles["Heading3"]),
        Paragraph(
            f"{comps['comparable_count']} comparable(s), {comps['verified_comparable_count']} verified. "
            f"Comparable estimate {inr(comps['comparable_estimate_inr'])}"
            + (f" (model gap {comps['model_vs_comparable_gap_pct']:+.1f}%)."
               if comps["model_vs_comparable_gap_pct"] is not None else "."),
            styles["BodyText"],
        ),
        Spacer(1, 4 * mm),
        Paragraph("Routing reasons: " + " ".join(ds["reasons"]), styles["BodyText"]),
        Spacer(1, 4 * mm),
        Paragraph(r["disclaimer"], small),
        Paragraph(conf["method"], small),
    ]
    doc.build(story)
    return buf.getvalue()
