"""Build the slide deck for the two-tier scheduler engineering study.

Run with system python3 (python-pptx lives there, not in the uv venv):

    python3 deck/build_deck.py

Every number here is post-2026-08-07, i.e. after the three fidelity
corrections. If a figure changes, change it here and rebuild -- do not edit
the .pptx by hand, or the deck and the repo will drift.

Colours are slots 1 and 2 of the dataviz reference categorical palette, used
in fixed order. That order is documented as pre-validated as a set (worst
adjacent CVD dE 9.1 in light mode); no JS runtime was available on this
machine to re-run the validator, so the fixed order is relied on rather than
re-derived.
"""

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

# --- design tokens ---------------------------------------------------------
INK = RGBColor(0x1A, 0x1A, 0x19)        # text-primary
INK_2 = RGBColor(0x5C, 0x5B, 0x54)      # text-secondary
INK_3 = RGBColor(0x8A, 0x89, 0x80)      # muted
RULE = RGBColor(0xDD, 0xDC, 0xD6)
SURFACE = RGBColor(0xFF, 0xFF, 0xFF)
BAND = RGBColor(0xF5, 0xF4, 0xF0)       # table header / callout fill
SERIES_1 = RGBColor(0x2A, 0x78, 0xD6)   # blue  -- PF
SERIES_2 = RGBColor(0xEB, 0x68, 0x34)   # orange -- TwoTier
GOOD = RGBColor(0x00, 0x83, 0x00)
BAD = RGBColor(0xE3, 0x49, 0x48)

FONT = "Calibri"
W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.9)
BODY_W = W - 2 * MARGIN


def text(slide, x, y, w, h, runs, size=18, color=INK, bold=False,
         align=PP_ALIGN.LEFT, space_after=6, line=1.25):
    """runs: a string, or a list of (text, {overrides}) tuples per paragraph."""
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    items = runs if isinstance(runs, list) else [runs]
    for i, item in enumerate(items):
        content, over = item if isinstance(item, tuple) else (item, {})
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = over.get("align", align)
        p.space_after = Pt(over.get("space_after", space_after))
        p.line_spacing = over.get("line", line)
        # inline bold via ** markers
        for j, seg in enumerate(content.split("**")):
            if not seg:
                continue
            r = p.add_run()
            r.text = seg
            r.font.size = Pt(over.get("size", size))
            r.font.color.rgb = over.get("color", color)
            r.font.name = FONT
            r.font.bold = (j % 2 == 1) or over.get("bold", bold)
    return box


def rule(slide, y, x=MARGIN, w=None, color=RULE, h=Pt(1.25)):
    w = w or BODY_W
    s = slide.shapes.add_shape(1, x, y, w, h)   # 1 = rectangle
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()
    s.shadow.inherit = False
    return s


