# Blockwise: risk-aware inventory commitments for a B2B travel distributor

*TBO VoyageHack 4.0 · Problem statement: Automate Inventory Optimization · Round 1 prototype (team 5rods)*

Blockwise decides **which hotel rooms and flight seats to lock in, how many, under which contract, and within what budget**. It weighs three contract types against each other:

| Contract | How it works | Why it matters |
|---|---|---|
| **Hard block** | Prepaid, non-refundable, deepest rate | Cheapest unit, but you eat it if unsold |
| **Allotment** | Pay only for rooms used; unsold rooms go back free N days before arrival | A free option on early demand |
| **Buy as needed** | Market rate at sale time | No risk, thin margin, and **unavailable when the market is sold out** |

It optimises expected profit minus a chosen weight on the **bad case** (the average of the worst 5% of futures), plus a penalty for every booking turned away. The problem statement asks to maximise availability *and* profit, so both are in the objective.

## Results

### 1. Real bookings: walk-forward backtest (EUR)
Data: the public *Hotel booking demand* dataset (António, de Almeida & Nunes, *Data in Brief* 22, 2019). It covers two hotels in Portugal, 2015–2017, and we use the **Offline TA/TO** (travel agent / tour operator) segment as the B2B stream.

Every 4 weeks we plan the 4 weeks of stays starting 8 weeks later, using **only what was known that day**, then score against what really happened. That covers 15 planning rounds × 2 hotels, Jul 2016 – Aug 2017. Demand, booking dates, cancellations, prices and sold-out nights are real; contract rates are assumptions. The 90% range comes from resampling the 15 rounds.

| Policy | Profit | % of perfect hindsight (90% range) | Demand served | Unsold block cost | Worst round | Rounds with a loss |
|---|---|---|---|---|---|---|
| Buy as needed only | €20,438 | 2.4% (−5–11) | 57.8% | €0 | −€19,165 | 6 |
| Block last year's volume | €257,988 | 30.7% (2–51) | 91.3% | €553,854 | −€72,613 | 4 |
| Block the median forecast | €522,395 | 62.1% (51–70) | 94.3% | €342,100 | −€2,097 | 2 |
| Allot last year's volume + block the 25th-percentile forecast | €674,542 | 80.2% (73–85) | 98.8% | €158,987 | €11,147 | 0 |
| Blockwise · Max profit | €746,875 | 88.8% (85–92) | 97.6% | €64,081 | €11,595 | 0 |
| **Blockwise · Balanced** | **€746,835** | **88.8% (85–91)** | 97.1% | €44,598 | €12,216 | **0** |
| Blockwise · Careful | €739,059 | 87.8% (85–90) | 96.2% | €27,603 | €12,895 | 0 |
| Perfect hindsight (upper bound) | €841,458 | 100% | 98.6% | €22,151 | €17,009 | 0 |

**The honest comparison** is with the two-contract rule, the strongest simple policy we found; it was fixed before seeing its result. Blockwise beats it by **8.6 points of hindsight profit**:
- 90% range 4.3–14.2 points, from a paired resampling of rounds;
- positive in every resample;
- 13 of 15 rounds won;
- it also cuts unsold-block cost from €159k to €45k.

The other baselines show how much the *contract mix* alone is worth (blocks only → blocks + allotments).

**Sensitivity:** share of perfect-hindsight profit. Every row is a full re-run (`out/backtest_*.json`).

