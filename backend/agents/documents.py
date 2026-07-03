"""
California Real Estate Document Auto-Fill — RLA, TDS, SPQ, AVID, NHD, disclosures.
Generates pre-filled PDFs ready for e-signature. Flags anything needing human review.
"""
import json
import os
from datetime import datetime, date
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from agents.brain import think
from config import settings


OUTPUT_DIR = Path("data/documents")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("FormTitle", fontSize=14, fontName="Helvetica-Bold",
                              spaceAfter=12, alignment=TA_CENTER))
    styles.add(ParagraphStyle("SectionHeader", fontSize=11, fontName="Helvetica-Bold",
                              spaceAfter=6, spaceBefore=10))
    styles.add(ParagraphStyle("FieldLabel", fontSize=9, fontName="Helvetica-Bold",
                              spaceAfter=2))
    styles.add(ParagraphStyle("FieldValue", fontSize=10, fontName="Helvetica",
                              spaceAfter=4))
    styles.add(ParagraphStyle("SmallText", fontSize=8, fontName="Helvetica",
                              spaceAfter=3))
    styles.add(ParagraphStyle("Flag", fontSize=9, fontName="Helvetica-Bold",
                              textColor=colors.red, spaceAfter=4))
    styles.add(ParagraphStyle("Disclaimer", fontSize=8, fontName="Helvetica-Oblique",
                              textColor=colors.grey, spaceAfter=3))
    return styles


def _field_row(label: str, value: str, styles) -> list:
    return [
        Paragraph(f"<b>{label}:</b>", styles["FieldLabel"]),
        Paragraph(value or "___________________________", styles["FieldValue"]),
        Spacer(1, 2)
    ]


def _flag(text: str, styles):
    return Paragraph(f"⚠ REVIEW REQUIRED: {text}", styles["Flag"])


async def ai_fill_document(doc_type: str, listing_data: dict, seller_data: dict) -> dict:
    """Use AI to intelligently fill in document fields based on property data."""
    today = date.today().strftime("%B %d, %Y")

    filled = await think(
        f"""You are filling out a California real estate {doc_type} form.

Listing data: {json.dumps(listing_data, indent=2)}
Seller data: {json.dumps(seller_data, indent=2)}
Today's date: {today}
Agent: {settings.agent_name}, DRE #{settings.agent_license}, {settings.broker_name}

Generate pre-filled values for this {doc_type}. Return JSON with all fillable fields.
Mark fields that MUST be completed by the human seller/agent with "REQUIRES_REVIEW: [reason]".

For RLA include: listing_price, commission_rate, listing_period, property_address,
seller_names, agent_name, broker_name, agent_dre, list_date, expiration_date,
mls_submission_days, lockbox_authorized, sign_authorized, showing_instructions.

For TDS include: all known property conditions, known defects, seller disclosures,
items marked as "REQUIRES_REVIEW: Seller must answer personally".

For SPQ include: HOA info, permits, improvements, disputes, any known issues.

Return as flat JSON key:value pairs.""",
        use_haiku=True
    )

    try:
        return json.loads(filled)
    except Exception:
        return {"error": "Could not parse AI fill", "raw": filled[:300]}


