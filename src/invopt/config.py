"""Contract terms and risk levels shared by every part of the planner.

All money parameters are fractions of a cell's *reference rate*: the rate a
contract is negotiated against before the stay. Dynamic ("buy as needed")
units are bought at a discount to the *market price* at the time of sale.
These are labelled assumptions; the UI shows and the README lists them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

# Risk appetite -> lambda in  max  E[profit] - lambda * CVaR95(loss)
RISK_LEVELS: dict[str, float] = {
    "Max profit": 0.0,
    "Balanced": 0.25,
    "Careful": 1.0,
    "Very careful": 3.0,
}


@dataclass(frozen=True)
class ContractTerms:
    hard_discount: float = 0.30  # hard block: prepaid, non-refundable, deepest rate
    soft_discount: float = 0.20  # soft allotment: pay only for units used; free release
    dyn_discount: float = 0.10  # buy-as-needed net rate vs the market price at sale time
    soft_hold_cost: float = 0.02  # per allotted unit: utilisation penalty with the supplier
    stockout_penalty: float = 0.10  # per unit of unmet demand: agent goodwill / churn
    salvage: float = 0.0  # share of hard cost recovered for an unsold hard unit
    release_days: int = 21  # allotment returns to the supplier this many days before arrival

    def validate(self) -> "ContractTerms":
        for name in ("hard_discount", "soft_discount", "dyn_discount", "salvage"):
            v = getattr(self, name)
            if not 0.0 <= v < 1.0:
                raise ValueError(f"{name} must be in [0, 1), got {v}")
        if self.soft_hold_cost < 0 or self.stockout_penalty < 0:
            raise ValueError("soft_hold_cost and stockout_penalty must be >= 0")
        if self.hard_discount < self.soft_discount:
            raise ValueError(
                "hard_discount must be >= soft_discount: a prepaid hard block must not cost "
                f"more per unit than a refundable allotment ({self.hard_discount} < {self.soft_discount})"
            )
        if self.release_days < 0:
            raise ValueError("release_days must be >= 0")
        return self

    def costs(self, ref_rate, market_price) -> dict[str, np.ndarray]:
        """Per-unit money terms for arrays of reference rates and market prices."""
        ref = np.asarray(ref_rate, dtype=float)
        mkt = np.asarray(market_price, dtype=float)
        hard = (1.0 - self.hard_discount) * ref
        return {
            "hard": hard,
            "soft": (1.0 - self.soft_discount) * ref,
            "dyn": (1.0 - self.dyn_discount) * mkt,
            "hold": self.soft_hold_cost * ref,
            "stockout": self.stockout_penalty * ref,
            "salvage": self.salvage * hard,
        }

    def as_dict(self) -> dict:
        return asdict(self)
