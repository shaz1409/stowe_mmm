import pandas as pd
from config.dates import DATE_START, DATE_END

BOE_BASE_URL = "https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp"

BOE_SERIES = {
    "boe_base_rate":          "IUDBEDR",
    "consumer_credit_growth": "LPMVTXA",
    "mortgage_approvals":     "LPMBI2N",
}


def fetch(start: str = DATE_START, end: str = DATE_END) -> pd.DataFrame:
    """
    Download BoE base rate, consumer credit growth, and mortgage approvals.

    Returns a monthly-indexed DataFrame with one column per BOE_SERIES key.
    Requires: requests, lxml  (pip install requests lxml)
    """
    raise NotImplementedError
