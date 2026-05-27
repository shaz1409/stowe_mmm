import requests
import pandas as pd
from config.dates import DATE_START, DATE_END

ONS_API_BASE = "https://api.ons.gov.uk/v1"

# ONS timeseries IDs → output column names
ONS_SERIES = {
    "retail_sales_index": "J5EK",  # Retail Sales Index (all retailing, seasonally adjusted)
}


def _fetch_timeseries(series_id: str) -> pd.Series:
    """
    Pull monthly values for one ONS timeseries via the ONS API.

    ONS API returns JSON with a `months` key:
      [{"date": "2020 JAN", "value": "105.3"}, ...]
    """
    url  = f"{ONS_API_BASE}/timeseries/{series_id}/data"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    data   = resp.json()
    months = data.get("months", [])
    if not months:
        return pd.Series(dtype=float, name=series_id)

    records = {
        pd.to_datetime(row["date"], format="%Y %b"): float(row["value"])
        for row in months
        if row.get("value") not in (None, "", ".")
    }

    s = pd.Series(records, name=series_id)
    s.index.name = "date"
    return s.sort_index()


def fetch(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Pull ONS series defined in ONS_SERIES via the ONS API.

    Returns a monthly-indexed DataFrame with one column per series key.
    Requires: requests  (pip install requests)
    """
    frames = {}
    for col_name, series_id in ONS_SERIES.items():
        print(f"  Fetching ONS timeseries {series_id} ({col_name})")
        s = _fetch_timeseries(series_id)
        # Trim to requested date range
        if not s.empty:
            s = s.loc[start:end]
        frames[col_name] = s

    df = pd.DataFrame(frames)
    df.index.name = "date"
    return df
