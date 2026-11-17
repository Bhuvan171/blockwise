"""Load and shape the public "Hotel booking demand" data (António et al., 2019).

Each booking is one room. A booking stays on nights [arrival, arrival + nights).
Only bookings with status "Check-Out" consumed a room; "Canceled" and "No-Show"
did not. `booking_date = arrival - lead_time`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# Closest analogue to a B2B wholesaler like TBO in this data: offline travel agents / tour operators.
B2B_SEGMENTS: tuple[str, ...] = ("Offline TA/TO",)

_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

ADR_MAX = 1000.0


def load_bookings(path: str | Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """Return the cleaned bookings frame and the number of rows dropped per reason."""
    raw = pd.read_csv(path, na_values=["NA", "NULL"], keep_default_na=True)
    df = pd.DataFrame({
        "hotel": raw["hotel"].astype(str),
        "segment": raw["market_segment"].astype(str),
        "channel": raw["distribution_channel"].astype(str),
        "lead_time": pd.to_numeric(raw["lead_time"], errors="coerce"),
        "nights": pd.to_numeric(raw["stays_in_weekend_nights"], errors="coerce").fillna(0)
        + pd.to_numeric(raw["stays_in_week_nights"], errors="coerce").fillna(0),
        "guests": pd.to_numeric(raw["adults"], errors="coerce").fillna(0)
        + pd.to_numeric(raw["children"], errors="coerce").fillna(0)
        + pd.to_numeric(raw["babies"], errors="coerce").fillna(0),
        "adr": pd.to_numeric(raw["adr"], errors="coerce"),
        "status": raw["reservation_status"].astype(str),
    })
    month = raw["arrival_date_month"].map(_MONTHS)
    df["arrival"] = pd.to_datetime(
        dict(year=raw["arrival_date_year"], month=month, day=raw["arrival_date_day_of_month"]),
        errors="coerce",
    )
    status_date = pd.to_datetime(raw["reservation_status_date"], errors="coerce")

    drops: dict[str, int] = {}
    keep = pd.Series(True, index=df.index)

    def drop(reason: str, mask: pd.Series) -> None:
        nonlocal keep
        hit = mask & keep
        n = int(hit.sum())
        if n:
            drops[reason] = n
        keep &= ~hit

    drop("bad_date", df["arrival"].isna() | df["lead_time"].isna())
    drop("zero_nights", df["nights"] <= 0)
    drop("no_guests", df["guests"] <= 0)
    drop("adr_nonpositive", df["adr"].isna() | (df["adr"] <= 0))
    drop("adr_outlier", df["adr"] > ADR_MAX)
    drop("unknown_status", ~df["status"].isin(["Check-Out", "Canceled", "No-Show"]))

    df = df[keep].copy()
    df["nights"] = df["nights"].astype(int)
    df["lead_time"] = df["lead_time"].astype(int)
    df["booking_date"] = df["arrival"] - pd.to_timedelta(df["lead_time"], unit="D")
    df["cancel_date"] = status_date[keep].where(df["status"] == "Canceled")
    df = df.drop(columns=["guests"]).reset_index(drop=True)
    return df, drops


def expand_nights(bookings: pd.DataFrame) -> pd.DataFrame:
    """One row per (booking, night stayed or booked)."""
    n = bookings["nights"].to_numpy()
    idx = np.repeat(np.arange(len(bookings)), n)
    offset = np.arange(len(idx)) - np.repeat(np.cumsum(n) - n, n)
    out = bookings.iloc[idx].reset_index(drop=True)
    out["night"] = out["arrival"].to_numpy() + pd.to_timedelta(offset, unit="D").to_numpy()
    return out


def night_panel(
    bookings: pd.DataFrame,
    hotel: str,
    segments: tuple[str, ...],
    release_days: int,
    asof: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Per-night demand panel for one hotel.

    Columns: final, early_final, adr_mean, occ_total and, if `asof` is given, on_hand.
    """
    nights = expand_nights(bookings[bookings["hotel"] == hotel])
    stayed = nights["status"] == "Check-Out"
    b2b = nights["segment"].isin(segments)
    early = nights["lead_time"] >= release_days

    full_index = pd.date_range(nights["night"].min(), nights["night"].max(), freq="D", name="night")

    def count(mask: pd.Series) -> pd.Series:
        return nights.loc[mask].groupby("night").size().reindex(full_index, fill_value=0)

    panel = pd.DataFrame(index=full_index)
    panel["final"] = count(stayed & b2b)
    panel["early_final"] = count(stayed & b2b & early)
    panel["occ_total"] = count(stayed)
    panel["adr_mean"] = nights.loc[stayed & b2b].groupby("night")["adr"].mean().reindex(full_index)
    if asof is not None:
        asof = pd.Timestamp(asof)
        on_books = (nights["booking_date"] <= asof) & (
            nights["cancel_date"].isna() | (nights["cancel_date"] > asof)
        )
        panel["on_hand"] = count(b2b & on_books)
    return panel
