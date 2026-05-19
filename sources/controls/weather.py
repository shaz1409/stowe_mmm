import os
import pandas as pd
from config.dates import DATE_START, DATE_END

# UK centroid — adjust if regional breakdown is needed
OPEN_METEO_LAT  = 52.5
OPEN_METEO_LON  = -1.5
OPEN_METEO_URL  = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_VARS = ["temperature_2m_mean", "precipitation_sum"]

MET_OFFICE_BASE    = "http://datapoint.metoffice.gov.uk/public/data"
MET_OFFICE_API_KEY = os.environ.get("MET_OFFICE_API_KEY", "")


def fetch_open_meteo(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Pull daily UK temperature and precipitation from Open-Meteo historical archive.

    Returns a daily-indexed DataFrame; align_to_grain will resample to TIME_GRAIN.
    No API key required.
    Requires: requests  (pip install requests)
    """
    raise NotImplementedError


def fetch_met_office(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Pull UK regional weather observations from Met Office DataPoint.

    Returns a daily-indexed DataFrame with temperature and rainfall columns.
    Requires MET_OFFICE_API_KEY to be set in .env.

    Note: Open-Meteo is simpler to start with — use this if you need
    official Met Office provenance or finer regional granularity.
    """
    if not MET_OFFICE_API_KEY:
        raise ValueError("Set MET_OFFICE_API_KEY in .env before calling fetch_met_office.")
    raise NotImplementedError
