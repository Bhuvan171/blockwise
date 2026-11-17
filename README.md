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

Every 4 weeks we plan the 4 weeks of stays starting 8 weeks later, using **only what was known that day**, then score against what really happened. That covers 15 planning rounds × 2 hotels, Jul 2016 – Aug 2017. Demand, booking dates, cancellations, prices and sold-out nights are real; contract rates are assumptions.

| Policy | Profit | % of perfect hindsight | Demand served | Unsold block cost | Worst round | Rounds with a loss |
|---|---|---|---|---|---|---|
| Buy as needed only | €20,438 | 2.4% | 57.8% | €0 | −€19,165 | 6 |
| Block last year's volume | €257,988 | 30.7% | 91.3% | €553,854 | −€72,613 | 4 |
| Block the median forecast | €522,395 | 62.1% | 94.3% | €342,100 | −€2,097 | 2 |
| Blockwise · Max profit | €746,875 | 88.8% | 97.6% | €64,081 | €11,595 | 0 |
| **Blockwise · Balanced** | **€746,835** | **88.8%** | 97.1% | €44,598 | €12,216 | **0** |
| Blockwise · Careful | €739,059 | 87.8% | 96.2% | €27,603 | €12,895 | 0 |
| Perfect hindsight (upper bound) | €841,458 | 100% | 98.6% | €22,151 | €17,009 | 0 |

**Sensitivity:** share of perfect-hindsight profit under each assumption. Every row is a full re-run (`out/backtest_*.json`).

| Scenario | Blockwise · Balanced | Block median forecast | Block last year | Buy as needed |
|---|---|---|---|---|
| Headline (allotment ≤ last year's production; sold out at 98% occupancy) | **88.8%** | 62.1% | 30.7% | 2.4% |
| Allotments not capped | 88.9% | 60.9% | 30.1% | 2.4% |
| Sold out only at 100% of capacity | 89.4% | 63.5% | 33.5% | 21.8% |
| Prepaid budget halved | 91.0% | 58.4% | 58.6% | 2.6% |

**Forecast quality**, 8–12 weeks ahead, per hotel-night (840 nights): typical error (WAPE) **23%** vs 50% for "same night last year". The 10–90% band held the real value 74% of the time; the target is 80%, so the bands are slightly narrow.

### 2. TBO-like portfolio (synthetic, INR, Jan–Mar 2027)
12 destinations × 2 hotel tiers + 4 flight seat routes, 13 weeks. Regional correlation, seasonality and event weeks are included; every parameter is a labelled assumption (`src/invopt/portfolio.py`). Plans are optimised on 150 simulated futures and **scored on 4,000 fresh ones**.

- **Budget frontier (Balanced):** ₹50.5 Cr prepaid → ₹71.6 Cr expected profit · ₹101 Cr → ₹82.4 Cr · ₹152 Cr → ₹90.9 Cr · ₹202.5 Cr → ₹95.6 Cr. At ₹152 Cr the next ₹1 Cr of budget earns ₹0.17 Cr. Above about ₹202 Cr extra budget isn't used.
- **Stress tests** on every plan: a Middle East disruption, an Indian airline collapse, and a rupee slide.
- **Robustness:** the Balanced plan, optimised for the base world only, was scored in **seven worlds it was not planned in**: demand ±20%, stronger seasons, higher correlation, later bookings, more volatile demand. It had the **highest expected profit in 7/7 and the best bad case in 7/7** against blocking the median forecast, blocking expected volume, and buying as needed. Example ("more volatile"): ₹82.8 Cr expected / ₹41.2 Cr bad case vs ₹69.9 Cr / ₹33.5 Cr for the median-forecast block.

Open the decision page: `out/blockwise_standalone.html`. It has budget, risk and shock controls, the buy list with a reason per line, the frontier, the profit distribution, exposure by region, where a new supplier would help most, and the proof tables.

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
- Allocation per scenario: hard block → late demand first, allotment → early demand, buy as needed → the rest when the market isn't sold out.
- The optimiser ran in under 2 minutes per plan on a laptop CPU. The full grid (20 plans + stress tests + robustness) takes 15 min.

## Run it
```bash
cd inventory
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
./scripts/fetch_data.sh                 # 16.9 MB public CSV
.venv/bin/pytest                        # tests
.venv/bin/python -m invopt.cli all      # backtest (~3 min) → grid (~15 min) → page
open out/blockwise_standalone.html
```
Sensitivity runs: `python -m invopt.cli backtest --soft-cap-mult none --tag _uncapped`, `--soldout-tau 1.0 --tag _tau1`, `--budget-share 0.5 --tag _budget0.5`, then `grid` and `page` again.

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
- The forecast bands are slightly narrow (74% vs 80% coverage).
- Not yet built (Round 2): weekly re-planning as bookings arrive, selling-price optimisation, buy-by timing, a supplier-integration ranking with integration cost, a TBO data adapter (search logs with sold-outs and look-to-book), a faster decomposition solver, and million-scenario tests on GPU.

## Repository
`src/invopt/`: `hotel_data` (loader), `economics` (profit truth), `optimizer` (LP), `forecast`, `scenarios`, `backtest`, `portfolio` (synthetic world, shocks, worlds), `grid`, `page`, `cli` · `tests/` (pytest) · `data/README.md` (data card) · `out/` (results and pages) · `docs/superpowers/plans/` (implementation plan).

## Licences and tools
numpy, pandas, scipy (BSD; HiGHS solver MIT) and scikit-learn (BSD) at runtime; pytest (MIT) for tests. The data is from an open-access *Data in Brief* article; cite it when reusing. Built with AI coding assistance (Claude Code).