def generate_rla_pdf(listing_data: dict, seller_data: dict, ai_fields: dict) -> str:
    """Generate California Residential Listing Agreement PDF."""
    filename = f"RLA_{listing_data.get('address','').replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    filepath = OUTPUT_DIR / filename
    doc = SimpleDocTemplate(str(filepath), pagesize=letter,
                            rightMargin=0.75*inch, leftMargin=0.75*inch,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)
    styles = _styles()
    story = []

    # Header
    story.append(Paragraph("CALIFORNIA RESIDENTIAL LISTING AGREEMENT", styles["FormTitle"]))
    story.append(Paragraph("(EXCLUSIVE AUTHORIZATION AND RIGHT TO SELL)", styles["FormTitle"]))
    story.append(Paragraph("California Association of REALTORS® — C.A.R. Form RLA", styles["SmallText"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "⚠ ARIA-GENERATED DRAFT — This document is auto-filled for review purposes only. "
        "Do NOT use as a legally binding document without review by a licensed California real estate broker "
        "and all parties signing a proper C.A.R. form RLA.",
        styles["Disclaimer"]
    ))
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%"))
    story.append(Spacer(1, 8))

    # Property Info
    story.append(Paragraph("PROPERTY INFORMATION", styles["SectionHeader"]))
    fields = [
        ("Property Address", listing_data.get("address", "") + ", " + listing_data.get("city", "") + ", CA " + listing_data.get("zip_code", "")),
        ("Property Type", listing_data.get("property_type", "Single Family Residence")),
        ("APN (Tax Parcel)", ai_fields.get("apn", "REQUIRES_REVIEW: Pull from county records")),
        ("Listing Price", f"${listing_data.get('list_price', 0):,.0f}"),
        ("Listing Period", f"{ai_fields.get('list_date', datetime.now().strftime('%m/%d/%Y'))} through {ai_fields.get('expiration_date', 'REQUIRES_REVIEW')}"),
    ]
    for label, value in fields:
        if "REQUIRES_REVIEW" in str(value):
            story.append(_flag(f"{label} — {value.replace('REQUIRES_REVIEW: ','')}"))
        else:
            story.append(Paragraph(f"<b>{label}:</b> {value}", styles["FieldValue"]))
    story.append(Spacer(1, 8))

    # Seller Info
    story.append(Paragraph("SELLER INFORMATION", styles["SectionHeader"]))
    story.append(Paragraph(f"<b>Seller(s):</b> {seller_data.get('full_name', 'REQUIRES_REVIEW: Enter seller legal name(s)')}", styles["FieldValue"]))
    story.append(_flag("Seller must sign. Verify all seller names match title exactly."))
    story.append(Spacer(1, 8))

    # Agent/Broker
    story.append(Paragraph("LISTING AGENT & BROKER", styles["SectionHeader"]))
    agent_fields = [
        ("Listing Agent", settings.agent_name),
        ("Agent DRE License #", settings.agent_license or "REQUIRES_REVIEW: Enter DRE #"),
        ("Brokerage", settings.broker_name),
        ("Agent Phone", settings.agent_phone),
        ("Agent Email", settings.agent_email),
    ]
    for label, value in agent_fields:
        story.append(Paragraph(f"<b>{label}:</b> {value}", styles["FieldValue"]))
    story.append(Spacer(1, 8))

    # Commission
    story.append(Paragraph("COMPENSATION", styles["SectionHeader"]))
    commission = ai_fields.get("commission_rate", "2.5% listing + 2.5% buyer's agent = 5% total")
    story.append(Paragraph(f"<b>Commission:</b> {commission}", styles["FieldValue"]))
    story.append(_flag("Commission terms must be agreed upon and signed by seller."))
    story.append(Spacer(1, 8))

    # MLS & Marketing
    story.append(Paragraph("MLS & MARKETING AUTHORIZATION", styles["SectionHeader"]))
    story.append(Paragraph("<b>MLS Submission:</b> Within 3 days of listing (California law)", styles["FieldValue"]))
    story.append(Paragraph(f"<b>Lockbox Authorized:</b> {ai_fields.get('lockbox_authorized', 'YES — Supra/SentriLock')}", styles["FieldValue"]))
    story.append(Paragraph(f"<b>Sign Authorized:</b> {ai_fields.get('sign_authorized', 'YES')}", styles["FieldValue"]))
    story.append(Spacer(1, 8))

    # Signatures
    story.append(Paragraph("SIGNATURES", styles["SectionHeader"]))
    sig_table = Table([
        ["SELLER SIGNATURE", "DATE", "AGENT SIGNATURE", "DATE"],
        ["", "", "", ""],
        ["_____________________", "_______", "_____________________", "_______"],
        ["Seller Printed Name", "", f"{settings.agent_name}", ""],
    ], colWidths=[2.2*inch, 1.2*inch, 2.2*inch, 1.2*inch])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 10))

    # Footer
    story.append(HRFlowable(width="100%"))
    story.append(Paragraph(
        f"Generated by ARIA Real Estate Agent | {settings.agent_name} | {settings.broker_name} | "
        f"{datetime.now().strftime('%m/%d/%Y %H:%M')} | "
        "This is an AI-generated draft. Use official C.A.R. forms for execution.",
        styles["Disclaimer"]
    ))

    doc.build(story)
    return str(filepath)


