"""Storyboard drawings for the Blockwise design board (marker style, 480 x 320).

Each panel is one SVG string: no <text>, no style attributes, single-quoted
attributes, so it can go into a whiteboard data URI or be rendered to PNG for Miro.
"""

ROOT = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 480 320' fill='none' "
        "stroke='currentColor' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'>")

INK = "#1f2a37"
BLUE = "#2f6fd1"
NAVY = "#1f4f9c"
SKY = "#d9e6f7"
RED = "#e0564b"
GREEN = "#2e9e4f"
AMBER = "#f2b134"
WOOD = "#d69a5f"
WOOD2 = "#a86c3a"
WOOD3 = "#8a5530"
STEEL = "#a9b1bb"
SCREEN = "#2f3742"


def _desk_island():
    return ("<path d='M30 268 Q40 238 140 236 Q300 228 440 240 Q472 256 452 280 "
            "Q420 302 260 298 Q90 306 46 292 Q22 284 30 268 Z' fill='#ead8bd'/>")


def panel_plan_today():
    """12 weeks out: last year's spreadsheet, a circled event week, unsold invoices."""
    p = [ROOT,
         "<desc>A contracting desk twelve weeks before arrival, seen from the front: floor, office window, city "
         "skyline with one very tall tower, wall calendar, calendar header band, two calendar rings, calendar grid, "
         "a red circle round one February week, desk legs, desk side, desk top, desk front edge, coffee mug, mug "
         "handle, steam, blue pen, laptop lid, laptop display, spreadsheet header row, spreadsheet grid, one red "
         "spreadsheet cell, laptop base, keyboard line, stack of two invoices, red unsold stamp, invoice lines.</desc>",
         "<path d='M36 292 Q52 270 150 272 Q270 262 392 270 Q452 274 446 292 Q434 308 300 305 Q160 312 72 306 Q30 302 36 292 Z' fill='#ece6da'/>",
         "<rect x='290' y='26' width='150' height='96' rx='4' fill='#cfe6ff'/>",
         "<path d='M296 120 L296 92 L314 92 L314 78 L330 78 L330 98 L346 98 L346 60 L352 60 L355 32 L358 60 L364 60 "
         "L364 100 L382 100 L382 86 L400 86 L400 104 L416 104 L416 94 L434 94 L434 120 Z' fill='#86a7cf' stroke-width='1.5'/>",
         "<rect x='56' y='34' width='118' height='104' rx='4' fill='#ffffff'/>",
         f"<rect x='56' y='34' width='118' height='24' rx='4' fill='{BLUE}'/>",
         "<circle cx='82' cy='34' r='5' fill='#ffffff'/>",
         "<circle cx='148' cy='34' r='5' fill='#ffffff'/>",
    ]
    for y in (78, 98, 118):
        p.append(f"<line x1='56' y1='{y}' x2='174' y2='{y}' stroke-width='1.2'/>")
    for x in (86, 115, 144):
        p.append(f"<line x1='{x}' y1='58' x2='{x}' y2='138' stroke-width='1.2'/>")
    p += [
        f"<ellipse cx='130' cy='88' rx='22' ry='13' stroke='{RED}' stroke-width='3.5'/>",
        f"<rect x='124' y='240' width='14' height='52' fill='{WOOD3}'/>",
        f"<rect x='410' y='240' width='14' height='52' fill='{WOOD3}'/>",
        "<rect x='92' y='220' width='10' height='62' fill='#7a4a28'/>",
        f"<polygon points='84,204 114,224 114,240 84,220' fill='{WOOD3}'/>",
        f"<polygon points='84,204 404,204 434,224 114,224' fill='{WOOD}'/>",
        f"<rect x='114' y='224' width='320' height='16' fill='{WOOD2}'/>",
        f"<path d='M136 176 L164 176 L162 204 Q150 209 138 204 Z' fill='{AMBER}'/>",
        "<path d='M163 182 Q175 184 173 192 Q171 199 162 198'/>",
        "<path d='M146 168 Q141 160 147 154 Q153 147 149 140' stroke-width='1.5'/>",
        "<path d='M156 168 Q152 162 157 156' stroke-width='1.5'/>",
        f"<polygon points='118,214 168,208 169,211 119,217' fill='{BLUE}'/>",
        f"<rect x='198' y='100' width='132' height='100' rx='5' fill='{SCREEN}'/>",
        "<rect x='205' y='107' width='118' height='86' rx='2' fill='#f6f8fb'/>",
        f"<rect x='206' y='108' width='116' height='12' fill='{SKY}' stroke='none'/>",
        f"<rect x='266' y='150' width='28' height='12' fill='{RED}' stroke='none'/>",
    ]
    for y in (121, 135, 149, 163, 177):
        p.append(f"<line x1='205' y1='{y}' x2='323' y2='{y}' stroke-width='1.2'/>")
    for x in (235, 265, 295):
        p.append(f"<line x1='{x}' y1='107' x2='{x}' y2='193' stroke-width='1.2'/>")
    p += [
        f"<polygon points='190,200 338,200 352,214 176,214' fill='{STEEL}'/>",
        "<line x1='194' y1='207' x2='334' y2='207' stroke-width='1.2'/>",
        "<polygon points='352,180 398,176 404,196 358,200' fill='#ffffff'/>",
        "<polygon points='348,188 394,182 400,202 354,208' fill='#ffffff'/>",
        "<line x1='356' y1='194' x2='388' y2='190' stroke-width='1.2'/>",
        f"<polygon points='362,198 392,194 394,202 364,206' fill='{RED}' stroke='none'/>",
        "</svg>"]
    return "".join(p)