def slide_base(prs, title, kicker=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    y = Inches(0.55)
    if kicker:
        text(s, MARGIN, y, BODY_W, Inches(0.3), kicker.upper(),
             size=11, color=INK_3, bold=True)
        y += Inches(0.34)
    text(s, MARGIN, y, BODY_W, Inches(0.7), title, size=30, bold=True)
    rule(s, Inches(1.62))
    return s


def table(slide, x, y, w, rows, col_w=None, header=True, size=14,
          emphasis=None, numeric=True):
    """rows: list of lists of str. emphasis: {(r,c): RGBColor}.

    numeric=True right-aligns every column but the first (the default, for
    figures); numeric=False left-aligns throughout, for tables of prose.
    """
    nr, nc = len(rows), len(rows[0])
    h = Inches(0.34) * nr
    shape = slide.shapes.add_table(nr, nc, x, y, w, h)
    tbl = shape.table
    if col_w:
        total = sum(col_w)
        for i, frac in enumerate(col_w):
            tbl.columns[i].width = Emu(int(w * frac / total))
    for r, row in enumerate(rows):
        tbl.rows[r].height = Inches(0.34)
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.text = ""
            cell.fill.solid()
            cell.fill.fore_color.rgb = BAND if (header and r == 0) else SURFACE
            cell.margin_left = Inches(0.09)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
            p = cell.text_frame.paragraphs[0]
            p.alignment = (PP_ALIGN.RIGHT if (numeric and c > 0)
                           else PP_ALIGN.LEFT)
            r_ = p.add_run()
            r_.text = val
            r_.font.size = Pt(size)
            r_.font.name = FONT
            r_.font.bold = (header and r == 0)
            r_.font.color.rgb = (emphasis or {}).get((r, c), INK if r == 0 else INK_2)
    return shape


def callout(slide, x, y, w, h, body, accent=SERIES_2):
    bg = slide.shapes.add_shape(1, x, y, w, h)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BAND
    bg.line.fill.background()
    bg.shadow.inherit = False
    bar = slide.shapes.add_shape(1, x, y, Pt(4), h)
    bar.fill.solid()
    bar.fill.fore_color.rgb = accent
    bar.line.fill.background()
    bar.shadow.inherit = False
    text(slide, x + Inches(0.25), y + Inches(0.14), w - Inches(0.5),
         h - Inches(0.28), body, size=16, color=INK)


# ===========================================================================
prs = Presentation()
prs.slide_width, prs.slide_height = W, H

# --- 1. title --------------------------------------------------------------
s = prs.slides.add_slide(prs.slide_layouts[6])
text(s, MARGIN, Inches(2.3), BODY_W, Inches(1.6),
     "An Engineering Study of a Two-Tier\nQoS-Aware Scheduler for Private 5G",
     size=40, bold=True, line=1.15)
rule(s, Inches(4.05), w=Inches(2.2), color=SERIES_2, h=Pt(3))
text(s, MARGIN, Inches(4.35), BODY_W, Inches(1.4), [
    ("Should we replace the proportional-fair scheduler OpenAirInterface ships?",
     {"size": 19, "color": INK_2}),
    ("The decision, the measurements behind it — and the three modelling "
     "errors found on the way.", {"size": 19, "color": INK_2}),
], size=19, color=INK_2)

# --- 2. the setting --------------------------------------------------------
s = slide_base(prs, "One cell, three kinds of promise", "the setting")
text(s, MARGIN, Inches(1.95), BODY_W, Inches(0.5),
     "A factory floor puts traffic on one carrier whose classes want "
     "qualitatively different things:", size=18, color=INK_2)
table(s, MARGIN, Inches(2.6), BODY_W, [
    ["Class", "Example", "What it wants", "What failure looks like"],
    ["GBR", "Robot camera / LIDAR uplink", "A sustained rate floor", "Visible artefacts, lost frames"],
    ["Delay", "Motion control, teleoperation", "Bytes before a deadline", "A late command — a safety event"],
    ["Best-effort", "Firmware, log upload", "Whatever is left", "Slower; nobody notices"],
], col_w=[1.1, 2.4, 2.0, 2.6], size=15, numeric=False)
callout(s, MARGIN, Inches(4.5), BODY_W, Inches(1.15),
        "Proportional fair — the LTE/NR default, and what OAI ships — "
        "represents **neither a rate contract nor a deadline**. It is a good "
        "answer to a question the factory is not asking.")
text(s, MARGIN, Inches(5.95), BODY_W, Inches(0.6),
     "A GBR flow wants a specific rate or nothing of value. A delay flow "
     "wants its bytes before a deadline, after which they are worthless.",
     size=16, color=INK_3)

# --- 3. the design ---------------------------------------------------------
s = slide_base(prs, "The design — and we claim no novelty for it", "what we built")
text(s, MARGIN, Inches(1.95), Inches(5.9), Inches(3.2), [
    ("Tier-1  ·  every ~1 s", {"size": 17, "bold": True, "color": SERIES_2}),
    ("A convex program sets a target rate per flow: max-min GBR floor, then "
     "minimise contract shortfall, then maximise weighted log utility.",
     {"size": 16, "color": INK_2, "space_after": 14}),
    ("Tier-2  ·  every slot", {"size": 17, "bold": True, "color": SERIES_2}),
    ("Drift-plus-penalty virtual queues track those targets. Grants are "
     "per UE — one DCI, one transport block — filled by a MAC "
     "logical-channel multiplexer.", {"size": 16, "color": INK_2, "space_after": 14}),
    ("Configured grants", {"size": 17, "bold": True, "color": SERIES_2}),
    ("Periodic flows get standing allocations, self-gated so they stand "
     "aside when they would hurt.", {"size": 16, "color": INK_2}),
])
callout(s, Inches(7.2), Inches(1.95), Inches(5.2), Inches(2.9),
        "This composes established parts — network utility maximisation over "
        "a slow horizon feeding Lyapunov drift-plus-penalty per slot.\n\n"
        "**It is the pattern behind NVS and the O-RAN RIC split.** We present "
        "it because the composition, and the places it goes wrong, are "
        "instructive.", accent=INK_3)
text(s, MARGIN, Inches(6.45), BODY_W, Inches(0.8),
     "Evaluated against Round Robin, Proportional Fair and a class-aware "
     "Gradient baseline. All four grant per UE, so the comparison isolates "
     "QoS-awareness rather than grant granularity.", size=16, color=INK_3)

# --- 4. result: control channel --------------------------------------------
s = slide_base(prs, "Where it wins outright (1): the control channel binds",
                "result · sensor_dense")
text(s, MARGIN, Inches(1.95), BODY_W, Inches(0.5),
     "30 dense periodic uplink sensors, 15 ms deadline. The DCI/CCE budget "
     "runs out before the data channel does.", size=17, color=INK_2)
table(s, MARGIN, Inches(2.85), Inches(7.6), [
    ["Scheduler", "On time", "Worst p99"],
    ["Round Robin", "0/30", "15.0 ms"],
    ["Proportional Fair", "2/30", "15.0 ms"],
    ["Two-tier", "30/30", "5.0 ms"],
], col_w=[3, 1.5, 1.5], size=16,
   emphasis={(3, 1): GOOD, (3, 2): GOOD, (2, 1): BAD})
callout(s, MARGIN, Inches(4.35), BODY_W, Inches(1.5),
        "Configured grants cost **zero PDCCH per slot and need no buffer-status "
        "round trip**. PF is throttled by both budgets at once and has no "
        "mechanism to bypass either — this is a capability gap, not a tuning "
        "gap, so no amount of PF tuning closes it.", accent=GOOD)
text(s, MARGIN, Inches(6.1), BODY_W, Inches(0.5),
     "Independently reported by Larrañaga et al. (JNCA 2023) from ns-3/5G-LENA. "
     "We reproduce it in a simulator sharing no code with theirs.",
     size=15, color=INK_3)

# --- 5. result: deadlines --------------------------------------------------
s = slide_base(prs, "Where it wins outright (2): deadline-blindness is silent",
                "result · latency_bound")
text(s, MARGIN, Inches(1.95), BODY_W, Inches(0.5),
     "Eight interactive 5 Mbps streams, 12 ms deadline, sharing a saturated "
     "downlink with 80 Mbps of bulk.", size=17, color=INK_2)
table(s, MARGIN, Inches(2.65), Inches(9.4), [
    ["Scheduler", "On time", "Mean delivery", "Worst p99", "Bulk carried"],
    ["Round Robin", "3/8", "84%", "12.0 ms", "22.8 M"],
    ["Proportional Fair", "5/8", "86%", "12.0 ms", "24.6 M"],
    ["Two-tier", "8/8", "100%", "4.5 ms", "13.2 M"],
], col_w=[2.6, 1.2, 1.6, 1.4, 1.5], size=16,
   emphasis={(3, 1): GOOD, (3, 3): GOOD})
callout(s, MARGIN, Inches(4.5), BODY_W, Inches(1.5),
        "PF's control-flow mean delivery is **86% — which reads healthy on a "
        "dashboard.** The missing 14% are aged-out packets: the late motion "
        "commands, the safety-relevant ones. Mean delivery is not a safety "
        "metric.", accent=BAD)
text(s, MARGIN, Inches(6.2), BODY_W, Inches(0.5),
     "The two-tier design pays for it explicitly — bulk drops 24.6 → 13.2 Mbps "
     "to clear every deadline.", size=15, color=INK_3)

# --- 6. result: GBR, the mixed one -----------------------------------------
s = slide_base(prs, "Where it is mixed: the metric differs, not the outcome",
                "result · factory_robots")
text(s, MARGIN, Inches(1.88), Inches(6.0), Inches(0.6),
     "Ten robots, uplink-heavy, swept across offered load. "
     "Two metrics disagree.", size=17, color=INK_2)

chart_data = CategoryChartData()
chart_data.categories = ["1.00x", "0.67x", "0.50x", "0.33x"]
chart_data.add_series("Proportional Fair", (1, 21, 52, 83))
chart_data.add_series("Two-tier", (44, 67, 81, 83))
chart_shape = s.shapes.add_chart(
    XL_CHART_TYPE.COLUMN_CLUSTERED, MARGIN, Inches(2.55),
    Inches(5.9), Inches(3.4), chart_data)
ch = chart_shape.chart
ch.has_title = True
ch.chart_title.text_frame.text = "Worst-served GBR flow (% of contract)"
tp = ch.chart_title.text_frame.paragraphs[0]
tp.runs[0].font.size = Pt(14)
tp.runs[0].font.bold = False
tp.runs[0].font.color.rgb = INK_2
tp.runs[0].font.name = FONT
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.BOTTOM
ch.legend.include_in_layout = False
ch.legend.font.size = Pt(12)
ch.legend.font.name = FONT
ch.legend.font.color.rgb = INK_2
ch.plots[0].gap_width = 60
ch.plots[0].series[0].format.fill.solid()
ch.plots[0].series[0].format.fill.fore_color.rgb = SERIES_1
ch.plots[0].series[1].format.fill.solid()
ch.plots[0].series[1].format.fill.fore_color.rgb = SERIES_2
va = ch.value_axis
va.has_major_gridlines = True
va.maximum_scale = 100
va.tick_labels.font.size = Pt(11)
va.tick_labels.font.color.rgb = INK_3
ca = ch.category_axis
ca.tick_labels.font.size = Pt(11)
ca.tick_labels.font.color.rgb = INK_3

text(s, Inches(7.1), Inches(2.35), Inches(5.3), Inches(0.4),
     "Contracts met (≥95% of the rate floor)", size=14, color=INK_2)
table(s, Inches(7.1), Inches(2.85), Inches(5.3), [
    ["Load", "PF", "Two-tier"],
    ["1.00x  (as shipped)", "1/10", "0/10"],
    ["0.67x", "6/10", "1/10"],
    ["0.50x", "8/10", "10/10"],
    ["0.33x", "10/10", "10/10"],
], col_w=[2.6, 1.2, 1.4], size=15,
   emphasis={(2, 1): GOOD, (3, 2): GOOD})
callout(s, Inches(7.1), Inches(4.8), Inches(5.3), Inches(1.8),
        "At 0.67x load every robot gets **≥67%** of its rate under two-tier, "
        "while PF leaves its worst at 21% — yet PF scores 6/10 to our 1/10, "
        "because six of its flows clear the 95% bar and none of ours do.")
text(s, MARGIN, Inches(6.68), BODY_W, Inches(0.7),
     "A threshold count rewards concentrating a shortfall. This design "
     "spreads it. Which is better depends on whether 90% of a video feed is "
     "worth anything — for cameras yes, for a control loop no.",
     size=15, color=INK_3)

# --- 7. the turn -----------------------------------------------------------
s = prs.slides.add_slide(prs.slide_layouts[6])
bg = s.shapes.add_shape(1, 0, 0, W, H)
bg.fill.solid()
bg.fill.fore_color.rgb = BAND
bg.line.fill.background()
bg.shadow.inherit = False
text(s, MARGIN, Inches(2.5), BODY_W, Inches(1.2),
     "Every result above is a claim about a scheduler\n**mediated by a simulator.**",
     size=32, bold=False, line=1.2)
rule(s, Inches(4.35), w=Inches(2.2), color=SERIES_2, h=Pt(3))
text(s, MARGIN, Inches(4.65), BODY_W, Inches(1.2),
     "Three times, a natural-looking modelling shortcut produced a result "
     "that did not survive being corrected. One of them was a headline "
     "finding of an earlier draft of this work.", size=19, color=INK_2)

# --- 8. shortcut 1 ---------------------------------------------------------
s = slide_base(prs, "The scheduler was filling the uplink transport block",
                "shortcut 1 · the expensive one")
text(s, MARGIN, Inches(1.9), BODY_W, Inches(0.8),
     "Our multiplexer was direction-agnostic — the same code split a UE's "
     "transport block in both directions, ordering flows by the **gNB's own "
     "virtual queues.** In the uplink no gNB may do that.", size=17, color=INK_2)
table(s, MARGIN, Inches(2.95), Inches(9.6), [
    ["Mixed-flow UE (GBR video + best-effort)", "RR", "PF", "Gradient", "Two-tier"],
    ["Scheduler fills the block  (what we had)", "3%", "3%", "3%", "53%"],
    ["UE fills the block  (TS 38.321 §5.4.3.1)", "100%", "100%", "72%", "89%"],
], col_w=[4.8, 1.0, 1.0, 1.3, 1.3], size=15,
   emphasis={(1, 4): SERIES_2, (2, 1): GOOD, (2, 2): GOOD})
callout(s, MARGIN, Inches(4.5), BODY_W, Inches(1.55),
        "We had described the top row as a clean demonstration of QoS-aware "
        "multiplexing. **It was the UE's prioritised-bit-rate configuration "
        "all along** — available to every scheduler. Correcting it also raised "
        "PF's contract count at 0.50x load from 5/10 to 8/10.", accent=BAD)
text(s, MARGIN, Inches(6.25), BODY_W, Inches(0.5),
     "The gNB grants a block; the UE splits it by its own logical-channel "
     "prioritisation. The gNB configures the PBRs but never learns the split.",
     size=15, color=INK_3)

# --- 9. shortcuts 2 and 3 --------------------------------------------------
s = slide_base(prs, "Two more, and what they have in common",
                "shortcuts 2 and 3")
text(s, MARGIN, Inches(1.9), Inches(5.9), Inches(2.6), [
    ("Flows shared a priority level", {"size": 18, "bold": True, "color": SERIES_2}),
    ("With every flow at one priority, the multiplexer's sort silently fell "
     "back to the order flows appear in the config file. Results were "
     "reproducible only by accident.", {"size": 16, "color": INK_2}),
    ("Deriving priority from the standardised 5QI fixed it — and the numbers "
     "did not change, which is exactly why this class of error survives "
     "testing.", {"size": 16, "color": INK_3}),
])
text(s, Inches(7.1), Inches(1.9), Inches(5.3), Inches(2.6), [
    ("Tier-1 was handed the true offered load", {"size": 18, "bold": True, "color": SERIES_2}),
    ("Read straight from the traffic generator: exact, noise-free, static. "
     "No gNB has that.", {"size": 16, "color": INK_2}),
    ("Estimating it instead produced a starvation lock-in — a starved flow's "
     "data ages out, so it stops appearing in the arrival count. The flow "
     "never stopped asking; we stopped counting.",
     {"size": 16, "color": INK_3}),
])
callout(s, MARGIN, Inches(4.6), BODY_W, Inches(2.15),
        "All three gave the scheduler information or authority the 3GPP split "
        "does not grant it. **All three flattered the scheduler, not the "
        "baselines** — which is not coincidence: a simulator is written from "
        "the scheduler's point of view, so its conveniences accrue there.\n\n"
        "The check we now apply: for every quantity the scheduler reads — "
        "**which network element learns this, and how?**")

# --- 10. adoption ----------------------------------------------------------
s = slide_base(prs, "So: adopt it — and do not build a fallback to PF",
                "the decision")
text(s, MARGIN, Inches(1.9), Inches(5.9), Inches(2.9), [
    ("Two wins are unconditional", {"size": 18, "bold": True, "color": GOOD}),
    ("Configured grants and the deadline-aware tracker address capabilities "
     "PF lacks entirely. Both survived every fidelity correction untouched — "
     "neither scenario has a multi-flow uplink UE.",
     {"size": 16, "color": INK_2, "space_after": 14}),
    ("One metric loss, and it is a metric choice", {"size": 18, "bold": True, "color": SERIES_2}),
    ("Under GBR infeasibility a threshold count prefers concentration. We "
     "measured whether a knob recovers it: sweeping the max-min floor from "
     "1 to 0 moves contracts only 1/10 → 2/10, against PF's 6/10. It does not.",
     {"size": 16, "color": INK_2}),
])
callout(s, Inches(7.1), Inches(1.9), Inches(5.3), Inches(2.9),
        "A scheduler-level switch to PF is the **wrong instrument** — it would "
        "surrender configured grants and deadline awareness to improve one "
        "metric on one flow class.\n\n"
        "Only the max-min floor is regime-dependent. It is a continuous knob, "
        "and Tier-1 already computes an **exact feasibility test** — so "
        "degradation can be graceful, with no regime guessing.", accent=GOOD)
text(s, MARGIN, Inches(6.15), BODY_W, Inches(1.0),
     "And detection is not needed for safety: with the floor off, the design "
     "leads PF on mean and worst-case delivery at both loaded points while "
     "keeping both structural wins.", size=17, color=INK_2)

# --- 11. closing -----------------------------------------------------------
s = slide_base(prs, "What this is, and what it is not", "in closing")
text(s, MARGIN, Inches(1.95), Inches(5.9), Inches(3.4), [
    ("What we offer", {"size": 18, "bold": True, "color": GOOD}),
    ("• Independent reproduction of two results, in a simulator sharing no "
     "code with the work that first reported them.", {"size": 16, "color": INK_2}),
    ("• Three fidelity corrections, each with the measurement it changed.",
     {"size": 16, "color": INK_2}),
    ("• An adoption decision with its reasoning, not just its verdict.",
     {"size": 16, "color": INK_2}),
    ("• Simulator, scheduler library and one script per result table.",
     {"size": 16, "color": INK_2}),
])
text(s, Inches(7.1), Inches(1.95), Inches(5.3), Inches(3.4), [
    ("What we do not claim", {"size": 18, "bold": True, "color": INK_3}),
    ("• Novelty for the design. It composes known parts.",
     {"size": 16, "color": INK_2}),
    ("• Silicon. This is simulation; comparative, not absolute. An OAI "
     "integration is the next step and is under way.",
     {"size": 16, "color": INK_2}),
    ("• External validity beyond three synthetic single-cell scenarios — no "
     "churn, no mobility, no inter-cell interference.",
     {"size": 16, "color": INK_2}),
])
callout(s, MARGIN, Inches(5.85), BODY_W, Inches(1.35),
        "The remaining unmodelled effects we know of — uplink grant timing, "
        "HARQ retransmissions consuming PRBs — would **widen** the "
        "configured-grant advantage, not narrow it. Though after the last "
        "three slides, we note that is asserted from mechanism, not measured.",
        accent=INK_3)

prs.save("deck/two-tier-scheduler.pptx")
print(f"wrote deck/two-tier-scheduler.pptx  ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
