import io
import requests
import pandas as pd
from config.dates import DATE_START, DATE_END

# Bulk CSV download from the HM Land Registry UKHPI application.
# Returns all available monthly indicators for the selected region.
LAND_REGISTRY_DOWNLOAD_URL = "https://landregistry.data.gov.uk/app/ukhpi/download"
LAND_REGISTRY_REGION_URI   = "http://landregistry.data.gov.uk/id/region/united-kingdom"

# Column names as returned by the UKHPI bulk CSV download
_COL_MAP = {
    "Date":              "month",
    "House Price Index": "hpi_index",
    "Annual Change":     "hpi_yoy_change",   # reported as a decimal (e.g. 0.052 = 5.2%)
    "Sales Volume":      "transaction_count",
}


def fetch(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Pull UK House Price Index and transaction volumes from Land Registry linked-data API.

    Returns a monthly-indexed DataFrame with columns:
      - hpi_index            float  (house price index, base 100 = Jan 2015)
      - hpi_yoy_change       float  (annual % change as decimal, e.g. 0.052)
      - transaction_count    int
    Requires: requests  (pip install requests)
    """
    params = {
        "from":     start,
        "to":       end,
        "location": LAND_REGISTRY_REGION_URI,
        "format":   "csv",
    }
    print(f"  Fetching Land Registry UKHPI ({start} → {end})")
    resp = requests.get(LAND_REGISTRY_DOWNLOAD_URL, params=params, timeout=60)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))

    # Select and rename only the columns we need; tolerate missing columns
    available = {k: v for k, v in _COL_MAP.items() if k in df.columns}
    df = df.rename(columns=available)

    if "month" not in df.columns:
        raise ValueError(
            f"Land Registry CSV missing expected 'Date' column. "
            f"Columns found: {list(df.columns)}"
        )

    df["month"] = pd.to_datetime(df["month"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["month"]).set_index("month")
    df = df[[c for c in ["hpi_index", "hpi_yoy_change", "transaction_count"] if c in df.columns]]

    df["hpi_index"]      = pd.to_numeric(df.get("hpi_index"),      errors="coerce")
    df["hpi_yoy_change"] = pd.to_numeric(df.get("hpi_yoy_change"), errors="coerce")

    if "transaction_count" in df.columns:
        df["transaction_count"] = pd.to_numeric(df["transaction_count"], errors="coerce").astype("Int64")

    df.index.name = "date"
    return df