def panel_dial():
    """Budget typed, risk dial on Balanced, a fan of simulated futures."""
    p = [ROOT,
         "<desc>A laptop on a desk, close up: desk surface, potted plant, pot, three leaves, laptop lid, display, "
         "risk dial with green, amber and red segments, dial needle pointing to the middle, needle hub, three mode "
         "buttons with the middle one selected, chart axes, shaded band of outcomes, seven simulated future lines, "
         "bold median line, keyboard deck, key rows, trackpad, yellow sticky note with a scribbled budget.</desc>",
         _desk_island(),
         "<rect x='40' y='206' width='36' height='36' rx='3' fill='#d9724a'/>",
         "<ellipse cx='48' cy='190' rx='10' ry='20' fill='#59b36b'/>",
         "<ellipse cx='68' cy='186' rx='10' ry='24' fill='#4a9c5b'/>",
         "<ellipse cx='58' cy='176' rx='9' ry='22' fill='#6cc07c'/>",
         f"<rect x='110' y='40' width='260' height='176' rx='8' fill='{SCREEN}'/>",
         "<rect x='122' y='52' width='236' height='152' rx='3' fill='#f6f8fb'/>",
         "<path d='M132 150 A48 48 0 0 1 156 108.4 L180 150 Z' fill='#59b36b'/>",
         f"<path d='M156 108.4 A48 48 0 0 1 204 108.4 L180 150 Z' fill='{AMBER}'/>",
         f"<path d='M204 108.4 A48 48 0 0 1 228 150 L180 150 Z' fill='{RED}'/>",
         f"<line x1='180' y1='150' x2='182' y2='110' stroke='{INK}' stroke-width='4'/>",
         f"<circle cx='180' cy='150' r='6' fill='{INK}'/>",
         "<rect x='140' y='166' width='24' height='10' rx='5' fill='#ffffff'/>",
         f"<rect x='168' y='166' width='24' height='10' rx='5' fill='{BLUE}'/>",
         "<rect x='196' y='166' width='24' height='10' rx='5' fill='#ffffff'/>",
         f"<polygon points='256,170 346,70 346,196' fill='{SKY}' stroke='none'/>",
         "<line x1='252' y1='62' x2='252' y2='196' stroke-width='1.2'/>",
         "<line x1='252' y1='196' x2='350' y2='196' stroke-width='1.2'/>",
    ]
    ends = [74, 92, 112, 132, 150, 170, 190]
    for i, e in enumerate(ends):
        mid = (170 + e) / 2 + (8 if i % 2 else -8)
        col = BLUE if i % 2 else "#86a7cf"
        p.append(f"<polyline points='256,170 286,{mid:.0f} 316,{(mid + e) / 2 + (-6 if i % 2 else 6):.0f} 346,{e}' "
                 f"stroke='{col}' stroke-width='1.6'/>")
    p += [
        f"<polyline points='256,170 286,148 316,138 346,130' stroke='{NAVY}' stroke-width='3.5'/>",
        f"<polygon points='96,216 384,216 410,240 70,240' fill='{STEEL}'/>",
        "<line x1='104' y1='223' x2='376' y2='223' stroke-width='1.2'/>",
        "<line x1='96' y1='230' x2='386' y2='230' stroke-width='1.2'/>",
        "<rect x='210' y='232' width='60' height='6' rx='2' fill='#c6ccd3' stroke-width='1.2'/>",
        "<polygon points='398,150 446,144 452,190 404,196' fill='#fff27a'/>",
        "<path d='M408 162 Q416 156 422 164 T 438 160' stroke-width='1.5'/>",
        "<path d='M410 176 Q420 170 428 178 T 444 172' stroke-width='1.5'/>",
        "</svg>"]
    return "".join(p)