| Scenario | Blockwise · Balanced | Allot last year + block p25 | Block median forecast | Block last year | Buy as needed |
|---|---|---|---|---|---|
| Headline (allotment ≤ last year's production; sold out at 98% occupancy) | **88.8%** | 80.2% | 62.1% | 30.7% | 2.4% |
| Allotments not capped | 88.9% | 78.7% | 60.9% | 30.1% | 2.4% |
| Sold out only at 100% of capacity | 89.4% | 79.9% | 63.5% | 33.5% | 21.8% |
| Budget capped at 50% of last year's volume at block cost | 91.0% | 88.9% | 58.4% | 58.6% | 2.6% |
| Smaller contract discounts (block −25%, allotment −15%) | 85.9% | 74.2% | 51.9% | 13.2% | 2.9% |
| Larger contract discounts (block −35%, allotment −25%) | 90.4% | 84.2% | 68.9% | 42.9% | 2.1% |

**Forecast quality**, 8–12 weeks ahead, per hotel-night (840 nights): typical error (WAPE) **23%** vs 50% for "same night last year". The 10–90% band held the real value 74% of the time; the target is 80%, so the bands are slightly narrow.

**Disclosures:**
- The allotment cap (≤ last year's production) was added *after* the first full run, because unlimited free allotments were unrealistic. It lowers our own profit; the uncapped run is shown above.
- Sold-out modelling is a simplification. A night at ≥ 98% occupancy is closed to buy-as-needed purchases for all of that night's demand, which is pessimistic for "buy as needed only". At a 100% threshold the ranking is unchanged.

### 2. TBO-like portfolio (synthetic, INR, Jan–Mar 2027)
12 destinations × 2 hotel tiers + 4 flight seat routes, 13 weeks. Regional correlation, seasonality and event weeks are included; every parameter is a labelled assumption (`src/invopt/portfolio.py`). Plans are optimised on 150 simulated futures and **scored on 4,000 fresh ones**.

- **Budget frontier (Balanced):** a ₹50.5 Cr budget → ₹71.6 Cr expected profit · ₹101 Cr → ₹82.4 Cr · ₹152 Cr → ₹90.9 Cr · ₹202.5 Cr budget (₹188.5 Cr used) → ₹95.6 Cr. At ₹152 Cr the next ₹1 Cr of budget adds **₹0.09 Cr** to expected profit, measured on fresh futures.
- **Stress tests** on every plan: a Middle East disruption, an Indian airline collapse, and a rupee slide.
- **Robustness:** the Balanced plan, optimised for the base world only, was scored in **six worlds it was not planned in** (demand ±20%, stronger seasons, higher correlation, later bookings, more volatile demand). It was compared with four simple rules, including "allot expected volume + block the 25th percentile":
  - **Best bad case in 6 of 6**, often by a wide margin: demand −20% → ₹37.4 Cr vs ₹23.3 Cr for the two-contract rule; higher correlation → ₹62.3 Cr vs ₹51.6 Cr.
  - **Best expected profit in 5 of 6.** With demand +20%, the rule's bigger commitments earn more on average (₹111.2 Cr vs ₹107.5 Cr) but have a worse bad case (₹89.1 Cr vs ₹92.3 Cr).

Open the decision page: `out/blockwise_standalone.html`. It has budget, risk and shock controls, the buy list with a reason per line, the frontier, the profit distribution, exposure by region, where a new supplier would help most, and the proof tables.

### 3. Real-shock replay on official Singapore data (SGD, 2011–2026)
**Real data:** SingStat monthly
- **visitor arrivals resident in India** (M550001, Jan 2008 – Sep 2026);
- **average room rate and occupancy** for small, medium and large hotels (M550081).

Every month from Mar 2011 to Sep 2026 (187 decisions), Blockwise commits inventory **two months ahead** using **only the statistics already published that day** (data lags about 2 months). It is then scored against real demand, real rates and real occupancy. Occupancy decides whether buying as needed was possible.

| Blockwise · Balanced vs simple rules | All months | 2020–21 COVID | 2022–23 recovery | 2024–26 | Worst-5% month (avg) |
|---|---|---|---|---|---|
| **Blockwise · Balanced** | **80.2% of hindsight** | **−S$2.54M** | **+S$4.50M, 0 losing months** | 88.5% | **−S$0.31M** |
| Block last year's volume | 70.9% | −S$6.47M | +S$3.53M | 89.9% | −S$0.64M |
| Allot + block p25 (two-contract rule) | 70.8% | −S$3.55M | +S$2.22M | 87.8% | −S$0.61M |
| Block the median forecast | 59.6% | −S$4.05M | −S$3.36M (9 losing months) | 87.8% | −S$0.84M |

**What each part contributes (ablations, same data):**

| Variant | All months | COVID | Recovery | 2024–26 |
|---|---|---|---|---|
| Adaptive calibration + safeguards (headline) | 80.2% | −S$2.54M | +S$4.50M | 88.5% |
| … breaker at 1.5× / 3× error | 81.2% / 80.4% | −S$1.99M / −S$2.54M | +S$4.42M / +S$4.61M | 88.5% / 88.5% |
| Static calibration (equal weights) + safeguards | 74.1% | −S$2.55M | +S$4.08M | **67.1%** (remembers COVID forever, under-commits) |
| Adaptive calibration, **no safeguards** | **47.7%** | −S$7.86M | −S$5.66M | 90.8% |

- **Adaptive calibration** is weighted, non-exchangeable split conformal (Barber, Candès, Ramdas & Tibshirani, 2023) on log forecast errors, with a half-life of 6 months. Uncertainty widens within months of a shock and narrows again once things calm down.
- **Safeguards:**
  - a **circuit breaker**: no prepaid blocks while the forecast was more than 2× off in any of the last 3 published months (allotments and buy-as-needed only);
  - forecasts are capped at 1.5× the highest month ever published.
  The breaker was on for 33 months (Jul 2020 – Mar 2023).
- **Disclosure:**
  - The safeguards were added **after** the first replay exposed over-commitment through COVID. The thresholds are round numbers, and the result barely moves between 1.5× and 3×.
  - In calm years, simple rules do as well as Blockwise (2011–19: 91.4% vs 93.1% for last year's volume). **Blockwise's edge is surviving regime change.**
- **Assumptions:**
  - demand = 0.05 room-nights per Indian arrival, split 35/40/25% across small/medium/large hotels (percentages don't depend on the scale);
  - 85% of demand booked 3+ weeks ahead (from the real hotel bookings);
  - buying as needed is possible below 80% occupancy and impossible above 95%;
  - contract rates as above.
- **Licence:** contains information from SingStat Table Builder (tables M550001 and M550081), accessed on 19 Nov 2026, made available under the Singapore Open Data Licence.

### 4. Forecaster benchmark (real bookings, same backtest for every forecaster)
| Forecaster | Blockwise · Balanced % of hindsight (90% range) | Typical error (WAPE) | 80% / 90% band holds |
|---|---|---|---|
| **Ensemble: calibrated linear + calibrated gradient-boosted (booking pace) + Chronos-2** | **89.9% (87–92)** | **21.8%** | **82% / 92%** |
| Linear quantile regression (Round 1 model) | 88.8% (85–91) | 23.2% | 74% / 84% |
| Gradient-boosted quantiles + booking pace + conformal | 88.6% (85–91) | 27.1% | 72% / 85% |
| Auto: lowest realised error so far (**pre-declared headline**) | 88.0% (85–90) | 24.8% | 77% / 86% |
| Chronos-2 foundation model (Amazon, Oct 2025), zero-shot with booking-pace covariates | 86.8% (82–91) | 23.7% | 90% / 95% (too wide) |
| Linear + conformal | 86.0% (82–89) | 28.9% | 66% / 74% |

- **Honest reading:**
  - The foundation model on its own isn't the best, because its bands are too wide. It adds value **inside the ensemble**, which wins on every accuracy metric and is the only well-calibrated model.
  - Conformal recalibration of a single model *hurt* here: its calibration window holds the latest nights, which sit in a different season from the nights being forecast.
  - The pre-declared online selector had only 15 rounds to learn from. City Hotel stayed on the linear model; Resort Hotel moved to the ensemble from round 9.
- The headline table in §1 keeps the Round 1 forecaster, which was fixed before this benchmark.

## How it works
```
real bookings / synthetic portfolio
   → per-night features known at decision time (rooms on the books, same night last year, trailing level)
   → quantile forecasts (linear quantile regression, one model per horizon week)
   → 150–200 correlated scenarios (Gaussian copula; correlations estimated from past forecast errors)
   → optimiser: max E[profit] − λ·CVaR95(loss), stockout penalty, budget, allotment and region caps
        (sample-average LP, HiGHS via SciPy; reports the value of the next unit of budget)
   → scored on scenarios / real outcomes it never saw
```
- `economics.py` is the single definition of what a plan earns. The optimiser's LP is tested to agree with it exactly.
- Allocation per scenario: hard block first (late demand before early, because early demand still has the allotment). For the rest of early demand, whichever of allotment and buy-as-needed is cheaper that night. Buy-as-needed covers what's left, when the market isn't sold out.
- Per plan on a laptop CPU: about 25 s risk-neutral, up to ~3 min risk-averse (time limit 15 min). The full grid (20 plans + stress tests + robustness) takes about 15 min.
- Safety: if the hindsight benchmark or the reference-budget solve fails, the run stops. Any grid plan that falls back to buy-as-needed is counted and marked on the page.

## Run it
```bash
cd inventory
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
./scripts/fetch_data.sh                 # 16.9 MB public CSV
./scripts/fetch_singstat.sh             # 2 official SingStat tables (~270 KB)
.venv/bin/pytest                        # tests
.venv/bin/python -m invopt.cli all      # backtest (~3 min) → grid (~15 min) → page
.venv/bin/python -m invopt.cli singapore  # real-shock replay, 2011–2026 (~1 min; Chronos-2 on CPU)
.venv/bin/python -m invopt.cli bench      # forecaster benchmark (~1 h on a laptop)
.venv/bin/python -m invopt.cli page       # refresh the page with the latest replay / benchmark
open out/blockwise_standalone.html
```
Sensitivity runs: `python -m invopt.cli backtest --soft-cap-mult none --tag _uncapped`, `--soldout-tau 1.0 --tag _tau1`, `--budget-share 0.5 --tag _budget0.5`, `--hard-discount 0.25 --soft-discount 0.15 --tag _rates_low`, `--hard-discount 0.35 --soft-discount 0.25 --tag _rates_high`, then `grid` and `page` again.

## Assumptions (all shown on the page)
| | Value |
|---|---|
| Hard block rate | −30% vs reference rate |
| Allotment rate | −20% vs reference, pay per room used |
| Buy-as-needed rate | −10% vs market price at sale time |
| Allotment hold cost | 2% of rate per allotted unit (utilisation penalty) |
| Turned-away booking | 10% of rate (goodwill) |
| Allotment release | 21 days before arrival |
| Allotment size | ≤ last year's production (backtest) / expected weekly production (portfolio) |
| Region limit (portfolio) | ≤ 60% of prepaid budget in one region |
| Sold-out night (backtest) | occupancy ≥ 98% of capacity, estimated only from nights before the first decision |

## Honest limits
- TBO's own demand, net rates and contract terms are not available. The real-data proof covers two hotels, not TBO's portfolio, and the portfolio is synthetic.
- Real B2B bookings on sold-out nights are what the hotel actually served. Demand that was turned away isn't visible in this data, so Round 1 doesn't "unconstrain" it.
- The 15 real planning rounds are a small sample; the 90% ranges above say how much the results could move.
- The forecast bands are slightly narrow (74% vs 80% coverage).
- Not yet built (Round 2): weekly re-planning as bookings arrive, selling-price optimisation, buy-by timing, a supplier-integration ranking with integration cost, a TBO data adapter (search logs with sold-outs and look-to-book), a faster decomposition solver, and million-scenario tests on GPU.

## Repository
`src/invopt/`: `hotel_data` (loader), `economics` (profit truth), `optimizer` (LP), `forecast`, `scenarios`, `backtest`, `portfolio` (synthetic world, shocks, worlds), `grid`, `page`, `cli` · `tests/` (pytest) · `data/README.md` (data card) · `out/` (results and pages) · `docs/superpowers/plans/` (implementation plan).

## Licences and tools
numpy, pandas, scipy (BSD; HiGHS solver MIT) and scikit-learn (BSD) at runtime; optional forecasting stack: PyTorch CPU (BSD), chronos-forecasting and transformers (Apache-2.0), Chronos-2 weights `amazon/chronos-2` (Apache-2.0); pytest (MIT) for tests. SingStat data under the Singapore Open Data Licence (attribution above). The data is from an open-access *Data in Brief* article; cite it when reusing. Built with AI coding assistance (Claude Code).
