from invopt.forecast_bench import aggregate


def _run(pct, wape):
    summary = [{"policy": "ours_0.25", "pct_of_hindsight": pct, "pct_ci_lo": pct - 3, "pct_ci_hi": pct + 3,
                "total_profit": pct * 1000, "batches_with_loss": 0},
               {"policy": "hindsight", "pct_of_hindsight": 100.0, "pct_ci_lo": 100, "pct_ci_hi": 100,
                "total_profit": 100000, "batches_with_loss": 0}]
    fm = {"all": {"wape_median": wape, "pinball": 3.0, "coverage_80": 0.8, "coverage_90": 0.9, "width_80_rel": 0.5,
                  "nights": 840, "wape_last_year": 0.5}}
    return {"summary": summary, "forecast_metrics": fm, "meta": {"forecaster": "x"}}


def test_aggregate_ranks_by_profit_and_keeps_all():
    res = aggregate({"qr": _run(88.8, 0.23), "gbm_conf": _run(90.1, 0.20), "auto": _run(89.5, 0.21)}, headline="auto")
    names = [r["forecaster"] for r in res["rows"]]
    assert set(names) == {"qr", "gbm_conf", "auto"}
    assert res["headline"] == "auto"
    row = {r["forecaster"]: r for r in res["rows"]}["gbm_conf"]
    assert row["pct_of_hindsight"] == 90.1 and row["wape"] == 0.20 and row["coverage_80"] == 0.8
    assert "| forecaster" in res["markdown"] and "auto" in res["markdown"]
