import requests
import pandas as pd
from config.dates import DATE_START, DATE_END

GOV_UK_HOLIDAYS_URL = "https://www.gov.uk/bank-holidays.json"


def fetch(start: str = DATE_START, end: str = DATE_END) -> pd.Series:
    """
    Pull England & Wales bank holidays from GOV.UK.

    Returns a boolean Series indexed by date (True = bank holiday).
    Requires: requests  (pip install requests)
    """
    resp = requests.get(GOV_UK_HOLIDAYS_URL, timeout=30)
    resp.raise_for_status()

    events    = resp.json()["england-and-wales"]["events"]
    hol_dates = pd.to_datetime([e["date"] for e in events])

    all_dates = pd.date_range(start=start, end=end, freq="D")
    return pd.Series(
        all_dates.isin(hol_dates).astype(int),
        index=all_dates,
        name="is_bank_holiday",
    )
