"""Build the synthetic supplier rebate/SLA policy used by the benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#12233F")
BLUE = colors.HexColor("#2266CC")
PALE_BLUE = colors.HexColor("#EAF1FB")
INK = colors.HexColor("#182230")
MUTED = colors.HexColor("#5B6574")
LINE = colors.HexColor("#D7DEE8")


def _header_footer(canvas, doc) -> None:
    canvas.saveState()
    width, height = letter
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 0.52 * inch, width, 0.52 * inch, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.62 * inch, height - 0.33 * inch, "NORTHSTAR PROCUREMENT OPERATIONS")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(
        width - 0.62 * inch, height - 0.33 * inch, "CONTROLLED POLICY | SYNTHETIC"
    )
    canvas.setStrokeColor(LINE)
    canvas.line(0.62 * inch, 0.55 * inch, width - 0.62 * inch, 0.55 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.62 * inch, 0.34 * inch, "Policy SR-SLA-2026.1 | Effective 2026-01-01")
    canvas.drawRightString(width - 0.62 * inch, 0.34 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "PolicyTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=29,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=16,
        )
    )
    styles.add(
        ParagraphStyle(
            "PolicySubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            "H1x",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=NAVY,
            spaceBefore=4,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            "H2x",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=BLUE,
            spaceBefore=10,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            "Bodyx",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.6,
            leading=14,
            textColor=INK,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            "Callout",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=14,
            textColor=NAVY,
            backColor=PALE_BLUE,
            borderColor=colors.HexColor("#ABC4E9"),
            borderWidth=0.7,
            borderPadding=9,
            spaceBefore=7,
            spaceAfter=10,
        )
    )
    return styles


def _rule(rule_id: str, title: str, sentence: str, styles) -> KeepTogether:
    return KeepTogether(
        [
            Paragraph(f"{rule_id} &nbsp; {title}", styles["H2x"]),
            Paragraph(sentence, styles["Bodyx"]),
        ]
    )


def build(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    frame = Frame(0.62 * inch, 0.72 * inch, 7.26 * inch, 9.1 * inch, id="body")
    doc = BaseDocTemplate(
        str(output),
        pagesize=letter,
        leftMargin=0.62 * inch,
        rightMargin=0.62 * inch,
        topMargin=0.76 * inch,
        bottomMargin=0.72 * inch,
        title="Supplier Rebate and SLA Settlement Policy",
        author="FormulaWitness synthetic benchmark",
        subject="Synthetic policy for reproducible formula-repair evaluation",
    )
    doc.addPageTemplates([PageTemplate(id="policy", frames=[frame], onPage=_header_footer)])

    story = [
        Spacer(1, 0.55 * inch),
        Paragraph("Supplier Rebate &amp;<br/>SLA Settlement Policy", styles["PolicyTitle"]),
        Paragraph(
            "Quarterly settlement controls for strategic suppliers", styles["PolicySubtitle"]
        ),
        Spacer(1, 0.18 * inch),
        Table(
            [
                ["Policy ID", "SR-SLA-2026.1"],
                ["Effective", "1 January 2026"],
                ["Owner", "Procurement Operations"],
                ["Currency", "USD"],
                ["Classification", "Synthetic evaluation material"],
            ],
            colWidths=[1.6 * inch, 3.9 * inch],
            hAlign="CENTER",
        ),
        Spacer(1, 0.28 * inch),
        Paragraph(
            "Purpose. This policy defines the controlled calculation and review sequence for quarterly supplier rebates. It is intentionally synthetic and contains no production, customer, or supplier data.",
            styles["Bodyx"],
        ),
        Paragraph(
            "Control objective. A settlement is payable only when eligible spend, tiering, service performance, effective-date proration, caps, rounding, and exclusions are applied in the order stated in this document.",
            styles["Callout"],
        ),
        Paragraph("Document conventions", styles["H2x"]),
        Paragraph(
            "Rates are decimals between zero and one. Monetary amounts are US dollars. Calendar-day counts are inclusive. Boundary words such as below and above are strict unless an inclusive symbol or phrase is used.",
            styles["Bodyx"],
        ),
        PageBreak(),
        Paragraph("1. Eligible spend and rebate tier", styles["H1x"]),
        _rule(
            "RB-101",
            "Eligible spend",
            "Eligible spend equals gross eligible invoices minus returns and credits minus pass-through charges, floored at zero.",
            styles,
        ),
        _rule(
            "RB-102",
            "Ordered tier lookup boundaries",
            "The tier schedule is an ordered range lookup: the rebate rate is 0% when eligible spend is below $100,000; 2% from $100,000 inclusive to below $250,000; 3% from $250,000 inclusive to below $500,000; and 4% at $500,000 or above.",
            styles,
        ),
        _rule(
            "RB-103",
            "Gross rebate",
            "Gross rebate equals eligible spend multiplied by the rebate rate, with no intermediate rounding.",
            styles,
        ),
        Paragraph("Required source fields", styles["H2x"]),
        Table(
            [
                ["Field", "Type / unit", "Control"],
                ["Gross eligible invoices", "USD", "Non-negative"],
                ["Returns and credits", "USD", "Non-negative"],
                ["Pass-through charges", "USD", "Non-negative"],
                ["Period start / end", "Date", "Start must not exceed end"],
                ["Contract start", "Date", "Required"],
            ],
            colWidths=[2.1 * inch, 1.35 * inch, 3.15 * inch],
            repeatRows=1,
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.7),
                    ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F7F9FC")],
                    ),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            ),
        ),
        PageBreak(),
        Paragraph("2. Service and effective-date adjustments", styles["H1x"]),
        Spacer(1, 0.10 * inch),
        _rule(
            "RB-201",
            "Critical incident precedence",
            "One or more critical incidents sets the SLA multiplier to zero unless the critical-incident waiver is Y; this exclusion is evaluated before ordinary SLA penalties.",
            styles,
        ),
        _rule(
            "RB-202",
            "Ordinary SLA penalties",
            "When critical exclusion does not apply, the SLA multiplier is 0.60 if on-time delivery is below 95% and defect rate is above 2%, 0.75 if exactly one of those conditions is true, and 1.00 otherwise.",
            styles,
        ),
        _rule(
            "RB-203",
            "Waiver scope",
            "A critical-incident waiver waives only the critical exclusion; it does not waive an ordinary delivery or quality penalty.",
            styles,
        ),
        _rule(
            "RB-204",
            "Contract-effective active days",
            "Contract-effective active days are inclusive calendar days from the later of the period start and contract start through the period end, floored at zero.",
            styles,
        ),
        _rule(
            "RB-205",
            "Effective-date proration multiplier",
            "The effective-date proration multiplier equals contract-effective active days divided by the inclusive calendar days in the settlement period, capped at 1.00 and floored at zero.",
            styles,
        ),
        Paragraph(
            "Boundary control: 95% on-time delivery is not a delivery breach, and a 2% defect rate is not a quality breach.",
            styles["Callout"],
        ),
        PageBreak(),
        Paragraph("3. Settlement order, cap, and decision", styles["H1x"]),
        _rule(
            "RB-301",
            "Adjustment order",
            "Adjusted rebate equals gross rebate multiplied by the SLA multiplier and then by the effective-date proration multiplier.",
            styles,
        ),
        _rule(
            "RB-302",
            "Cap and rounding",
            "The $20,000 cap is applied after all multipliers, and the resulting final rebate is rounded to two decimal places only after the cap is applied.",
            styles,
        ),
        _rule(
            "RB-303",
            "Decision code",
            "Decision code is EXCLUDED_CRITICAL for an unwaived critical incident, NO_REBATE when final rebate is zero for any other reason, and PAYABLE otherwise.",
            styles,
        ),
        Paragraph("Controlled calculation sequence", styles["H2x"]),
        Table(
            [
                ["Step", "Output", "Rule"],
                ["1", "Eligible spend", "RB-101"],
                ["2", "Contract-effective active days", "RB-204"],
                ["3", "Tier rate", "RB-102"],
                ["4", "Gross rebate", "RB-103"],
                ["5", "SLA multiplier", "RB-201 to RB-203"],
                ["6", "Effective-date proration multiplier", "RB-205"],
                ["7", "Adjusted rebate", "RB-301"],
                ["8", "Final rebate", "RB-302"],
                ["9", "Decision code", "RB-303"],
            ],
            colWidths=[0.65 * inch, 2.35 * inch, 3.6 * inch],
            repeatRows=1,
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.7),
                    ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F7F9FC")],
                    ),
                    ("ALIGN", (0, 1), (0, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            ),
        ),
        Spacer(1, 0.16 * inch),
        Paragraph(
            "Review control. Any formula change requires evidence of the cited rule, a before/after formula diff, counterexamples that distinguish the interpretations, and explicit reviewer approval. The source workbook must remain unchanged.",
            styles["Callout"],
        ),
        Paragraph("4. Unsupported workbook features", styles["H1x"]),
        Paragraph(
            "This controlled calculator accepts ordinary .xlsx workbooks only. Macros, VBA, Power Query, external workbook links, DDE, embedded executable content, volatile functions, and network refreshes are outside this policy and must be rejected rather than approximated.",
            styles["Bodyx"],
        ),
        Paragraph(
            "All examples and supplier identifiers used for testing are synthetic. Production settlement requires the organization-specific approval and retention process in addition to this calculation policy.",
            styles["Bodyx"],
        ),
    ]
    doc.build(story)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.output.resolve())


if __name__ == "__main__":
    main()
