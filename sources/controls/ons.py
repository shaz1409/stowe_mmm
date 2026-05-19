import pandas as pd
from config.dates import DATE_START, DATE_END

ONS_API_BASE = "https://api.ons.gov.uk/v1"

ONS_SERIES = {
    "retail_sales_index": "J5EK",
}


def fetch(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Pull ONS series defined in ONS_SERIES via the ONS API.

    Returns a monthly-indexed DataFrame with one column per series key.
    Requires: requests  (pip install requests)
    """
    raise NotImplementedError
