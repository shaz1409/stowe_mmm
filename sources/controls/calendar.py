import numpy as np
import pandas as pd
from dateutil.easter import easter


def build_calendar_features(date_range: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Build derived calendar columns for the given date index:
      - week_of_year     int
      - month            int
      - is_december      bool   (Christmas trading uplift)
      - is_january       bool   (post-Christmas demand dip)
      - is_divorce_day   bool   (first Monday of January — spike in enquiries)
      - days_to_easter   int    (signed: negative = before, positive = after)
      - month_sin / _cos float  (cyclic encoding of month, avoids Dec→Jan cliff)
    """
    df = pd.DataFrame({"date": date_range})

    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["month"]        = df["date"].dt.month
    df["is_december"]  = (df["month"] == 12).astype(int)
    df["is_january"]   = (df["month"] == 1).astype(int)

    # First Monday of January = "Divorce Day" — see CLAUDE.md Domain Notes
    divorce_days = set()
    for year in df["date"].dt.year.unique():
        d = pd.Timestamp(year, 1, 1)
        days_ahead = (7 - d.weekday()) % 7  # days until next Monday
        if d.weekday() != 0:
            d = d + pd.Timedelta(days=days_ahead)
        divorce_days.add(d)

    df["is_divorce_day"] = df["date"].isin(divorce_days).astype(int)

    # days_to_easter: always references nearest Easter (handles Jan/Dec edge cases)
    def _days_to_easter(d: pd.Timestamp) -> int:
        e_this = pd.Timestamp(easter(d.year))
        delta  = (d - e_this).days
        if delta > 180:
            return (d - pd.Timestamp(easter(d.year + 1))).days
        if delta < -180:
            return (d - pd.Timestamp(easter(d.year - 1))).days
        return delta

    df["days_to_easter"] = df["date"].apply(_days_to_easter)

    # Cyclic month encoding: sin/cos pair avoids the hard cliff between Dec and Jan
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    return df.set_index("date")
