import pandas as pd
from config.dates import DATE_START, DATE_END

LAND_REGISTRY_URL = "http://landregistry.data.gov.uk/data/ukhpi/region/united-kingdom/month/{year}-{month:02d}.json"


def fetch(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Pull UK House Price Index and transaction volumes from Land Registry linked-data API.

    Returns a monthly-indexed DataFrame with columns:
      - hpi_index            float  (house price index, base 100 = Jan 2015)
      - hpi_yoy_change       float  (% change YoY)
      - transaction_count    int
    Requires: requests  (pip install requests)
    """
    raise NotImplementedError
