import time
import pandas as pd
from config.dates import DATE_START, DATE_END

# Search terms most predictive of divorce enquiry intent for a UK law firm.
# pytrends batches up to 5 terms per payload; split into multiple calls if adding more.
GOOGLE_TRENDS_TERMS = [
    "divorce solicitor",
    "divorce lawyer",
    "how to get divorced",
    "divorce proceedings",
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
    from pytrends.request import TrendReq  # lazy import — not installed in all envs

    pytrends = TrendReq(hl="en-GB", tz=0)

    # pytrends accepts at most 5 terms per payload; chunk if needed
    results = []
    for i in range(0, len(terms), 5):
        batch = terms[i : i + 5]
        timeframe = f"{start} {end}"
        pytrends.build_payload(batch, cat=0, timeframe=timeframe, geo="GB", gprop="")
        df = pytrends.interest_over_time()
        if not df.empty:
            results.append(df.drop(columns=["isPartial"], errors="ignore"))
        if i + 5 < len(terms):
            time.sleep(1)  # avoid 429 from pytrends rate limiting

    if not results:
        return pd.DataFrame(columns=["date"] + terms)

    combined = pd.concat(results, axis=1)
    combined.index.name = "date"
    return combined.reset_index()
