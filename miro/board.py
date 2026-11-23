#!/usr/bin/env python3
"""Blockwise design-thinking board: one source, two outputs.

    python3 miro/board.py png                 # render storyboard panels to miro/storyboard/*.png (needs Chrome)
    python3 miro/board.py miro --dry-run      # build every Miro API request without sending (writes miro/out/)
    MIRO_TOKEN=... python3 miro/board.py miro # create a new Miro board and fill it
    MIRO_TOKEN=... python3 miro/board.py miro --board-id uXjV...=   # fill an existing board instead
    python3 miro/board.py whiteboard DIR      # element JSON for the claude.ai Whiteboard copy

Standard library only (Python 3.9+). Coordinates are board units; x, y are top-left corners.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from drawings import PANELS, svg_data_uri  # noqa: E402

BOARD_TITLE = "Blockwise Design Board"
PAD = 40           # inside a section
GAP = 24           # between neighbours
SW = 220           # sticky width
SH = 144           # sticky height (Miro rectangle sticky ratio 0.652)
SIZES = {"small": 14, "body": 16, "large": 28, "title": 48, "huge": 96}


def plain(text):
    return re.sub(r"\*+|`", "", text)


def n_lines(text, cpl):
    total = 0
    for line in plain(text).split("\n"):
        words, cur, lines = line.split(" "), 0, 1
        for w in words:
            add = len(w) + (1 if cur else 0)
            if cur + add > cpl and cur:
                lines += 1
                cur = len(w)
            else:
                cur += add
        total += lines
    return total


def est_h(text, w, size="body"):
    px = SIZES[size]
    cpl = max(6, int((w - 32) / (px * 0.56)))
    return int(math.ceil(n_lines(text, cpl) * px * 1.5 + 34))


def text_w(text, size="body"):
    return int(max(len(plain(l)) for l in text.split("\n")) * SIZES[size] * 0.56) + 8


class Board:
    def __init__(self):
        self.items = []
        self.n = 0
        self.sec = None

    def _add(self, **kw):
        self.n += 1
        kw["id"] = "e%d" % self.n
        kw["parent"] = self.sec["id"] if (self.sec and kw["kind"] != "section") else None
        self.items.append(kw)
        return kw

    # sections -------------------------------------------------------------
    def begin(self, title, x, y):
        self.sec = self._add(kind="section", title=title, x=x, y=y, w=0, h=0)
        return x + PAD, y + PAD

    def end(self, min_w=0):
        s = self.sec
        r = max([i["x"] + i["w"] for i in self.items if i.get("parent") == s["id"] and "w" in i] + [s["x"] + min_w])
        b = max(i["y"] + i["h"] for i in self.items if i.get("parent") == s["id"] and "h" in i)
        s["w"], s["h"] = int(r - s["x"] + PAD), int(b - s["y"] + PAD)
        self.sec = None
        return s

    # elements -------------------------------------------------------------
    def block(self, x, y, w, text, color="white", h=None, size="body", align="center", shape="rounded", min_h=0):
        h = h or max(min_h, est_h(text, w, size))
        return self._add(kind="block", x=x, y=y, w=w, h=h, text=text, color=color, size=size, align=align,
                         shape=shape)

    def sticky(self, x, y, text, color="yellow", w=SW):
        return self._add(kind="sticky", x=x, y=y, w=w, h=int(round(w * 0.652)), text=text, color=color)

    def text(self, x, y, text, size="body", wrap=None, align="left"):
        w = wrap or text_w(text, size)
        return self._add(kind="text", x=x, y=y, w=w, h=int(n_lines(text, max(6, int(w / (SIZES[size] * 0.56))))
                                                         * SIZES[size] * 1.5), text=text, size=size, wrap=wrap,
                         align=align)

    def arrow(self, a, b, fs=None, ts=None, label=None, head=True, dash=False, curve=False):
        return self._add(kind="arrow", a=a["id"], b=b["id"], fs=fs, ts=ts, label=label, head=head, dash=dash,
                         curve=curve)

    def image(self, x, y, w, h, svg, name):
        return self._add(kind="image", x=x, y=y, w=w, h=h, svg=svg, name=name)

    def table(self, x, y, cols, rows, fills=None, row_h=48):
        return self._add(kind="table", x=x, y=y, w=sum(c[1] for c in cols), h=row_h * (len(rows) + 1), cols=cols,
                         rows=rows, fills=fills or {}, row_h=row_h)


# =========================================================================================================
# Content
# =========================================================================================================

def header(b, top=-360):
    d = top + 360  # everything below was laid out for top = -360
    b.text(0, -360 + d, "Blockwise · design thinking board", size="title")
    b.text(0, -284 + d, "Commit the right rooms at the right risk.", size="large")
    b.text(0, -232 + d, "TBO VoyageHack 4.0 · Automate Inventory Optimization · Team 5rods · Round 1", size="body")
    lx = 1500
    b.text(lx, -360 + d, "**How to read this board**", size="body")
    for i, (c, t) in enumerate([("yellow", "Idea"), ("pink", "Pain or problem"), ("green", "Goal or opportunity"),
                                ("blue", "Blockwise or proof")]):
        b.block(lx + i * 194, -326 + d, 170, t, color=c, h=48)
    b.text(lx, -258 + d, "Start at frame 0, then read left to right, top to bottom: Empathise → Define → Ideate → "
                         "Prototype → Test → Strategy.\n"
                         "✓ built in Round 1 · ● one dot vote · personas are composites, story numbers are illustrative.",
           size="small", wrap=780)


# Live board ids, used only to make the frame-0 board map clickable (python3 miro/board.py canvas).
MIRO_BOARD_URL = "https://miro.com/app/board/uXjVELZJtVY=/"
FRAME_IDS = {1: "3458764691236074021", 2: "3458764691236121208", 3: "3458764691236121209",
             4: "3458764691236168601", 5: "3458764691236168602", 6: "3458764691236203416",
             7: "3458764691236203417", 8: "3458764691236256766", 9: "3458764691236256767",
             10: "3458764691236365429", 11: "3458764691236365430", 12: "3458764691236365431",
             13: "3458764691242217855"}


def frame_link(n, label):
    fid = FRAME_IDS.get(n)
    return '<a href="%s?moveToWidget=%s">%d %s</a>' % (MIRO_BOARD_URL, fid, n, label) if fid else "%d %s" % (n, label)


def start_here(b, x, y):
    cx, cy = b.begin("0  Start here · Blockwise in one minute", x, y)
    b.text(cx, cy, "**Blockwise tells TBO which hotel rooms and flight seats to lock in, how many, under which "
                   "contract, and within what budget.**", size="large", wrap=2300)
    cy += 80
    cw, ag = 420, 56
    cards = [
        ("pink", "**1 · The problem**\nTBO must commit rooms and seats weeks before demand is known. Commit too "
                 "much and unsold prepaid rooms become losses. Commit too little and agents are turned away on the "
                 "nights that matter most."),
        ("white", "**2 · Who feels it**\n- Arjun, contracting: plans on last year's volume in a spreadsheet\n"
                  "- Kavita, finance: can't see the bad case\n- Rahul, travel agent: loses clients to ‘sold out’\n"
                  "- Mei Lin, hotel: gets rooms handed back late"),
        ("blue", "**3 · What Blockwise does**\nForecasts a range of demand, simulates 150 to 200 futures, then "
                 "picks the mix of hard blocks, allotments and buying as needed that earns the most while limiting "
                 "the worst 5% of outcomes."),
        ("blue", "**4 · Proof on real data**\n- 92.7% of perfect-hindsight profit vs 89.8% for the best fixed "
                 "rule (2 hotels, 15 rounds)\n- Won 12 of 15 rounds, half the unsold prepaid cost\n"
                 "- 17% smaller COVID loss in the Singapore replay"),
        ("green", "**5 · What's next**\nRound 2: plug in TBO's search logs and sold-out flags, re-plan weekly as "
                  "bookings arrive, and add flight deposit and name-change terms."),
    ]
    ch = max(est_h(t, cw) for _, t in cards) + 8
    prev = None
    for i, (c, t) in enumerate(cards):
        blk = b.block(cx + i * (cw + ag), cy, cw, t, color=c, h=ch, align="left")
        if prev:
            b.arrow(prev, blk, fs="right", ts="left")
        prev = blk
    cy += ch + 48
    b.text(cx, cy, "**Board map** · click a name to jump to that frame", size="body")
    cy += 36
    stages = [("Empathise", [(1, "Personas"), (2, "Empathy map"), (3, "Journey map")]),
              ("Define", [(4, "Why it goes wrong"), (5, "Problem and HMW")]),
              ("Ideate", [(6, "Brainstorm"), (7, "Prioritise"), (8, "Product mind map")]),
              ("Prototype", [(9, "How it works"), (10, "Storyboard")]),
              ("Test", [(11, "Evidence"), (12, "Roadmap")]),
              ("Strategy", [(13, "SWOT")])]
    total_w = 5 * cw + 4 * ag
    sw_ = (total_w - 5 * GAP) // 6
    for i, (stage, frames) in enumerate(stages):
        body = "**%s**\n" % stage + "\n".join(frame_link(n, lab) for n, lab in frames)
        b.block(cx + i * (sw_ + GAP), cy, sw_, body, color="white", h=130, align="left")
    cy += 130 + 32
    b.text(cx, cy, "Live demo: https://bhuvan171.github.io/blockwise/ · Code: https://github.com/Bhuvan171/blockwise "
                   "· Tip: press Present (top right) to step through the frames as slides.", size="body",
           wrap=total_w)
    return b.end()


PERSONAS = [
    dict(head="**Arjun Mehta**, 38\nHotel contracting lead, Middle East and South-East Asia\n*Primary user*",
         quote="*“Block too little and agents hear ‘sold out’. Block too much and finance asks why we ate the rooms.”*",
         goals=["Lock deep rates before peak weeks", "Never turn an agent away on a peak night",
                "Defend every commitment with a reason"],
         pains=["Plans on last year's volume in a spreadsheet", "Finds unsold blocks only at the release date",
                "Events and shocks wreck the plan", "Guesses which contract fits which week"],
         today=["Supplier emails, extranets, a 40-tab workbook", "Negotiates 8 to 12 weeks before arrival",
                "Reviews blocks once a month"],
         gives=["A buy list per hotel-week, with contract and reason", "A risk dial: Max profit, Balanced, Careful",
                "A quote desk: take, counter or wait"]),
    dict(head="**Kavita Rao**, 46\nFinance controller, treasury and risk\n*Approver*",
         quote="*“Don't show me the average. Show me the bad case, and what the next crore buys.”*",
         goals=["Cap prepaid cash at risk", "No single region carrying the quarter", "A predictable margin"],
         pains=["Prepaid exposure is invisible until it is a write-off", "COVID-era losses still in memory",
                "Budgets set by habit, not by return"],
         today=["Approves the quarterly block budget", "Tracks exposure by region after the fact"],
         gives=["Budget frontier and the value of the next ₹1 Cr", "Worst-5% outcome beside expected profit",
                "Region cap: at most 60% of prepaid in one region"]),
    dict(head="**Rahul Sharma**, 31\nOwner of a small travel agency in Jaipur, TBO customer\n*End customer*",
         quote="*“When my client is ready to pay, I need a confirmed room in seconds, not ‘on request’.”*",
         goals=["Instant confirmation in peak and event weeks", "Net rates he can mark up",
                "One supplier he can trust"],
         pains=["‘Sold out’ on peak nights sends him to a rival platform", "Rates jump when the market fills",
                "One lost family booking can cost him the client"],
         today=["Books Dubai, Singapore and Bali packages and MICE groups", "Compares 2 to 3 B2B platforms per booking"],
         gives=["More confirmed rooms on sold-out nights", "Steadier net rates from contracted rooms"]),
    dict(head="**Mei Lin Tan**, 42\nRevenue manager, 4-star hotel in Singapore\n*Supplier*",
         quote="*“Commit early and I'll give you the rate. Release late and I can't resell the room.”*",
         goals=["Base occupancy secured early", "Partners who release on time", "Fair release terms"],
         pains=["Allotments handed back at the last minute", "Distributors who block, then dump",
                "No view of a partner's real demand"],
         today=["Offers blocks about 30% off and allotments about 20% off", "Asks for release 21 days out"],
         gives=["Earlier, steadier commitments sized to demand", "Releases planned before the deadline"]),
]


def personas(b, x, y):
    cx, cy = b.begin("1  Empathise · Personas", x, y)
    cw = 400
    rows = [("head", "white", None), ("quote", "white", None), ("goals", "green", "Goals"),
            ("pains", "pink", "Pains"), ("today", "white", "Today"), ("gives", "blue", "What Blockwise gives")]
    for key, color, label in rows:
        texts = []
        for p in PERSONAS:
            v = p[key]
            texts.append(("**%s**\n" % label + "\n".join("- " + s for s in v)) if label else v)
        h = max(est_h(t, cw) for t in texts) + 8
        for i, t in enumerate(texts):
            b.block(cx + i * (cw + GAP), cy, cw, t, color=color, h=h,
                    align="center" if key == "quote" else "left")
        cy += h + GAP
    return b.end()


def empathy(b, x, y):
    cx, cy = b.begin("2  Empathise · Empathy map for Arjun", x, y)
    b.text(cx, cy, "Arjun Mehta, hotel contracting lead, planning the January to March season", size="body")
    cy += 44
    qw = 3 * SW + 2 * GAP
    quads = [
        ("Says", ["“Let's block what we sold last year.”", "“Can we push the release date?”",
                  "“Who approved 400 rooms for that week?”"]),
        ("Thinks", ["Is this event week real demand or hype?", "If I'm wrong, my name is on the write-off.",
                    "Allotment or block? I'm guessing."]),
        ("Does", ["Copies last year's volumes into a spreadsheet", "Chases hotels for better rates by email",
                  "Releases rooms the night before the deadline"]),
        ("Feels", ["Anxious before every release deadline", "Blamed for both sold-outs and unsold rooms",
                   "Proud when a peak week sells through"]),
    ]
    for qi, (label, notes) in enumerate(quads):
        qx = cx + (qi % 2) * (qw + 48)
        qy = cy + (qi // 2) * (SH + 76)
        b.text(qx, qy, "**%s**" % label, size="body")
        for i, n in enumerate(notes):
            b.sticky(qx + i * (SW + GAP), qy + 34, n, color="white")
    cy += 2 * (SH + 76) + 10
    for qi, (label, color, notes) in enumerate([
            ("Pains", "pink", ["No view of the bad case", "Decisions run on gut feel", "Shocks arrive with no warning"]),
            ("Gains", "green", ["A defensible plan in minutes", "Fewer unsold rooms", "Confidence on peak weeks"])]):
        qx = cx + qi * (qw + 48)
        b.text(qx, cy, "**%s**" % label, size="body")
        for i, n in enumerate(notes):
            b.sticky(qx + i * (SW + GAP), cy + 34, n, color=color)
    return b.end()


JOURNEY = [
    ("Look ahead", "12 weeks out", "Pulls last year's sales for the quarter", "“Which weeks will spike this year?”", 0,
     "History shows no events, shocks or sold-out nights", "Forecast a range per hotel-night, with booking pace"),
    ("Set budget", "10 weeks out", "Asks finance for a prepaid budget", "“How much can I ask for without a fight?”",
     -1, "Budget set by habit, not by return", "Budget frontier: value of the next ₹1 Cr"),
    ("Negotiate", "8 to 10 weeks", "Emails hotels for block and allotment rates", "“Is this quote actually good?”",
     0, "No way to price a quote against demand", "Quote desk: take, counter or wait"),
    ("Commit", "8 weeks out", "Signs blocks at about last year's volume", "“Allotment or block? I'm guessing.”", -1,
     "Same contract for every week", "Contract mix per week: block, allotment, buy as needed"),
    ("Sell and watch", "8 to 3 weeks", "Watches bookings in a spreadsheet", "“Are we behind pace?”", 0,
     "Shock news arrives before the data does", "Circuit breaker pauses prepaid buying when forecasts break"),
    ("Release", "21 days out", "Rushes to hand back unsold allotment", "“Did I release too much?”", -2,
     "Rooms dumped late, hotel unhappy", "Releases planned from the forecast"),
    ("Stay and reconcile", "after the stay", "Counts unsold blocks and turned-away bookings",
     "“Whose fault was this?”", -2, "Lessons never reach next season's plan",
     "Score every plan against what really happened"),
]
FACES = {2: "😀", 1: "🙂", 0: "😐", -1: "😟", -2: "😣"}


def journey(b, x, y):
    cx, cy = b.begin("3  Empathise · Journey map today: Arjun's season", x, y)
    lw = 150
    col = lambda i: cx + lw + i * (SW + GAP)  # noqa: E731
    for i, st in enumerate(JOURNEY):
        b.block(col(i), cy, SW, "**%d · %s**\n%s" % (i + 1, st[0], st[1]), color="white", h=72)
    cy += 72 + GAP
    rows = [("Doing", 2, "white"), ("Thinking", 3, "white"), ("Feeling", None, None), ("Pain points", 5, "pink"),
            ("Blockwise opportunity", 6, "green")]
    for label, idx, color in rows:
        if idx is None:
            fh = 190
            b.text(cx, cy + fh / 2 - 12, "**%s**" % label, size="body", wrap=lw - 16)
            prev = None
            for i, st in enumerate(JOURNEY):
                s = st[4]
                fy = cy + (2 - s) * (fh - 56) / 4
                f = b.block(col(i) + SW / 2 - 28, int(fy), 56, FACES[s], color="white", h=56, shape="ellipse",
                            size="large")
                if prev:
                    b.arrow(prev, f, fs="right", ts="left", head=False)
                prev = f
            cy += fh + GAP
            continue
        b.text(cx, cy + SH / 2 - 12, "**%s**" % label, size="body", wrap=lw - 16)
        for i, st in enumerate(JOURNEY):
            b.sticky(col(i), cy, st[idx], color=color)
        cy += SH + GAP
    return b.end()


def mindmap(b, x0, y0, center, ccolor, branches, n_right, leaf_color="white", leaf_w=300):
    cw, bw, lgap, ggap = 250, 230, 14, 36
    ch = est_h(center, cw, "large")
    groups = []
    for label, leaves in branches:
        bh = est_h(label, bw)
        lhs = [max(52, est_h(l, leaf_w)) for l in leaves]
        lt = sum(lhs) + lgap * (len(lhs) - 1)
        groups.append(dict(label=label, leaves=leaves, bh=bh, lhs=lhs, lt=lt, gh=max(bh, lt)))
    right, left = groups[:n_right], groups[n_right:]
    side_h = lambda gs: sum(g["gh"] for g in gs) + ggap * (len(gs) - 1)  # noqa: E731
    total = max(side_h(right), side_h(left), ch)
    xl_leaf = x0
    xl_br = x0 + leaf_w + 64
    xc = xl_br + bw + 96
    xr_br = xc + cw + 96
    xr_leaf = xr_br + bw + 64
    c = b.block(xc, int(y0 + total / 2 - ch / 2), cw, center, color=ccolor, h=ch, size="large")
    for gs, is_right in ((right, True), (left, False)):
        gy = y0 + (total - side_h(gs)) / 2
        for g in gs:
            bx = xr_br if is_right else xl_br
            br = b.block(bx, int(gy + (g["gh"] - g["bh"]) / 2), bw, "**%s**" % g["label"], color="white", h=g["bh"])
            b.arrow(c, br, fs="right" if is_right else "left", ts="left" if is_right else "right", curve=True)
            ly = gy + (g["gh"] - g["lt"]) / 2
            for leaf, lh in zip(g["leaves"], g["lhs"]):
                lf = b.block(xr_leaf if is_right else xl_leaf, int(ly), leaf_w, leaf, color=leaf_color, h=lh,
                             align="left")
                b.arrow(br, lf, fs="right" if is_right else "left", ts="left" if is_right else "right",
                        head=False, curve=True)
                ly += lh + lgap
            gy += g["gh"] + ggap


def rootcause(b, x, y):
    cx, cy = b.begin("4  Define · Mind map: why commitments go wrong", x, y)
    mindmap(b, cx, cy, "Unsold rooms **and** turned-away agents", "pink", [
        ("Demand is uncertain", ["Seasons and event weeks", "Shocks: pandemic, airline collapse, conflict",
                                 "About 15% of bookings land in the last 3 weeks"]),
        ("Contracts are rigid", ["Prepaid blocks are non-refundable", "Allotments must go back 21 days out",
                                 "Buying as needed vanishes when the market sells out"]),
        ("Decisions run on habit", ["“Block last year's volume”", "One contract for every week",
                                    "No view of the bad case"]),
        ("Data has gaps", ["Turned-away demand is invisible", "Sold-out nights hide true demand",
                           "Supplier quotes live in email"]),
        ("Teams are siloed", ["Finance sets budgets without a demand view", "Contracting carries the blame",
                              "Agents' failed searches never reach planners"]),
    ], n_right=3, leaf_color="pink", leaf_w=290)
    return b.end()


def problem(b, x, y):
    cx, cy = b.begin("5  Define · Problem and How Might We", x, y)
    lw, rw = 640, 3 * SW + 2 * GAP
    ps = b.block(cx, cy, lw, "**Problem**\nTBO's contracting team must decide, weeks ahead, which hotel rooms and "
                            "flight seats to commit to, how many, and under which contract, without knowing demand. "
                            "Commit too much and unsold prepaid rooms become losses. Commit too little and agents "
                            "are turned away on the nights that matter most.", color="white", align="left")
    b.block(cx, ps["y"] + ps["h"] + GAP, lw, "**Point of view**\nArjun needs a commitment plan he can defend for "
                                             "every hotel-week, because today's habit of blocking last year's "
                                             "volume loses money in both directions.", color="white", align="left")
    b.text(cx + lw + GAP, cy, "**How might we…**", size="body")
    hmw = ["HMW know how many rooms a week will need, as a range?", "HMW mix blocks, allotments and buying as needed week by week?",
           "HMW show finance the bad case, not just the average?", "HMW price a supplier quote before signing it?",
           "HMW protect the plan when a shock breaks the forecast?", "HMW prove the plan works before anyone trusts it?"]
    for i, t in enumerate(hmw):
        b.sticky(cx + lw + GAP + (i % 3) * (SW + GAP), cy + 34 + (i // 3) * (SH + GAP), t, color="yellow")
    by = cy + 34 + 2 * (SH + GAP) + 16
    cw3 = (lw + GAP + rw - 2 * GAP) // 3
    for i, (t, c) in enumerate([
        ("**Success looks like**\n- Profit as a share of perfect hindsight\n- Share of demand served\n"
         "- Unsold prepaid cost\n- Worst-5% outcome\n- Rounds that lose money", "green"),
        ("**Constraints**\n- Prepaid budget\n- At most 60% of prepaid in one region\n"
         "- Allotment at most last year's production\n- Release 21 days before arrival\n"
         "- No buying once the market sells out", "white"),
        ("**Out of scope for Round 1**\n- Setting selling prices\n- Flight deposit and name-change terms\n"
         "- Live TBO data feeds", "white")]):
        b.block(cx + i * (cw3 + GAP), by, cw3, t, color=c, align="left", h=200)
    return b.end()


BRAINSTORM = [
    ("Forecast demand", ["Quantile forecast, not one number ✓ ●●●", "Use rooms already on the books ✓ ●●",
                         "Same night last year as a signal ✓", "Foundation model, Chronos-2 ✓",
                         "Ensemble of models ✓ ●", "Search and look-to-book logs as a demand signal",
                         "Event calendar: expos, concerts, festivals"]),
    ("Mix the contracts", ["Treat allotment as a free option on early demand ✓ ●●●",
                           "Block only the confident floor ✓ ●●", "Buy the rest as needed, unless sold out ✓",
                           "Cap allotments at last year's production ✓", "Negotiate later release dates",
                           "Re-plan weekly as bookings arrive ●●"]),
    ("Control the risk", ["Optimise the worst 5%, not just the average ✓ ●●●",
                          "Risk dial: Max profit, Balanced, Careful ✓ ●●", "Region cap: at most 60% of prepaid ✓",
                          "Stress tests: Middle East, airline collapse, rupee slide ✓",
                          "Circuit breaker when forecasts break ✓ ●●", "Hedge currency on prepaid blocks"]),
    ("Make it usable", ["Buy list with a reason per line ✓ ●●●", "Allotment calendar: solid, hatched, outline ✓",
                        "Quote desk: take, counter or wait ✓ ●●", "Type a budget, get a plan ✓",
                        "Approval register and CSV export ✓", "Alert when a week drifts off plan"]),
    ("Prove it", ["Walk-forward backtest on real bookings ✓ ●●●", "Replay COVID on official Singapore data ✓ ●●",
                  "Fair baselines, fixed before results ✓", "Score against perfect hindsight ✓",
                  "Disclose every change made after seeing results ✓"]),
    ("Parked", ["Resell unused blocks to other distributors", "Auto-negotiation bot for supplier quotes",
                "Optimise selling prices too", "Million-scenario runs on GPU", "Rank suppliers by integration value"]),
]


def brainstorm(b, x, y):
    cx, cy = b.begin("6  Ideate · Brainstorm, clustered and dot-voted", x, y)
    width = 6 * SW + 5 * GAP
    b.block(cx, cy, width, "**HMW commit the right inventory, under the right contract, at the right risk?**\n"
                           "Silent ideation, then clustering, then 3 dot votes each. ✓ = built in Round 1.",
            color="white", h=80)
    cy += 80 + 40
    for ci, (head, ideas) in enumerate(BRAINSTORM):
        x0 = cx + ci * (SW + GAP)
        b.text(x0, cy, "**%s**" % head, size="body")
        for i, t in enumerate(ideas):
            b.sticky(x0, cy + 36 + i * (SH + 16), t, color="yellow")
    return b.end()


def prioritise(b, x, y):
    cx, cy = b.begin("7  Ideate · Prioritise: impact × effort", x, y)
    qw, qh = 2 * SW + 3 * 20, 40 + 2 * (SH + 16) + 20
    b.text(cx, cy, "**Impact ↑**", size="body")
    gy = cy + 36
    quads = [
        ("Quick wins", "high impact, low effort", ["Risk dial ✓", "Buy list with reasons ✓", "Circuit breaker ✓",
                                                    "Region cap ✓"]),
        ("Big bets", "high impact, high effort", ["Forecast + worst-case optimiser ✓", "Quote desk ✓",
                                                  "Weekly re-planning (next)", "TBO data adapter (next)"]),
        ("Fill-ins", "low impact, low effort", ["CSV export ✓", "Allotment calendar view ✓", "Drift alert"]),
        ("Later", "low impact, high effort", ["Million-scenario GPU runs", "Auto-negotiation bot",
                                              "Block resale marketplace"]),
    ]
    for qi, (name, sub, notes) in enumerate(quads):
        qx = cx + (qi % 2) * (qw + GAP)
        qy = gy + (qi // 2) * (qh + GAP)
        b.block(qx, qy, qw, "", color="white", h=qh)
        b.text(qx + 20, qy + 12, "**%s** · %s" % (name, sub), size="small")
        for i, t in enumerate(notes):
            b.sticky(qx + 20 + (i % 2) * (SW + 20), qy + 44 + (i // 2) * (SH + 16), t, color="yellow")
    b.text(cx + 2 * qw + GAP - 110, gy + 2 * qh + GAP + 12, "**Effort →**", size="body")
    return b.end()


def product_map(b, x, y):
    cx, cy = b.begin("8  Ideate · Mind map: Blockwise, the product", x, y)
    mindmap(b, cx, cy, "**Blockwise**\nwhat to commit, how much, which contract", "blue", [
        ("Inputs", ["Real bookings and booking pace", "SingStat arrivals, rates and occupancy",
                    "Supplier quotes", "Next: TBO search and look-to-book logs"]),
        ("Forecast", ["Quantile regression per horizon week", "Gradient-boosted with conformal bands",
                      "Chronos-2, zero-shot", "Ensemble: 21.8% typical error"]),
        ("Scenarios", ["150 to 200 correlated futures", "Stress shocks by region", "Six ‘wrong’ worlds for robustness"]),
        ("Optimiser", ["Max expected profit − λ × worst-5% loss", "Budget, region and allotment caps",
                       "Penalty per turned-away booking", "Value of the next ₹1 Cr"]),
        ("Safeguards", ["Circuit breaker on broken forecasts", "Forecast cap at 1.5× the record month",
                        "Stop the run if a benchmark fails"]),
        ("Outputs", ["Buy list with a reason per line", "Allotment calendar", "Budget frontier",
                     "Quote desk", "Exposure by region"]),
        ("Proof", ["Real backtest: 92.7% of hindsight", "Singapore COVID replay", "Robustness: best bad case 6 of 6",
                   "Forecaster benchmark"]),
    ], n_right=4, leaf_w=290)
    return b.end()


def how_it_works(b, x, y):
    cx, cy = b.begin("9  Prototype · How it works", x, y)
    steps = ["**Data**\nbookings, rates, occupancy", "**Features**\nonly what was known that day",
             "**Forecast**\na range per hotel-night", "**Futures**\n150 to 200 correlated scenarios",
             "**Optimiser**\nprofit vs worst 5%, within budget", "**Plan**\nbuy list, calendar, frontier",
             "**Score**\non outcomes it never saw"]
    bw, sgap = 190, 64
    boxes = []
    for i, s in enumerate(steps):
        boxes.append(b.block(cx + i * (bw + sgap), cy, bw, s, color="blue", h=104))
        if i:
            b.arrow(boxes[-2], boxes[-1], fs="right", ts="left")
    cy += 104 + 96
    b.text(cx, cy, "**Three contracts it mixes, week by week**", size="body")
    cards = ["**Hard block**\nPrepaid, non-refundable, about 30% off.\nCheapest unit, but you eat it if unsold.",
             "**Allotment**\nPay per room used, about 20% off. Unsold rooms go back free 21 days out.\n"
             "A free option on early demand.",
             "**Buy as needed**\nMarket rate at sale time, about 10% off.\nNo risk, thin margin, gone when the market "
             "sells out."]
    cwid = 360
    hh = max(est_h(c, cwid) for c in cards) + 8
    for i, c in enumerate(cards):
        b.block(cx + i * (cwid + GAP), cy + 36, cwid, c, color="white", h=hh, align="left")
    sx = cx + 3 * (cwid + GAP) + 40
    sg = b.block(sx, cy + 36, 2 * bw + sgap + 30,
                 "**Safeguards**\n- Circuit breaker: no new prepaid blocks while the forecast is more than 2× off\n"
                 "- Forecast capped at 1.5× the record month\n- Falls back to buying as needed if a solve fails",
                 color="white", h=hh, align="left")
    b.arrow(sg, boxes[4], fs="top", ts="bottom", dash=True, label="guards")
    return b.end()


STORY = [
    "**1 · Twelve weeks out**\nDubai has an expo week in February. Last year Arjun blocked 400 rooms and ate the unsold ones.",
    "**2 · Budget and risk**\nHe types a ₹150 Cr budget and sets the dial to Balanced. Blockwise runs 150 futures.",
    "**3 · The plan**\nFor the expo week: block 220, allot 180, buy the rest as needed, each line with its reason.",
    "**4 · Approval**\nKavita checks the worst-5% outcome and what the next ₹1 Cr would add, then approves.",
    "**5 · The shock**\nFlights into the region are cut. The circuit breaker pauses new prepaid blocks; allotments go back free.",
    "**6 · Expo night**\nThe market is sold out, but Rahul in Jaipur confirms 3 rooms for a family in seconds.",
]


def storyboard(b, x, y):
    cx, cy = b.begin("10  Prototype · Storyboard: the expo week", x, y)
    pw, ph, g = 480, 320, 48
    ch = max(est_h(s, pw) for s in STORY) + 4
    for i, (fn, cap) in enumerate(zip(PANELS, STORY)):
        px = cx + (i % 3) * (pw + g)
        py = cy + (i // 3) * (ph + GAP + ch + g)
        b.image(px, py, pw, ph, fn(), "panel-%d" % (i + 1))
        b.block(px, py + ph + GAP, pw, cap, color="white", h=ch, align="left")
    return b.end()


def evidence(b, x, y):
    cx, cy = b.begin("11  Test · What the prototype proved", x, y)
    cols = [("c1", 440, "What we tested"), ("c2", 150, "Blockwise"), ("c3", 210, "Best fixed rule"),
            ("c4", 120, "Data")]
    rows = [
        ["Profit, share of perfect hindsight (2 hotels, 15 rounds)", "92.7%", "89.8%", "Real"],
        ["Rounds won against the best fixed rule", "12 of 15", "—", "Real"],
        ["Unsold prepaid cost (vs the rule set in advance)", "€20k", "€41k", "Real"],
        ["Rounds that lost money", "0", "0", "Real"],
        ["Singapore COVID loss, 2020 to 2021", "−S$2.56M", "−S$3.07M", "Real"],
        ["Singapore total profit, share of hindsight", "79.3%", "80.1%", "Real"],
        ["Best bad case in untested worlds", "6 of 6", "0 of 6", "Synthetic"],
        ["Forecast error 8 to 12 weeks out (WAPE)", "21.8%", "50% (last year)", "Real"],
        ["Profit in euros, same 15 rounds", "€750,527", "€727,342", "Real"],
        ["Ahead in re-runs that change one assumption", "10 of 10", "—", "Real"],
    ]
    fills = {"r%d" % (i + 2): {"c2": "green"} for i in (0, 1, 2, 4, 6, 7, 8, 9)}
    t = b.table(cx, cy, cols, rows, fills)
    b.text(cx, cy + t["h"] + 14, "Prepaid capped at 50% of last year's volume. Best fixed rule chosen with hindsight.", size="small",
           wrap=sum(c[1] for c in cols))
    ly = cy + t["h"] + 62
    b.text(cx, ly, "**Limits we state up front**", size="body")
    lim = ["No TBO data yet: the real proof is 2 hotels in Portugal", "The TBO-like portfolio is synthetic",
           "Only 15 real planning rounds", "Singapore safeguards were added after the first replay (disclosed)",
           "Forecast bands run slightly narrow: 74% vs 80%", "On total Singapore profit it ties the best rule"]
    for i, s in enumerate(lim):
        b.sticky(cx + (i % 3) * (SW + GAP + 50), ly + 36 + (i // 3) * (int(round((SW + 50) * 0.652)) + GAP), s,
                 color="pink", w=SW + 50)
    return b.end()


def roadmap(b, x, y):
    cx, cy = b.begin("12  Test · Roadmap and open questions", x, y)
    cw = 270
    cols = [
        ("Now · built in Round 1", "blue", ["Forecast, futures and worst-case optimiser", "Buy list, calendar and frontier",
                                            "Quote desk and typed-budget planner", "Real backtest and Singapore replay",
                                            "Live site on GitHub Pages"]),
        ("Next · Round 2", "green", ["Weekly re-planning as bookings arrive",
                                     "TBO data adapter: search logs, sold-outs, look-to-book",
                                     "Buy-by timing: when to commit", "Flight terms: deposits and name changes",
                                     "Live supplier quotes in the quote desk"]),
        ("Later", "white", ["Selling-price optimisation", "Supplier ranking by integration value",
                            "Faster decomposition solver", "Million-scenario tests on GPU"]),
        ("Open questions for TBO", "white", ["Which contract terms do top hotels really offer?",
                                             "Can we get search logs with sold-out flags?",
                                             "Who signs off budgets: contracting or finance?",
                                             "How often can a plan change after signing?"]),
    ]
    for ci, (head, color, cards) in enumerate(cols):
        x0 = cx + ci * (cw + GAP)
        b.text(x0, cy, "**%s**" % head, size="body")
        yy = cy + 36
        for c in cards:
            blk = b.block(x0, yy, cw, c, color=color, align="left", min_h=64)
            yy += blk["h"] + 16
    return b.end()


SWOT = [
    # (title, subtitle, sticky colour, notes). Every number is from the main README.
    ("Strengths", "what Blockwise does well", "blue", [
        "Plans all 3 contract types together: hard block, allotment and buy as needed",
        "Real bookings: 92.7% of perfect-hindsight profit vs 89.8% for the best fixed rule, even one picked with hindsight",
        "Won 12 of 15 real planning rounds, and halved unsold prepaid cost (€20k vs €41k)",
        "Plans for the bad case (worst 5% of futures), with a risk dial from Max profit to Careful",
        "Circuit breaker: 17% smaller COVID loss than the best rule in the Singapore replay",
        "Explains every buy with a reason, and states its limits up front",
    ]),
    ("Weaknesses", "where Blockwise falls short today", "pink", [
        "No TBO data yet: the real-data proof covers 2 hotels in Portugal",
        "The TBO-like portfolio (12 destinations, 4 flight routes) is synthetic",
        "Only 15 real planning rounds: a small sample",
        "Round 1 forecast bands run slightly narrow: they held 74% of the time vs the 80% target",
        "In calm years simple rules do as well or better (Singapore 2011–19: 91.4% vs up to 93.1%)",
        "Without its safeguards it loses to simple rules (74.7% vs 79.8% in Singapore)",
    ]),
    ("Opportunities", "outside chances we can use", "green", [
        "TBO search logs with sold-out flags and look-to-book data could sharpen the forecast",
        "Sold-out event weeks: buying as needed fails just when demand peaks, so planning ahead pays most",
        "Quote desk: price a supplier's quote before signing and negotiate from evidence",
        "Flights: add deposit and name-change terms to the 4 seat routes already modelled",
        "Finance budgeting: the frontier shows where more budget stops paying (at ₹137.5 Cr the next ₹1 Cr adds only ₹0.05 Cr)",
        "Open forecasting models keep improving: adding Chronos-2 to our ensemble gave the lowest error (21.8%)",
    ]),
    ("Threats", "outside risks to the plan", "pink", [
        "Shocks break forecasts: pandemics, airline collapses, regional disruptions, currency slides",
        "Real contract rates may differ from our assumptions (block −30%, allotment −20%); with smaller discounts Blockwise still leads, 90.3% vs 87.6%",
        "One shock can hit a whole region at once, so prepaid money must not pile up in one place",
        "After COVID the forecast kept missing by over 2×: the Singapore breaker stayed on for 33 months",
        "Turned-away demand isn't recorded on sold-out nights, so peaks look smaller than they were",
        "Habit: teams may stick to blocking last year's volume and keep spreadsheets",
    ]),
]

TOWS = [
    ("S + O · Push", "Pilot on TBO's top destinations with their search logs, using the optimiser already proven "
                     "on real bookings."),
    ("W + O · Fix", "Build the TBO data adapter in Round 2, so the proof runs on TBO's own demand instead of "
                    "2 hotels in Portugal."),
    ("S + T · Defend", "Keep the circuit breaker and the 60% region cap on by default, and stress-test every plan "
                       "against shocks."),
    ("W + T · Avoid", "Start with allotments and small blocks while trust builds, and show finance the bad case, "
                      "not just the average."),
]


def swot(b, x, y):
    cx, cy = b.begin("13  Strategy · SWOT analysis", x, y)
    lw, sw, sg = 120, 270, 16                       # row-label width, sticky width, sticky gap
    shh = int(round(sw * 0.652))
    qw = 20 + 3 * sw + 2 * sg + 20
    qh = 52 + 2 * shh + sg + 20
    qx = [cx + lw + GAP, cx + lw + GAP + qw + GAP]
    qy = [cy + 40 + GAP, cy + 40 + GAP + qh + GAP]
    b.block(qx[0], cy, qw, "**Helpful** to winning", color="white", h=40)
    b.block(qx[1], cy, qw, "**Harmful** to winning", color="white", h=40)
    b.block(cx, qy[0], lw, "**Internal**\nBlockwise itself", color="white", h=qh)
    b.block(cx, qy[1], lw, "**External**\nthe market and TBO", color="white", h=qh)
    for qi, (name, sub, color, notes) in enumerate(SWOT):
        x0, y0 = qx[qi % 2], qy[qi // 2]
        b.block(x0, y0, qw, "", color="white", h=qh)
        b.text(x0 + 20, y0 + 14, "**%s** · %s" % (name, sub), size="body")
        for i, t in enumerate(notes):
            b.sticky(x0 + 20 + (i % 3) * (sw + sg), y0 + 52 + (i // 3) * (shh + sg), t, color=color, w=sw)
    ty = qy[1] + qh + 40
    b.text(qx[0], ty, "**So what? Our strategy from the SWOT (TOWS)**", size="body")
    tw = (2 * qw + GAP - 3 * GAP) // 4
    for i, (head, body) in enumerate(TOWS):
        b.block(qx[0] + i * (tw + GAP), ty + 36, tw, "**%s**\n%s" % (head, body), color="white", align="left",
                h=150)
    b.text(qx[0], ty + 36 + 150 + 20, "Internal = about Blockwise itself · External = the market and TBO · "
                                      "Numbers are from the main README. The TBO-like portfolio is synthetic; the "
                                      "backtest and Singapore replay use real data with stated contract-rate "
                                      "assumptions.", size="small", wrap=2 * qw + GAP)
    return b.end()


def build():
    b = Board()
    sh = start_here(Board(), 0, 0)["h"]        # measure frame 0 first so the header can sit above it
    start_y = -(sh + 200)
    header(b, top=start_y - 340)
    rowgap, colgap = 220, 160

    def row(y, makers):
        x, hmax = 0, 0
        for mk in makers:
            s = mk(b, x, y)
            x += s["w"] + colgap
            hmax = max(hmax, s["h"])
        return y + hmax + rowgap

    y = 0
    y = row(y, [personas, empathy])
    y = row(y, [journey, rootcause])
    y = row(y, [problem, brainstorm, prioritise])
    y = row(y, [product_map, how_it_works])
    y = row(y, [storyboard, evidence, roadmap])
    y = row(y, [swot])
    start_here(b, 0, start_y)
    return b


# =========================================================================================================
# Whiteboard (claude.ai) export
# =========================================================================================================

def to_whiteboard(b, out_dir):
    os.makedirs(os.path.join(out_dir, "elements"), exist_ok=True)
    order = []
    for it in b.items:
        k = it["kind"]
        if k == "section":
            el = {"type": "container", "x": it["x"], "y": it["y"], "w": it["w"], "h": it["h"], "text": it["title"]}
        elif k in ("block", "sticky"):
            kind = {"rounded": "rounded", "ellipse": "ellipse", "rect": "rect"}.get(it.get("shape", "rounded"), "rounded")
            el = {"type": "shape", "kind": kind, "x": it["x"], "y": it["y"], "w": it["w"], "h": it["h"],
                  "color": it["color"], "size": it.get("size", "body"), "text": it["text"]}
            if it.get("align", "center") != "center":
                el["textAlign"] = it["align"]
        elif k == "text":
            el = {"type": "text", "x": it["x"], "y": it["y"], "text": it["text"], "size": it["size"]}
            if it.get("wrap"):
                el["wrap"] = it["wrap"]
        elif k == "arrow":
            el = {"type": "arrow", "from": it["a"], "to": it["b"]}
            if it["fs"]:
                el["fromSide"], el["toSide"] = it["fs"], it["ts"]
            if it["label"]:
                el["label"] = it["label"]
            if not it["head"]:
                el["head"] = "none"
            if it["dash"]:
                el["dash"] = True
        elif k == "image":
            el = {"type": "image", "x": it["x"], "y": it["y"], "w": it["w"], "h": it["h"], "by": "claude",
                  "style": "marker", "src": svg_data_uri(it["svg"])}
        elif k == "table":
            cols = {cid: {"at": i + 1, "w": w} for i, (cid, w, _) in enumerate(it["cols"])}
            rows = {"r1": dict({"at": 1}, **{cid: head for cid, _, head in it["cols"]})}
            for ri, r in enumerate(it["rows"]):
                rows["r%d" % (ri + 2)] = dict({"at": ri + 2}, **{c[0]: v for c, v in zip(it["cols"], r)})
            el = {"type": "table", "x": it["x"], "y": it["y"], "cols": cols, "rows": rows, "fills": it["fills"]}
        else:
            raise ValueError(k)
        with open(os.path.join(out_dir, "elements", it["id"] + ".json"), "w") as f:
            json.dump(el, f, ensure_ascii=False)
        order.append(it["id"])
    with open(os.path.join(out_dir, "board_meta.json"), "w") as f:
        json.dump({"v": 1, "title": BOARD_TITLE, "order": order}, f)
    return order


# =========================================================================================================
# Miro export (REST API v2)
# =========================================================================================================

API = "https://api.miro.com/v2"
HEX = {"yellow": "#fff6b6", "pink": "#ffd9e2", "green": "#d8f3cf", "blue": "#d6e6ff", "white": "#ffffff",
       "peach": "#ffe2c7", "purple": "#e8dcff"}
STICKY = {"yellow": "light_yellow", "pink": "light_pink", "green": "light_green", "blue": "light_blue"}
INK = "#1a1a1a"
FONT = {"small": "14", "body": "16", "large": "28", "title": "48", "huge": "96"}


def html(text):
    out = []
    for line in text.split("\n"):
        line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if line.startswith("- "):
            line = "• " + line[2:]
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"\*(.+?)\*", r"<em>\1</em>", line)
        out.append("<p>%s</p>" % line)
    return "".join(out)


class Miro:
    def __init__(self, token, dry_run=False):
        self.token, self.dry, self.log, self.n = token, dry_run, [], 0

    def call(self, method, path, body=None, multipart=None):
        if self.dry:
            self.n += 1
            self.log.append({"method": method, "path": path, "body": body,
                             "multipart": {k: json.loads(v[2]) for k, v in (multipart or {}).items()
                                           if k != "resource"}})
            return {"id": "dry%d" % self.n, "viewLink": "https://miro.com/app/board/DRY-RUN/"}
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
        if multipart:
            boundary = uuid.uuid4().hex
            parts = []
            for name, (fname, ctype, data) in multipart.items():
                disp = 'form-data; name="%s"' % name + ('; filename="%s"' % fname if fname else "")
                parts.append(("--%s\r\nContent-Disposition: %s\r\nContent-Type: %s\r\n\r\n" % (boundary, disp, ctype))
                             .encode() + data + b"\r\n")
            data = b"".join(parts) + ("--%s--\r\n" % boundary).encode()
            headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
        else:
            data = json.dumps(body).encode() if body is not None else None
            headers["Content-Type"] = "application/json"
        for attempt in range(6):
            req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "replace")
                if e.code == 429 or e.code >= 500:
                    time.sleep(float(e.headers.get("Retry-After") or 2 * (attempt + 1)))
                    continue
                raise SystemExit("Miro API %s %s failed with %d:\n%s\nRequest: %s"
                                 % (method, path, e.code, msg, json.dumps(body)[:600] if body else "(multipart)"))
            except urllib.error.URLError as e:
                if "CERTIFICATE" in str(e).upper():
                    raise SystemExit("SSL certificate error. On macOS run the 'Install Certificates.command' that "
                                     "ships with python.org Python, or use a Homebrew Python.\n%s" % e)
                time.sleep(2 * (attempt + 1))
        raise SystemExit("Miro API %s %s kept failing; try again in a minute." % (method, path))


def push_miro(b, token, board_id=None, dry_run=False, dx=0, dy=0, png_dir=None):
    m = Miro(token, dry_run)
    if not board_id:
        res = m.call("POST", "/boards", {"name": "Blockwise · Design thinking",
                                         "description": "Personas, empathy map, journey, mind maps, brainstorm, "
                                                        "storyboard and evidence for Blockwise (TBO VoyageHack 4.0)."})
        board_id, link = res["id"], res.get("viewLink")
    else:
        link = "https://miro.com/app/board/%s/" % board_id
    base = "/boards/%s" % board_id
    ids, secs = {}, {}
    total = len(b.items)

    def pos(it, h=None):
        h = it["h"] if h is None else h
        cx, cy = it["x"] + it["w"] / 2.0, it["y"] + h / 2.0
        if it.get("parent"):
            s = secs[it["parent"]]
            return {"x": round(cx - s["x"], 1), "y": round(cy - s["y"], 1), "origin": "center"}
        return {"x": round(cx + dx, 1), "y": round(cy + dy, 1), "origin": "center"}

    def parent(it, body):
        if it.get("parent"):
            body["parent"] = {"id": ids[it["parent"]]}
        return body

    for n, it in enumerate(b.items, 1):
        k = it["kind"]
        if k == "section":
            secs[it["id"]] = it
            res = m.call("POST", base + "/frames", {
                "data": {"title": it["title"], "format": "custom", "type": "freeform"},
                "style": {"fillColor": "#ffffff"},
                "position": {"x": it["x"] + it["w"] / 2.0 + dx, "y": it["y"] + it["h"] / 2.0 + dy, "origin": "center"},
                "geometry": {"width": it["w"], "height": it["h"]}})
        elif k == "sticky" and it["color"] in STICKY:
            res = m.call("POST", base + "/sticky_notes", parent(it, {
                "data": {"content": html(it["text"]), "shape": "rectangle"},
                "style": {"fillColor": STICKY[it["color"]], "textAlign": "center", "textAlignVertical": "middle"},
                "position": pos(it), "geometry": {"width": it["w"]}}))
        elif k in ("block", "sticky"):
            shape = {"ellipse": "circle", "rect": "rectangle"}.get(it.get("shape"), "round_rectangle")
            res = m.call("POST", base + "/shapes", parent(it, {
                "data": {"content": html(it["text"]), "shape": shape},
                "style": {"fillColor": HEX[it["color"]], "borderColor": "#c9ced6", "borderWidth": "1.5",
                          "color": INK, "fontSize": FONT[it.get("size", "body")],
                          "textAlign": it.get("align", "center"), "textAlignVertical": "middle"},
                "position": pos(it), "geometry": {"width": it["w"], "height": it["h"]}}))
        elif k == "text":
            res = m.call("POST", base + "/texts", parent(it, {
                "data": {"content": html(it["text"])},
                "style": {"fontSize": FONT[it["size"]], "color": INK, "textAlign": it.get("align", "left")},
                "position": pos(it), "geometry": {"width": it["w"]}}))
        elif k == "arrow":
            body = {"startItem": {"id": ids[it["a"]], "snapTo": it["fs"] or "auto"},
                    "endItem": {"id": ids[it["b"]], "snapTo": it["ts"] or "auto"},
                    "shape": "curved" if it["curve"] else "elbowed",
                    "style": {"strokeColor": "#4b586b", "strokeWidth": "1.5",
                              "endStrokeCap": "stealth" if it["head"] else "none",
                              "strokeStyle": "dashed" if it["dash"] else "normal"}}
            if it["label"]:
                body["captions"] = [{"content": it["label"]}]
            res = m.call("POST", base + "/connectors", body)
        elif k == "image":
            png = os.path.join(png_dir, it["name"] + ".png")
            if not os.path.exists(png) and not dry_run:
                raise SystemExit("Missing %s. Run `python3 miro/board.py png` first." % png)
            meta = parent(it, {"title": it["name"], "position": pos(it), "geometry": {"width": it["w"]}})
            blob = open(png, "rb").read() if os.path.exists(png) else b""
            res = m.call("POST", base + "/images", multipart={
                "data": (None, "application/json", json.dumps(meta).encode()),
                "resource": (it["name"] + ".png", "image/png", blob)})
        elif k == "table":
            x0 = it["x"]
            for ri, r in enumerate([[c[2] for c in it["cols"]]] + it["rows"]):
                xx = x0
                for ci, (cid, w, _) in enumerate(it["cols"]):
                    fill = it["fills"].get("r%d" % (ri + 1), {}).get(cid)
                    cell = {"x": xx, "y": it["y"] + ri * it["row_h"], "w": w, "h": it["row_h"],
                            "parent": it["parent"]}
                    txt = r[ci] if ri else "**%s**" % r[ci]
                    m.call("POST", base + "/shapes", parent(cell, {
                        "data": {"content": html(txt), "shape": "rectangle"},
                        "style": {"fillColor": HEX.get(fill, "#f4f6f8" if ri == 0 else "#ffffff"),
                                  "borderColor": "#c9ced6", "borderWidth": "1", "color": INK, "fontSize": "14",
                                  "textAlign": "left", "textAlignVertical": "middle"},
                        "position": pos(cell), "geometry": {"width": w, "height": it["row_h"]}}))
                    xx += w
            res = {"id": None}
        ids[it["id"]] = res["id"]
        if not dry_run and n % 25 == 0:
            print("  %d / %d items" % (n, total), flush=True)
    return board_id, link, m


# =========================================================================================================
# Miro MCP export (Canvas Composer SVG, one document per frame)
# =========================================================================================================

PAPER = {"yellow": "#fff6b6", "pink": "#ffc6c6", "green": "#adf0c7", "blue": "#c6dcff", "white": "#ffffff",
         "peach": "#f8d3af", "purple": "#dedaff"}


def _attr(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _rich(text, br="<br>"):
    out = []
    for line in text.split("\n"):
        if line.startswith("- "):
            line = "• " + line[2:]
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"\*(.+?)\*", r"<i>\1</i>", line)
        out.append(line.replace("`", ""))
    return br.join(out)


def _xml_body(text):
    # textArea bodies take literal markup: escape '&' only, keep our own tags
    return _rich(text.replace("&", "&amp;"), "<br/>")


def to_canvas(b):
    """Return [(name, svg)] documents: 'header' plus one per section, positioned absolutely."""
    docs, by_sec = [], {}
    for it in b.items:
        by_sec.setdefault(it["parent"], []).append(it)
    ids = {it["id"]: it for it in b.items}

    def el(it, ox, oy):
        k, x, y = it["kind"], it.get("x", 0) - ox, it.get("y", 0) - oy
        if k == "sticky" and it["color"] in STICKY:
            return ('<rect id="%s" data-type="sticky" x="%d" y="%d" width="%d" height="%d" data-color="%s" '
                    'data-content="%s"/>' % (it["id"], x, y, it["w"], it["h"], STICKY[it["color"]],
                                              _attr(_rich(it["text"]))))
        if k in ("block", "sticky"):
            fill = PAPER[it["color"]]
            stroke = ' stroke="#b0b0b0" stroke-width="2"' if it["color"] == "white" else ' stroke="none"'
            common = '%s data-content="%s" data-font-size="%s" data-text-color="#1a1a1a"%s' % (
                stroke, _attr(_rich(it["text"])), FONT[it.get("size", "body")],
                ' data-text-align="%s"' % it["align"] if it.get("align", "center") != "center" else "")
            if it.get("shape") == "ellipse":
                return '<ellipse id="%s" cx="%d" cy="%d" rx="%d" ry="%d" fill="%s"%s/>' % (
                    it["id"], x + it["w"] // 2, y + it["h"] // 2, it["w"] // 2, it["h"] // 2, fill, common)
            rx = "" if it.get("shape") == "rect" else ' rx="12"'
            return '<rect id="%s" x="%d" y="%d" width="%d" height="%d"%s fill="%s"%s/>' % (
                it["id"], x, y, it["w"], it["h"], rx, fill, common)
        if k == "text":
            w = it["wrap"] or int(it["w"] * 1.15) + 24
            return '<textArea id="%s" x="%d" y="%d" width="%d" font-size="%s" fill="#1a1a1a"%s>%s</textArea>' % (
                it["id"], x, y, w, FONT[it["size"]], ' font-weight="bold"' if it["size"] == "title" else "",
                _xml_body(it["text"]))
        if k == "arrow":
            a, c = ids[it["a"]], ids[it["b"]]
            pts = [(n["x"] + n["w"] / 2 - ox, n["y"] + n["h"] / 2 - oy) for n in (a, c)]
            extra = ""
            if it["fs"]:
                extra += ' data-start-side="%s" data-end-side="%s"' % (it["fs"], it["ts"])
            if it["head"]:
                extra += ' data-arrow="end"'
            if it["dash"]:
                extra += ' stroke-dasharray="5,5"'
            if it["label"]:
                extra += ' data-content="%s"' % _attr(it["label"])
            return ('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#313131" stroke-width="2" data-shape="%s" '
                    'data-start="%s" data-end="%s"%s/>' % (pts[0][0], pts[0][1], pts[1][0], pts[1][1],
                                                          "curved" if it["curve"] else "elbowed",
                                                          it["a"], it["b"], extra))
        if k == "table":
            cells = []
            for ri, r in enumerate([[c[2] for c in it["cols"]]] + it["rows"]):
                xx = x
                for ci, (cid, w, _) in enumerate(it["cols"]):
                    fill = it["fills"].get("r%d" % (ri + 1), {}).get(cid)
                    txt = r[ci] if ri else "**%s**" % r[ci]
                    cells.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="#b0b0b0" '
                                 'stroke-width="2" data-content="%s" data-font-size="14" data-text-color="#1a1a1a" '
                                 'data-text-align="left"/>' % (xx, y + ri * it["row_h"], w, it["row_h"],
                                                               PAPER.get(fill, "#f7f7f7" if ri == 0 else "#ffffff"),
                                                               _attr(_rich(txt))))
                    xx += w
            return "\n".join(cells)
        if k == "image":
            return None  # uploaded separately (miro/storyboard/*.png)
        raise ValueError(k)

    head = [el(it, 0, 0) for it in by_sec.get(None, []) if it["kind"] != "section"]
    docs.append(("header", "<svg>\n%s\n</svg>" % "\n".join(h for h in head if h)))
    for s in (it for it in b.items if it["kind"] == "section"):
        kids = [el(it, s["x"], s["y"]) for it in by_sec.get(s["id"], [])]
        body = "\n".join(k for k in sorted((k for k in kids if k), key=lambda t: t.startswith("<line")))
        docs.append((s["id"], '<svg>\n<g id="f%s" transform="translate(%d,%d)" data-frame="%s">\n'
                              '<rect data-type="frame" x="0" y="0" width="%d" height="%d" fill="#ffffff"/>\n%s\n'
                              '</g>\n</svg>' % (s["id"], s["x"], s["y"], _attr(s["title"]), s["w"], s["h"], body)))
    return docs


# =========================================================================================================
# Storyboard PNGs for Miro
# =========================================================================================================

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def render_pngs(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for i, fn in enumerate(PANELS, 1):
            svg = fn().replace("viewBox='0 0 480 320'", "viewBox='0 0 480 320' width='960' height='640'", 1)
            page = os.path.join(tmp, "p%d.html" % i)
            with open(page, "w") as f:
                f.write("<!doctype html><meta charset='utf-8'><body style='margin:0;background:#fff'>%s</body>" % svg)
            out = os.path.join(out_dir, "panel-%d.png" % i)
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            "--window-size=960,640", "--screenshot=" + out, "file://" + page],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("wrote", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("png")
    pm = sub.add_parser("miro")
    pm.add_argument("--board-id", help="fill this existing board instead of creating one")
    pm.add_argument("--dry-run", action="store_true", help="build requests without sending; writes miro/out/")
    pm.add_argument("--offset-x", type=float, default=0, help="shift the whole layout right (existing boards)")
    pm.add_argument("--offset-y", type=float, default=0)
    pw = sub.add_parser("whiteboard")
    pw.add_argument("out_dir")
    pc = sub.add_parser("canvas", help="write Canvas Composer SVGs for the Miro MCP")
    pc.add_argument("out_dir", nargs="?", default=os.path.join(HERE, "out", "canvas"))
    a = ap.parse_args()
    b = build()
    if a.cmd == "png":
        render_pngs(os.path.join(HERE, "storyboard"))
    elif a.cmd == "canvas":
        os.makedirs(a.out_dir, exist_ok=True)
        for name, svg in to_canvas(b):
            with open(os.path.join(a.out_dir, name + ".svg"), "w") as f:
                f.write(svg)
            print("%-8s %6d chars" % (name, len(svg)))
    elif a.cmd == "whiteboard":
        order = to_whiteboard(b, a.out_dir)
        print("%d elements -> %s" % (len(order), a.out_dir))
    else:
        token = os.environ.get("MIRO_TOKEN", "")
        if not token and not a.dry_run:
            raise SystemExit("Set MIRO_TOKEN first (see miro/README.md).")
        print("Building %d items in Miro..." % len(b.items), flush=True)
        bid, link, m = push_miro(b, token, a.board_id, a.dry_run, a.offset_x, a.offset_y,
                                 os.path.join(HERE, "storyboard"))
        if a.dry_run:
            os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
            p = os.path.join(HERE, "out", "miro_requests.json")
            with open(p, "w") as f:
                json.dump(m.log, f, ensure_ascii=False, indent=1)
            print("Dry run: %d requests written to %s" % (len(m.log), p))
        else:
            print("Done. Board: %s" % link)


if __name__ == "__main__":
    main()
