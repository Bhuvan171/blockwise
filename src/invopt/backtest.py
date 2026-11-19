"""Walk-forward backtest on real bookings: would these commitments have paid off?

Every 4 weeks (decision date T) we plan the 4 weeks of stays that start
`horizon_days` later, for both hotels, using only what was known at T: rooms
already on the books, past nights' outcomes, past prices. Each policy's plan is
then scored against what really happened: real B2B demand, real booking lead
times (allotment vs late demand), real cancellations, real prices, and real
sold-out nights (hotel occupancy at capacity means nothing to buy as needed).

Contract rates are assumptions (ContractTerms). Demand, timing, prices and
sell-outs are real. Currency: EUR (source data).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from invopt.config import ContractTerms
from invopt.economics import Cells, Plan, evaluate
from invopt.forecast import QUANTILES, build_features, coverage, make_forecaster, pinball_loss, wape
from invopt.hotel_data import B2B_SEGMENTS, expand_nights
from invopt.optimizer import OptimizerParams, optimize
from invopt.scenarios import DEFAULT_RHOS, correlated_uniforms, estimate_rhos, sample_from_quantiles

_QS = np.asarray(QUANTILES)
_MEDIAN = QUANTILES.index(0.5)


@dataclass(frozen=True)
class BacktestConfig:
    start: str = "2016-07-04"
    end: str = "2017-08-27"
    horizon_days: int = 56
    batch_weeks: int = 4
    release_days: int = 21
    n_scen: int = 200
    seed: int = 7
    soldout_tau: float = 0.98
    lambdas: tuple[float, ...] = (0.0, 0.25, 1.0)
    budget_share: float | None = None
    soft_cap_mult: float | None = 1.0  # allotment per night <= this x last year's production that week (None = no cap)
    segments: tuple[str, ...] = B2B_SEGMENTS
    hotels: tuple[str, ...] = ("City Hotel", "Resort Hotel")
    train_from: str = "2015-07-15"  # skip the first nights: stays from arrivals before 1 Jul 2015 are missing
    soldout_window_days: int = 14
    forecaster: str = "qr"  # qr | qr_conf | gbm | gbm_conf | chronos2 | ensemble_conf | auto


class HotelBook:
    """Pre-expanded room-nights of one hotel, for fast as-of queries."""

    def __init__(self, bookings: pd.DataFrame, hotel: str, segments: tuple[str, ...], release_days: int):
        rows = expand_nights(bookings[bookings["hotel"] == hotel])
        self.hotel = hotel
        self.index = pd.date_range(rows["night"].min(), rows["night"].max(), freq="D", name="night")
        self._pos = (rows["night"] - self.index[0]).dt.days.to_numpy()
        self._night = rows["night"].to_numpy("datetime64[ns]")
        self._book = rows["booking_date"].to_numpy("datetime64[ns]")
        self._cancel = rows["cancel_date"].to_numpy("datetime64[ns]")
        self._b2b = rows["segment"].isin(segments).to_numpy()
        stayed = (rows["status"] == "Check-Out").to_numpy()
        early = (rows["lead_time"] >= release_days).to_numpy()
        n = len(self.index)

        def cnt(m):
            return np.bincount(self._pos[m], minlength=n).astype(float)

        m = stayed & self._b2b
        adr_sum = np.bincount(self._pos[m], weights=rows["adr"].to_numpy(float)[m], minlength=n)
        final = cnt(m)
        self.panel = pd.DataFrame({
            "final": final,
            "early_final": cnt(m & early),
            "occ_total": cnt(stayed),
            "adr_mean": np.where(final > 0, adr_sum / np.maximum(final, 1.0), np.nan),
        }, index=self.index)

    def _count_on_books(self, asof: np.ndarray) -> pd.Series:
        not_cancelled = np.isnat(self._cancel) | (self._cancel > asof)
        m = self._b2b & (self._book <= asof) & not_cancelled
        return pd.Series(np.bincount(self._pos[m], minlength=len(self.index)).astype(float), index=self.index)

    def on_hand(self, asof: pd.Timestamp) -> pd.Series:
        """B2B room-nights on the books at `asof`, per night."""
        return self._count_on_books(np.datetime64(pd.Timestamp(asof), "ns"))

    def on_hand_at_horizon(self, h: int) -> pd.Series:
        """For every night n: B2B room-nights on the books at n - h days."""
        return self._count_on_books(self._night - np.timedelta64(h, "D"))


def capacity(book: HotelBook, before: pd.Timestamp) -> float:
    occ = book.panel.loc[book.index < pd.Timestamp(before), "occ_total"]
    if occ.empty:
        raise ValueError(f"no nights before {before} to estimate capacity for {book.hotel}")
    return float(np.quantile(occ, 0.99))


ENSEMBLE = ("qr_conf", "gbm_conf", "chronos2")
AUTO_POOL = ("qr", "qr_conf", "gbm_conf", "chronos2", "ensemble_conf")  # ensemble_conf must come after its members
PACE = ["oh_m7", "oh_m14", "ly_oh"]  # booking pace: rooms on the books 1 and 2 weeks earlier, and last year at the same lead


def _training_frame(book: HotelBook, train_nights: pd.DatetimeIndex, h: int, pace: bool = False) -> pd.DataFrame:
    """Same features as `build_features`, for past nights as if decided h days ahead."""
    final = book.panel["final"]
    asof = train_nights - pd.Timedelta(days=h)
    r28 = final.rolling(28, min_periods=7).mean().shift(1)
    exp_mean = final.expanding(min_periods=1).mean().shift(1)
    trail = r28.reindex(asof).to_numpy()
    trail = np.where(np.isfinite(trail), trail, exp_mean.reindex(asof).to_numpy())
    trail = np.where(np.isfinite(trail), trail, 0.0)
    ly = final.reindex(train_nights - pd.Timedelta(days=364)).to_numpy()
    ly = np.where(np.isfinite(ly), ly, trail)
    oh = book.on_hand_at_horizon(h).reindex(train_nights).fillna(0.0).to_numpy()
    out = pd.DataFrame({"on_hand": oh, "ly_final": ly, "trail28": trail}, index=train_nights)
    dow = train_nights.day_of_week.to_numpy()
    for i in range(7):
        out[f"dow_{i}"] = (dow == i).astype(float)
    angle = 2 * np.pi * (train_nights.day_of_year.to_numpy() - 1) / 365.25
    out["woy_sin"], out["woy_cos"] = np.sin(angle), np.cos(angle)
    if pace:
        out["oh_m7"] = book.on_hand_at_horizon(h + 7).reindex(train_nights).fillna(0.0).to_numpy()
        out["oh_m14"] = book.on_hand_at_horizon(h + 14).reindex(train_nights).fillna(0.0).to_numpy()
        ly_n = train_nights - pd.Timedelta(days=364)
        out["ly_oh"] = book.on_hand_at_horizon(h).reindex(ly_n).fillna(0.0).to_numpy()
    return out


def _target_pace(book: HotelBook, T: pd.Timestamp, nights: pd.DatetimeIndex) -> pd.DataFrame:
    """Pace features for target nights, using only bookings known by T."""
    d = pd.Timedelta(days=1)
    return pd.DataFrame({
        "oh_m7": book.on_hand(T - 7 * d).reindex(nights).fillna(0.0).to_numpy(),
        "oh_m14": book.on_hand(T - 14 * d).reindex(nights).fillna(0.0).to_numpy(),
        "ly_oh": book.on_hand(T - 364 * d).reindex(nights - 364 * d).fillna(0.0).to_numpy(),
    }, index=nights)


def _circular_doy_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = np.abs(a[:, None] - b[None, :])
    return np.minimum(d, 365 - d)


def planning_inputs(book: HotelBook, T: pd.Timestamp, nights: pd.DatetimeIndex, cfg: BacktestConfig,
                    K: float) -> dict:
    """Everything the planner may know at decision date T about `nights`."""
    T = pd.Timestamp(T)
    nights = pd.DatetimeIndex(nights)
    hist = book.panel.loc[book.index < T]
    on_hand = book.on_hand(T)
    feats = build_features(book.panel, nights, on_hand, T)

    horizons = np.asarray((nights - T).days)
    buckets = (horizons - cfg.horizon_days) // 7
    train_nights = book.index[(book.index >= pd.Timestamp(cfg.train_from)) & (book.index < T)]
    y_train = book.panel["final"].reindex(train_nights).to_numpy()
    notes: list[str] = []

    def run(name: str) -> np.ndarray:
        if name == "chronos2":
            from invopt import chronos_fc
            try:
                return chronos_fc.chronos2_quantiles(book, T, nights, cfg)
            except Exception as e:  # noqa: BLE001 - a failed foundation-model call must not abort the backtest
                notes.append(f"chronos2 failed for {book.hotel} at {T.date()} ({type(e).__name__}); used qr")
                return run("qr")
        if name == "ensemble_conf":  # quantile averaging (Vincentization) of calibrated + foundation models
            return np.clip(np.sort(np.mean([run(m) for m in ENSEMBLE], axis=0), axis=1), 0.0, None)
        out = np.zeros((len(nights), len(QUANTILES)))
        pace = make_forecaster(name).feature_set == "pace"
        X_target = pd.concat([feats, _target_pace(book, T, nights)], axis=1) if pace else feats
        for b in np.unique(buckets):
            h = int(cfg.horizon_days + 7 * b + 3)
            model = make_forecaster(name).fit(_training_frame(book, train_nights, h, pace), y_train)
            sel = buckets == b
            out[sel] = model.predict(X_target.loc[sel])
        return out

    candidates = None
    if cfg.forecaster == "auto":
        candidates = {}
        for name in AUTO_POOL:
            candidates[name] = (np.clip(np.sort(np.mean([candidates[m] for m in ENSEMBLE], axis=0), axis=1), 0.0, None)
                                if name == "ensemble_conf" else run(name))
        q = candidates["qr"]  # run_backtest replaces this with the selected candidate
    else:
        q = run(cfg.forecaster)

    # share of demand booked before the allotment release date, by day of week
    by_dow = hist.groupby(hist.index.day_of_week)[["early_final", "final"]].sum()
    overall = hist["early_final"].sum() / max(hist["final"].sum(), 1.0)
    share = (by_dow["early_final"] / by_dow["final"].where(by_dow["final"] > 0)).reindex(range(7)).fillna(overall)
    early_share = share.to_numpy()[nights.day_of_week.to_numpy()]

    # contract reference rate: same night last year x year-on-year ADR trend
    adr = hist["adr_mean"]
    recent = adr[adr.index >= T - pd.Timedelta(days=90)].mean()
    prior = adr[(adr.index >= T - pd.Timedelta(days=90 + 364)) & (adr.index < T - pd.Timedelta(days=364))].mean()
    yoy = float(np.clip(recent / prior, 0.7, 1.5)) if np.isfinite(recent) and np.isfinite(prior) and prior > 0 else 1.0
    trail_adr = adr[adr.index >= T - pd.Timedelta(days=28)].mean()
    if not np.isfinite(trail_adr):
        trail_adr = adr.mean() if np.isfinite(adr.mean()) else 100.0
    ly_adr = adr.reindex(nights - pd.Timedelta(days=364)).to_numpy()
    ref = np.where(np.isfinite(ly_adr), ly_adr * yoy, trail_adr)

    # historical chance the hotel is sold out around this time of year
    sold = (hist["occ_total"] >= cfg.soldout_tau * K).to_numpy(float)
    near = _circular_doy_distance(nights.day_of_year.to_numpy(), hist.index.day_of_year.to_numpy()) <= cfg.soldout_window_days
    with np.errstate(invalid="ignore"):
        q_soldout = np.where(near.sum(1) > 0, (near * sold[None, :]).sum(1) / np.maximum(near.sum(1), 1), 0.0)

    return {
        "notes": notes,
        "features": feats,
        "quantiles": q,
        "candidates": candidates,
        "early_share": early_share,
        "ref_rate": ref,
        "q_soldout": q_soldout,
        "ly_final": feats["ly_final"].to_numpy(),
        "on_hand": feats["on_hand"].to_numpy(),
    }


def _select_forecaster(history: list[dict], T: pd.Timestamp, default: str = "qr") -> str:
    """Lowest mean pinball loss over forecasts whose nights had all happened by T (leak-free)."""
    seen = [r for r in history if r["available_from"] <= T]
    if not seen:
        return default
    scores = pd.DataFrame(seen).groupby("name")["pinball"].mean()
    return str(scores.idxmin())


def _pit(q: np.ndarray, y: np.ndarray) -> np.ndarray:
    out = np.empty(len(y))
    for i in range(len(y)):
        xp = np.maximum.accumulate(q[i])
        out[i] = np.interp(y[i], xp + np.arange(len(xp)) * 1e-9, _QS)
    return np.clip(out, 0.01, 0.99)


def _cap_to_budget(hard_g: np.ndarray, spend_coef: np.ndarray, budget: float) -> np.ndarray:
    hard_g = np.floor(np.maximum(hard_g, 0.0))
    spend = float(spend_coef @ hard_g)
    if np.isfinite(budget) and spend > budget > 0:
        hard_g = np.floor(hard_g * budget / spend)
    elif np.isfinite(budget) and budget <= 0:
        hard_g = np.zeros_like(hard_g)
    return hard_g


@dataclass
class BacktestResult:
    by_batch: pd.DataFrame
    summary: pd.DataFrame
    forecast_metrics: dict
    meta: dict = field(default_factory=dict)

    def to_json(self, path: str | Path) -> None:
        payload = {
            "meta": self.meta,
            "summary": self.summary.reset_index().to_dict(orient="records"),
            "by_batch": self.by_batch.assign(batch_start=self.by_batch["batch_start"].astype(str)).to_dict(orient="records"),
            "forecast_metrics": self.forecast_metrics,
        }
        Path(path).write_text(json.dumps(payload, indent=2, default=float))

    def to_markdown(self) -> str:
        head = ("| policy | total profit (EUR) | % of hindsight | 90% range | fill rate | unsold hard cost (EUR) "
                "| worst 4-week batch (EUR) | batches with a loss |\n|---|---|---|---|---|---|---|---|")
        lines = [head]
        for pol, r in self.summary.iterrows():
            lines.append(f"| {pol} | {r.total_profit:,.0f} | {r.pct_of_hindsight:.1f}% | "
                         f"{r.pct_ci_lo:.1f}–{r.pct_ci_hi:.1f}% | {r.fill_rate:.1%} | "
                         f"{r.unsold_hard_cost:,.0f} | {r.worst_batch:,.0f} | {int(r.batches_with_loss)} |")
        return "\n".join(lines)


def run_backtest(bookings: pd.DataFrame, cfg: BacktestConfig, terms: ContractTerms) -> BacktestResult:
    terms.validate()
    books = {h: HotelBook(bookings, h, cfg.segments, cfg.release_days) for h in cfg.hotels}
    start, end = pd.Timestamp(cfg.start), pd.Timestamp(cfg.end)
    horizon = pd.Timedelta(days=cfg.horizon_days)
    n_nights = 7 * cfg.batch_weeks
    T0 = start - horizon
    K = {h: capacity(b, T0) for h, b in books.items()}
    dates = []
    T = T0
    while T + horizon + pd.Timedelta(days=n_nights - 1) <= end:
        dates.append(T)
        T += pd.Timedelta(days=n_nights)

    rng = np.random.default_rng(cfg.seed)
    pit_store: list[dict] = []
    rows: list[dict] = []
    fc_rows: list[pd.DataFrame] = []
    batch_meta: list[dict] = []
    fc_hist: dict[str, list[dict]] = {h: [] for h in cfg.hotels}
    cand_rows: list[pd.DataFrame] = []
    for k, T in enumerate(dates):
        nights = pd.date_range(T + horizon, periods=n_nights, freq="D")
        parts = []
        chosen: dict[str, str] = {}
        for hi, h in enumerate(cfg.hotels):
            inp = planning_inputs(books[h], T, nights, cfg, K[h])
            if inp["candidates"] is not None:
                chosen[h] = _select_forecaster(fc_hist[h], T, default="qr")
                inp["quantiles"] = inp["candidates"][chosen[h]]
            else:
                chosen[h] = cfg.forecaster
            real = books[h].panel.reindex(nights)
            parts.append((hi, h, inp, real))
            if inp["candidates"] is not None:  # score every candidate once these nights have happened
                y_h = real["final"].fillna(0).to_numpy()
                for name, qc in inp["candidates"].items():
                    fc_hist[h].append({"available_from": nights[-1] + pd.Timedelta(days=1), "name": name,
                                       "pinball": pinball_loss(y_h, qc)})
                    cand_rows.append(pd.DataFrame({"name": name, "hotel": h, "y": y_h, "ly": inp["ly_final"],
                                                   **{f"q{t}": qc[:, i] for i, t in enumerate(QUANTILES)}}))
        group = np.concatenate([hi * cfg.batch_weeks + np.arange(n_nights) // 7 for hi, *_ in parts])
        hotel_of = np.concatenate([np.full(n_nights, h) for _, h, _, _ in parts])
        q = np.vstack([p[2]["quantiles"] for p in parts])
        es = np.concatenate([p[2]["early_share"] for p in parts])
        ref = np.concatenate([p[2]["ref_rate"] for p in parts])
        qsold = np.concatenate([p[2]["q_soldout"] for p in parts])
        ly = np.concatenate([p[2]["ly_final"] for p in parts])
        fin = np.concatenate([p[3]["final"].fillna(0).to_numpy() for p in parts])
        ef = np.concatenate([p[3]["early_final"].fillna(0).to_numpy() for p in parts])
        occ = np.concatenate([p[3]["occ_total"].fillna(0).to_numpy() for p in parts])
        kap = np.concatenate([np.full(n_nights, K[h]) for _, h, _, _ in parts])
        price_real = np.concatenate([p[3]["adr_mean"].to_numpy() for p in parts])
        price_real = np.where(np.isfinite(price_real), price_real, ref)

        avail = pd.DataFrame([r for r in pit_store if r["available_from"] <= T])
        rc, rg = estimate_rhos(avail) if len(avail) else DEFAULT_RHOS
        u = correlated_uniforms(group, cfg.n_scen, rc, rg, rng)
        D = np.round(sample_from_quantiles(q, u))
        E = np.round(D * es[:, None])
        plan_cells = Cells(group=group, price=ref, ref_rate=ref, late=D - E, early=E,
                           dyn_cap=np.where(u > 1.0 - qsold[:, None], 0.0, np.inf))
        sold_out = occ >= cfg.soldout_tau * kap
        real_cells = Cells(group=group, price=price_real, ref_rate=ref, late=(fin - ef)[:, None], early=ef[:, None],
                           dyn_cap=np.where(sold_out, 0.0, np.inf)[:, None], dyn_price=price_real[:, None])

        hard_cost = terms.costs(ref, ref)["hard"]
        G = int(group.max()) + 1
        spend_coef = np.bincount(group, weights=hard_cost, minlength=G)
        cells_per_g = np.bincount(group, minlength=G)
        budget = np.inf if cfg.budget_share is None else float(cfg.budget_share * (hard_cost * ly).sum())

        plans: dict[str, Plan] = {"dynamic_only": Plan.zeros(G)}
        ly_g = np.bincount(group, weights=ly, minlength=G) / cells_per_g
        plans["last_year_hard"] = Plan(hard=_cap_to_budget(ly_g, spend_coef, budget), soft=np.zeros(G))
        med_g = np.bincount(group, weights=q[:, _MEDIAN], minlength=G) / cells_per_g
        plans["point_forecast_hard"] = Plan(hard=_cap_to_budget(med_g, spend_coef, budget), soft=np.zeros(G))
        # hotels grant allotments in line with past production; same limit for every policy incl. hindsight
        soft_cap = None if cfg.soft_cap_mult is None else np.floor(ly_g * cfg.soft_cap_mult)
        # a sensible two-contract rule (fixed before seeing results): allot last year's volume,
        # hard-block the 25th-percentile forecast
        p25_g = np.bincount(group, weights=q[:, QUANTILES.index(0.25)], minlength=G) / cells_per_g
        plans["allot_ly_block_p25"] = Plan(hard=_cap_to_budget(p25_g, spend_coef, budget),
                                           soft=np.floor(ly_g) if soft_cap is None else soft_cap.copy())
        statuses = {}
        for lam in cfg.lambdas:
            res = optimize(plan_cells, terms, OptimizerParams(risk_aversion=lam, budget=budget, soft_cap=soft_cap))
            statuses[f"ours_{lam:g}"] = res.status
            plans[f"ours_{lam:g}"] = res.plan_int if res.status == "optimal" else Plan.zeros(G)
        hs = optimize(real_cells, terms, OptimizerParams(budget=budget, soft_cap=soft_cap))
        if hs.status != "optimal":
            raise RuntimeError(f"hindsight solve for the batch starting {nights[0].date()} returned {hs.status!r}; "
                               "the 100% benchmark would be wrong, so the backtest stops")
        statuses["hindsight"] = hs.status
        plans["hindsight"] = hs.plan

        for name, plan in plans.items():
            out = evaluate(real_cells, plan, terms)
            hard_cells = np.asarray(plan.hard)[group]
            for h in cfg.hotels:
                m = hotel_of == h
                rows.append({
                    "hotel": h, "batch_start": nights[0], "policy": name,
                    "profit": float(out.cell_profit[m, 0].sum()),
                    "demand": float(out.demand[m, 0].sum()),
                    "served": float(out.served[m, 0].sum()),
                    "unsold_hard": float(out.unsold_hard[m, 0].sum()),
                    "unsold_cost": float(((hard_cost - terms.salvage * hard_cost) * out.unsold_hard[:, 0])[m].sum()),
                    "spend": float((hard_cost * hard_cells)[m].sum()),
                    "hard_units": float(hard_cells[m].sum()),
                    "soft_units": float(np.asarray(plan.soft)[group][m].sum()),
                    "soft_cap_units": float(soft_cap[group][m].sum()) if soft_cap is not None else -1.0,
                    "budget": budget, "status": statuses.get(name, "rule"),
                })
        pits = _pit(q, fin)
        for c in range(len(fin)):
            pit_store.append({"batch": k, "group": int(group[c]), "pit": float(pits[c]),
                              "available_from": nights[-1] + pd.Timedelta(days=1)})
        fc_rows.append(pd.DataFrame({"hotel": hotel_of, "night": nights.tolist() * len(cfg.hotels), "y": fin, "ly": ly,
                                     **{f"q{t}": q[:, i] for i, t in enumerate(QUANTILES)}}))
        batch_meta.append({"decision_date": str(T.date()), "first_night": str(nights[0].date()),
                           "rho_common": rc, "rho_group": rg, "statuses": statuses, "forecaster": chosen})

    by_batch = pd.DataFrame(rows)
    summary = _summarise(by_batch)
    fc = pd.concat(fc_rows, ignore_index=True)
    meta = {"config": {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(cfg).items()},
            "terms": terms.as_dict(), "capacity": K, "batches": batch_meta, "currency": "EUR"}
    fm = _forecast_metrics(fc)
    if cand_rows:
        cr = pd.concat(cand_rows, ignore_index=True)
        fm["candidates"] = {name: _forecast_metrics(d)["all"] for name, d in cr.groupby("name")}
    meta["forecaster"] = cfg.forecaster
    return BacktestResult(by_batch=by_batch, summary=summary, forecast_metrics=fm, meta=meta)


def _summarise(by_batch: pd.DataFrame) -> pd.DataFrame:
    tot = by_batch.groupby("policy").agg(total_profit=("profit", "sum"), demand=("demand", "sum"),
                                          served=("served", "sum"), unsold_hard_cost=("unsold_cost", "sum"),
                                          spend=("spend", "sum"))
    per_batch = by_batch.groupby(["policy", "batch_start"])["profit"].sum()
    tot["worst_batch"] = per_batch.groupby("policy").min()
    tot["batches_with_loss"] = (per_batch < 0).groupby("policy").sum()
    tot["fill_rate"] = tot["served"] / tot["demand"]
    tot["pct_of_hindsight"] = 100.0 * tot["total_profit"] / tot.loc["hindsight", "total_profit"]
    # 90% range from resampling planning rounds (both hotels of a round stay together)
    wide = per_batch.unstack("policy")
    rng = np.random.default_rng(0)
    idx = rng.integers(0, len(wide), size=(2000, len(wide)))
    sums = wide.to_numpy()[idx].sum(axis=1)  # [draws, policies]
    ratios = 100.0 * sums / sums[:, [list(wide.columns).index("hindsight")]]
    tot["pct_ci_lo"] = pd.Series(np.percentile(ratios, 5, axis=0), index=wide.columns)
    tot["pct_ci_hi"] = pd.Series(np.percentile(ratios, 95, axis=0), index=wide.columns)
    order = ["dynamic_only", "last_year_hard", "point_forecast_hard", "allot_ly_block_p25"] + \
            sorted([p for p in tot.index if p.startswith("ours_")], key=lambda s: float(s.split("_")[1])) + ["hindsight"]
    return tot.loc[[p for p in order if p in tot.index]]


def _forecast_metrics(fc: pd.DataFrame) -> dict:
    qcols = [f"q{t}" for t in QUANTILES]
    out = {}
    for name, d in [("all", fc)] + list(fc.groupby("hotel")):
        q = d[qcols].to_numpy()
        y = d["y"].to_numpy()
        out[name] = {
            "nights": int(len(d)),
            "wape_median": wape(y, q[:, _MEDIAN]),
            "wape_last_year": wape(y, d["ly"].to_numpy()),
            "pinball": pinball_loss(y, q),
            "coverage_80": coverage(y, q),
            "coverage_90": coverage(y, q, lo=0.05, hi=0.95),
            "width_80_rel": float((q[:, QUANTILES.index(0.9)] - q[:, QUANTILES.index(0.1)]).mean() / max(y.mean(), 1e-9)),
        }
    return out
