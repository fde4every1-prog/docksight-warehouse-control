"""Generate the Repo3 DockSight solution deck from Prompt_Deck_22Sep.txt."""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


OUT = Path(__file__).resolve().parent / "DockSight_Repo3_Solution_Deck.pptx"

# Prompt_Deck_22Sep corporate theme.
CHARCOAL = RGBColor(0x1A, 0x1A, 0x24)
DARK_GRAY = RGBColor(0x2E, 0x2E, 0x38)
YELLOW = RGBColor(0xFF, 0xE6, 0x00)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT_GRAY = RGBColor(0xC4, 0xC4, 0xCD)
MEDIUM_GRAY = RGBColor(0x74, 0x74, 0x80)
OFF_WHITE = RGBColor(0xF6, 0xF6, 0xFA)
INK = RGBColor(0x1A, 0x1A, 0x24)
LINE = RGBColor(0xDE, 0xDE, 0xE5)
GREEN = RGBColor(0x4C, 0xAF, 0x50)
AMBER = RGBColor(0xFF, 0xB3, 0x00)
RED = RGBColor(0xD3, 0x2F, 0x2F)


def set_run(run, text, size=14, bold=False, color=INK):
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Aptos"


def fill(shape, color):
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def send_back(slide, shape):
    tree = slide.shapes._spTree
    element = shape._element
    tree.remove(element)
    tree.insert(2, element)


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def base(slide, number, section, dark=False):
    bg_color = CHARCOAL if dark else WHITE
    fg = WHITE if dark else INK
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5)
    )
    fill(bg, bg_color)
    send_back(slide, bg)

    accent = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(0.08)
    )
    fill(accent, YELLOW)

    footer = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        0,
        Inches(7.17),
        Inches(13.333),
        Inches(0.33),
    )
    fill(footer, DARK_GRAY if dark else OFF_WHITE)
    tb = slide.shapes.add_textbox(
        Inches(0.34), Inches(7.21), Inches(11.8), Inches(0.18)
    )
    r = tb.text_frame.paragraphs[0].add_run()
    set_run(
        r,
        f"DockSight · Repo3 / V3 Solution Deck · {section}",
        9,
        False,
        LIGHT_GRAY if dark else MEDIUM_GRAY,
    )
    nb = slide.shapes.add_textbox(
        Inches(12.30), Inches(7.19), Inches(0.60), Inches(0.22)
    )
    p = nb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    r = p.add_run()
    set_run(r, f"{number:02d}", 10, True, YELLOW if dark else INK)
    return fg


def heading(slide, kicker, title, subtitle=None, dark=False):
    fg = WHITE if dark else INK
    kb = slide.shapes.add_textbox(
        Inches(0.48), Inches(0.21), Inches(11.9), Inches(0.26)
    )
    r = kb.text_frame.paragraphs[0].add_run()
    set_run(r, kicker.upper(), 10, True, YELLOW if dark else MEDIUM_GRAY)

    tb = slide.shapes.add_textbox(
        Inches(0.48), Inches(0.51), Inches(12.25), Inches(0.58)
    )
    tb.text_frame.word_wrap = True
    r = tb.text_frame.paragraphs[0].add_run()
    set_run(r, title, 27, True, fg)

    if subtitle:
        sb = slide.shapes.add_textbox(
            Inches(0.48), Inches(1.06), Inches(12.15), Inches(0.36)
        )
        sb.text_frame.word_wrap = True
        r = sb.text_frame.paragraphs[0].add_run()
        set_run(r, subtitle, 12, False, LIGHT_GRAY if dark else MEDIUM_GRAY)


