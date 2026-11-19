from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("chronos")

from invopt.backtest import BacktestConfig, HotelBook  # noqa: E402
from invopt.chronos_fc import chronos2_quantiles  # noqa: E402
from invopt.hotel_data import B2B_SEGMENTS, load_bookings  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "raw" / "hotels.csv"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="run scripts/fetch_data.sh first")
T = pd.Timestamp("2016-09-26")
CFG = BacktestConfig()
NIGHTS = pd.date_range(T + pd.Timedelta(days=56), periods=28, freq="D")


@pytest.fixture(scope="module")
def bookings():
    return load_bookings(DATA)[0]


def test_chronos_shapes_sorted(bookings):
    book = HotelBook(bookings, "Resort Hotel", B2B_SEGMENTS, CFG.release_days)
    q = chronos2_quantiles(book, T, NIGHTS, CFG)
    assert q.shape == (28, 7)
    assert np.all(np.isfinite(q)) and np.all(q >= 0) and np.all(np.diff(q, axis=1) >= -1e-9)


def test_chronos_no_lookahead(bookings):
    alt = bookings.copy()
    m = alt["booking_date"] > T
    alt.loc[m, "arrival"] += pd.Timedelta(days=3)
    alt.loc[m, "booking_date"] += pd.Timedelta(days=3)
    a = chronos2_quantiles(HotelBook(bookings, "City Hotel", B2B_SEGMENTS, CFG.release_days), T, NIGHTS, CFG)
    b = chronos2_quantiles(HotelBook(alt, "City Hotel", B2B_SEGMENTS, CFG.release_days), T, NIGHTS, CFG)
    np.testing.assert_allclose(a, b, rtol=1e-5, atol=1e-4)
