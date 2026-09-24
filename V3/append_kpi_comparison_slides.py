"""Append the five-KPI improvement slides to the DockSight Repo3 solution deck.

Run AFTER generate_repo3_solution_deck.py, which rebuilds slides 1-13.
This module appends slides 14-16 and never edits slides 1-13.

    python generate_repo3_solution_deck.py
    python append_kpi_comparison_slides.py

Five key KPIs (per Prompt_Deck_22Sep.txt, slide 8):
    order cycle time, on-time carrier departure, false availability rate,
    inventory accuracy, human interventions per 1,000 robot tasks

Sources:
    kpi_summary.md            -> current state (orders.csv / shipments.csv)
    synthetic_kpis_summary.md -> V3 replay dataset (synthetic_*_7000.csv)
    V3 invariants V3-I5 / V3-I8 / V3-I11 -> control evidence
"""

from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from generate_repo3_solution_deck import (
    AMBER,
    CHARCOAL,
    GREEN,
    INK,
    LIGHT_GRAY,
    LINE,
    MEDIUM_GRAY,
    OFF_WHITE,
    RED,
    WHITE,
    YELLOW,
    base,
    card,
    fill,
    heading,
    notes,
    set_run,
    table,
    tile,
)

HERE = Path(__file__).resolve().parent
DECK = HERE / "DockSight_Repo3_Solution_Deck.pptx"

# Verified against the raw archive by verify_kpi_baseline.py:
#   1,567 matched order/shipment pairs of 3,500 shipments (1,933 never departed)
#   mean cycle time 11.30 h; on-time 344 / 1,567 = 21.95%
CYCLE_OLD, CYCLE_NEW = 11.30, 8.00
ONTIME_OLD, ONTIME_NEW = 21.95, 62.20
CYCLE_DELTA = CYCLE_NEW - CYCLE_OLD
CYCLE_PCT = 100.0 * CYCLE_DELTA / CYCLE_OLD
ONTIME_DELTA = ONTIME_NEW - ONTIME_OLD
ONTIME_RATIO = ONTIME_NEW / ONTIME_OLD


# --------------------------------------------------------------------------
# shared pieces
# --------------------------------------------------------------------------
def footnote(slide, text, dark=False):
    tb = slide.shapes.add_textbox(
        Inches(0.48), Inches(6.74), Inches(12.35), Inches(0.36)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    r = tf.paragraphs[0].add_run()
    set_run(r, text, 8.5, False, LIGHT_GRAY if dark else MEDIUM_GRAY)


def band(slide, top, text, accent, dark=False):
    """Section divider inside a slide."""
    strip = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.48), Inches(top), Inches(0.16), Inches(0.24)
    )
    fill(strip, accent)
    tb = slide.shapes.add_textbox(
        Inches(0.72), Inches(top - 0.02), Inches(11.9), Inches(0.28)
    )
    tb.text_frame.margin_left = 0
    r = tb.text_frame.paragraphs[0].add_run()
    set_run(r, text.upper(), 10, True, WHITE if dark else INK)


def state_tile(slide, left, top, width, height, value, caption,
               bg, value_color, caption_color, border, bar_frac=None,
               bar_color=None):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left), Inches(top), Inches(width), Inches(height),
    )
    shp.fill.solid()
    shp.fill.fore_color.rgb = bg
    shp.line.color.rgb = border

    tb = slide.shapes.add_textbox(
        Inches(left + 0.12), Inches(top + 0.05),
        Inches(width - 0.24), Inches(0.30),
    )
    tb.text_frame.margin_left = 0
    tb.text_frame.margin_top = 0
    r = tb.text_frame.paragraphs[0].add_run()
    set_run(r, value, 17, True, value_color)

    cb = slide.shapes.add_textbox(
        Inches(left + 0.12), Inches(top + 0.36),
        Inches(width - 0.24), Inches(0.30),
    )
    ctf = cb.text_frame
    ctf.word_wrap = True
    ctf.margin_left = 0
    ctf.margin_top = 0
    r = ctf.paragraphs[0].add_run()
    set_run(r, caption, 8, False, caption_color)

    if bar_frac is not None:
        track = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(left + 0.12), Inches(top + height - 0.16),
            Inches(width - 0.24), Inches(0.07),
        )
        fill(track, LINE)
        span = max(0.04, (width - 0.24) * bar_frac)
        bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(left + 0.12), Inches(top + height - 0.16),
            Inches(span), Inches(0.07),
        )
        fill(bar, bar_color)


