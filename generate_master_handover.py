import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def build_pdf():
    pdf_filename = "ATHENA_Complete_Specification_v1.pdf"
    
    # Page-budget conscious margins to pack detailed data into 3 clean pages
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=letter,
        rightMargin=36, leftMargin=36,
        topMargin=36, bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    # Cohesive Modern Corporate Palette (Navy & Cool Slate)
    primary_color = colors.HexColor('#0F1E36')   # Midnight Navy
    secondary_color = colors.HexColor('#1D3557') # Deep Slate Blue
    accent_color = colors.HexColor('#457B9D')    # Steel Blue
    bg_light = colors.HexColor('#F8F9FA')        # Cool Grey Background
    text_dark = colors.HexColor('#212529')       # Charcoal Body Text
    
    # Custom Typographical Hierarchy
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=primary_color,
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-BoldOblique',
        fontSize=10,
        leading=12,
        textColor=accent_color,
        spaceAfter=15
    )
    
    h1_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=secondary_color,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )
    
    h2_style = ParagraphStyle(
        'SubSectionHeader',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=accent_color,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=text_dark,
        spaceAfter=6
    )
    
    bullet_style = ParagraphStyle(
        'BulletCustom',
        parent=body_style,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=4
    )
    
    code_style = ParagraphStyle(
        'CodeStyleCustom',
        parent=styles['Code'],
        fontName='Courier',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#2C3E50'),
        backColor=bg_light,
        borderPadding=6,
        spaceAfter=8
    )

    story = []
    
    # -------------------------------------------------------------------------
    # PAGE 1: SYSTEM OVERVIEW & ARCHITECTURAL SCHEMA
    # -------------------------------------------------------------------------
    story.append(Paragraph("ATHENA SYSTEM SPECIFICATION & HANDOVER BLUEPRINT", title_style))
    story.append(Paragraph("<b>Author/Lead Engineer:</b> Oluwasegun Moses | <b>Target Audience:</b> Secondary AI Agent Engine", subtitle_style))
    
    # Divider Rule
    divider = Table([['']], colWidths=[540])
    divider.setStyle(TableStyle([
        ('LINEBELOW', (0,0), (-1,-1), 1.5, primary_color),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0)
    ]))
    story.append(divider)
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("1. System Identity & Mission Statement", h1_style))
    story.append(Paragraph(
        "ATHENA is a production-grade, modular AI Tactical Football Analytics Engine built to bypass high-variance sports-betting markets. "
        "The system digests raw match feeds, models goal distributions using custom statistical functions, applies live contextual friction vectors "
        "(squad fatigue, weather severity indices, referee card density, and injury tracking), and constructs highly secure, filtered multi-fold accumulator wagers. "
        "The platform's guiding operational principle is <b>zero volatility</b>—aggressively filtering out high-risk scenarios and volatile league segments.",
        body_style
    ))
    
    story.append(Paragraph("2. Permanent Constraints & Hardcoded Safety Filters", h1_style))
    story.append(Paragraph("The incoming AI must enforce these rules across all loader, modeling, and accumulator modules without exception:", body_style))
    story.append(Paragraph("• <b>Zero Volatility League Filtering:</b> All youth selections (under-21, under-19, etc.) must be permanently discarded during API ingestion.", bullet_style))
    story.append(Paragraph("• <b>Absolute Demographics Exclusion:</b> No women's fixtures are permitted in any betting selection or accumulator generation pipeline. This is managed via rigid regex blocks.", bullet_style))
    story.append(Paragraph("• <b>Safe-Haven Volatility Traps:</b> If weather severity or referee card density values cross danger thresholds, the analyst must automatically default to risk-averse markets (e.g., <i>DNB</i> or <i>Win to Nil -> No</i>) instead of raw 1X2 outcomes.", bullet_style))
    
    story.append(Paragraph("3. Core Codebase Layout", h1_style))
    
    schema_data = [
        ["Module Path", "Type", "Operational Responsibility", "Status"],
        ["workers/fotmob_loader.py", "Worker", "Asynchronous API sync-down to SQLite database.", "Active (Stable)"],
        ["services/team_form_service.py", "Service", "Aggregates historical results and form ratios.", "Active (Stable)"],
        ["intelligence/match_analyst.py", "Engine", "Compiles Poisson curves, applies context modifiers.", "Active (Stable)"],
        ["intelligence/accumulator.py", "Engine", "Builds safe multi-fold betting slips from active lines.", "Active (Stable)"],
        ["run_pipeline.sh", "Bash Script", "Sequential driver for worker ingest and engine execution.", "Active (Stable)"],
        ["generate_master_handover.py", "Utility", "Compiles this complete PDF handover system asset.", "Active (Stable)"]
    ]
    
    schema_table = Table(schema_data, colWidths=[140, 50, 270, 80])
    schema_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), primary_color),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 8.5),
        ('BOTTOMPADDING', (0,0), (-1,0), 4),
        ('TOPPADDING', (0,0), (-1,0), 4),
        ('BACKGROUND', (0,1), (-1,-1), bg_light),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#BDC3C7')),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(schema_table)
    
    story.append(PageBreak())
    
    # -------------------------------------------------------------------------
    # PAGE 2: MATHEMATICAL FORMULATIONS & DATABASE INGESTION
    # -------------------------------------------------------------------------
    story.append(Paragraph("4. Deep-Tier Quantitative Mathematics", h1_style))
    story.append(Paragraph(
        "ATHENA operates on a double-Poisson joint probability distribution model to establish expected outcomes. "
        "The model calculates home expected goals ($$\\lambda$$) and away expected goals ($$\\mu$$) using relative offensive and defensive strengths "
        "extracted directly from real historical league and fixture results.",
        body_style
    ))
    
    story.append(Paragraph("<b>The Probability Mass Function (PMF):</b>", h2_style))
    story.append(Paragraph(
        "For any scoreline projection of Home Goals ($$x$$) and Away Goals ($$y$$):",
        body_style
    ))
    story.append(Paragraph(
        "$$P(X=x, Y=y) = \\frac{\\lambda^x e^{-\\lambda}}{x!} \\times \\frac{\\mu^y e^{-\\mu}}{y!}$$",
        code_style
    ))
    
    story.append(Paragraph("<b>Phase 4 Context-Adjustment Integration:</b>", h2_style))
    story.append(Paragraph(
        "Raw expected goals are scaled up or down in real-time before grid calculation using active environmental multipliers:",
        body_style
    ))
    story.append(Paragraph(
        "$$\\lambda_{\\text{adjusted}} = \\lambda_{\\text{base}} \\times (1 + \\Delta_{\\text{motivation}} - \\Delta_{\\text{injury}} - \\Delta_{\\text{fatigue}})$$<br/>"
        "$$\\mu_{\\text{adjusted}} = \\mu_{\\text{base}} \times (1 + \\Delta_{\\text{motivation}} - \\Delta_{\\text{injury}} - \\Delta_{\\text{fatigue}})$$",
        code_style
    ))
    story.append(Paragraph(
        "Where: "
        "$$\\Delta_{\\text{fatigue}}$$ is derived from fixture congestion; "
        "$$\\Delta_{\\text{injury}}$$ is parsed from team injury reports; "
        "$$\\Delta_{\\text{motivation}}$$ represents competitive urgency metrics calculated from league point requirements.",
        body_style
    ))
    
    story.append(Paragraph("5. Live Data Ingest & Database Schema", h1_style))
    story.append(Paragraph(
        "The system's local SQLite database (<code>athena.db</code>) contains historical performance figures and synchronized lines. "
        "The automated worker (<code>workers/fotmob_loader.py</code>) bypasses typical browser detection headers and writes incoming lines using the following SQLite structure:",
        body_style
    ))
    
    story.append(Paragraph(
        "CREATE TABLE IF NOT EXISTS fixtures (<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;fixture_id INTEGER PRIMARY KEY,<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;league TEXT,<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;season INTEGER,<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;home_team TEXT,<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;away_team TEXT,<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;match_date TEXT,<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;status TEXT<br/>"
        ");",
        code_style
    ))
    
    story.append(Paragraph("6. Automated Execution Infrastructure (Cron)", h1_style))
    story.append(Paragraph(
        "The integration worker is tied directly into an Ubuntu system crontab, ensuring hands-free, automated operation. "
        "The cron job executes every morning to grab fresh lines and run analysis snapshots without human intervention:",
        body_style
    ))
    story.append(Paragraph(
        "0 6 * * * /home/thabearr/ATHENA/run_pipeline.sh >> /home/thabearr/ATHENA/logs/pipeline.log 2>&1",
        code_style
    ))
    
    story.append(PageBreak())
    
    # -------------------------------------------------------------------------
    # PAGE 3: COMPLETED WORK & ROADMAP FORWARD (AI PLAN)
    # -------------------------------------------------------------------------
    story.append(Paragraph("7. Comprehensive Implementation Audit", h1_style))
    story.append(Paragraph("<b>Completed Operational Phases:</b>", h2_style))
    story.append(Paragraph("• <b>Phase 1 (Foundation):</b> SQLite schemas, basic prediction layouts, and repository structure mapped cleanly.", bullet_style))
    story.append(Paragraph("• <b>Phase 2 (Real Data Integration):</b> Connected historical team performance scores directly from SQL queries into the predictive loop.", bullet_style))
    story.append(Paragraph("• <b>Phase 3 (Advanced Football Models):</b> Developed and mapped complete $6 \\times 6$ Poisson score grid simulations.", bullet_style))
    story.append(Paragraph("• <b>Phase 4 (Context Intelligence):</b> Fully integrated live referee card density weights, fatigue calculations, weather metrics, and squad injury penalties to dynamically adjust the base Poisson curves.", bullet_style))
    
    story.append(Paragraph("8. The Path Forward: Where We Need to Be", h1_style))
    story.append(Paragraph("To fully complete the ATHENA platform, the incoming AI engineer must prioritize the execution of these remaining developmental phases:", body_style))
    
    story.append(Paragraph("<b>Phase 5: Betting Intelligence & Market Expansion (High Priority)</b>", h2_style))
    story.append(Paragraph(
        "The accumulator engine must expand past basic goal lines. You must program in dynamic, value-based threshold selectors for "
        "Asian Handicap, Draw No Bet (DNB), and Double Chance (DC) selections. Integrate a real-time bookmaker API parser to "
        "automatically compare current market odds against your calculated model probabilities to highlight positive-expected-value (+EV) discrepancies.",
        body_style
    ))
    
    story.append(Paragraph("<b>Phase 6: Learning Engine & Self-Calibration (Medium Priority)</b>", h2_style))
    story.append(Paragraph(
        "Develop an automated post-match results collector that links directly back to your <code>fixtures</code> table. "
        "This script must cross-reference previous predictions with actual outcomes, logging your ROI and win-rate statistics inside a dedicated table. "
        "The engine must automatically run self-calibration scripts to fine-tune the context intelligence multipliers (motivation and fatigue weights) when validation thresholds slip.",
        body_style
    ))
    
    story.append(Paragraph("<b>Phase 7: Production Platform & Dashboard (Low Priority)</b>", h2_style))
    story.append(Paragraph(
        "Wrap the core analytics suite in a lightweight FastAPI application. Expose secure endpoints for the current active betting slips "
        "and build a clean, mobile-responsive dashboard to display the engine's performance metrics, active models, and upcoming slips.",
        body_style
    ))
    
    story.append(Spacer(1, 15))
    story.append(Paragraph("<b>SYSTEM STATUS: CALIBRATED AND READY FOR DEPLOYMENT.</b>", body_style))
    
    doc.build(story)
    print(f"✅ Handover blueprint successfully built: '{pdf_filename}'")

if __name__ == "__main__":
    build_pdf()