def card(
    slide,
    left,
    top,
    width,
    height,
    title,
    body,
    dark=False,
    accent=YELLOW,
    font_size=12,
):
    bg = DARK_GRAY if dark else OFF_WHITE
    fg = WHITE if dark else INK
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(height),
    )
    shp.fill.solid()
    shp.fill.fore_color.rgb = bg
    shp.line.color.rgb = DARK_GRAY if dark else LINE

    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(0.07),
        Inches(height),
    )
    fill(bar, accent)

    tb = slide.shapes.add_textbox(
        Inches(left + 0.20),
        Inches(top + 0.13),
        Inches(width - 0.38),
        Inches(height - 0.24),
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    r = tf.paragraphs[0].add_run()
    set_run(r, title, 13, True, accent if dark else INK)
    for line in body:
        p = tf.add_paragraph()
        p.space_before = Pt(6)
        r = p.add_run()
        set_run(r, line, font_size, False, fg)


def tile(slide, left, top, width, value, label, dark=False, accent=YELLOW):
    bg = DARK_GRAY if dark else OFF_WHITE
    fg = WHITE if dark else INK
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(1.04),
    )
    shp.fill.solid()
    shp.fill.fore_color.rgb = bg
    shp.line.color.rgb = accent
    tb = slide.shapes.add_textbox(
        Inches(left + 0.10),
        Inches(top + 0.10),
        Inches(width - 0.20),
        Inches(0.80),
    )
    tf = tb.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    set_run(r, value, 21, True, accent)
    p = tf.add_paragraph()
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    set_run(r, label, 9, False, LIGHT_GRAY if dark else MEDIUM_GRAY)


def label_box(slide, left, top, width, height, text, dark=False, accent=None):
    bg = DARK_GRAY if dark else OFF_WHITE
    fg = WHITE if dark else INK
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(height),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg
    shape.line.color.rgb = accent or (MEDIUM_GRAY if dark else LINE)
    tb = slide.shapes.add_textbox(
        Inches(left + 0.08),
        Inches(top + 0.08),
        Inches(width - 0.16),
        Inches(height - 0.16),
    )
    tf = tb.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    set_run(r, text, 11, True, fg)
    return shape


def connector(slide, x1, y1, x2, y2, color=MEDIUM_GRAY):
    line = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        Inches(x1),
        Inches(y1),
        Inches(x2),
        Inches(y2),
    )
    line.line.color.rgb = color
    line.line.width = Pt(1.5)
    line.line.end_arrowhead = True
    return line


def hbar(slide, left, top, width, label, value, numerator, denominator):
    lb = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(3.20), Inches(0.42)
    )
    r = lb.text_frame.paragraphs[0].add_run()
    set_run(r, label, 11, True, INK)

    track_left = left + 3.25
    track_width = width - 5.15
    track = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(track_left),
        Inches(top + 0.06),
        Inches(track_width),
        Inches(0.24),
    )
    fill(track, LINE)
    actual = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(track_left),
        Inches(top + 0.06),
        Inches(track_width * value / 100.0),
        Inches(0.24),
    )
    fill(actual, YELLOW)

    vb = slide.shapes.add_textbox(
        Inches(left + width - 1.75),
        Inches(top - 0.03),
        Inches(1.70),
        Inches(0.40),
    )
    p = vb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    r = p.add_run()
    set_run(r, f"{value:.1f}%  ({numerator}/{denominator})", 11, True, INK)


def table(slide, left, top, width, rows, col_widths, row_height=0.55, font_size=10):
    shape = slide.shapes.add_table(
        len(rows),
        len(rows[0]),
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(row_height * len(rows)),
    )
    tbl = shape.table
    for i, col_width in enumerate(col_widths):
        tbl.columns[i].width = Inches(col_width)
    for ri, row in enumerate(rows):
        for ci, value in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.text = ""
            cell.margin_left = Inches(0.09)
            cell.margin_right = Inches(0.09)
            cell.margin_top = Inches(0.04)
            cell.margin_bottom = Inches(0.03)
            cell.fill.solid()
            cell.fill.fore_color.rgb = CHARCOAL if ri == 0 else (
                WHITE if ri % 2 else OFF_WHITE
            )
            p = cell.text_frame.paragraphs[0]
            r = p.add_run()
            set_run(
                r,
                value,
                font_size + 1 if ri == 0 else font_size,
                ri == 0,
                WHITE if ri == 0 else INK,
            )
    return shape


def screenshot_placeholder(slide, left, top, width, height, label, path):
    frame = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(height),
    )
    frame.fill.solid()
    frame.fill.fore_color.rgb = OFF_WHITE
    frame.line.color.rgb = DARK_GRAY
    topbar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(0.30),
    )
    fill(topbar, DARK_GRAY)
    tb = slide.shapes.add_textbox(
        Inches(left + 0.18),
        Inches(top + 0.70),
        Inches(width - 0.36),
        Inches(0.85),
    )
    p = tb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    set_run(r, label, 14, True, INK)
    p = tb.text_frame.add_paragraph()
    p.space_before = Pt(5)
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    set_run(r, path, 9, False, MEDIUM_GRAY)