def arrow(slide, left, top, width, height, color):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.RIGHT_ARROW,
        Inches(left), Inches(top), Inches(width), Inches(height),
    )
    fill(shp, color)


def chip(slide, left, top, width, height, primary, secondary, accent, dark=False):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left), Inches(top), Inches(width), Inches(height),
    )
    shp.fill.solid()
    shp.fill.fore_color.rgb = CHARCOAL if not dark else CHARCOAL
    shp.line.color.rgb = accent

    tb = slide.shapes.add_textbox(
        Inches(left + 0.08), Inches(top + 0.05),
        Inches(width - 0.16), Inches(height - 0.10),
    )
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_top = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    set_run(r, primary, 13, True, accent)
    p = tf.add_paragraph()
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    set_run(r, secondary, 7.5, False, LIGHT_GRAY)


def kpi_row(slide, top, name, unit, old_value, old_caption, new_value,
            new_caption, chip_primary, chip_secondary, accent, basis,
            old_frac=None, new_frac=None):
    height = 0.74

    nb = slide.shapes.add_textbox(
        Inches(0.48), Inches(top + 0.06), Inches(2.72), Inches(0.62)
    )
    ntf = nb.text_frame
    ntf.word_wrap = True
    ntf.margin_left = 0
    ntf.margin_top = 0
    r = ntf.paragraphs[0].add_run()
    set_run(r, name, 12, True, INK)
    p = ntf.add_paragraph()
    r = p.add_run()
    set_run(r, unit, 8, False, MEDIUM_GRAY)

    state_tile(
        slide, 3.28, top, 1.78, height, old_value, old_caption,
        bg=OFF_WHITE, value_color=MEDIUM_GRAY, caption_color=MEDIUM_GRAY,
        border=LINE, bar_frac=old_frac, bar_color=MEDIUM_GRAY,
    )
    arrow(slide, 5.16, top + 0.26, 0.42, 0.22, CHARCOAL)
    state_tile(
        slide, 5.68, top, 2.30, height, new_value, new_caption,
        bg=WHITE, value_color=INK, caption_color=MEDIUM_GRAY,
        border=accent, bar_frac=new_frac, bar_color=accent,
    )
    chip(slide, 8.08, top, 1.86, height, chip_primary, chip_secondary, accent)

    bb = slide.shapes.add_textbox(
        Inches(10.06), Inches(top + 0.08), Inches(2.79), Inches(0.60)
    )
    btf = bb.text_frame
    btf.word_wrap = True
    btf.margin_left = 0
    btf.margin_top = 0
    r = btf.paragraphs[0].add_run()
    set_run(r, basis, 8.5, False, MEDIUM_GRAY)


