# Forecasting upgrade: SOTA benchmark, judged by accuracy and profit

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (native). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the single linear quantile model with a benchmarked set of forecasters. Pick the headline one leak-free, and report both forecast accuracy and the profit each one produces in the real-bookings backtest.

**Architecture:** A `Forecaster` protocol (`fit(X, y)` / `predict(X) -> [n, 7 quantiles]`) with several implementations:
- the current linear quantile regression (`qr`);
- a gradient-boosted quantile model with booking-pace features (`gbm`);
- Chronos-2 zero-shot with booking-pace covariates (`chronos2`);
- a quantile-averaging ensemble (`ensemble`).

Every forecaster can be wrapped in **rolling conformal calibration**, so each quantile's empirical coverage on recent past nights matches its level.

`backtest.planning_inputs` takes a forecaster name. `forecast_bench.py` runs the rolling-origin benchmark on the backtest's own decision dates. A leak-free **online selector** (`auto`) picks, for each batch, the forecaster with the lowest pinball loss on batches already realised.

**Tech:** sklearn `HistGradientBoostingRegressor(loss="quantile")` (no new dependencies); `chronos-forecasting` 2.3.2 + `torch` CPU (installed, approved); existing pipeline.

## Global constraints
- No look-ahead. Training rows, calibration residuals and Chronos context use only nights `< T`. Covariates for target nights use only bookings made by `T`.
- Chronos-2 covariate per horizon bucket `b`: rooms on the books at lead `H_b = 56 + 7b + 6` days, the bucket's longest lead. For every night `n <= T + H_b`, the value at `n - H_b <= T` is known at `T`, consistently for past and future nights.
- Quantile levels stay `(0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)`.
- The headline policy may only use a forecaster chosen without seeing test outcomes: `auto` (online selection), or one fixed before the run.
- The existing 72 tests stay green; `qr` stays the default until the benchmark says otherwise.

## Review focus
1. Leakage through calibration windows or the Chronos context (nights `>= T`).
2. Quantile crossing after calibration (outputs must stay sorted and non-negative).
3. Chronos failures (OOM, NaN): fall back to `qr` and record it.
4. Runtime: the whole benchmark must fit in about 30 min on this laptop.
5. Ties and short histories in the online selector (first batches): default to `qr`.

### Task A: forecaster registry + GBM with pace features + conformal wrapper
- Test: `test_gbm_monotone_calibrated`, `test_conformal_fixes_undercoverage` (a deliberately too-narrow model reaches ~80% coverage on a holdout), `test_registry_names`.
- Code: `forecast.py` adds `make_forecaster(name)`, `GBMQuantileForecaster`, `ConformalWrapper(base, cal_frac=0.25)`; `backtest._training_frame` adds pace features (`on_hand_lead_plus7`, `on_hand_lead_plus14`, `ly_on_hand_same_lead`).

### Task B: Chronos-2 forecaster (per-bucket covariate, leak-free)
- Test: `test_chronos_no_lookahead` (altering finals for nights `>= T` leaves its quantiles unchanged), `test_chronos_shapes_sorted`.
- Code: `chronos_fc.py`: `chronos2_quantiles(book, T, nights, cfg) -> [n, 7]`, with the model loaded once and cached.

### Task C: plug into the backtest + online selector + benchmark
- Test: `test_backtest_accepts_forecaster`, `test_auto_selector_uses_only_realised_batches`.
- Code: `BacktestConfig.forecaster` (`qr` | `qr_conf` | `gbm_conf` | `chronos2` | `ensemble_conf` | `auto`); `forecast_bench.py` produces `out/forecast_bench.json/.md` (WAPE, pinball, 80% and 90% coverage, interval width, % of hindsight per forecaster).
- Run: the benchmark plus a full backtest per forecaster; update README / page / ROUND1 with the winner, chosen by the pre-declared rule.
