# 01a_control_vars.py
# Pull macroeconomic and calendar control variables for use in MMM.
# Run before or alongside 01_data_prep.py.
#
# Inputs:  DATE_START, DATE_END, COUNTRY config constants below
# Outputs: data/control_vars.csv
#
# Sources:
#   - OECD SDMX-JSON API       → CLI, CPI, unemployment, household confidence
#   - Bank of England API      → base rate, consumer credit growth, mortgage approvals
#   - ONS API                  → retail sales index
#   - Google Trends (pytrends) → branded + category search volume
#   - Open-Meteo API           → UK temperature, precipitation (no key required)
#   - Met Office DataPoint API → UK weather (requires free API key)
#   - Land Registry HPI API    → UK house price index + transaction volumes
#   - GOV.UK API               → UK bank holidays
#   - Derived                  → week-of-year, month dummies, Easter flag, cyclic encodings

import pandas as pd

# --- Config ------------------------------------------------------------------

DATE_START = "2020-01-01"   # adjust to match your MMM window
DATE_END   = "2024-12-31"
COUNTRY    = "GBR"          # OECD country code for UK
TIME_GRAIN = "W-MON"        # pandas frequency: weekly Monday anchor

# Met Office DataPoint API key — register free at metoffice.gov.uk/services/data
MET_OFFICE_API_KEY = ""

# Google Trends search terms — tune to your brand and product category
GOOGLE_TRENDS_TERMS = [
    "experian",           # branded
    "credit score",       # category
    "credit check",       # category
    "personal loan",      # adjacent product intent
]

# --- OECD --------------------------------------------------------------------

OECD_BASE = "https://stats.oecd.org/SDMX-JSON/data"

OECD_DATASETS = {
    "cli":           ("MEI_CLI",    "LOLITOAA", "Composite Leading Indicator"),
    "cpi_yoy":       ("PRICES_CPI", "CPALTT01", "CPI all-items YoY %"),
    "unemployment":  ("MEI_LABOUR", "LRUNTTTT", "Unemployment rate %"),
    "hh_confidence": ("HH_DASH",    "CSCICP03", "Consumer confidence index"),
}


def fetch_oecd(start: str = DATE_START, end: str = DATE_END, country: str = COUNTRY) -> pd.DataFrame:
    """
    Pull all OECD_DATASETS for the given country and date range.

    Returns a monthly-indexed DataFrame with one column per indicator.
    Requires: requests, pandasdmx  (pip install requests pandasdmx)
    """
    raise NotImplementedError


# --- Bank of England ---------------------------------------------------------

BOE_BASE_URL = "https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp"

# Series codes for BoE interactive database
BOE_SERIES = {
    "boe_base_rate":          "IUDBEDR",   # Official bank rate
    "consumer_credit_growth": "LPMVTXA",   # Consumer credit net lending MoM
    "mortgage_approvals":     "LPMBI2N",   # Mortgage approvals for house purchase
}