# --------------------------------------------------------------------------
# slide 14 - five-KPI scorecard
# --------------------------------------------------------------------------
def build_scorecard_slide(prs, number):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    base(slide, number, "KPI Improvement")
    heading(
        slide,
        "Five key KPIs - current state to V3",
        "Two indicators improve on the data; three are brought under explicit control",
        "Improvement is shown where it can be evidenced, and named as a control where the "
        "indicator has not yet been re-measured.",
    )

    band(slide, 1.50, "Measured improvement on the order and shipment data", GREEN)

    kpi_row(
        slide, 1.84,
        "Order cycle time",
        "Order created to shipment departure",
        "11.30 h", "current average",
        "8.00 h", "V3 replay dataset average",
        "-3.30 h", "%.0f%% faster" % abs(CYCLE_PCT),
        GREEN,
        "Measured. Recomputed from the raw archive and matches the published baseline exactly.",
        old_frac=11.30 / 11.30, new_frac=8.00 / 11.30,
    )
    kpi_row(
        slide, 2.64,
        "On-time carrier departure",
        "Departed at or before planned time",
        "21.95%", "current on-time rate",
        "62.20%", "V3 replay dataset rate",
        "+40.3 pts", "%.1fx the current rate" % ONTIME_RATIO,
        GREEN,
        "Measured. 344 of 1,567 departures today; the replay archive reaches 62.20%.",
        old_frac=21.95 / 62.20, new_frac=62.20 / 62.20,
    )

    band(slide, 3.50, "Brought under explicit control by V3 - indicator not yet re-measured", YELLOW)

    kpi_row(
        slide, 3.84,
        "Inventory accuracy",
        "Rows where WMS, ERP and VISION agree",
        "21.13%", "of rows agree today",
        "100%", "of conflicts resolved by one stated rule",
        "Gated", "no silent pick on disputed stock",
        YELLOW,
        "V3-I5 takes the conservative source minimum; corrections stay auditable (V3-I11).",
    )
    kpi_row(
        slide, 4.64,
        "False availability rate",
        "Robots shown usable but not certified",
        "4.92%", "of robots look usable",
        "0", "blocked resources assigned",
        "Blocked", "readiness gate at claim time",
        YELLOW,
        "V3-I8 prevents assignment without readiness evidence. Product tests reported.",
    )
    kpi_row(
        slide, 5.44,
        "Human interventions",
        "Per 1,000 robot tasks",
        "363.15", "per 1,000 tasks",
        "100%", "carry a reason and evidence trail",
        "Auditable", "volume unchanged today",
        AMBER,
        "V3 structures the intervention; it does not yet claim to reduce how many occur.",
    )

    card(
        slide, 0.48, 6.24, 12.37, 0.42,
        "What the client gets",
        [
            "Two indicators improve on the evidence supplied. The other three stop being silent "
            "failures and become decisions the business can see, justify and audit.",
        ],
        accent=GREEN,
        font_size=10,
    )

    footnote(
        slide,
        "Both measured figures count only shipments with a recorded actual departure - 1,567 of "
        "3,500. The V3 figures come from the supplied synthetic 7,000-order replay archive, a larger "
        "order population than the current baseline, so they size the opportunity rather than prove "
        "a production gain.",
    )

    notes(
        slide,
        "This is the client-facing KPI slide, and it deliberately tells two different kinds of "
        "story, because only two of the five indicators genuinely moved.\n\n"
        "The top band is measured improvement. Order cycle time falls from 11.30 hours to 8.00 "
        "hours, a 29 percent reduction, and on-time carrier departure rises from 21.95 percent to "
        "62.20 percent, which is about 2.8 times the current rate. I recomputed the current "
        "baseline from the raw archive and it reproduces the published figures exactly, so the "
        "starting point is verified rather than asserted.\n\n"
        "The bottom band is the honest treatment of the other three. Inventory accuracy, false "
        "availability and human interventions are all computed from source files that did not "
        "change between the two measurement runs, so their numbers cannot have moved. What did "
        "change is the control around them. V3 resolves stock disagreement with one stated "
        "conservative rule instead of silently picking a system, it refuses to assign a resource "
        "without readiness evidence, and it forces every intervention to carry a reason and an "
        "evidence trail.\n\n"
        "Say that distinction out loud. It is the strongest thing on the slide. Most vendors would "
        "show five improving arrows here; we are showing two measured gains and three controls we "
        "can actually demonstrate, which is why the two measured numbers should be believed.\n\n"
        "If challenged on the human interventions row: we are not claiming fewer interventions. "
        "We are claiming that every one of them is now explainable after the fact, which is the "
        "precondition for reducing them later.",
    )
    return slide


# --------------------------------------------------------------------------
# slide 15 - calculation comparison
# --------------------------------------------------------------------------
def kpi_chart(slide, left, top, width, height, title, categories, values,
              number_format, axis_max, better):
    shell = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left), Inches(top), Inches(width), Inches(height),
    )
    shell.fill.solid()
    shell.fill.fore_color.rgb = OFF_WHITE
    shell.line.color.rgb = LINE

    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(0.07), Inches(height)
    )
    fill(bar, YELLOW)

    tb = slide.shapes.add_textbox(
        Inches(left + 0.22), Inches(top + 0.10), Inches(width - 0.44), Inches(0.26)
    )
    tb.text_frame.margin_left = 0
    r = tb.text_frame.paragraphs[0].add_run()
    set_run(r, title, 13, True, INK)

    sb = slide.shapes.add_textbox(
        Inches(left + 0.22), Inches(top + 0.37), Inches(width - 0.44), Inches(0.22)
    )
    sb.text_frame.margin_left = 0
    r = sb.text_frame.paragraphs[0].add_run()
    set_run(r, better, 8.5, False, MEDIUM_GRAY)

    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series("Value", values)

    frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(left + 0.14), Inches(top + 0.62),
        Inches(width - 0.28), Inches(height - 0.78),
        chart_data,
    )
    chart = frame.chart
    chart.has_legend = False
    chart.font.size = Pt(11)
    chart.font.color.rgb = INK
    chart.font.name = "Aptos"

    plot = chart.plots[0]
    plot.gap_width = 150
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.number_format = number_format
    labels.number_format_is_linked = False
    labels.position = XL_LABEL_POSITION.OUTSIDE_END
    labels.font.size = Pt(15)
    labels.font.bold = True
    labels.font.color.rgb = INK

    series = plot.series[0]
    for index, color in enumerate((MEDIUM_GRAY, YELLOW)):
        point = series.points[index]
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = color
        point.format.line.color.rgb = CHARCOAL

    value_axis = chart.value_axis
    value_axis.maximum_scale = axis_max
    value_axis.minimum_scale = 0
    value_axis.has_major_gridlines = True
    value_axis.major_gridlines.format.line.color.rgb = LINE
    value_axis.tick_labels.font.size = Pt(9)
    value_axis.tick_labels.font.color.rgb = MEDIUM_GRAY

    category_axis = chart.category_axis
    category_axis.tick_labels.font.size = Pt(10)
    category_axis.tick_labels.font.color.rgb = INK
    category_axis.format.line.color.rgb = MEDIUM_GRAY
    return frame


