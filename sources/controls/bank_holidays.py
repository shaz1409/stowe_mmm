import pandas as pd
from config.dates import DATE_START, DATE_END

GOV_UK_HOLIDAYS_URL = "https://www.gov.uk/bank-holidays.json"


def fetch(start: str = DATE_START, end: str = DATE_END) -> pd.Series:
    """
    Pull England & Wales bank holidays from GOV.UK.

    Returns a boolean Series indexed by date (True = bank holiday).
    Requires: requests  (pip install requests)
    """
    raise NotImplementedError
