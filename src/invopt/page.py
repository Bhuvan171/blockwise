"""Render the static decision page: the template plus results.json, embedded."""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[2] / "web" / "blockwise.template.html"
PLACEHOLDER = "/*__RESULTS__*/null"


def compact(data: dict) -> dict:
    """Columnar buy-list lines for the page (product/week tables + value arrays); reasons kept verbatim.

    Returns a new dict; `data` is not modified. The page's `linesOf()` rebuilds row objects.
    """
    data = json.loads(json.dumps(data))
    products: dict[str, int] = {}
    prod_rows: list[dict] = []
    weeks: dict[str, int] = {}
    for row in data.get("cells", {}).values():
        for cell in row.values():
            lines = cell.get("lines")
            if not isinstance(lines, list):
                continue
            col = {k: [] for k in ("product", "week", "hard", "soft", "prepaid", "profit", "p_loss", "sell", "reason")}
            for ln in lines:
                if ln["product"] not in products:
                    products[ln["product"]] = len(prod_rows)
                    prod_rows.append({"name": ln["product"], "kind": ln.get("kind"), "region": ln.get("region")})
                weeks.setdefault(ln["week_start"], len(weeks))
                col["product"].append(products[ln["product"]])
                col["week"].append(weeks[ln["week_start"]])
                col["hard"].append(ln["hard"])
                col["soft"].append(ln["soft"])
                col["prepaid"].append(round(ln["prepaid_inr"]))
                col["profit"].append(round(ln["exp_profit_inr"]))
                col["p_loss"].append(round(ln["p_line_loss"], 4))
                st = ln.get("hard_sell_through")
                col["sell"].append(None if st is None else round(st, 3))
                col["reason"].append(ln["reason"])
            cell["lines"] = col
    data["line_products"] = prod_rows
    data["line_weeks"] = list(weeks)
    return data


_SKELETON_HEAD = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                  '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                  '</head>\n<body>\n')
_SKELETON_TAIL = "\n</body>\n</html>\n"


def build_page(results_path: str | Path, out_path: str | Path = "out/blockwise.html",
               template_path: str | Path = TEMPLATE, standalone: bool = False) -> Path:
    """Write the page. `standalone=True` adds a document skeleton for opening the file directly;
    without it the output is page content for an artifact host that supplies its own skeleton."""
    data = compact(json.loads(Path(results_path).read_text()))
    # compact JSON; escape "</" and U+2028/9 so the data can never end the <script> element early
    blob = (json.dumps(data, separators=(",", ":"), allow_nan=False, ensure_ascii=False)
            .replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    html = Path(template_path).read_text()
    if PLACEHOLDER not in html:
        raise ValueError(f"template {template_path} has no {PLACEHOLDER} placeholder")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = html.replace(PLACEHOLDER, blob)
    out.write_text(_SKELETON_HEAD + body + _SKELETON_TAIL if standalone else body)
    return out
