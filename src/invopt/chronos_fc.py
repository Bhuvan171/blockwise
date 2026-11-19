"""Chronos-2 (Amazon, Oct 2025, Apache-2.0): a pretrained time-series foundation model, zero-shot.

It sees each hotel's nightly B2B room-nights before the decision date T, plus two
covariates known for past *and* future nights:
  oh  rooms already on the books at a fixed lead H (the horizon bucket's longest lead)
  ly  the same night last year
One call per horizon bucket keeps it leak-free: in bucket b every future night n satisfies
n - H_b <= T, so its covariate uses only bookings made by T.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from invopt.forecast import QUANTILES

MODEL_ID = "amazon/chronos-2"
CONTEXT_DAYS = 730
_PIPE = None


def _pipe():
    global _PIPE
    if _PIPE is None:
        from chronos import Chronos2Pipeline

        _PIPE = Chronos2Pipeline.from_pretrained(MODEL_ID, device_map="cpu")
    return _PIPE


def chronos2_quantiles(book, T: pd.Timestamp, nights: pd.DatetimeIndex, cfg) -> np.ndarray:
    T = pd.Timestamp(T)
    nights = pd.DatetimeIndex(nights)
    day = pd.Timedelta(days=1)
    final = book.panel["final"]
    start = max(pd.Timestamp(cfg.train_from), T - CONTEXT_DAYS * day, book.index[0])
    ctx = pd.date_range(start, T - day, freq="D")
    target = final.reindex(ctx).fillna(0.0)
    fill = float(target.mean()) if len(target) else 0.0
    horizons = np.asarray((nights - T).days)
    buckets = (horizons - cfg.horizon_days) // 7
    qcols = [str(q) for q in QUANTILES]
    out = np.zeros((len(nights), len(QUANTILES)))
    for b in np.unique(buckets):
        H = int(cfg.horizon_days + 7 * b + 6)
        sel = buckets == b
        fut = pd.date_range(T, nights[sel].max(), freq="D")
        oh = book.on_hand_at_horizon(H)  # for night n: rooms on the books at n - H
        assert (fut - H * day).max() <= T, "covariate would use bookings made after T"
        ly = final.reindex(ctx.append(fut) - 364 * day).to_numpy()
        ly = np.where(np.isfinite(ly) & (ctx.append(fut) - 364 * day < T), ly, fill)
        ctx_df = pd.DataFrame({"item_id": f"b{b}", "timestamp": ctx, "target": target.to_numpy(),
                               "oh": oh.reindex(ctx).fillna(0.0).to_numpy(), "ly": ly[:len(ctx)]})
        fut_df = pd.DataFrame({"item_id": f"b{b}", "timestamp": fut,
                               "oh": oh.reindex(fut).fillna(0.0).to_numpy(), "ly": ly[len(ctx):]})
        pred = _pipe().predict_df(ctx_df, future_df=fut_df, prediction_length=len(fut),
                                  quantile_levels=list(QUANTILES), id_column="item_id")
        pred = pred.set_index("timestamp")
        out[sel] = pred.loc[nights[sel], qcols].to_numpy(dtype=float)
    if not np.all(np.isfinite(out)):
        raise FloatingPointError("Chronos-2 returned non-finite quantiles")
    return np.clip(np.sort(out, axis=1), 0.0, None)
