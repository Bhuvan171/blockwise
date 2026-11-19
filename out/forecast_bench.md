| forecaster | Blockwise·Balanced % of hindsight (90% range) | WAPE | pinball | 80% band holds | 90% band holds | 80% band width |
|---|---|---|---|---|---|---|
| Ensemble: conformal LQR + conformal GBM + Chronos-2 (`ensemble_conf`) | 89.9% (87–92) | 21.8% | 2.81 | 82% | 92% | 96% of demand |
| Linear quantile regression (Round 1 baseline) (`qr`) | 88.8% (85–91) | 23.2% | 2.85 | 74% | 84% | 85% of demand |
| Gradient-boosted quantiles + booking pace + conformal (`gbm_conf`) | 88.6% (85–91) | 27.1% | 3.17 | 72% | 85% | 81% of demand |
| Auto: pick the model with the lowest realised error so far (`auto`) **(headline, pre-declared)** | 88.0% (85–90) | 24.8% | 2.93 | 77% | 86% | 87% of demand |
| Chronos-2 foundation model (zero-shot, pace covariates) (`chronos2`) | 86.8% (82–91) | 23.7% | 3.22 | 90% | 95% | 120% of demand |
| Linear quantile regression + conformal (`qr_conf`) | 86.0% (82–89) | 28.9% | 3.76 | 66% | 74% | 88% of demand |

Accuracy of every candidate inside the auto run (same nights):

| candidate | WAPE | pinball | 80% band holds | 90% band holds |
|---|---|---|---|---|
| Ensemble: conformal LQR + conformal GBM + Chronos-2 | 21.8% | 2.81 | 82% | 92% |
| Linear quantile regression (Round 1 baseline) | 23.2% | 2.85 | 74% | 84% |
| Gradient-boosted quantiles + booking pace + conformal | 27.1% | 3.17 | 72% | 85% |
| Chronos-2 foundation model (zero-shot, pace covariates) | 23.7% | 3.22 | 90% | 95% |
| Linear quantile regression + conformal | 28.9% | 3.76 | 66% | 74% |
