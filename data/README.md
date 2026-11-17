# Data card

## Real data: "Hotel booking demand"
- **Source:** Nuno António, Ana de Almeida, Luís Nunes (2019), *Hotel booking demand datasets*, Data in Brief 22, 41–49, doi:10.1016/j.dib.2018.11.126. An open-access article; the data was published with it for research use. We use the TidyTuesday 2020-02-11 copy (`scripts/fetch_data.sh`, 16,855,599 bytes; not committed).
- **What it is:** 119,390 real bookings for two hotels in Portugal ("City Hotel", "Resort Hotel"), arrivals 1 Jul 2015 – 31 Aug 2017. Each row is one room booking, with lead time, stay length, market segment, distribution channel, average daily rate (ADR, EUR), and final status (Check-Out / Canceled / No-Show) with its date. Hotel and guest identities were removed by the authors.
- **Cleaning** (`load_bookings`): 117,398 rows kept. Dropped: 715 zero-night stays, 110 with no guests, 1,166 with ADR ≤ 0, 1 with ADR > 1,000 (the known 5,400 outlier). No rows had unparseable dates.
- **B2B stream:** market segment **"Offline TA/TO"** (offline travel agents and tour operators), the closest analogue in this data to a B2B wholesaler like TBO. Decision rule from the plan: widen to "Groups" only if median weekly room-nights < 50. Both hotels pass, so Offline TA/TO alone is used.

| Hotel | Offline TA/TO bookings | Cancel/no-show rate | Mean ADR (EUR) | Median weekly B2B room-nights | Booked ≥ 21 days ahead | Max rooms occupied in data |
|---|---|---|---|---|---|---|
| City Hotel | 16,508 | 43.3% | 94.0 | 234.5 | 84.9% | 225 |
| Resort Hotel | 7,376 | 15.3% | 75.6 | 327.0 | 89.6% | 184 |

## Real vs assumed in the backtest
| Field | Status |
|---|---|
| B2B demand per night, booking dates, lead times, cancellations, no-shows | **Real** |
| Realised selling price per night (mean ADR of B2B room-nights) | **Real** |
| Hotel occupancy per night (all segments), used for sold-out nights | **Real** (capacity estimated only from nights before the first decision date). Simplification: a night at ≥ 98% of capacity is treated as closed to buy-as-needed purchases for all of that night's B2B demand, including bookings made weeks earlier. That is pessimistic for buy-as-needed; the 100% threshold is reported as a sensitivity. |
| Contract types and their rates (hard −30%, allotment −20%, buy-as-needed −10% vs reference/market) | **Assumption**. Swept: block −25% / allotment −15% (`out/backtest_rates_low.*`) and −35% / −25% (`out/backtest_rates_high.*`) |
| Allotment hold cost (2%), stockout penalty (10%), salvage (0%), release window (21 days) | **Assumption** |
| Currency | EUR, as in the source. Never mixed with the synthetic INR portfolio. |

## Synthetic data
The TBO-like multi-destination portfolio (`src/invopt/portfolio.py`) is **fully synthetic**. Every parameter is a labelled assumption with a one-line rationale in code.
