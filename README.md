# Blockwise: risk-aware inventory commitments for a B2B travel distributor

*TBO VoyageHack 4.0 · Problem statement: Automate Inventory Optimization · Round 1 prototype (team 5rods)*

**Live site:** https://bhuvan171.github.io/blockwise/ (built from this repo; the `gh-pages` branch holds the published page)

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

Every 4 weeks we plan the 4 weeks of stays starting 8 weeks later, using **only what was known that day**, then score against what really happened. That covers 15 planning rounds × 2 hotels, Jul 2016 – Aug 2017. Prepaid spend is **capped at 50% of last year's volume** at block cost, and buying as needed stops on the date a night **really filled up** in the bookings, rather than for the whole night. Demand, booking dates, cancellations, prices and fill dates are real; contract rates are assumptions. The 90% range comes from resampling the 15 rounds.

| Policy | Profit | % of perfect hindsight (90% range) | Demand served | Unsold block cost | Worst round | Rounds with a loss |
|---|---|---|---|---|---|---|
| Buy as needed only | €304,252 | 37.6% (34–42) | 99.8% | €0 | €5,334 | 0 |
| Block last year's volume | €608,374 | 75.1% (71–79) | 100.0% | €53,929 | €12,952 | 0 |
| Block the median forecast | €608,484 | 75.1% (72–78) | 100.0% | €48,356 | €13,439 | 0 |
| Allot last year's volume + block the 5th-percentile forecast | €727,342 | 89.8% (87–92) | 100.0% | €18,738 | €12,573 | 0 |
| Allot last year's volume + block the 10th-percentile forecast | €726,914 | 89.7% (86–92) | 100.0% | €27,351 | €12,320 | 0 |
| Allot last year's volume + block the 25th-percentile forecast (fixed in advance) | €721,623 | 89.1% (84–93) | 100.0% | €41,198 | €13,769 | 0 |
| Allot last year's volume + block the median forecast | €716,895 | 88.5% (83–93) | 100.0% | €48,356 | €13,976 | 0 |
| Blockwise · Max profit | €754,534 | 93.2% (91–95) | 100.0% | €24,199 | €12,093 | 0 |
| **Blockwise · Balanced** | **€750,527** | **92.7% (90–95)** | 100.0% | €19,748 | €12,216 | 0 |
| Blockwise · Careful | €743,958 | 91.9% (89–94) | 100.0% | €14,102 | €12,895 | 0 |
| Perfect hindsight (upper bound) | €809,936 | 100.0% | 100.0% | €5,085 | €17,009 | 0 |

**The honest comparison** is with the best fixed buying rule, **even one picked with hindsight**: allot last year's volume and block the 5th-percentile forecast (89.8%).
- Blockwise (Balanced) is ahead by **2.9 points** of hindsight profit (90% range 1.0–4.9) and wins **12 of 15** rounds.
- Against the rule fixed before seeing any result (allot + block the 25th percentile, 89.1%), it is ahead by 3.6 points (90% range −1.3 to 9.5), winning 8 of 15 rounds.
- Unsold prepaid cost is **€19.7k vs €41.2k** for the rule fixed in advance. The hindsight-picked rule holds slightly less (€18.7k).
- With the cap and real fill dates, every policy serves essentially all demand, so the differences are in profit and unsold stock.

**Sensitivity:** share of perfect-hindsight profit. Every row is a full re-run that changes one assumption. Blockwise leads the best fixed rule in **all 10**; in 5 of them the 90% range includes zero.

