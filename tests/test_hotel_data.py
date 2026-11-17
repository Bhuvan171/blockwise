from pathlib import Path

import pandas as pd
import pytest

from invopt.hotel_data import load_bookings, night_panel

FIX = Path(__file__).parent / "fixtures" / "hotels_small.csv"
SEG = ("Offline TA/TO",)
NIGHT = pd.Timestamp("2016-07-03")


@pytest.fixture(scope="module")
def loaded():
    return load_bookings(FIX)


def test_arrival_and_booking_dates(loaded):
    df, _ = loaded
    first = df[(df.lead_time == 10) & (df.status == "Check-Out")].iloc[0]
    assert first.arrival == pd.Timestamp("2016-07-03")
    assert first.booking_date == pd.Timestamp("2016-06-23")
    assert first.nights == 2


def test_nights_and_dirty_rows_dropped(loaded):
    df, drops = loaded
    assert len(df) == 7
    assert drops == {"zero_nights": 1, "adr_nonpositive": 1, "adr_outlier": 1, "no_guests": 1}
    assert (df.adr > 0).all() and (df.adr <= 1000).all() and (df.nights > 0).all()


def test_noshow_not_stayed(loaded):
    df, _ = loaded
    panel = night_panel(df, "City Hotel", SEG, release_days=21)
    # rows 1, 8, 10 stay on 07-03; the No-Show (row 6) and cancellations do not
    assert panel.loc[NIGHT, "final"] == 3
    assert panel.loc[pd.Timestamp("2016-07-04"), "final"] == 1  # only row 1's 2nd night
    assert panel.loc[NIGHT, "occ_total"] == 4  # + the Online TA booking


def test_on_hand_asof(loaded):
    df, _ = loaded
    panel = night_panel(df, "City Hotel", SEG, release_days=21, asof=pd.Timestamp("2016-06-25"))
    # counts: row 1 (booked 06-23), row 7 (booked 06-23, cancelled later on 06-30), row 10 (booked 06-03)
    # excludes: row 8 (booked 06-26), row 9 (cancelled 06-24), row 6 (booked 06-28)
    assert panel.loc[NIGHT, "on_hand"] == 3


def test_early_final_split(loaded):
    df, _ = loaded
    panel = night_panel(df, "City Hotel", SEG, release_days=21)
    assert panel.loc[NIGHT, "early_final"] == 1  # only the lead-30 booking
    assert panel.loc[NIGHT, "adr_mean"] == pytest.approx((100 + 110 + 120) / 3)
