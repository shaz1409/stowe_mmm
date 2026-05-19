import pandas as pd
from config.dates import DATE_START, DATE_END, COUNTRY

OECD_BASE = "https://stats.oecd.org/SDMX-JSON/data"

OECD_DATASETS = {
    "cli":           ("MEI_CLI",    "LOLITOAA", "Composite Leading Indicator"),
    "cpi_yoy":       ("PRICES_CPI", "CPALTT01", "CPI all-items YoY %"),
    "unemployment":  ("MEI_LABOUR", "LRUNTTTT", "Unemployment rate %"),
    "hh_confidence": ("HH_DASH",    "CSCICP03", "Consumer confidence index"),
}


def fetch(start: str = DATE_START, end: str = DATE_END, country: str = COUNTRY) -> pd.DataFrame:
    """
    Pull all OECD_DATASETS for the given country and date range.

    Returns a monthly-indexed DataFrame with one column per indicator.
    Requires: requests, pandasdmx  (pip install requests pandasdmx)
    """
    raise NotImplementedError
