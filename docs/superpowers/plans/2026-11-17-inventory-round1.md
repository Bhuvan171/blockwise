# Blockwise (Inventory Optimization) Round 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working, honest Round 1 prototype for TBO's "Automate Inventory Optimization" PS (idea round due Thu 20 Nov 2026, 23:59 IST). It decides how many units to commit per product-period as **hard block / soft allotment / buy-as-needed** under a budget, trading expected profit against tail risk and sold-out losses. It is proven on **real bookings** (walk-forward backtest) and on a TBO-like synthetic portfolio scored in **worlds it was not planned in**. The results are shown on one decision page.

**Architecture:** One Python package `invopt`. A vectorised evaluator (`economics.py`) defines the truth of what a plan earns in each scenario. A sample-average-approximation LP (`optimizer.py`, HiGHS via SciPy) maximises `mean profit − λ·CVaR95(loss)` with a stockout penalty, budget and caps, and must agree with the evaluator. Two data worlds feed the same engine: real hotel bookings (`hotel_data.py` → `forecast.py` → `scenarios.py` → `backtest.py`) and a synthetic TBO-like portfolio (`portfolio.py`). `grid.py` precomputes plans across budgets × risk levels × shocks into one JSON, and `page.py` renders a static decision page from it.

**Tech Stack:** Python 3.12 venv; numpy, pandas, scipy (≥1.11: `linprog(method="highs")` with marginals), scikit-learn (`QuantileRegressor`, solver `highs`), pytest. CPU only. Working product name "Blockwise" (team may rename; never brand it as TBO's).

**Spec:** `~/tbo_hackathon/INVENTORY_PIPELINE.md` (stages 1–8, 10–12 in reduced form). **Deferred to Round 2, stated in the README and deck:** weekly re-plan (stage 9), selling-price optimisation, buy-by timing, a deep-learning forecaster, live API, demand unconstraining on the real data, and an explicit cancellation model. In Round 1, cancellations are handled implicitly: the forecaster predicts *net* checked-out demand from on-hand bookings that may still cancel. The synthetic world generates unconstrained demand directly. Supplier integration ships in reduced form as a "gaps" list (where the plan still loses the most bookings).

## Global Constraints
- Repo root `~/tbo_hackathon/inventory/`; venv `.venv/`; package in `src/invopt/`; tests in `tests/`; generated outputs in `out/`.
- Dependencies limited to: numpy, pandas, scipy>=1.11, scikit-learn>=1.4, pytest. No other runtime deps. No network at runtime; the dataset is fetched once by `scripts/fetch_data.sh`.
- Data: `data/raw/hotels.csv` = TidyTuesday 2020-02-11 copy of António, de Almeida & Nunes (2019) "Hotel booking demand", 16,855,599 bytes. Gitignored; the data card is committed.
- Currency: the backtest reports **EUR** (source data); the synthetic portfolio reports **INR**. Never mix; label every number.
- Default contract terms (assumptions, editable, shown in the UI): `hard_discount=0.30`, `soft_discount=0.20`, `dyn_discount=0.10`, `soft_hold_cost=0.02`, `stockout_penalty=0.10`, `salvage=0.0`, `release_days=21`. Costs are fractions of the reference rate; ordering `hard ≤ soft ≤ dyn` cost must hold (validated).
- Risk measure: CVaR at `alpha=0.95` of loss (= −profit). Risk levels: `{"Max profit": 0.0, "Balanced": 0.25, "Careful": 1.0, "Very careful": 3.0}`.
- Reproducibility: every random draw takes an explicit `numpy.random.Generator` seeded from config. Plan on seed 1; evaluate on seeds ≥ 100 (never the planning draws).
- Performance: full `grid` run ≤ 20 min and peak RAM ≤ 2.5 GB on this laptop (16 cores, ~3 GB free). Planning scenarios `n_plan=150`, evaluation `n_eval=4000`.
- No look-ahead in the backtest: a decision at date `T` may use only bookings with `booking_date ≤ T`, cancellation status as known at `T`, and nights that ended before `T`.
- Copy rules for the page and README: no "AI-powered"/"seamless"/"revolutionary"; every number traces to `out/*.json`; synthetic vs real always labelled.
- Git: local repo only, commit after each task, never push.

## Review Focus
1. **Look-ahead leakage in the backtest** (future bookings, later cancellations, unfinished nights, hotel capacity estimated from the test period): features at `T` must not change when post-`T` data is altered. Test in Task 5.
2. **Degenerate budget/risk inputs** (budget 0, budget smaller than one unit, budget ∞, λ very large): optimiser returns a valid plan (zeros or capped), spend ≤ budget, no solver exception. Test in Task 3.
3. **Cells with no history or no bookings** (first weeks of data, zero on-hand, missing ADR): forecaster and reference-rate fallbacks produce finite numbers. The LP refuses non-finite coefficients with a clear error. Tests in Tasks 4 and 3.
4. **Dirty source rows** (adr ≤ 0 or > 1000, zero-night stays, zero guests, No-Show, unparseable dates): dropped or recoded with counts in the data card, never silently. Test in Task 1.
5. **Solver failure or time limit:** result carries `status != "optimal"`, the caller falls back to the buy-as-needed plan, and the page shows a warning. It never silently uses a partial solution. Test in Task 3.

## File Structure
```
inventory/
  pyproject.toml            # package + deps + pytest config
  scripts/fetch_data.sh     # one-time download of hotels.csv
  data/README.md            # data card: source, licence, cleaning counts, real vs assumed fields
  src/invopt/__init__.py
  src/invopt/config.py      # ContractTerms, RISK_LEVELS, validation
  src/invopt/economics.py   # Cells, Plan, Outcome, evaluate()  ← the truth
  src/invopt/optimizer.py   # OptimizerParams, OptResult, optimize()  (SAA LP)
  src/invopt/hotel_data.py  # load/clean bookings, night panel, on-hand as of T
  src/invopt/forecast.py    # features, QuantileForecaster, baselines, metrics
  src/invopt/scenarios.py   # quantile sampling, correlated uniforms
  src/invopt/backtest.py    # walk-forward runner, policies, report
  src/invopt/portfolio.py   # synthetic TBO-like world, shocks, misspecified worlds
  src/invopt/grid.py        # results grid → out/results.json
  src/invopt/page.py        # static decision page from results.json
  src/invopt/cli.py         # `python -m invopt.cli backtest|grid|page|all`
  web/blockwise.template.html
  tests/fixtures/hotels_small.csv
  tests/test_*.py
  README.md                 # run steps, results tables, assumptions, Round 2 list
```

---

### Task 1: Scaffold, data fetch, loader and data card

**Files:**
- Create: `pyproject.toml`, `scripts/fetch_data.sh`, `src/invopt/__init__.py`, `src/invopt/config.py`, `src/invopt/hotel_data.py`, `data/README.md`, `.gitignore`, `tests/fixtures/hotels_small.csv`, `tests/test_hotel_data.py`

**Interfaces:**
- Produces:
  - `config.ContractTerms` (frozen dataclass; fields and defaults per Global Constraints; `.costs(ref_rate, market_price) -> (hard, soft, dyn, hold, stockout, salvage)` arrays; `.validate()` raises `ValueError` on ordering violation)
  - `config.RISK_LEVELS: dict[str, float]`
  - `hotel_data.load_bookings(path) -> tuple[pd.DataFrame, dict]`: cleaned frame + drop counts. Columns `hotel, segment, channel, arrival (Timestamp), nights (int), lead_time, booking_date, status ('Check-Out'|'Canceled'|'No-Show'), cancel_date (NaT unless Canceled), adr`.
  - `hotel_data.night_panel(bookings, hotel, segments, release_days, asof=None) -> pd.DataFrame` indexed by night with columns `final` (checked-out B2B room-nights), `early_final` (subset with `lead_time ≥ release_days`), `adr_mean` (mean ADR of B2B room-nights, NaN if none), `occ_total` (all-segment checked-out room-nights), and `on_hand` (B2B room-nights booked ≤ asof and not cancelled by asof, only when `asof` is given).
  - `hotel_data.B2B_SEGMENTS = ("Offline TA/TO",)`

- [ ] **Step 1:** Create the venv and install deps: `cd ~/tbo_hackathon/inventory && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'` (pyproject declares the deps above; `dev` adds pytest). Expected: `.venv/bin/python -c "import scipy, sklearn; print(scipy.__version__)"` prints ≥ 1.11.
- [ ] **Step 2:** `scripts/fetch_data.sh` downloads `https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/2020/2020-02-11/hotels.csv` to `data/raw/hotels.csv` and verifies the size is 16855599 bytes. Run it. Expected: the size check prints OK.
- [ ] **Step 3: Write failing tests** in `tests/test_hotel_data.py` against a 6-row fixture (`hotels_small.csv`, same columns as the source):
  - `test_arrival_and_booking_dates`: a row with `arrival_date_year=2016, arrival_date_month="July", day=3, lead_time=10` gives `arrival == 2016-07-03` and `booking_date == 2016-06-23`.
  - `test_nights_and_dirty_rows_dropped`: rows with `stays_in_weekend_nights + stays_in_week_nights == 0`, `adr <= 0`, `adr > 1000` or `adults+children+babies == 0` are absent; `drops` dict has one count per reason.
  - `test_noshow_not_stayed`: a `No-Show` row contributes 0 to `final`.
  - `test_on_hand_asof`: for `asof=2016-06-25`, a booking made 06-23 and cancelled 06-30 **counts**; a booking made 06-26 does **not**; a booking cancelled 06-24 does **not**.
  - `test_early_final_split`: with `release_days=21`, lead 30 goes to `early_final`, lead 10 does not.
- [ ] **Step 4:** Run `pytest tests/test_hotel_data.py -v`. Expected: FAIL (module missing).
- [ ] **Step 5:** Implement `config.py` and `hotel_data.py` to the interfaces. Room-nights expand each booking over `[arrival, arrival+nights)`. Only `status == "Check-Out"` counts toward `final`/`early_final`/`occ_total`.
- [ ] **Step 6:** Run `pytest tests/test_hotel_data.py -v`. Expected: PASS.
- [ ] **Step 7:** On the real file, print per hotel: B2B bookings, median weekly B2B room-nights, cancellation rate, date range. **Decision rule:** if either hotel's median weekly `Offline TA/TO` room-nights < 50, set `B2B_SEGMENTS = ("Offline TA/TO", "Groups")` and record why in the data card. Write `data/README.md`: source + citation, licence note, cleaning counts from `drops`, which fields are real vs assumed (contract terms, dynamic cost).
- [ ] **Step 8:** `git init`, add `.gitignore` (`.venv/`, `data/raw/`, `__pycache__/`), commit: `feat: scaffold, hotel bookings loader, data card`.

### Task 2: Contract economics evaluator (the truth)

**Files:**
- Create: `src/invopt/economics.py`, `tests/test_economics.py`

**Interfaces:**
- Consumes: `ContractTerms`.
- Produces:
  - `Cells` dataclass: `group: int[C]`, `price: float[C] | float[C,S]`, `ref_rate: float[C]`, `late: float[C,S]`, `early: float[C,S]`, `dyn_cap: float[C,S]` (np.inf = unlimited), `dyn_price: float[C,S] | None` (defaults to `price`), `meta: pd.DataFrame | None`; `.n_groups`, `.n_scen`.
  - `Plan` dataclass: `hard: float[G]`, `soft: float[G]` (units **per cell** of the group).
  - `evaluate(cells, plan, terms) -> Outcome` with `Outcome.profit: float[S]`, `cell_profit, served, lost, unsold_hard: float[C,S]`, and `Outcome.summary(alpha=0.95) -> dict` with keys `mean, cvar95_profit` (mean of the worst 5% profits), `p_loss, fill_rate, unsold_hard_cost, spend`.
- Allocation rule (optimal when `salvage·hard ≤ soft ≤ dyn` cost, which `validate()` guarantees): hard→late, hard→early, soft→early, buy-as-needed→remaining up to `dyn_cap` (only if `price + stockout ≥ dyn cost`).
- Profit per cell: `price·served − hard_cost·hard − soft_cost·soft_used − dyn_cost·dyn_used − hold·soft − stockout·lost + salvage·hard_cost·unsold_hard`.

- [ ] **Step 1: Write failing tests** (1 cell, 1 scenario, `price=ref=100`, default terms → hard 70, soft 80, dyn 90, hold 2/unit, stockout 10):
  - `test_mixed_contracts`: late 5, early 10, `dyn_cap=inf`, plan hard 8 soft 6 → profit **358**, served 15, lost 0.
  - `test_soldout_market`: same with `dyn_cap=0` → profit **338**, lost 1.
  - `test_unsold_hard`: late 2, early 1, hard 8 soft 6 → profit **−272**, `unsold_hard == 5`.
  - `test_group_broadcast`: 3 cells in group 0 with hard 2 each → spend = 3·2·70.
  - `test_summary_cvar`: profits `[−100, 0, …]` over 20 scenarios → `cvar95_profit == −100`, `p_loss == 0.05`.
  - `test_terms_validate`: `soft_discount=0.35` (soft cheaper than hard) raises `ValueError`.
- [ ] **Step 2:** Run `pytest tests/test_economics.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `economics.py`, fully vectorised over `[C,S]` (no Python loops over scenarios).
- [ ] **Step 4:** Run `pytest tests/test_economics.py -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: vectorised contract economics evaluator`.

### Task 3: SAA optimiser (mean − λ·CVaR, budget, caps)

**Files:**
- Create: `src/invopt/optimizer.py`, `tests/test_optimizer.py`

**Interfaces:**
- Consumes: `Cells`, `Plan`, `evaluate`, `ContractTerms`.
- Produces:
  - `OptimizerParams(risk_aversion=0.0, alpha=0.95, budget=np.inf, hard_cap: float[G]|None=None, soft_cap: float[G]|None=None, group_region: int[G]|None=None, region_share: float=1.0, time_limit_s=120.0)`
  - `optimize(cells, terms, params) -> OptResult` with `plan: Plan` (LP), `plan_int: Plan` (hard floored, soft rounded), `status: str`, `objective: float`, `budget_shadow_price: float` (objective gain per extra currency unit of budget; 0 if slack), `solve_seconds: float`.
  - `fallback_plan(cells) -> Plan` (all zeros = buy-as-needed).
- LP: variables `[hard G, soft G, u1..u4 per (c,s), η, z S]`; `u1 ≤ late`, `u4 ≤ dyn_cap` as bounds; rows `u2+u3 ≤ early`, `u1+u2+u3+u4 ≤ late+early`, `u1+u2 ≤ hard_g`, `u3 ≤ soft_g`, CVaR rows `−Π_s − η − z_s ≤ 0` (Π_s includes the constant `−stockout·(late+early)`), budget row `Σ_c hard_cost_c·hard_g(c) ≤ budget`, optional region rows. Built with `scipy.sparse`, solved by `linprog(method="highs", options={"time_limit": ...})`. Shadow price from `res.ineqlin.marginals` (sign-converted). Before solving, `ValueError` if any coefficient is non-finite.

- [ ] **Step 1: Write failing tests** (default terms; unless stated, `ref_rate = price = 100`):
  - `test_deterministic_full_cover`: 1 cell, 1 scenario (late 5, early 10, price 100, `dyn_cap=inf`) → `hard≈15, soft≈0`, objective **450**.
  - `test_budget_binding_and_shadow`: same with `budget=700` → `hard≈10, soft≈5`, objective **390**, `budget_shadow_price ≈ 12/70` (abs tol 1e-6).
  - `test_risky_demand_no_hard`: 2 scenarios late ∈ {0,10}, early 0, price 100 → `hard≈0`, objective **50**.
  - `test_cvar_reduces_commitment`: late ∈ {0,20}, early 0, `price=200, ref_rate=100` (hard cost 70, stockout 10), `dyn_cap=0` in both, `alpha=0.5`: λ=0 → `hard≈20`; λ=5 → `hard≈200/210` (tol 1e-5).
  - `test_lp_matches_evaluator`: random 20-cell × 50-scenario instance → LP in-sample mean profit equals `evaluate(cells, res.plan, terms).summary()["mean"]` (rel tol 1e-6).
  - `test_degenerate_inputs`: `budget=0` → zero hard; `budget=1e-9` → spend ≤ budget; `risk_aversion=1e4` → status optimal and finite plan.
  - `test_nonfinite_rejected`: a NaN price raises `ValueError` mentioning the field name.
  - `test_time_limit_status`: `time_limit_s=1e-6` on a 200×100 instance → `status != "optimal"` and `fallback_plan` is all zeros.
- [ ] **Step 2:** Run `pytest tests/test_optimizer.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `optimizer.py` to the interface.
- [ ] **Step 4:** Run `pytest tests/test_optimizer.py -v`. Expected: PASS. Also time a 364-cell × 150-scenario random instance: < 60 s, RSS < 1.5 GB (print both).
- [ ] **Step 5:** Commit `feat: mean-CVaR SAA optimiser with budget shadow price`.

### Task 4: Forecaster and scenario sampler

**Files:**
- Create: `src/invopt/forecast.py`, `src/invopt/scenarios.py`, `tests/test_forecast.py`, `tests/test_scenarios.py`

**Interfaces:**
- Consumes: `night_panel` output.
- Produces:
  - `QUANTILES = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)`
  - `forecast.build_features(panel_hist: pd.DataFrame, nights: pd.DatetimeIndex, on_hand: pd.Series, asof: Timestamp) -> pd.DataFrame` with columns `on_hand, ly_final, trail28, dow_0..dow_6, woy_sin, woy_cos`. `ly_final` = final for night − 364 days (NaN → `trail28`); `trail28` = mean `final` of the 28 nights ending before `asof`. Only nights `< asof` are read from `panel_hist`.
  - `forecast.QuantileForecaster(alpha_reg=0.0).fit(X, y).predict(X) -> float[n, len(QUANTILES)]`: one `sklearn.linear_model.QuantileRegressor(solver="highs")` per quantile, outputs sorted per row, clipped ≥ 0. Fallback when fewer than 60 training rows: empirical quantiles of `y` scaled by `trail28` ratio.
  - `forecast.pinball_loss(y, q) -> float`, `coverage(y, q, lo=0.1, hi=0.9) -> float`, `wape(y, yhat) -> float`.
  - `scenarios.sample_from_quantiles(q: float[n,Q], u: float[n,S]) -> float[n,S]`: piecewise-linear inverse CDF through `QUANTILES`, linear tail extrapolation, clipped ≥ 0.
  - `scenarios.correlated_uniforms(group: int[n], S, rho_common, rho_group, rng) -> float[n,S]` via a Gaussian copula `√ρc·Z + √ρg·Z_group + √(1−ρc−ρg)·ε`.
  - `scenarios.estimate_rhos(pit_residuals: pd.DataFrame) -> (rho_common, rho_group)` from normal scores of past PIT values; defaults `(0.3, 0.4)` when < 30 observations.

- [ ] **Step 1: Write failing tests:**
  - `test_quantiles_monotone_and_calibrated`: y = 2·x + N(0,1) on 600 rows; on a 200-row holdout, predictions non-decreasing across quantiles and 80% coverage in [0.72, 0.88].
  - `test_small_sample_fallback`: 30 rows → no exception, finite outputs.
  - `test_features_ignore_future`: changing `final` for nights ≥ `asof` leaves `build_features` output identical.
  - `test_sample_hits_quantiles`: `u = 0.5` returns the median column; `u = 0.9` returns the 0.9 column; all ≥ 0.
  - `test_copula_correlation`: n=40 in 4 groups, S=20000 → mean within-group normal-score correlation ≈ `rho_common+rho_group` (±0.03), across-group ≈ `rho_common` (±0.03).
- [ ] **Step 2:** Run `pytest tests/test_forecast.py tests/test_scenarios.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement both modules to the interfaces.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `feat: quantile forecaster and copula scenario sampler`.

### Task 5: Real-data walk-forward backtest

**Files:**
- Create: `src/invopt/backtest.py`, `tests/test_backtest.py`; Modify: `src/invopt/cli.py` (create with `backtest` command)

**Interfaces:**
- Consumes: `load_bookings`, `night_panel`, `build_features`, `QuantileForecaster`, `sample_from_quantiles`, `correlated_uniforms`, `estimate_rhos`, `optimize`, `evaluate`, `Cells`, `Plan`.
- Produces:
  - `BacktestConfig(start="2016-07-04", end="2017-08-27", horizon_days=56, batch_weeks=4, release_days=21, n_scen=200, seed=7, soldout_tau=0.98, lambdas=(0.0, 0.25, 1.0), budget_share=None)`
  - `run_backtest(bookings, cfg, terms) -> BacktestResult` with `.by_batch: pd.DataFrame` (hotel, batch_start, policy, profit, demand, served, unsold_hard, spend) and `.summary: pd.DataFrame` (policy → total profit, % of hindsight, fill rate, unsold hard cost, worst batch, batches with loss), `.forecast_metrics: dict` (WAPE, pinball, 80% coverage for ours vs last-year baseline), `.to_json(path)`, `.to_markdown() -> str`.
- Mechanics:
  - Decision dates `T` every 4 weeks from `start − horizon`. Each batch covers nights in `[T+56d, T+56d+28d)` for both hotels; group = (hotel, ISO week).
  - Capacity `K` per hotel = 99th percentile of `occ_total` over nights **before `cfg.start`**. A realised night is sold out when `occ_total ≥ soldout_tau·K`, which sets realised `dyn_cap = 0`.
  - Planning `dyn_cap` per scenario = 0 when the scenario's demand uniform `u > 1 − q_soldout`, where `q_soldout` is the historical sold-out frequency for that hotel and week-of-year ±2 weeks before `T`; otherwise inf.
  - Planning price = reference rate = last-year same-night `adr_mean` × trailing YoY ADR ratio (fallback: trailing 28-night mean). Realised price = actual night `adr_mean` (fallback reference).
  - Early/late split per scenario uses the historical mean early share for that hotel and day-of-week before `T`.
- Policies: `dynamic_only`; `last_year_hard` (hard = week mean of `ly_final`, soft 0); `point_forecast_hard` (hard = week mean of the median forecast, soft 0); `ours_λ` for each λ; `hindsight` (single realised scenario, λ=0).

- [ ] **Step 1: Write failing tests:**
  - `test_no_lookahead`: build the inputs for one decision date on (a) full data and (b) data where every booking with `booking_date > T` has its nights shifted and its ADR doubled → planning inputs (features, quantiles, ref rates, `q_soldout`) identical.
  - `test_capacity_uses_pre_start_only`: altering `occ_total` after `cfg.start` leaves `K` unchanged.
  - `test_hindsight_dominates`: on a 2-batch run, hindsight profit ≥ every other policy per batch (tol 1e-6).
  - `test_policies_respect_budget`: with `budget_share=0.3`, every policy's spend per batch ≤ budget.
- [ ] **Step 2:** Run `pytest tests/test_backtest.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `backtest.py` and `cli.py backtest` (writes `out/backtest.json`, `out/backtest.md`).
- [ ] **Step 4:** Run `pytest tests/test_backtest.py -v`. Expected: PASS.
- [ ] **Step 5:** Run `.venv/bin/python -m invopt.cli backtest`. Expected: it completes and prints the summary. **Parameters are frozen before this run; no tuning on these results.** If `ours` doesn't beat `point_forecast_hard` on total profit, investigate for bugs (systematic debugging) before reporting, and report honestly either way.
- [ ] **Step 6:** Commit `feat: walk-forward backtest on real bookings` (including `out/backtest.*`).

### Task 6: Synthetic TBO-like portfolio and misspecified worlds

**Files:**
- Create: `src/invopt/portfolio.py`, `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `Cells`, `correlated_uniforms`.
- Produces:
  - `PRODUCTS: list[dict]` with 24 hotel products (12 destinations × {4★, 5★}: Dubai, Abu Dhabi (Middle East); Bangkok, Phuket, Singapore, Bali, Kuala Lumpur (SE Asia); London, Paris (Europe); Maldives (Indian Ocean); Goa, Jaipur (India)) and 4 flight seat products (DEL–DXB, BOM–DXB, DEL–BKK, BOM–SIN). Each has `id, kind, name, region, base_weekly_units, price_inr, season (12 monthly multipliers), early_share, dispersion`. All values are **labelled assumptions** with a one-line rationale comment.
  - `WorldParams(level=1.0, season_amp=1.0, rho_global=0.15, rho_region=0.35, early_mult=1.0, dispersion_mult=1.0, price_mult=1.0, shock=None)`
  - `SHOCKS = {"middle_east_disruption": Middle East demand ×0.45 and ME flights' dyn_cap ×0.5; "india_airline_collapse": flight dyn_cap ×0.3 and international hotel demand ×0.85; "rupee_slide": international demand ×0.9 and price ×1.08}`
  - `WORLDS = {"base", "demand −20%", "demand +20%", "stronger seasons", "higher correlation", "later bookings", "more volatile"}` mapped to `WorldParams`.
  - `generate(world, n_scen, seed, start="2027-01-04", weeks=13) -> Cells` (one cell per product-week; group = cell; demand = negative binomial with a lognormal factor model per region/global; dyn_cap tightens in high-demand scenarios: `cap = base_cap·clip(1.6 − d/mean, 0, 1)`), with `meta` columns `product_id, name, kind, region, week_start`.

- [ ] **Step 1: Write failing tests:**
  - `test_means_match_base`: S=20000, base world → each cell's mean demand within ±3% of `base_weekly_units × season × level`.
  - `test_shock_scales_region`: `middle_east_disruption` → Middle East cells' mean ≈ 0.45× base (±3%); other cells unchanged (±3%).
  - `test_seed_reproducible`: same seed gives identical arrays; different seed differs.
  - `test_region_correlation_positive`: within-region demand correlation > across-region.
- [ ] **Step 2:** Run `pytest tests/test_portfolio.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `portfolio.py`.
- [ ] **Step 4:** Run `pytest tests/test_portfolio.py -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: synthetic TBO-like portfolio, shocks and misspecified worlds`.

### Task 7: Results grid (frontier, shocks, robustness, gaps, reasons)

**Files:**
- Create: `src/invopt/grid.py`, `tests/test_grid.py`; Modify: `src/invopt/cli.py` (add `grid`)

**Interfaces:**
- Consumes: `generate`, `WORLDS`, `SHOCKS`, `optimize`, `evaluate`, `RISK_LEVELS`, `out/backtest.json`.
- Produces: `run_grid(budget_fracs=(0.25, 0.5, 0.75, 1.0, 1.25), n_plan=150, n_eval=4000) -> dict`, written to `out/results.json`:
  - `budgets_inr`: fractions × `B*`, where `B*` = prepaid spend of the unconstrained "Max profit" plan, rounded to ₹0.5 Cr.
  - `cells[budget][risk]` → `kpis` (evaluated on base-world seeds ≥ 100: mean, cvar95_profit, p_loss, fill_rate, spend, budget_shadow_price), `lines` (per committed cell: product, region, week, hard, soft, prepaid ₹, expected profit ₹, P(line loss), expected sell-through of hard, `reason` text), `exposure` (prepaid by region × month), `gaps` (top 10 product-weeks by expected lost units × margin), `shocks[name]` → kpis + 30-bin profit histogram, `status`.
  - `frontier[risk]`: arrays of mean and cvar95 by budget.
  - `robustness`: for the plan at budget 1.0×B*, risk "Balanced", vs `point_forecast_hard`, `expected_volume_hard` (hard = mean demand) and `dynamic_only`, evaluated in every `WORLDS` entry → mean, cvar95, p_loss, fill.
  - `backtest`: copied summary from `out/backtest.json`.
  - `assumptions`: ContractTerms values + generator parameter table.
- `reason` template (deterministic, from numbers): `"{hard} hard: covers late bookings in {p}% of futures; {soft} allotted: early demand, released free {release} days out if unsold. Expected ₹{profit}; chance this line loses money {ploss}%."`

- [ ] **Step 1: Write failing tests** (tiny run: 2 budgets × 2 risks, `n_plan=20, n_eval=200`):
  - `test_grid_keys`: all keys above present; JSON-serialisable.
  - `test_spend_within_budget`: every cell's `kpis.spend ≤ budget + 1e-6`.
  - `test_frontier_monotone_in_budget`: for risk "Max profit", mean profit non-decreasing in budget (tol 0.5% of the largest value, since planning and evaluation draws differ).
  - `test_more_careful_lower_tail_risk`: "Very careful" cvar95_profit ≥ "Max profit" cvar95_profit at the same budget (evaluated on the same seeds).
- [ ] **Step 2:** Run `pytest tests/test_grid.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `grid.py` and `cli.py grid`.
- [ ] **Step 4:** Run `pytest tests/test_grid.py -v`. Expected: PASS.
- [ ] **Step 5:** Run `/usr/bin/time -v .venv/bin/python -m invopt.cli grid`. Expected: ≤ 20 min, max RSS ≤ 2.5 GB, all statuses optimal (print any that aren't).
- [ ] **Step 6:** Commit `feat: results grid with frontier, shocks, robustness, gaps` (including `out/results.json`).

### Task 8: Decision page, README and Round 1 numbers

**Files:**
- Create: `src/invopt/page.py`, `web/blockwise.template.html`, `tests/test_page.py`, `README.md`; Modify: `src/invopt/cli.py` (add `page`, `all`)

**Interfaces:**
- Consumes: `out/results.json`.
- Produces: `build_page(results_path, out_path="out/blockwise.html") -> Path`. The template has the placeholder `/*__RESULTS__*/null`, replaced with the JSON.
- Page content (load the `dataviz` skill before writing charts; follow the artifact page contract: tokens on `:root`, dark mode, 16px gutters, no horizontal page scroll):
  - controls: budget, risk level, shock;
  - KPI row: expected profit, worst-5% average, chance of loss, fill rate, prepaid spend, value of the next ₹1 Cr;
  - buy list with reasons;
  - budget frontier (one line per risk level, current point marked);
  - profit distribution base vs selected shock;
  - exposure by region × month;
  - gaps list (labelled "where a new supplier would help most");
  - real-data backtest table (EUR, with hindsight %);
  - robustness table across worlds;
  - assumptions panel;
  - footer stating what is synthetic vs real.

- [ ] **Step 1: Write failing tests:**
  - `test_page_embeds_results`: built HTML contains the `budgets_inr` values and no leftover placeholder.
  - `test_page_size`: < 3 MB.
  - `test_page_offline_safe`: no `<script src=` pointing anywhere except `cdnjs.cloudflare.com` (prefer none) and no `http://` URLs.
- [ ] **Step 2:** Run `pytest tests/test_page.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement the template and `page.py`; `cli.py all` runs backtest → grid → page.
- [ ] **Step 4:** Run `pytest -q` (whole suite). Expected: all PASS.
- [ ] **Step 5:** Run `.venv/bin/python -m invopt.cli page`, open `out/blockwise.html` (preview once), fix what the preview shows, then publish it as a private artifact.
- [ ] **Step 6:** Write `README.md`: one-paragraph pitch; run steps (`scripts/fetch_data.sh`, `pip install -e .`, `python -m invopt.cli all`); results tables copied from `out/backtest.md` and the robustness table; assumptions; real vs synthetic; Round 2 list (weekly re-plan, pricing, buy-by timing, supplier-integration ranking with integration cost, DL forecaster challenger on the A100, live API, TBO data contract adapter).
- [ ] **Step 7:** Commit `feat: decision page, README and Round 1 numbers`.