def panel_calendar():
    """The buy list as an allotment calendar: solid = block, hatched = allotment, outline = buy as needed."""
    p = [ROOT,
         "<desc>A desktop monitor showing the allotment calendar: desk surface, monitor bezel, display, three faint "
         "gridlines, baseline, seven weekly stacked bars, solid navy prepaid blocks, hatched light blue allotments "
         "with diagonal hatching, dashed outlines for rooms bought as needed, week tick marks, a gold star over "
         "the event week, monitor neck, monitor foot, phone, phone screen, computer mouse.</desc>",
         _desk_island(),
         f"<rect x='70' y='20' width='340' height='212' rx='8' fill='{SCREEN}'/>",
         "<rect x='82' y='32' width='316' height='188' rx='3' fill='#ffffff'/>",
    ]
    for y in (80, 120, 160):
        p.append(f"<line x1='94' y1='{y}' x2='388' y2='{y}' stroke='#d6dde6' stroke-width='1'/>")
    base = 200
    weeks = [(34, 26, 16), (42, 34, 20), (50, 40, 24), (78, 40, 22), (46, 38, 20), (38, 30, 16), (30, 24, 14)]
    for i, (s, a, o) in enumerate(weeks):
        x = 100 + i * 42
        w = 28
        ys = base - s
        ya = ys - a
        yo = ya - o
        p.append(f"<rect x='{x}' y='{yo}' width='{w}' height='{o}' stroke='#7d8792' stroke-width='1.6' "
                 f"stroke-dasharray='4 3' fill='#ffffff'/>")
        p.append(f"<rect x='{x}' y='{ya}' width='{w}' height='{a}' fill='#bcd6f5' stroke-width='1.4'/>")
        k = 0
        while k < a + w:
            x1, y1 = x, ya + k
            x2, y2 = x + k, ya
            if y1 > ya + a:
                x1, y1 = x + (y1 - (ya + a)), ya + a
            if x2 > x + w:
                y2, x2 = ya + (x2 - (x + w)), x + w
            p.append(f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{BLUE}' stroke-width='1.2'/>")
            k += 8
        p.append(f"<rect x='{x}' y='{ys}' width='{w}' height='{s}' fill='{NAVY}' stroke-width='1.4'/>")
        p.append(f"<line x1='{x + w / 2}' y1='{base}' x2='{x + w / 2}' y2='{base + 6}' stroke-width='1.2'/>")
    p += [
        f"<line x1='94' y1='{base}' x2='388' y2='{base}' stroke-width='1.6'/>",
        f"<polygon points='240,42 244,51 254,52 246,58 249,68 240,62 231,68 234,58 226,52 236,51' fill='{AMBER}' stroke-width='1.4'/>",
        "<polygon points='222,232 258,232 266,262 214,262' fill='#9aa3ad'/>",
        "<ellipse cx='240' cy='266' rx='58' ry='8' fill='#7d8792'/>",
        f"<rect x='404' y='236' width='34' height='54' rx='6' fill='{SCREEN}'/>",
        f"<rect x='409' y='242' width='24' height='40' rx='2' fill='{SKY}'/>",
        "<ellipse cx='352' cy='282' rx='16' ry='10' fill='#c6ccd3'/>",
        "<line x1='352' y1='272' x2='352' y2='280' stroke-width='1.2'/>",
        "</svg>"]
    return "".join(p)


def panel_approve():
    """Finance checks the frontier and the bad case, then approves."""
    p = [ROOT,
         "<desc>An approval desk: desk surface, tablet body, tablet screen, chart axes, budget frontier curve that "
         "rises then flattens, five budget points, the chosen point in gold, a green expected-profit bar, a red "
         "worst-case bar below the baseline, a sheet of paper, a green approval check stamped on it, a stamp with "
         "wooden handle, stamp neck and rubber base, two stacks of gold coins with coin tops and edges.</desc>",
         _desk_island(),
         f"<rect x='54' y='40' width='256' height='196' rx='14' fill='{SCREEN}'/>",
         "<rect x='66' y='52' width='232' height='172' rx='4' fill='#ffffff'/>",
         "<line x1='86' y1='66' x2='86' y2='200' stroke-width='1.2'/>",
         "<line x1='86' y1='200' x2='290' y2='200' stroke-width='1.2'/>",
         f"<path d='M90 196 Q118 120 156 104 T 222 90' stroke='{NAVY}' stroke-width='3'/>",
    ]
    for (cx, cy) in ((96, 178), (116, 136), (138, 114), (196, 96), (220, 91)):
        p.append(f"<circle cx='{cx}' cy='{cy}' r='4.5' fill='{BLUE}'/>")
    p += [
        f"<circle cx='166' cy='101' r='7' fill='{AMBER}'/>",
        "<rect x='242' y='150' width='18' height='50' fill='#59b36b'/>",
        f"<rect x='266' y='200' width='18' height='18' fill='{RED}'/>",
        "<polygon points='326,168 450,158 458,252 336,262' fill='#ffffff'/>",
        f"<ellipse cx='394' cy='212' rx='34' ry='30' stroke='{GREEN}' stroke-width='4'/>",
        f"<path d='M377 212 L390 225 L413 197' stroke='{GREEN}' stroke-width='5'/>",
        f"<ellipse cx='392' cy='56' rx='22' ry='12' fill='{WOOD3}'/>",
        f"<rect x='384' y='62' width='16' height='52' fill='{WOOD2}'/>",
        "<polygon points='362,112 422,112 428,134 356,134' fill='#3b4450'/>",
        "<rect x='92' y='252' width='52' height='22' fill='#e0a92e'/>",
        "<ellipse cx='118' cy='274' rx='26' ry='7' fill='#e0a92e'/>",
        "<ellipse cx='118' cy='252' rx='26' ry='7' fill='#f2c14e'/>",
        "<line x1='92' y1='260' x2='144' y2='260' stroke-width='1.2'/>",
        "<line x1='92' y1='267' x2='144' y2='267' stroke-width='1.2'/>",
        "<rect x='154' y='262' width='52' height='14' fill='#e0a92e'/>",
        "<ellipse cx='180' cy='276' rx='26' ry='7' fill='#e0a92e'/>",
        "<ellipse cx='180' cy='262' rx='26' ry='7' fill='#f2c14e'/>",
        "</svg>"]
    return "".join(p)


def panel_shock():
    """A shock: flights cancelled, the circuit breaker pauses new prepaid buying."""
    p = [ROOT,
         "<desc>An airport apron during a disruption: tarmac, storm cloud, lightning bolt, departures board on two "
         "legs, six board rows with flight code, destination and status, four red cancelled statuses, two amber "
         "delayed statuses, a grounded airliner with fuselage, tail fin, wing, engine, cabin windows, cockpit "
         "window, two wheels, two orange traffic cones with white bands, and a blue shield with a pause sign for "
         "the circuit breaker.</desc>",
         "<path d='M24 262 Q40 240 160 242 Q320 234 446 246 Q472 262 452 286 Q410 306 250 300 Q80 308 40 294 Q18 282 24 262 Z' fill='#d9dde3'/>",
         "<path d='M40 82 Q34 58 60 54 Q66 30 94 36 Q112 18 136 34 Q162 30 162 56 Q182 64 170 84 Z' fill='#8f9aa8'/>",
         f"<polygon points='100,86 86,118 100,116 92,142 118,104 104,106 112,86' fill='{AMBER}'/>",
         "<rect x='232' y='166' width='10' height='70' fill='#3b4450'/>",
         "<rect x='410' y='166' width='10' height='70' fill='#3b4450'/>",
         f"<rect x='200' y='28' width='252' height='142' rx='6' fill='{INK}'/>",
    ]
    status = [RED, RED, AMBER, RED, AMBER, RED]
    for i, col in enumerate(status):
        y = 42 + i * 20
        p.append(f"<rect x='214' y='{y}' width='46' height='11' rx='2' fill='#f2c14e' stroke='none'/>")
        p.append(f"<rect x='270' y='{y}' width='100' height='11' rx='2' fill='#9aa3ad' stroke='none'/>")
        p.append(f"<rect x='382' y='{y}' width='56' height='11' rx='2' fill='{col}' stroke='none'/>")
    p += [
        "<polygon points='112,232 172,232 146,268 122,268' fill='#c6ccd3'/>",
        "<ellipse cx='150' cy='254' rx='16' ry='8' fill='#9aa3ad'/>",
        f"<polygon points='58,222 42,186 66,186 94,222' fill='{BLUE}'/>",
        "<path d='M38 236 Q38 222 60 220 L200 220 Q224 222 228 234 Q224 246 200 248 L60 248 Q38 248 38 236 Z' fill='#ffffff'/>",
        "<path d='M206 224 Q218 226 222 232 L206 232 Z' fill='#3b4450'/>",
    ]
    for x in range(78, 196, 16):
        p.append(f"<circle cx='{x}' cy='231' r='3' fill='{BLUE}' stroke='none'/>")
    p += [
        "<circle cx='84' cy='254' r='6' fill='#3b4450'/>",
        "<circle cx='190' cy='254' r='6' fill='#3b4450'/>",
        "<polygon points='252,286 262,248 272,286' fill='#f28c38'/>",
        "<rect x='256' y='266' width='12' height='6' fill='#ffffff' stroke='none'/>",
        "<polygon points='286,290 296,252 306,290' fill='#f28c38'/>",
        "<rect x='290' y='270' width='12' height='6' fill='#ffffff' stroke='none'/>",
        f"<path d='M392 196 L436 208 Q436 254 392 278 Q348 254 348 208 Z' fill='{BLUE}'/>",
        "<rect x='378' y='216' width='9' height='36' rx='2' fill='#ffffff' stroke='none'/>",
        "<rect x='397' y='216' width='9' height='36' rx='2' fill='#ffffff' stroke='none'/>",
        "</svg>"]
    return "".join(p)


def panel_confirmed():
    """Event night: the market is sold out, the agent's booking still confirms."""
    p = [ROOT,
         "<desc>Event night at the hotel: night sky patch, crescent moon, six stars, street, hotel front wall, hotel "
         "side wall, flat roof edge, forty lit windows, entrance canopy, glass doors, red no-vacancy sign on the roof "
         "with white bars, a phone in front with case, screen, green confirmation badge, white check mark, three "
         "confirmed room rows each with a blue bed icon.</desc>",
         "<path d='M60 40 Q120 8 260 14 Q400 10 440 48 Q470 120 430 200 Q380 236 240 232 Q90 238 54 196 Q22 120 60 40 Z' fill='#2b3a67'/>",
         "<circle cx='392' cy='60' r='20' fill='#f6e7a1'/>",
         "<circle cx='402' cy='54' r='18' fill='#2b3a67' stroke='none'/>",
    ]
    for (x, y) in ((90, 60), (150, 34), (330, 30), (420, 120), (80, 150), (350, 100)):
        p.append(f"<circle cx='{x}' cy='{y}' r='2.5' fill='#f6e7a1' stroke='none'/>")
    p += [
        "<path d='M30 282 Q60 262 200 264 Q360 258 450 270 Q470 290 440 300 Q300 312 120 306 Q30 304 30 282 Z' fill='#5b6478'/>",
        "<polygon points='280,64 316,84 316,282 280,282' fill='#9aa1b5'/>",
        "<rect x='118' y='64' width='162' height='218' fill='#c7ccd9'/>",
        "<polygon points='118,64 280,64 316,84 154,84' fill='#b3b9c9'/>",
        f"<rect x='164' y='40' width='70' height='22' rx='3' fill='{RED}'/>",
        "<rect x='174' y='48' width='50' height='6' rx='2' fill='#ffffff' stroke='none'/>",
        "<line x1='180' y1='62' x2='180' y2='70' stroke-width='2'/>",
        "<line x1='218' y1='62' x2='218' y2='70' stroke-width='2'/>",
    ]
    for r in range(8):
        for c in range(5):
            x = 130 + c * 30
            y = 96 + r * 20
            p.append(f"<rect x='{x}' y='{y}' width='18' height='12' fill='#f6d45c' stroke-width='1.2'/>")
    p += [
        "<rect x='172' y='258' width='54' height='24' fill='#3b4450'/>",
        "<line x1='199' y1='258' x2='199' y2='282' stroke-width='1.2'/>",
        f"<polygon points='160,256 238,256 230,246 168,246' fill='{RED}'/>",
        f"<rect x='328' y='118' width='112' height='192' rx='14' fill='{INK}'/>",
        "<rect x='336' y='130' width='96' height='168' rx='6' fill='#ffffff'/>",
        f"<circle cx='384' cy='182' r='28' fill='{GREEN}' stroke='none'/>",
        "<path d='M370 182 L380 192 L398 170' stroke='#ffffff' stroke-width='5'/>",
    ]
    for i in range(3):
        y = 226 + i * 22
        p.append(f"<rect x='346' y='{y}' width='76' height='16' rx='4' fill='{SKY}' stroke-width='1.2'/>")
        p.append(f"<rect x='350' y='{y + 4}' width='14' height='8' rx='2' fill='{BLUE}' stroke='none'/>")
        p.append(f"<line x1='370' y1='{y + 8}' x2='414' y2='{y + 8}' stroke-width='1.2'/>")
    p.append("</svg>")
    return "".join(p)


PANELS = [panel_plan_today, panel_dial, panel_calendar, panel_approve, panel_shock, panel_confirmed]


def svg_data_uri(svg):
    """Whiteboard data URI: one line, % and # escaped."""
    s = svg.replace("\n", "").replace("%", "%25").replace("#", "%23")
    return "data:image/svg+xml," + s