def generate_tds_pdf(listing_data: dict, ai_fields: dict) -> str:
    """Generate Transfer Disclosure Statement PDF."""
    filename = f"TDS_{listing_data.get('address','').replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    filepath = OUTPUT_DIR / filename
    doc = SimpleDocTemplate(str(filepath), pagesize=letter,
                            rightMargin=0.75*inch, leftMargin=0.75*inch,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)
    styles = _styles()
    story = []

    story.append(Paragraph("REAL ESTATE TRANSFER DISCLOSURE STATEMENT (TDS)", styles["FormTitle"]))
    story.append(Paragraph("Civil Code § 1102 et seq. — Required for all residential 1-4 unit transfers in California",
                            styles["SmallText"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "⚠ ARIA DRAFT — The TDS MUST be completed by the SELLER personally. "
        "ARIA has pre-filled known property data for your review. "
        "Seller must answer all disclosure questions based on their actual knowledge.",
        styles["Disclaimer"]
    ))
    story.append(Spacer(1, 10))

    story.append(Paragraph("PROPERTY & TRANSACTION DETAILS", styles["SectionHeader"]))
    story.append(Paragraph(f"<b>Property Address:</b> {listing_data.get('address','')}, {listing_data.get('city','')}, CA", styles["FieldValue"]))
    story.append(Paragraph(f"<b>Seller(s):</b> {'REQUIRES_REVIEW: Enter seller name'}", styles["FieldValue"]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("SECTION I — AGENT'S INSPECTION DISCLOSURE (To be completed by Listing Agent)", styles["SectionHeader"]))
    story.append(Paragraph("Agent has conducted a visual inspection of the accessible areas of the property.", styles["FieldValue"]))
    story.append(_flag("Agent must complete Section I after physical walk-through of property."))

    story.append(Spacer(1, 8))
    story.append(Paragraph("SECTION II — SELLER'S INFORMATION", styles["SectionHeader"]))
    disclosure_items = [
        ("Roof", "REQUIRES_REVIEW: Seller to disclose age and any known leaks"),
        ("Plumbing", "REQUIRES_REVIEW: Seller to disclose any known issues"),
        ("Electrical", "REQUIRES_REVIEW: Seller to disclose panel, any issues"),
        ("HVAC", "REQUIRES_REVIEW: Seller to disclose age and service history"),
        ("Foundation", "REQUIRES_REVIEW: Any known cracks, settling, or repairs?"),
        ("Water Heater", ai_fields.get("water_heater", "REQUIRES_REVIEW")),
        ("HOA", f"{'Yes — $' + str(listing_data.get('hoa_fee','0')) + '/mo' if listing_data.get('hoa_fee') else 'No HOA'}"),
        ("Permit History", "REQUIRES_REVIEW: Seller to list all improvements and permits pulled"),
        ("Neighborhood Nuisances", "REQUIRES_REVIEW: Any noise, odors, or neighbor disputes?"),
        ("Insurance Claims", "REQUIRES_REVIEW: Any claims filed in last 5 years?"),
    ]
    for item, value in disclosure_items:
        if "REQUIRES_REVIEW" in str(value):
            story.append(_flag(f"{item}: {value.replace('REQUIRES_REVIEW: ','')}"))
        else:
            story.append(Paragraph(f"<b>{item}:</b> {value}", styles["FieldValue"]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("SELLER CERTIFICATION", styles["SectionHeader"]))
    story.append(Paragraph(
        "Seller certifies that the information herein is true and correct to the best of Seller's knowledge "
        "as of the date signed. Seller agrees to promptly notify Buyer in writing if, prior to close of escrow, "
        "Seller becomes aware of any change in the information contained in this document.",
        styles["FieldValue"]
    ))

    sig_table = Table([
        ["SELLER SIGNATURE", "DATE"],
        ["", ""],
        ["_____________________", "_______"],
        ["Seller Printed Name", ""],
    ], colWidths=[3.5*inch, 1.5*inch])
    sig_table.setStyle(TableStyle([
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(sig_table)

    doc.build(story)
    return str(filepath)


def generate_net_sheet_pdf(listing_data: dict, cma_data: dict) -> str:
    """Generate seller net sheet showing estimated proceeds."""
    filename = f"NetSheet_{listing_data.get('address','').replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    filepath = OUTPUT_DIR / filename
    doc = SimpleDocTemplate(str(filepath), pagesize=letter,
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    styles = _styles()
    story = []

    sale_price = cma_data.get("recommended_list_price", listing_data.get("list_price", 0))
    loan_balance = cma_data.get("estimated_loan_balance", 0)
    commission_pct = 0.05
    commission = sale_price * commission_pct
    transfer_tax = sale_price / 1000 * 1.10  # Santa Clara County rate
    title_escrow = 8500
    misc = 2500
    total_costs = commission + transfer_tax + title_escrow + misc + loan_balance
    net = sale_price - total_costs

    story.append(Paragraph(f"ESTIMATED SELLER NET SHEET", styles["FormTitle"]))
    story.append(Paragraph(f"{listing_data.get('address','')}, {listing_data.get('city','')}", styles["FormTitle"]))
    story.append(Paragraph(f"Prepared by {settings.agent_name} | {datetime.now().strftime('%B %d, %Y')}", styles["SmallText"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("⚠ ESTIMATE ONLY — Actual costs may vary. Consult your escrow officer for final figures.", styles["Disclaimer"]))
    story.append(Spacer(1, 10))

    data = [
        ["", "Amount", "Notes"],
        ["ESTIMATED SALE PRICE", f"${sale_price:,.0f}", "Based on CMA — mid-range estimate"],
        ["", "", ""],
        ["COSTS & DEDUCTIONS", "", ""],
        ["Agent Commission (5%)", f"-${commission:,.0f}", "2.5% listing + 2.5% buyer's agent"],
        ["Transfer Tax", f"-${transfer_tax:,.0f}", "Santa Clara County rate ~$1.10/$1,000"],
        ["Title & Escrow Fees", f"-${title_escrow:,.0f}", "Estimate — varies by escrow company"],
        ["Miscellaneous Closing", f"-${misc:,.0f}", "Recording, notary, HOA docs, etc."],
        ["Loan Payoff", f"-${loan_balance:,.0f}" if loan_balance else "TBD", "Contact lender for exact payoff"],
        ["", "", ""],
        ["ESTIMATED NET PROCEEDS", f"${net:,.0f}", "Before taxes — consult CPA"],
    ]

    table = Table(data, colWidths=[3*inch, 1.5*inch, 2.5*inch])
    table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME", (0,3), (-1,3), "Helvetica-Bold"),
        ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("BACKGROUND", (0,-1), (-1,-1), colors.lightblue),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TEXTCOLOR", (1,4), (1,8), colors.red),
        ("TEXTCOLOR", (1,-1), (1,-1), colors.darkblue),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"Want to see what you'd net at different price points? Ask {settings.agent_name} for a "
        "full pricing scenario analysis.",
        styles["FieldValue"]
    ))

    doc.build(story)
    return str(filepath)


async def generate_all_documents(listing_data: dict, seller_data: dict, cma_data: dict = None) -> dict:
    """Generate the full document package for a listing."""
    results = {"documents": [], "flags": [], "errors": []}

    try:
        ai_fields = await ai_fill_document("RLA", listing_data, seller_data)
        rla_path = generate_rla_pdf(listing_data, seller_data, ai_fields)
        results["documents"].append({"type": "RLA", "file": rla_path, "status": "generated"})
    except Exception as e:
        results["errors"].append(f"RLA generation failed: {e}")

    try:
        ai_fields = await ai_fill_document("TDS", listing_data, seller_data)
        tds_path = generate_tds_pdf(listing_data, ai_fields)
        results["documents"].append({"type": "TDS", "file": tds_path, "status": "generated"})
    except Exception as e:
        results["errors"].append(f"TDS generation failed: {e}")

    if cma_data:
        try:
            net_path = generate_net_sheet_pdf(listing_data, cma_data)
            results["documents"].append({"type": "Net Sheet", "file": net_path, "status": "generated"})
        except Exception as e:
            results["errors"].append(f"Net sheet generation failed: {e}")

    results["flags"] = [
        "RLA: Seller must sign official C.A.R. form — this PDF is for review only",
        "TDS: Seller must personally complete and sign all disclosures",
        "SPQ: Seller Property Questionnaire must be completed by seller",
        "AVID: Agent Visual Inspection Disclosure required after property walk-through",
        "NHD: Natural Hazard Disclosure — order from NHD vendor (e.g., JCP, First American)",
        "Lead Paint: Required for homes built before 1978",
    ]

    return results