| Scenario (full re-run each) | Blockwise · Balanced | Best fixed rule, picked with hindsight | Rule fixed in advance (allot + block p25) | Lead over best rule, points (90% range) | Rounds won |
|---|---|---|---|---|---|
| **Headline** (prepaid capped at 50% of last year's volume; sold-out nights from real fill dates) | **92.7%** | 89.8% (allot + block p5) | 89.1% | +2.9 (1.0 to 4.9) | 12 of 15 |
| Before review: no budget cap, a full night closed to buy-as-needed for all its bookings | 88.8% | 86.0% (allot + block p5) | 80.2% | +2.7 (−0.1 to 4.7) | 12 of 15 |
| No budget cap | 90.3% | 86.8% (allot + block p5) | 79.7% | +3.5 (0.7 to 5.6) | 12 of 15 |
| Re-plan every week (60 rounds) instead of every 4 weeks | 93.1% | 90.8% (allot + block p5) | 89.7% | +2.3 (0.5 to 4.1) | 44 of 60 |
| One block size per night instead of per week | 87.8% | 84.8% (allot + block p25) | 84.8% | +3.0 (−0.8 to 6.5) | 10 of 15 |
| TBO-like thin margins (block −15%, allotment −10%, buy as needed −5%) | 85.5% | 81.0% (allot + block p5) | 76.6% | +4.5 (−1.5 to 13.5) | 10 of 15 |
| Smaller contract discounts (block −25%, allotment −15%) | 90.3% | 87.6% (allot + block p5) | 85.9% | +2.7 (−0.9 to 6.9) | 9 of 15 |
| Larger contract discounts (block −35%, allotment −25%) | 93.8% | 91.4% (allot + block p10) | 91.2% | +2.4 (0.4 to 4.5) | 12 of 15 |
| Sold out only at 100% of capacity | 92.7% | 89.8% (allot + block p5) | 89.1% | +2.9 (1.0 to 4.9) | 12 of 15 |
| Allotments not capped at last year's production | 92.9% | 88.6% (allot + block p5) | 87.9% | +4.3 (1.4 to 5.6) | 12 of 15 |
| Decide 120 days ahead instead of 56 | 89.8% | 88.0% (allot + block p5) | 87.1% | +1.8 (−1.3 to 4.5) | 10 of 15 |

**Forecast quality**, 8–12 weeks ahead, per hotel-night (840 nights): typical error (WAPE) **23%** vs 50% for "same night last year". The 10–90% band held the real value 74% of the time; the target is 80%, so the bands are slightly narrow.

**Disclosures:**
- **Changed after two independent reviews:** the budget cap is now on in the headline, and the whole-night sold-out rule was replaced by real fill dates (that rule made "buy as needed only" look far worse). The pre-review setup is the "Before review" row above; it was the headline in Round 1 (88.8%).
- The allotment cap (≤ last year's production) was added *after* the first full run, because unlimited free allotments were unrealistic. It lowers our own profit; the uncapped run is shown above.
- **Where these numbers come from:** the run published on the live site (`gh-pages`). The code for the review changes (real fill dates, the extra fixed rules, and the weekly, per-night, thin-margin and 120-day re-runs) is not on `main` yet; `main` reproduces the pre-review run.

### 2. TBO-like portfolio (synthetic, INR, Jan–Mar 2027)
12 destinations × 2 hotel tiers + 4 flight seat routes, 13 weeks. Regional correlation, seasonality and event weeks are included; every parameter is a labelled assumption (`src/invopt/portfolio.py`). Plans are optimised on 150 simulated futures and **scored on 4,000 fresh ones**.

- **Budget frontier (Balanced):** a ₹46 Cr budget → ₹28.9 Cr expected profit · ₹92 Cr → ₹34.0 Cr · ₹137.5 Cr → ₹37.4 Cr · ₹183.5 Cr → ₹39.6 Cr · ₹229.5 Cr budget (₹206.9 Cr used) → ₹39.6 Cr. At ₹137.5 Cr the next ₹1 Cr of budget adds **₹0.05 Cr** to expected profit; from ₹183.5 Cr it adds nothing.
- **Stress tests** on every plan: a Middle East disruption, an Indian airline collapse, and a rupee slide.
- **Robustness:** the Balanced plan, optimised for the base world only, was scored in **six worlds it was not planned in** (demand ±20%, stronger seasons, higher correlation, later bookings, more volatile demand). It was compared with four simple rules, including "allot expected volume + block the 25th percentile":
  - **Best bad case in 6 of 6**, often by a wide margin: demand −20% → −₹2.1 Cr vs −₹19.1 Cr for the two-contract rule; higher correlation → ₹14.6 Cr vs ₹1.8 Cr.
  - **Best expected profit in 5 of 6.** With demand +20%, the rule's bigger commitments earn more on average (₹47.3 Cr vs ₹46.2 Cr) but have a worse bad case (₹26.5 Cr vs ₹32.3 Cr).

Open the decision page: `out/blockwise_standalone.html`. It has budget, risk and shock controls, the buy list with a reason per line, the frontier, the profit distribution, exposure by region, where a new supplier would help most, and the proof tables.

### 3. Real-shock replay on official Singapore data (SGD, 2011–2026)
**Real data:** SingStat monthly
- **visitor arrivals resident in India** (M550001, Jan 2008 – Sep 2026);
- **average room rate and occupancy** for small, medium and large hotels (M550081).

Every month from Mar 2011 to Sep 2026 (187 decisions), Blockwise commits inventory **two months ahead** using **only the statistics already published that day** (data lags about 2 months). It is then scored against real demand, real rates and real occupancy. Occupancy decides whether buying as needed was possible.

**Result, plainly:**
- **Total profit: a tie with the best simple rule.** Max profit earned 81.1% of hindsight and Balanced 79.3%. The best simple rule (block the median forecast, given the same breaker) earned 80.1%, and 79.8% without the breaker. It uses Blockwise's own median forecast, so it is a strong baseline.
- **Downside: Blockwise is better.**
  - Through COVID, Balanced lost S$2.56M vs S$3.07M for the best rule, 17% less.
  - Its worst 5% of months averaged a loss of S$0.31M vs S$0.37M.
- **The risk dial works.** From Max profit to Careful, Blockwise gives up 4.2 points of total profit and cuts the COVID loss from S$2.77M to S$2.42M.
- **The most valuable safeguard is simple.** Stopping prepaid buying while the forecast is badly wrong cut the COVID loss of "block last year's volume" from S$6.47M to S$3.37M. Blockwise has the breaker built in, and any rule can adopt it.

| Policy | All months, % of hindsight | 2020–21 COVID | 2022–23 recovery | 2011–19 | 2024–26 | Worst-5% month (avg) |
|---|---|---|---|---|---|---|
| **Blockwise · Max profit** | 81.1% | −S$2.77M | +S$4.20M | 94% | 92% | −S$0.34M |
| **Blockwise · Balanced** | 79.3% | −S$2.56M | +S$3.94M | 91% | 90% | −S$0.31M |
| **Blockwise · Careful** | 76.9% | −S$2.42M | +S$3.57M | 89% | 89% | −S$0.30M |
| Block the median forecast + same breaker | 80.1% | −S$3.14M | +S$4.47M | 93% | 90% | −S$0.37M |
| Block last year's volume + same breaker | 79.1% | −S$3.37M | +S$4.23M | 93% | 90% | −S$0.40M |
| Allot + block p25 + same breaker | 76.6% | −S$3.07M | +S$4.18M | 89% | 88% | −S$0.37M |
| Block the median forecast (no breaker) | 79.8% | −S$3.72M | +S$4.93M | 93% | 90% | −S$0.43M |
| Allot + block p25 (no breaker) | 76.5% | −S$3.55M | +S$4.64M | 89% | 88% | −S$0.42M |
| Block last year's volume (no breaker) | 70.9% | −S$6.47M | +S$3.53M | 93% | 90% | −S$0.64M |
| Buy as needed only | 18.3% | +S$0.19M | +S$1.39M | 16% | 21% | −S$0.04M |

**Ablations and sensitivity:** each row is a full re-run, and the best rule is re-run under the same conditions.

| Variant (full re-run each) | Blockwise · Balanced | Best rule, same conditions | COVID: Blockwise / best rule | Worst-5% month: Blockwise / best rule |
|---|---|---|---|---|
| Blockwise: adaptive calibration + safeguards (headline) | 79.3% | 80.1% | −S$2.56M / −S$3.07M | −S$0.31M / −S$0.37M |
| Same, breaker at 1.5x error | 80.4% | 81.6% | −S$1.99M / −S$2.26M | −S$0.25M / −S$0.28M |
| Same, breaker at 3x error | 79.3% | 80.5% | −S$2.56M / −S$3.07M | −S$0.31M / −S$0.37M |
| Static calibration (equal weights) + safeguards | 73.9% | 80.5% | −S$2.52M / −S$3.10M | −S$0.31M / −S$0.37M |
| Adaptive calibration, no safeguards (no breaker, no cap) | 74.7% | 79.8% | −S$6.14M / −S$3.55M | −S$0.71M / −S$0.42M |
| Same as headline, buy-as-needed cut-offs 75/90% occupancy | 79.1% | 79.7% | −S$2.57M / −S$3.08M | −S$0.32M / −S$0.37M |
| Same as headline, buy-as-needed cut-offs 85/98% occupancy | 79.3% | 80.1% | −S$2.56M / −S$3.07M | −S$0.31M / −S$0.37M |

- **Adaptive calibration:**
  - Exponentially weighted empirical quantiles of past log forecast errors (half-life 6 months). This is *inspired by* weighted conformal prediction (Barber, Candès, Ramdas & Tibshirani, 2023), but without its finite-sample correction, so there is no coverage guarantee.
  - It calibrates only the **width** of the band around the model's own median.
  - 80% bands held 78% of the time overall (static: 71%). In COVID they held 54% (static: 4%). In 2024–26 they held 91%.
  - Static calibration remembers COVID forever and under-commits afterwards: 2024–26 falls to 66.8% of hindsight.
- **Point forecast:** seasonal level (mean of the last 3 de-seasonalised months × the target month's seasonal factor), or Chronos-2 zero-shot, picked each month by realised error. The split was seasonal level 102 months, Chronos-2 85 months.
- **Safeguards:**
  - a **circuit breaker**: no prepaid blocks while the forecast was more than 2× off in any of the last 3 published months (allotments and buy-as-needed only). It was on for 33 months (2020-07 to 2023-03);
  - forecast quantiles capped at 1.5× the highest month ever published.
- **Disclosure: changes made after seeing replay results.**
  1. Seasonal level replaced seasonal naive, which exploded in the recovery by multiplying a COVID-depressed base by a huge trend.
  2. The safeguards were added after the first replay exposed over-commitment through COVID. The thresholds are round numbers and the result barely moves between 1.5× and 3×.
  3. After an independent review, calibration became **width-only**. Previously past bias also shifted the median, which over-forecast the recovery about 3× and made "block the median forecast" an unfair strawman.
  4. "+ same breaker" baselines were added so the comparison is like-for-like.

  Without any safeguards, Balanced earns 74.7% vs 79.8% for the best rule. **Blockwise without the breaker loses to simple rules here.**
- **Other limits:**
  - One shock in one market. In calm years simple rules do as well (2011–19: Balanced 91.4%, best rule up to 93.1%).
  - SingStat serves today's revised figures, not what was published at the time.
  - Chronos-2 was pretrained in 2025, so its weights may encode the period being replayed.
  - In planning scenarios, one random draw drives arrivals, occupancy and rates together (a shock hits all three).
- **Assumptions:**
  - demand = 0.05 room-nights per Indian arrival, split 35/40/25% across small/medium/large hotels (percentages don't depend on the scale);
  - 85% of demand booked 3+ weeks ahead (from the real hotel bookings);
  - buying as needed is possible below 80% occupancy and impossible above 95% (75/90 and 85/98 tested above);
  - contract rates as in §1.
- **Licence:** contains information from SingStat Table Builder (tables M550001 and M550081), accessed on 19 Nov 2026, made available under the Singapore Open Data Licence.

### 4. Forecaster benchmark (real bookings, same backtest for every forecaster)
| Forecaster | Blockwise · Balanced % of hindsight (90% range) | Typical error (WAPE) | 80% / 90% band holds |
|---|---|---|---|
| Ensemble: calibrated linear + calibrated gradient-boosted (booking pace) + Chronos-2 | 89.9% (87–92) | **21.8%** | **82% / 92%** |
| Linear quantile regression (Round 1 model) | 88.8% (85–91) | 23.2% | 74% / 84% |
| Gradient-boosted quantiles + booking pace + conformal | 88.6% (85–91) | 27.1% | 72% / 85% |
| Auto: lowest realised error so far (**pre-declared headline**) | 88.0% (85–90) | 24.8% | 77% / 86% |
| Chronos-2 foundation model (Amazon, Oct 2025), zero-shot with booking-pace covariates | 86.8% (82–91) | 23.7% | 90% / 95% (too wide) |
| Linear + conformal | 86.0% (82–89) | 28.9% | 66% / 74% |

- **Honest reading:**
  - The profit ranges overlap (ensemble 87–92 vs linear 85–91), so the profit difference is within noise. The accuracy and calibration differences are clearer.
  - The foundation model on its own isn't the best, because its bands are too wide. It adds value **inside the ensemble**, which wins on every accuracy metric and is the only well-calibrated model.
  - Conformal recalibration of a single model *hurt* here: its calibration window holds the latest nights, which sit in a different season from the nights being forecast.
  - The pre-declared online selector had only 15 rounds to learn from. City Hotel stayed on the linear model. Resort Hotel switched between models: linear in rounds 1–3 and 8–9, gradient-boosted in 4–5, and the ensemble in 6–7 and from round 10.
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
.venv/bin/python scripts/build_site.py OUT_DIR   # static website (index.html) into OUT_DIR
# publish: commit OUT_DIR/index.html to the gh-pages branch of this repo (GitHub Pages serves it)
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