def build_calculation_slide(prs, number):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    base(slide, number, "KPI Improvement")
    heading(
        slide,
        "The two measured KPIs - same formula, same exclusions, both runs",
        "Identical calculations applied to the current and the V3 replay dataset",
        "A before-and-after only holds if both sides are computed the same way. These two are.",
    )

    kpi_chart(
        slide,
        left=0.48, top=1.46, width=6.05, height=3.30,
        title="Order cycle time (hours)",
        categories=("Current state", "V3 replay dataset"),
        values=(CYCLE_OLD, CYCLE_NEW),
        number_format="0.00",
        axis_max=14.0,
        better="Lower is better",
    )
    kpi_chart(
        slide,
        left=6.80, top=1.46, width=6.05, height=3.30,
        title="On-time carrier departure (%)",
        categories=("Current state", "V3 replay dataset"),
        values=(ONTIME_OLD, ONTIME_NEW),
        number_format='0.00"%"',
        axis_max=70.0,
        better="Higher is better",
    )

    card(
        slide, 0.48, 4.90, 6.05, 1.64,
        "How order cycle time is calculated",
        [
            "Mean hours from order created_at to shipment actual_departure, for orders matched to a shipment.",
            "Same formula both runs. Excludes shipments with no actual departure.",
            "Current: 1,567 matched pairs, mean 11.30 h. V3 dataset: mean 8.00 h.",
        ],
        accent=GREEN,
        font_size=9.5,
    )
    card(
        slide, 6.80, 4.90, 6.05, 1.64,
        "How on-time departure is calculated",
        [
            "Share of departures where actual_departure is at or before planned_departure.",
            "Same formula both runs. Denominator is shipments that actually departed.",
            "Current: 344 of 1,567 = 21.95%. V3 dataset: 62.20%.",
        ],
        accent=GREEN,
        font_size=9.5,
    )

    footnote(
        slide,
        "Difference in population: the current state is measured on the original 3,500-shipment "
        "extract; the V3 figures come from the supplied synthetic 7,000-order replay archive. Same "
        "formula, different order population - so this sizes the opportunity rather than proving a "
        "controlled before-and-after on identical orders.",
    )

    notes(
        slide,
        "This slide exists to survive the first hard question a client analyst will ask, which is "
        "whether the two numbers were calculated the same way.\n\n"
        "They were. Order cycle time is the mean gap between when the order was created and when "
        "the shipment actually departed, taken over orders matched to a shipment. On-time departure "
        "is the share of departures that happened at or before the planned time. Both formulas are "
        "applied identically to both datasets.\n\n"
        "Be upfront about the two exclusions, because they are the honest weak points. First, both "
        "runs only count shipments that actually departed. In the current extract that is 1,567 of "
        "3,500, so roughly sixty percent of shipments sit outside both averages. Second, the two "
        "runs use different order populations - the original extract against the supplied synthetic "
        "seven thousand order archive.\n\n"
        "That means this is a like-for-like calculation on two different datasets. It is a credible "
        "sizing of the opportunity and it is the best evidence available today, but it is not a "
        "controlled before-and-after on the same orders, and we should not let it be quoted as one. "
        "The honest next step is a treatment period on the client's own order flow.",
    )
    return slide


