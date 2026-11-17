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
.venv/bin/pytest                        # tests
.venv/bin/python -m invopt.cli all      # backtest (~3 min) → grid (~15 min) → page
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
numpy, pandas, scipy (BSD; HiGHS solver MIT) and scikit-learn (BSD) at runtime; pytest (MIT) for tests. The data is from an open-access *Data in Brief* article; cite it when reusing. Built with AI coding assistance (Claude Code).
