# sources/stackadapt.py
# Load StackAdapt data from a manually exported CSV.
#
# StackAdapt API token requires account manager setup — in the meantime,
# export the campaign report manually from the StackAdapt UI and drop it in:
#   data/raw/stackadapt_export.csv
#
# Export steps (StackAdapt UI):
#   Campaigns -> select all -> Export -> CSV
#   Columns to include: Date, Campaign, Spend, Impressions, Clicks
#
# Outputs a daily DataFrame in the standard MMM schema.

import pandas as pd
import os

RAW_PATH = "data/raw/stackadapt_export.csv"

# Map StackAdapt export column names to MMM schema.
# Update keys here if StackAdapt changes its export headers.
COLUMN_MAP = {
    "Date":        "date",
    "Campaign":    "campaign",
    "Spend":       "spend",
    "Impressions": "impressions",
    "Clicks":      "clicks",
}


def fetch(start: str = None, end: str = None) -> pd.DataFrame:
    """
    Load and normalise the manually exported StackAdapt CSV.

    Args:
        start: optional ISO date string to filter from
        end:   optional ISO date string to filter to
    """
    if not os.path.exists(RAW_PATH):
        raise FileNotFoundError(
            f"StackAdapt export not found at {RAW_PATH}. "
            "Export from StackAdapt UI and save there."
        )

    df = pd.read_csv(RAW_PATH)
    df = df.rename(columns=COLUMN_MAP)

    df["date"]        = pd.to_datetime(df["date"])
    df["channel"]     = "stackadapt"
    df["spend"]       = pd.to_numeric(df["spend"], errors="coerce")
    df["impressions"] = pd.to_numeric(df["impressions"], errors="coerce").astype("Int64")
    df["clicks"]      = pd.to_numeric(df["clicks"], errors="coerce").astype("Int64")

    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]

    return df[["date", "channel", "campaign", "spend", "impressions", "clicks"]]