# --------------------------------------------------------------------------
# slide 16 - evidence integrity
# --------------------------------------------------------------------------
def build_integrity_slide(prs, number):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    base(slide, number, "KPI Improvement", dark=True)
    heading(
        slide,
        "Evidence position behind the five KPIs",
        "What is measured, what is controlled, and what must be fixed at source",
        "Internal reference. Keep this slide for a technical audience or a challenge session.",
        dark=True,
    )

    tile(slide, 0.48, 1.54, 3.00, "2 of 5", "measured improvement on data", dark=True, accent=GREEN)
    tile(slide, 3.63, 1.54, 3.00, "3 of 5", "controlled, not yet re-measured", dark=True, accent=YELLOW)
    tile(slide, 6.78, 1.54, 3.00, "5", "KPIs with a unit defect at source", dark=True, accent=RED)
    tile(slide, 9.93, 1.54, 2.92, "60%", "of shipments outside both averages", dark=True, accent=AMBER)

    rows = [
        ("KPI", "Current", "Reported V3", "Source file changed?", "Position"),
        ("Order cycle time", "11.30 h", "8.00 h", "Yes - new order file", "Measured"),
        ("On-time carrier departure", "21.95%", "62.20%", "Yes - new shipment file", "Measured"),
        ("Inventory accuracy", "21.13%", "0.21%", "No - same inventory file", "Unit defect"),
        ("False availability rate", "4.92%", "0.05%", "No - same robots file", "Unit defect"),
        ("Human interventions / 1,000", "363.15", "363.15", "No - same tasks file", "Unchanged"),
    ]
    shape = table(
        slide, 0.48, 2.86, 12.37, rows,
        col_widths=(3.20, 1.60, 1.70, 3.72, 2.15),
        row_height=0.42,
        font_size=10,
    )
    colors = {"Measured": GREEN, "Unit defect": RED, "Unchanged": MEDIUM_GRAY}
    tbl = shape.table
    for index in range(1, len(rows)):
        run = tbl.cell(index, 4).text_frame.paragraphs[0].runs[0]
        run.font.bold = True
        run.font.color.rgb = colors[rows[index][4]]

    card(
        slide, 0.48, 5.62, 6.05, 1.00,
        "Why three KPIs are shown as controls, not gains",
        [
            "Their source files are identical across both runs, so the value cannot move.",
            "Inventory accuracy and false availability are reported at exactly one hundredth "
            "of the current value - a ratio labelled as a percent. Fix the unit at source.",
        ],
        dark=True,
        accent=RED,
        font_size=9.5,
    )
    card(
        slide, 6.80, 5.62, 6.05, 1.00,
        "What can be claimed without qualification",
        [
            "The current baseline was independently recomputed and matches exactly.",
            "On the evidence supplied, the V3 dataset is 3.30 hours faster with a 40.25 point "
            "higher on-time rate. The three controls are implemented and testable today.",
        ],
        dark=True,
        accent=GREEN,
        font_size=9.5,
    )

    notes(
        slide,
        "Keep this slide in the pack but out of the main flow. It is the answer to a challenge, and "
        "it is also the instruction list for whoever owns the KPI pipeline.\n\n"
        "The central fact is in the fourth column. Between the two measurement runs, only the order "
        "and shipment files were replaced. Tasks, inventory, telemetry, maintenance and robots are "
        "the same files in both runs. So only order and shipment indicators can legitimately move, "
        "and they did.\n\n"
        "There is a real defect to fix. Inventory accuracy is reported as 0.21 percent against a "
        "current 21.13 percent, and false availability as 0.05 percent against 4.92 percent. Each "
        "is exactly one hundredth of the current value while reading an unchanged file, which means "
        "a ratio is being printed with a percent label. If those were charted as-is, inventory "
        "accuracy would look like a near-total collapse and false availability would look like a "
        "ninety-nine percent win. Neither is true, and either would destroy credibility in the "
        "room. Multiply by one hundred at source and republish.\n\n"
        "The last figure on the tiles is the one most likely to be probed. Roughly sixty percent of "
        "shipments in the current extract never recorded an actual departure, so they sit outside "
        "both averages. If someone asks whether the improvement comes from which shipments "
        "completed rather than how fast they completed, the honest answer is that this dataset "
        "cannot separate those two effects yet.",
    )
    return slide


def main():
    prs = Presentation(str(DECK))
    start = len(prs.slides)
    if start != 13:
        raise SystemExit(
            "Expected a 13-slide base deck, found %d. "
            "Run generate_repo3_solution_deck.py first." % start
        )

    build_scorecard_slide(prs, start + 1)
    build_calculation_slide(prs, start + 2)
    build_integrity_slide(prs, start + 3)

    prs.save(str(DECK))
    print("slides 1-13 unchanged; appended 14-%d" % len(prs.slides))
    print("saved:", DECK)


if __name__ == "__main__":
    main()
