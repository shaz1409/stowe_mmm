import pandas as pd


def build_calendar_features(date_range: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Build derived calendar columns for the given date index:
      - week_of_year     int
      - month            int
      - is_december      bool   (Christmas trading uplift)
      - is_january       bool   (post-Christmas demand dip)
      - days_to_easter   int    (signed — negative before, positive after)
      - month_sin / _cos float  (cyclic encoding of month, avoids Dec→Jan cliff)
    """
    raise NotImplementedError
