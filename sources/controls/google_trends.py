import pandas as pd
from config.dates import DATE_START, DATE_END

GOOGLE_TRENDS_TERMS = [
    "experian",
    "credit score",
    "credit check",
    "personal loan",
]


def fetch(
    terms: list[str] = GOOGLE_TRENDS_TERMS,
    start: str = DATE_START,
    end: str = DATE_END,
) -> pd.DataFrame:
    """
    Pull weekly relative search interest via pytrends.

    Returns a weekly-indexed DataFrame with one column per search term,
    normalised 0–100 (Google's scale, not absolute volume).

    Note: pytrends is unofficial — rate-limit with small sleeps between requests.
    Requires: pytrends  (pip install pytrends)
    """
    raise NotImplementedError