def fetch_boe(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Download BoE base rate, consumer credit growth, and mortgage approvals.

    Returns a monthly-indexed DataFrame with one column per BOE_SERIES key.
    Requires: requests, lxml  (pip install requests lxml)
    """
    raise NotImplementedError


# --- ONS ---------------------------------------------------------------------

ONS_API_BASE = "https://api.ons.gov.uk/v1"

ONS_SERIES = {
    "retail_sales_index": "J5EK",   # Retail Sales Index, all retailing, volume
}


def fetch_ons(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Pull ONS series defined in ONS_SERIES via the ONS API.

    Returns a monthly-indexed DataFrame with one column per series key.
    Requires: requests  (pip install requests)
    """
    raise NotImplementedError


# --- Google Trends -----------------------------------------------------------

def fetch_google_trends(
    terms: list[str] = GOOGLE_TRENDS_TERMS,
    start: str = DATE_START,
    end: str = DATE_END,
) -> pd.DataFrame:
    """
    Pull weekly relative search interest for GOOGLE_TRENDS_TERMS via pytrends.

    Returns a weekly-indexed DataFrame with one column per search term,
    normalised 0–100 (Google's scale, not absolute volume).

    Note: pytrends is unofficial — rate-limit with small sleeps between requests.
    Requires: pytrends  (pip install pytrends)
    """
    raise NotImplementedError


# --- Weather: Open-Meteo (no API key) ----------------------------------------

# UK centroid — adjust if regional breakdown is needed
OPEN_METEO_LAT  = 52.5
OPEN_METEO_LON  = -1.5
OPEN_METEO_URL  = "https://archive-api.open-meteo.com/v1/archive"

OPEN_METEO_VARS = [
    "temperature_2m_mean",
    "precipitation_sum",
]


def fetch_open_meteo(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Pull daily UK temperature and precipitation from Open-Meteo historical archive.

    Returns a daily-indexed DataFrame; align_to_grain will resample to TIME_GRAIN.
    No API key required.
    Requires: requests  (pip install requests)
    """
    raise NotImplementedError


# --- Weather: Met Office DataPoint (API key required) ------------------------

MET_OFFICE_BASE = "http://datapoint.metoffice.gov.uk/public/data"


def fetch_met_office(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Pull UK regional weather observations from Met Office DataPoint.

    Returns a daily-indexed DataFrame with temperature and rainfall columns.
    Requires MET_OFFICE_API_KEY to be set above.
    Requires: requests  (pip install requests)

    Note: Open-Meteo is simpler to start with — use this if you need
    official Met Office provenance or finer regional granularity.
    """
    if not MET_OFFICE_API_KEY:
        raise ValueError("Set MET_OFFICE_API_KEY in config before calling fetch_met_office.")
    raise NotImplementedError


# --- Land Registry HPI -------------------------------------------------------

LAND_REGISTRY_URL = "http://landregistry.data.gov.uk/data/ukhpi/region/united-kingdom/month/{year}-{month:02d}.json"


def fetch_land_registry_hpi(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Pull UK House Price Index and transaction volumes from Land Registry linked-data API.

    Returns a monthly-indexed DataFrame with columns:
      - hpi_index            float  (house price index, base 100 = Jan 2015)
      - hpi_yoy_change       float  (% change YoY)
      - transaction_count    int
    Requires: requests  (pip install requests)
    """
    raise NotImplementedError


# --- Bank holidays -----------------------------------------------------------

GOV_UK_HOLIDAYS_URL = "https://www.gov.uk/bank-holidays.json"


def fetch_bank_holidays(start: str = DATE_START, end: str = DATE_END) -> pd.Series:
    """
    Pull England & Wales bank holidays from GOV.UK.

    Returns a boolean Series indexed by date (True = bank holiday).
    Requires: requests  (pip install requests)
    """
    raise NotImplementedError


# --- Derived calendar features -----------------------------------------------

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


# --- Alignment ---------------------------------------------------------------

def align_to_grain(sources: dict[str, pd.DataFrame | pd.Series], grain: str = TIME_GRAIN) -> pd.DataFrame:
    """
    Resample all sources to TIME_GRAIN and join into a single wide DataFrame.

    Resampling conventions by source frequency:
      - Monthly (OECD, BoE, ONS, Land Registry): forward-fill within month
      - Daily (weather, bank holidays):           aggregate — mean for continuous,
                                                  sum for counts/flags
      - Weekly (Google Trends, calendar):         reindex to grain, forward-fill gaps

    Returns a single wide DataFrame indexed by period-start date.
    Trailing NaNs from publication lag are preserved — main() warns about them.
    """
    raise NotImplementedError


# --- Main --------------------------------------------------------------------

def main():
    sources = {
        "oecd":          fetch_oecd(),
        "boe":           fetch_boe(),
        "ons":           fetch_ons(),
        "google_trends": fetch_google_trends(),
        "open_meteo":    fetch_open_meteo(),
        "land_registry": fetch_land_registry_hpi(),
        "bank_holidays": fetch_bank_holidays(),
    }

    date_range = pd.date_range(DATE_START, DATE_END, freq=TIME_GRAIN)
    sources["calendar"] = build_calendar_features(date_range)

    df = align_to_grain(sources)

    df.to_csv("data/control_vars.csv", index=True, index_label="date")
    print(f"Saved {len(df)} rows × {len(df.columns)} control variables to data/control_vars.csv")

    lag_cols = [c for c in df.columns if df[c].isna().any()]
    if lag_cols:
        print(f"Warning: trailing NaNs in {lag_cols} — likely publication lag. Consider forward-filling.")


if __name__ == "__main__":
    main()
