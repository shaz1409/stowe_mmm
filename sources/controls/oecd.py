import requests
import pandas as pd
from config.dates import DATE_START, DATE_END, COUNTRY

OECD_BASE = "https://stats.oecd.org/SDMX-JSON/data"

# (dataset_id, series_code, human label)
OECD_DATASETS = {
    "cli":           ("MEI_CLI",    "LOLITOAA", "Composite Leading Indicator"),
    "cpi_yoy":       ("PRICES_CPI", "CPALTT01", "CPI all-items YoY %"),
    "unemployment":  ("MEI_LABOUR", "LRUNTTTT", "Unemployment rate %"),
    "hh_confidence": ("HH_DASH",    "CSCICP03", "Consumer confidence index"),
}


def _fetch_series(dataset: str, series: str, country: str, start: str, end: str) -> pd.Series:
    """
    Fetch one OECD SDMX-JSON series and return a date-indexed pd.Series.

    OECD SDMX-JSON structure:
      response["dataSets"][0]["observations"] — dict mapping "i:j:k:..." → [value, ...]
      response["structure"]["dimensions"]["observation"] — ordered list of dim definitions
    The last dimension is always TIME_PERIOD; its values list gives the date labels.
    """
    # M = monthly frequency
    url = f"{OECD_BASE}/{dataset}/{series}.{country}.M/all"
    params = {
        "startTime":                  start[:7],  # YYYY-MM
        "endTime":                    end[:7],
        "dimensionAtObservation":     "AllDimensions",
    }

    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code == 404:
        # Dataset/series combination not available for this country — return empty
        return pd.Series(dtype=float, name=series)
    resp.raise_for_status()

    payload = resp.json()
    observations = payload["dataSets"][0]["observations"]
    time_values  = payload["structure"]["dimensions"]["observation"][-1]["values"]

    # Key format: "dim0_idx:dim1_idx:...:time_idx" — time is last dimension
    n_dims = len(payload["structure"]["dimensions"]["observation"])

    records = {}
    for key, val in observations.items():
        parts    = key.split(":")
        time_idx = int(parts[-1])
        date_str = time_values[time_idx]["id"]  # e.g. "2020-01"
        records[date_str] = val[0]

    if not records:
        return pd.Series(dtype=float, name=series)

    s = pd.Series(records, name=series)
    s.index = pd.to_datetime(s.index)
    s.index.name = "date"
    return pd.to_numeric(s, errors="coerce").sort_index()


def fetch(start: str = DATE_START, end: str = DATE_END, country: str = COUNTRY) -> pd.DataFrame:
    """
    Pull all OECD_DATASETS for the given country and date range.

    Returns a monthly-indexed DataFrame with one column per indicator.
    Requires: requests  (pip install requests)
    """
    frames = {}
    for name, (dataset, series, label) in OECD_DATASETS.items():
        print(f"  Fetching OECD {dataset}/{series} ({label})")
        frames[name] = _fetch_series(dataset, series, country, start, end)

    df = pd.DataFrame(frames)
    df.index.name = "date"
    return df
