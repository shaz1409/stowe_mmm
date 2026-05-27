import io
import requests
import pandas as pd
from config.dates import DATE_START, DATE_END

BOE_BASE_URL = "https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp"

# Maps three-letter month abbreviations used by the BoE ISD query params
_MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",  5: "May",  6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

BOE_SERIES = {
    "boe_base_rate":          "IUDBEDR",  # BoE Bank Rate (%)
    "consumer_credit_growth": "LPMVTXA",  # Consumer credit net lending growth
    "mortgage_approvals":     "LPMBI2N",  # Mortgage approvals for house purchase
}


def _fetch_series(code: str, start: str, end: str) -> pd.Series:
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)

    # BoE ISD uses list-of-tuples for params so that multiple `C` values can be passed;
    # here we fetch one series per call to keep the response parsing simple.
    params = [
        ("Travel",      "NIxSUx"),
        ("FromSeries",  "1"),
        ("ToSeries",    "50"),
        ("DAT",         "RNG"),
        ("FD",          str(s.day)),
        ("FM",          _MONTH_ABBR[s.month]),
        ("FY",          str(s.year)),
        ("TD",          str(e.day)),
        ("TM",          _MONTH_ABBR[e.month]),
        ("TY",          str(e.year)),
        ("VFD",         "Y"),
        ("html.x",      "66"),
        ("html.y",      "26"),
        ("C",           code),
        ("csv.x",       "yes"),
    ]

    resp = requests.get(BOE_BASE_URL, params=params, timeout=30)
    resp.raise_for_status()

    # BoE CSV: first row is blank/metadata; Date column uses "DD Mon YYYY" format
    raw = pd.read_csv(io.StringIO(resp.text), header=0)
    raw.columns = raw.columns.str.strip()

    date_col  = raw.columns[0]
    value_col = raw.columns[1]

    dates  = pd.to_datetime(raw[date_col].str.strip(), dayfirst=True, errors="coerce")
    values = pd.to_numeric(raw[value_col], errors="coerce")

    series = pd.Series(values.values, index=dates, name=code).dropna(how="all")
    series.index.name = "date"
    return series


def fetch(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Download BoE base rate, consumer credit growth, and mortgage approvals.

    Returns a monthly-indexed DataFrame with one column per BOE_SERIES key.
    Requires: requests, lxml  (pip install requests lxml)
    """
    frames = {}
    for name, code in BOE_SERIES.items():
        print(f"  Fetching BoE series {code} ({name})")
        frames[name] = _fetch_series(code, start, end)

    df = pd.DataFrame(frames)
    df.index.name = "date"
    return df
