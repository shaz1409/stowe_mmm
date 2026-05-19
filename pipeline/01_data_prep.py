# 01_data_prep.py
# Pull data from all sources and produce a single MMM-ready dataframe.
#
# Inputs:  raw data files / API connections (media spend, impressions, sales, etc.)
# Outputs: data/processed/mmm_ready.csv
#
# Steps (to implement):
#   1. Run sources/controls to fetch macro/calendar controls -> data/processed/control_vars.csv
#   2. Load each data source (paid media, organic, sales/KPI)
#   3. Align to a common time grain (weekly / daily)
#   4. Merge into a single wide dataframe
#   5. Handle missing values and date gaps
#   6. Save to data/processed/mmm_ready.csv

import pandas as pd
from config.dates import DATE_START, DATE_END
from sources import controls
from sources.media import meta, stackadapt, google_ads, bing_ads, azure_dw


def load_sources() -> dict[str, pd.DataFrame]:
    """Return a dict of raw dataframes keyed by source name."""
    sources = {}

    sources["controls"]    = pd.read_csv("data/processed/control_vars.csv", parse_dates=["date"])
    sources["meta"]        = meta.fetch(start=DATE_START, end=DATE_END)
    sources["stackadapt"]  = stackadapt.fetch(start=DATE_START, end=DATE_END)
    sources["google_ads"]  = google_ads.fetch(start=DATE_START, end=DATE_END)
    sources["bing_ads"]    = bing_ads.fetch(start=DATE_START, end=DATE_END)

    sources["kpi"] = azure_dw.fetch(start=DATE_START, end=DATE_END)

    raise NotImplementedError

def align_and_merge(sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Align all sources to a common time grain and merge."""
    raise NotImplementedError

def main():
    controls.main()
    sources = load_sources()
    df = align_and_merge(sources)
    df.to_csv("data/processed/mmm_ready.csv", index=False)
    print(f"Saved {len(df)} rows to data/processed/mmm_ready.csv")

if __name__ == "__main__":
    main()
