# Singapore real-shock replay: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (native). Steps use `- [ ]`.

**Goal:** A walk-forward backtest on **real official data**, 2011–2026: Singapore hotels for Indian travellers. It runs through the COVID collapse, the recovery and 2026. It shows Blockwise's shock-aware commitments against simple rules and perfect hindsight, month by month.

**Data (SingStat, Singapore Open Data Licence, attribution):**
- `M550001`: international visitor arrivals by place of residence, monthly. Row **India**, Jan 2008 – Sep 2026.
- `M550081`: hotel statistics, monthly. **Average room rate (SGD)** and **average occupancy (%)** for small, medium and large hotels, Jan 2008 – Sep 2026.
- Real-data-derived assumption: share of B2B demand booked ≥ 21 days ahead = 0.85, from the Offline TA/TO segment of the real hotel-bookings dataset.

**Model (each line is a labelled assumption unless marked real):**
- **Products:** Singapore hotels in 3 size bands (small / medium / large). One cell per band per target month.
- **Demand:** room-nights = κ × India arrivals (real) × tier share. κ = 0.05 room-nights per arrival (≈1.25% of Indian visitors × 4 nights); tier shares 0.35 / 0.40 / 0.25. % of hindsight does not depend on κ, since everything is linear.
- **Timing:** decide at the start of month d with data through d−2 (SingStat publishes about 1 month after month-end). The target month is d+2, so forecasts are 4 steps beyond the last observed month.
- **Prices (real):**
  - Selling price = that tier's real average room rate in the target month.
  - Contract reference rate = same month last year × recent year-on-year ratio (known at d).
- **Sell-outs (real occupancy):**
  - Buy-as-needed available share = clip((95% − occupancy) / 15%, 0, 1).
  - Planning uses forecast occupancy; scoring uses actual occupancy.
- **Allotment cap:** ≤ max(last year's same-month demand, median forecast). It's the production the hotel expects.
- **Contract terms:** unchanged (block −30%, allotment −20%, buy-as-needed −10%, hold 2%, goodwill 10%).

**Forecasters (4 steps ahead):**
- `snaive`: same month last year × trailing year-on-year ratio, with empirical quantiles of past log-errors.
- `chronos2`: zero-shot on each series (arrivals, occupancy by tier, rate by tier).
- `*_aci` variants: **adaptive conformal quantile tracking**, a per-quantile log-offset updated online as each target month is published: δ ← δ + η·(miss − (1−τ)), η = 0.05.
- `auto`: per decision, the candidate with the lowest pinball loss on months already published. **Pre-declared headline.**

**Policies:** buy as needed only · block last year's volume · block the median forecast · allot last year + block p25 · Blockwise (Max profit / Balanced / Careful) · perfect hindsight. Same LP and evaluator as the main backtest.

**Report:** % of hindsight overall and by period (2011–19 normal · 2020–21 COVID · 2022–23 recovery · 2024–26 recent); worst month; months with a loss; worst-5% month average; forecast coverage by period (does ACI recover after the shock?); a monthly commitment timeline for the page.

## Review focus
1. Publication-lag leakage: nothing about months ≥ d−1 may affect a decision at d.
2. COVID zeros: log transforms and ratios must stay finite (floor at 1 arrival).
3. ACI updates must use only months published by d.
4. Chronos-2 failure → fall back to `snaive` and record it.
5. The 3 tiers share one arrivals uniform (comonotone); state it.

### Task S1: SingStat loader + monthly panel (`sg_data.py`)
- [ ] Tests: India 2019-May = 182,727; 225 months; tier rates and occupancy parsed; a missing value becomes NaN and is reported.

### Task S2: monthly forecasters + ACI (`sg_forecast.py`)
- [ ] Tests: snaive quantiles sorted; on a synthetic level shift, ACI's 80% coverage over the 24 months after the shift is ≥ 0.6, while static stays ≤ 0.35; Chronos monthly shapes; `quantiles_at(d)` unchanged when months ≥ d−1 are altered (no look-ahead).

### Task S3: walk-forward replay (`sg_backtest.py`) + CLI `singapore`
- [ ] Tests: hindsight ≥ every policy each month (tol 1e-6); allotment cap respected; period table has 4 periods; JSON is serialisable.
- [ ] Run; then page section (timeline + period table), README and ROUND1 updates.