def build():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # 1. Problem Statement
    s = prs.slides.add_slide(blank)
    base(s, 1, "Problem Statement", dark=True)
    heading(
        s,
        "1 · Problem statement",
        "Warehouse decisions are being made across systems that disagree",
        "The estate already has robots and enterprise platforms; the missing capability is a trustworthy decision and exception layer.",
        dark=True,
    )
    card(
        s,
        0.48,
        1.58,
        4.00,
        4.82,
        "Business context",
        [
            "18 distribution centers and a mixed robot / control-asset estate.",
            "OMS, WMS, WES, Fleet, CMMS, Vision and TMS evolved independently.",
            "Exceptions are resolved through manual comparison and local workarounds.",
        ],
        dark=True,
        accent=YELLOW,
    )
    card(
        s,
        4.68,
        1.58,
        4.00,
        4.82,
        "What breaks",
        [
            "A robot can look available while certification or maintenance blocks it.",
            "Inventory sources report different free quantities.",
            "Order and task states can report completion before work is complete.",
        ],
        dark=True,
        accent=AMBER,
    )
    card(
        s,
        8.88,
        1.58,
        3.96,
        4.82,
        "What the client expects",
        [
            "One defensible order-to-fulfillment view.",
            "Deterministic controls before simulated assignment.",
            "Auditable exceptions and recovery.",
            "A local proof without physical actuation.",
        ],
        dark=True,
        accent=GREEN,
    )
    notes(
        s,
        "Set the context: this is not a greenfield automation problem and not a request to add a chatbot. "
        "The estate has many operating systems, but no single trustworthy decision layer across order, inventory, resource readiness and shipment state. "
        "DockSight V3 addresses the product journey in a local simulator. It does not connect to physical robots or external warehouse write paths.",
    )

    # 2. Current State Landscape
    s = prs.slides.add_slide(blank)
    base(s, 2, "Current State Landscape")
    heading(
        s,
        "2 · Current state landscape",
        "A fragmented operating model with multiple competing records",
        "The current path crosses enterprise, warehouse, fleet, maintenance and carrier systems before an exception can be understood.",
    )
    systems = ["OMS", "WMS", "WES", "Fleet", "CMMS", "Vision", "TMS"]
    x = 0.48
    for i, name in enumerate(systems):
        label_box(s, x, 1.62, 1.45, 0.70, name, accent=YELLOW if i in (1, 3, 6) else None)
        if i < len(systems) - 1:
            connector(s, x + 1.45, 1.97, x + 1.67, 1.97, MEDIUM_GRAY)
        x += 1.75

    counts = [
        ("712", "Robots"),
        ("918", "Control assets"),
        ("9,360", "Inventory rows"),
        ("3,500", "Orders"),
        ("3,500", "Shipments"),
        ("8,732", "Tasks"),
    ]
    x = 0.48
    for value, label in counts:
        tile(s, x, 2.72, 1.86, value, label, accent=YELLOW)
        x += 2.08

    card(
        s,
        0.48,
        4.10,
        4.00,
        2.26,
        "Operating model",
        [
            "Supervisors reconcile several screens before acting.",
            "Source names do not guarantee authority or freshness.",
        ],
        accent=MEDIUM_GRAY,
    )
    card(
        s,
        4.68,
        4.10,
        4.00,
        2.26,
        "Exception load",
        [
            "Inventory, task and readiness contradictions are common—not edge cases.",
            "Manual workarounds are difficult to audit.",
        ],
        accent=AMBER,
    )
    card(
        s,
        8.88,
        4.10,
        3.96,
        2.26,
        "Current boundary",
        [
            "Source snapshot is synthetic and static.",
            "No live telemetry or physical command authority.",
        ],
        accent=RED,
    )
    notes(
        s,
        "Walk left to right through the current process. The counts are from the inherited synthetic source package: "
        "712 robots, 918 control assets, 9,360 inventory rows, 3,500 orders and shipments, and 8,732 tasks. "
        "These show scale, not production volume. The key point is that each system answers only part of the decision.",
    )

    # 3. Current KPI Baseline
    s = prs.slides.add_slide(blank)
    base(s, 3, "Current KPI Baseline")
    heading(
        s,
        "3 · Current KPI baseline",
        "Five indicators quantify why the existing decision path is unreliable",
        "Baseline percentages are computed from the inherited V2 synthetic estate and remain the starting evidence for Repo3.",
    )
    hbar(s, 0.55, 1.70, 12.15, "False-available robots", 28.5, "203", "712")
    hbar(s, 0.55, 2.63, 12.15, "Inventory source disagreement", 78.9, "7,382", "9,360")
    hbar(s, 0.55, 3.56, 12.15, "WES versus Fleet task-state mismatch", 84.2, "7,351", "8,732")
    hbar(s, 0.55, 4.49, 12.15, "OMS versus WMS order-state mismatch", 36.7, "1,283", "3,500")
    hbar(s, 0.55, 5.42, 12.15, "TMS shipments already delayed", 16.7, "586", "3,500")
    card(
        s,
        0.55,
        6.18,
        12.10,
        0.72,
        "Interpretation",
        ["These are diagnostic baselines—not achieved business outcomes and not a claim about a live warehouse."],
        accent=AMBER,
        font_size=10,
    )
    notes(
        s,
        "Define each KPI. False-available means a robot looks usable but has expired certification or blocking maintenance. "
        "Inventory disagreement compares WMS, ERP and vision quantities. Task and order mismatches expose false completion risk. "
        "Delayed shipments are a service indicator. Do not use the 84.2 percent mismatch as an on-time KPI; it is an exception baseline.",
    )

    # 4. Success Criteria & Target Improvements
    s = prs.slides.add_slide(blank)
    base(s, 4, "Success Criteria")
    heading(
        s,
        "4 · Success criteria and target improvements",
        "Targets focus on decision integrity—not invented productivity claims",
        "Targets apply to the V3 simulated treatment path; production impact remains unmeasured.",
    )
    targets = [
        ("0", "Blocked resources assigned", "Known certification, maintenance and claim gates"),
        ("0", "Duplicate order / stock movements", "Idempotency and movement identities"),
        ("0", "Completed stages replayed after restart", "Persisted clocks and transitions"),
        ("100%", "Exceptions with reason and evidence", "Holds, corrections and recovery audit"),
        ("0", "External or physical commands", "Simulation-only hard boundary"),
    ]
    x_positions = [0.48, 2.97, 5.46, 7.95, 10.44]
    for (value, label, detail), x in zip(targets, x_positions):
        tile(s, x, 1.62, 2.18, value, label, accent=YELLOW)
        card(s, x, 2.82, 2.18, 2.12, "Control", [detail], accent=GREEN, font_size=10)

    card(
        s,
        0.48,
        5.25,
        5.98,
        1.30,
        "User outcome",
        ["A Supervisor can see why work is accepted, held, rejected or recovered without comparing five systems."],
        accent=GREEN,
        font_size=11,
    )
    card(
        s,
        6.70,
        5.25,
        6.14,
        1.30,
        "Measurement boundary",
        ["Lead time, forecast error, resilience and financial value require approved live baselines and targets."],
        accent=AMBER,
        font_size=11,
    )
    notes(
        s,
        "These targets are deliberately bounded to behavior the simulator can verify. We can target zero duplicate movements and zero assignment of known blocked resources. "
        "We cannot honestly target a percentage improvement in live cycle time or ROI because there is no customer production treatment period or cost baseline.",
    )

    # 5. Solution Overview
    s = prs.slides.add_slide(blank)
    base(s, 5, "Solution Overview", dark=True)
    heading(
        s,
        "5 · Solution overview",
        "DockSight V3 connects customer intake, fulfillment control and fleet lifecycle",
        "A local modular monolith creates a durable end-to-end simulation while preserving inherited evidence.",
        dark=True,
    )
    label_box(s, 0.52, 1.66, 2.62, 0.90, "FDE Bazaar\nOrder entry", dark=True, accent=YELLOW)
    connector(s, 3.14, 2.11, 3.75, 2.11, YELLOW)
    label_box(s, 3.75, 1.66, 2.88, 0.90, "Control Tower API\nAccept + reserve", dark=True, accent=YELLOW)
    connector(s, 6.63, 2.11, 7.23, 2.11, YELLOW)
    label_box(s, 7.23, 1.66, 2.74, 0.90, "Task executor\nPick → Stage", dark=True, accent=YELLOW)
    connector(s, 9.97, 2.11, 10.57, 2.11, YELLOW)
    label_box(s, 10.57, 1.66, 2.24, 0.90, "Simulated\nresources", dark=True, accent=YELLOW)

    card(
        s,
        0.52,
        3.08,
        3.86,
        3.18,
        "Customer and order",
        [
            "Multi-SKU intake and service deadline.",
            "Durable outbox and stable request identity.",
            "Separate delivery and fulfillment progress.",
        ],
        dark=True,
        accent=YELLOW,
    )
    card(
        s,
        4.73,
        3.08,
        3.86,
        3.18,
        "Control and intelligence",
        [
            "Conservative free-stock allocation.",
            "Deterministic eligibility and scheduling.",
            "Forecast, replay and exception evidence.",
        ],
        dark=True,
        accent=GREEN,
    )
    card(
        s,
        8.94,
        3.08,
        3.87,
        3.18,
        "People and recovery",
        [
            "Supervisor, Fleet and Admin workspaces.",
            "Repair, approval, verification and audit.",
            "Failure, replacement, charging and recovery.",
        ],
        dark=True,
        accent=AMBER,
    )
    notes(
        s,
        "Explain the business architecture first: Bazaar owns customer intake, the Control Tower owns acceptance and accounting, the executor owns simulated task progression, "
        "and the Fleet Simulator owns lifecycle demonstrations. Supporting capabilities are deterministic control, human exception management and evidence. "
        "The system is one FastAPI process with separate Bazaar and fulfillment SQLite stores.",
    )

    # 6. Solution Flow
    s = prs.slides.add_slide(blank)
    base(s, 6, "Solution Flow")
    heading(
        s,
        "6 · Solution flow",
        "Happy path: request accepted once, work completed once, progress visible throughout",
        "User and system interactions are separated so retries or resource waits do not corrupt inventory accounting.",
    )
    stages = [
        ("1", "Create", "Bazaar user"),
        ("2", "Validate", "Control Tower"),
        ("3", "Reserve", "Inventory ledger"),
        ("4", "Start", "Supervisor"),
        ("5", "Assign", "Scheduler"),
        ("6", "Execute", "Resources"),
        ("7", "Complete", "Progress view"),
    ]
    x = 0.48
    for idx, name, owner in stages:
        circle = s.shapes.add_shape(
            MSO_SHAPE.OVAL, Inches(x), Inches(1.62), Inches(0.62), Inches(0.62)
        )
        fill(circle, YELLOW)
        nb = slide_text = s.shapes.add_textbox(
            Inches(x), Inches(1.75), Inches(0.62), Inches(0.22)
        )
        p = slide_text.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        set_run(r, idx, 11, True, INK)
        label_box(s, x - 0.26, 2.38, 1.15, 0.58, name)
        ob = s.shapes.add_textbox(
            Inches(x - 0.30), Inches(3.04), Inches(1.23), Inches(0.48)
        )
        p = ob.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        set_run(r, owner, 9, False, MEDIUM_GRAY)
        if idx != "7":
            connector(s, x + 0.64, 1.93, x + 1.40, 1.93, MEDIUM_GRAY)
        x += 1.75

    card(
        s,
        0.48,
        3.88,
        3.84,
        2.48,
        "Acceptance boundary",
        [
            "Validate every requested SKU in the selected warehouse.",
            "Debit free source values and credit reservation atomically.",
        ],
        accent=YELLOW,
    )
    card(
        s,
        4.75,
        3.88,
        3.84,
        2.48,
        "Execution boundary",
        [
            "Resource acquisition is separate from stock acceptance.",
            "Persist assignment token, start, due and completion.",
        ],
        accent=GREEN,
    )
    card(
        s,
        9.02,
        3.88,
        3.82,
        2.48,
        "Accounting boundary",
        [
            "Pick releases reservation without another free-stock debit.",
            "Movement identity prevents duplicate effects.",
        ],
        accent=AMBER,
    )
    notes(
        s,
        "Use the seven-stage journey as the demo spine. A customer creates the request, the Control Tower validates and reserves, a Supervisor releases planned work, "
        "the deterministic scheduler assigns suitable resources, and progress is persisted. The three consistency boundaries are the key technical design: acceptance, execution and accounting.",
    )

    # 7. Exception Management & Intelligence Mapping
    s = prs.slides.add_slide(blank)
    base(s, 7, "Exception Management")
    heading(
        s,
        "7 · Exception management and intelligence mapping",
        "Exceptions are explicit decisions; deterministic policy remains the authority",
        "Repo3 uses deterministic and statistical methods. It contains no trained ML model and no runtime AI agent.",
    )
    table(
        s,
        0.48,
        1.52,
        12.36,
        [
            ["Scenario", "Decision / handling", "Method", "Authority"],
            ["Selected-warehouse stock shortage", "Reject whole new Bazaar request; persist failure", "Deterministic", "Control Tower"],
            ["Blocked or incompatible resource", "Hold work; select only eligible unclaimed candidate", "Deterministic", "Scheduler policy"],
            ["Running resource fails", "Pause/kill; replace unfinished stage or wait", "Deterministic", "Fleet workflow"],
            ["Inventory discrepancy", "Surface intervention; correct app-owned evidence with revision", "Deterministic + HITL", "Supervisor"],
            ["Low-stock risk", "Compare current free availability with saved 7-day baseline", "Statistical", "Supervisor"],
        ],
        [2.75, 4.10, 2.40, 3.11],
        row_height=0.65,
        font_size=9,
    )
    card(
        s,
        0.48,
        5.72,
        3.84,
        0.94,
        "Deterministic",
        ["Eligibility · accounting · scheduling · recovery"],
        accent=GREEN,
        font_size=10,
    )
    card(
        s,
        4.75,
        5.72,
        3.84,
        0.94,
        "ML",
        ["None. Forecast is a transparent arithmetic baseline."],
        accent=MEDIUM_GRAY,
        font_size=10,
    )
    card(
        s,
        9.02,
        5.72,
        3.82,
        0.94,
        "AI / agents",
        ["None at runtime. No model or agent touches a write path."],
        accent=RED,
        font_size=10,
    )
    notes(
        s,
        "This slide answers the model question directly. Inventory allocation, eligibility, scheduling, idempotency and recovery are deterministic. "
        "The demand forecast is an arithmetic mean with transparent coverage labels; it is not ML. There is no LLM or autonomous agent in Repo3. "
        "Human workflows handle evidence changes and recovery where authority is needed.",
    )

    # 8. KPI Improvement Demonstration
    s = prs.slides.add_slide(blank)
    base(s, 8, "KPI Improvement")
    heading(
        s,
        "8 · KPI improvement demonstration",
        "V3 improves the treatment of known risks; live business improvement is not yet proven",
        "The comparison below distinguishes estate baseline, V3 control and the evidence available today.",
    )
    table(
        s,
        0.48,
        1.50,
        12.36,
        [
            ["Baseline risk", "Current state", "V3 treatment / target", "Evidence status"],
            ["False-available robot", "203 / 712 look usable", "0 known blocked resources assigned", "Product tests reported"],
            ["Inventory disagreement", "7,382 / 9,360 rows", "Use conservative source minimum; retain correction audit", "Implemented policy"],
            ["Duplicate retry / movement", "No unified durable identity", "0 duplicate order or quantity movement", "Idempotency tests reported"],
            ["False task completion", "7,351 / 8,732 mismatches", "Persist each stage and completion transition", "Lifecycle tests reported"],
            ["Delayed shipment visibility", "586 / 3,500 delayed", "Deadline-prioritized queue and explicit overdue state", "Simulation only"],
        ],
        [2.62, 2.55, 4.27, 2.92],
        row_height=0.68,
        font_size=9,
    )
    card(
        s,
        0.48,
        5.88,
        5.98,
        0.82,
        "Business value supported",
        ["Fewer ambiguous decisions, repeatable accounting and auditable recovery."],
        accent=GREEN,
        font_size=10,
    )
    card(
        s,
        6.70,
        5.88,
        6.14,
        0.82,
        "Business value not yet supported",
        ["No live lead-time gain, cost saving, safety outcome or financial ROI claim."],
        accent=AMBER,
        font_size=10,
    )
    notes(
        s,
        "Do not present the right-hand column as customer production results. These are implemented controls and reported simulation tests. "
        "The solution addresses the mechanisms behind the baseline risks: blocked-resource assignment, ambiguous stock, duplicate effects and false completion. "
        "A live pilot would be needed to measure service, cost or safety improvement.",
    )

    # 9. Moonshot Ideas
    s = prs.slides.add_slide(blank)
    base(s, 9, "Moonshot Ideas", dark=True)
    heading(
        s,
        "9 · Moonshot ideas",
        "Evolve only when evidence and authority justify the next horizon",
        "The roadmap expands trust before autonomy. None of these ideas are part of the current release claim.",
        dark=True,
    )
    card(
        s,
        0.48,
        1.54,
        3.86,
        4.96,
        "Horizon 1 · Harden",
        [
            "Clean-host Windows verification.",
            "Complete API contract and authorization inventory.",
            "Production-grade observability and database migrations.",
            "Forecast backtesting and KPI targets.",
        ],
        dark=True,
        accent=YELLOW,
    )
    card(
        s,
        4.73,
        1.54,
        3.86,
        4.96,
        "Horizon 2 · Shadow pilot",
        [
            "Secure identity and role authorization.",
            "Read-only connectors to approved enterprise sources.",
            "Parallel recommendations without external writes.",
            "Controlled before/after measurement.",
        ],
        dark=True,
        accent=AMBER,
    )
    card(
        s,
        8.94,
        1.54,
        3.87,
        4.96,
        "Horizon 3 · Governed field system",
        [
            "Verified topology, payload and state freshness.",
            "Command identity and outcome protocol.",
            "Independent hazard analysis and safety case.",
            "Optional explain-only AI if a real need is proven.",
        ],
        dark=True,
        accent=GREEN,
    )
    notes(
        s,
        "The future vision is not 'add an agent.' First harden the local product and verify it cleanly. Then consider a secure read-only shadow pilot. "
        "Only a separate field mandate with real interfaces, hazard analysis and independent assurance could justify a command path. "
        "AI remains optional and explain-only unless a future evaluated use case demonstrates value.",
    )

    # 10. Demo
    s = prs.slides.add_slide(blank)
    base(s, 10, "Demo")
    heading(
        s,
        "10 · Demo",
        "One order, one exception, one recovery",
        "Use the live loopback application. The frames below are placeholders for final screenshots.",
    )
    screenshot_placeholder(s, 0.48, 1.48, 3.86, 2.35, "1 · Create order", "/fde-bazaar/")
    screenshot_placeholder(s, 4.73, 1.48, 3.86, 2.35, "2 · Track fulfillment", "/fulfillment")
    screenshot_placeholder(s, 8.98, 1.48, 3.86, 2.35, "3 · Fail and recover", "/robot-lifecycle/")
    stages = [
        ("01", "Create multi-SKU request"),
        ("02", "Show acceptance or shortage"),
        ("03", "Start Pick → Stage flow"),
        ("04", "Fail / replace one assignment"),
        ("05", "Inspect audit and progress"),
    ]
    x = 0.48
    for number, label in stages:
        tile(s, x, 4.30, 2.18, number, label, accent=YELLOW)
        x += 2.49
    card(
        s,
        0.48,
        5.65,
        12.36,
        0.96,
        "Narration boundary",
        ["Every order, task and resource action shown is local simulated state. No physical robot or external warehouse system is affected."],
        accent=RED,
        font_size=10,
    )
    notes(
        s,
        "Run the demo on loopback. Start in Bazaar with a valid multi-SKU request. Show either all-or-nothing rejection for shortage or successful acceptance. "
        "In Core, show the staged progress and accounting. In Fleet Simulator, fail or kill one running assignment and show replacement or waiting, then explicit recovery. "
        "End on audit/progress. Repeat that all actions are simulated local state.",
    )

    # 11. Artefacts Delivered
    s = prs.slides.add_slide(blank)
    base(s, 11, "Artefacts Delivered")
    heading(
        s,
        "11 · Artefacts delivered",
        "A product evidence pack links business requirements, architecture, controls and verification",
        "Repo3 contains the implementation evidence; V3 adds presentation-ready PRD, ADR and assurance views.",
    )
    categories = [
        ("Business", ["V3/PRD.md", "V2_V3_COMPARISON.md", "OM21 matrix"]),
        ("Architecture", ["As-built C4", "6 ADRs", "OpenAPI + runtime map"]),
        ("Data", ["Evidence register", "Inventory ledger policy", "Database manifest"]),
        ("AI / ML", ["No-model decision", "Statistical forecast spec", "No-AI / no-OT ADR"]),
        ("Evaluation", ["Traceability", "Repo3 test suites", "Risk / readiness review"]),
    ]
    x = 0.48
    accents = [YELLOW, GREEN, AMBER, MEDIUM_GRAY, RED]
    for (category, items), accent in zip(categories, accents):
        card(s, x, 1.56, 2.28, 4.48, category, items, accent=accent, font_size=10)
        x += 2.49
    card(
        s,
        0.48,
        6.22,
        12.36,
        0.50,
        "Presentation locator",
        ["V3/ARTIFACTS/07_KEY_ARTIFACT_LOCATOR.md maps C4, ubiquitous language, evals and risk/resilience to their exact repositories."],
        accent=YELLOW,
        font_size=9,
    )
    notes(
        s,
        "Point to the artifact locator if reviewers ask where C4, ubiquitous language, evals or risk evidence live. "
        "The formal original FDE domain model and EVAL-001–022 remain in V2. Repo3 has product regression tests and as-built implementation evidence. "
        "The V3 pack does not invent an AI model; the AI/ML artifact is the explicit decision not to use one plus the transparent statistical forecast.",
    )

    # 12. FDE vs Traditional Design Thinking
    s = prs.slides.add_slide(blank)
    base(s, 12, "FDE vs Traditional")
    heading(
        s,
        "12 · FDE vs traditional design thinking",
        "FDE starts with operational contradictions and executable evidence",
        "The difference is not speed alone; it is how uncertainty, authority and verification shape the product.",
    )
    table(
        s,
        0.48,
        1.50,
        12.36,
        [
            ["Dimension", "Traditional approach", "FDE approach used here"],
            ["Starting point", "Desired future-state features", "Inherited code, data, workflows and failure evidence"],
            ["Data disagreement", "Clean or select one source", "Keep conflict visible; encode conservative treatment"],
            ["Automation", "Add intelligence to the workflow", "Prove deterministic controls before autonomy"],
            ["Users", "Generic personas and process maps", "Named decisions, authority boundaries and exception journeys"],
            ["Validation", "Acceptance tests after build", "Evals, invariants and negative cases before release claims"],
            ["Delivery", "Specification handoff", "Working local product plus evidence, ADRs and explicit gaps"],
        ],
        [2.02, 4.31, 6.03],
        row_height=0.70,
        font_size=10,
    )
    card(
        s,
        0.48,
        6.13,
        12.36,
        0.60,
        "Outcome",
        ["The solution becomes more defensible: uncertainty is explicit, writes are bounded, tests map to risks, and production gaps remain visible."],
        accent=GREEN,
        font_size=9,
    )
    notes(
        s,
        "Avoid criticizing traditional design as inherently weak. The distinction is emphasis. In this engagement, FDE began with the inherited brownfield estate and its contradictions, "
        "then used invariants, negative scenarios and authority boundaries to shape the product. Repo3 is a working simulation tied back to those decisions, not a generic target-state deck.",
    )

    # 13. Delivery Summary
    s = prs.slides.add_slide(blank)
    base(s, 13, "Delivery Summary", dark=True)
    heading(
        s,
        "13 · Delivery summary",
        "DockSight V3 is a complete local product simulation—with a clear path and clear limits",
        "The delivery is ready for stakeholder demonstration, not production or physical control.",
        dark=True,
    )
    summaries = [
        ("UI", "3 applications", "Bazaar · Core · Fleet"),
        ("Models", "Deterministic", "No runtime AI / ML"),
        ("Evaluation", "Product regressions", "Packaged evidence + gaps"),
        ("Architecture", "Local modular monolith", "FastAPI + 2 SQLite stores"),
        ("Analytics", "Forecast + replay", "Transparent, descriptive"),
        ("Business", "Auditable fulfillment", "Value not yet live-proven"),
    ]
    positions = [
        (0.48, 1.60),
        (4.67, 1.60),
        (8.86, 1.60),
        (0.48, 3.57),
        (4.67, 3.57),
        (8.86, 3.57),
    ]
    accents = [YELLOW, GREEN, AMBER, YELLOW, GREEN, AMBER]
    for (name, headline, detail), (x, y), accent in zip(summaries, positions, accents):
        card(s, x, y, 3.94, 1.62, name, [headline, detail], dark=True, accent=accent, font_size=11)

    card(
        s,
        0.48,
        5.56,
        12.32,
        0.98,
        "Executive decision",
        [
            "Accept Repo3/V3 as the updated local baseline; approve clean-host Windows verification; retain shared-network and physical-control NO-GO."
        ],
        dark=True,
        accent=YELLOW,
        font_size=12,
    )
    notes(
        s,
        "Summarize the delivery across UI, models, evaluation, architecture, analytics and business outcome. "
        "The application is materially beyond V2 as a product: three UIs, durable intake, accounting, staged work and recovery. "
        "The decision requested is to accept it as the local Repo3 baseline and complete clean-host verification. "
        "Do not seek approval for shared network use, customer production or physical robot control.",
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    return OUT


if __name__ == "__main__":
    print(build())
