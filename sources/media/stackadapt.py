# sources/media/stackadapt.py
# Load StackAdapt data from a manually exported CSV.
#
# TODO (when API access is granted):
#   1. Obtain API token from StackAdapt account manager; set STACKADAPT_API_TOKEN in .env
#   2. Replace fetch() body with a REST call to:
#        GET https://api.stackadapt.com/graphql  (GraphQL endpoint)
#      or the equivalent REST reporting endpoint — confirm with StackAdapt docs.
#   3. Map API response fields to COLUMN_MAP keys below.
#   4. Remove RAW_PATH / FileNotFoundError logic.
#   5. Add monthly chunking if the API has date-range limits.
#
# Until then: export the campaign report manually from the StackAdapt UI and drop it in:
#   data/raw/stackadapt_export.csv
#
# Export steps (StackAdapt UI):
#   Campaigns -> select all -> Export -> CSV
#   Columns to include: Date, Campaign, Region, City, Spend, Impressions, Clicks
#
# COLUMN_MAP keys below are best-guess from StackAdapt's typical export format.
# Verify column headers against an actual export and update keys here if they differ.
#
# Outputs a daily DataFrame in the standard MMM schema.

import pandas as pd
import os

RAW_PATH = "data/raw/stackadapt_export.csv"

# Map StackAdapt export column names to MMM schema.
# Update keys here if StackAdapt changes its export headers.
# Update the Region key if StackAdapt's export header differs (e.g. "Geographic Area").
COLUMN_MAP = {
    "Date":        "date",
    "Campaign":    "campaign",
    "Region":      "region",   # optional — include if available in export
    "City":        "city",     # optional — include if available in export
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
    df["region"]      = df["region"] if "region" in df.columns else None
    df["city"]        = df["city"]   if "city"   in df.columns else None
    df["spend"]       = pd.to_numeric(df["spend"], errors="coerce")
    df["impressions"] = pd.to_numeric(df["impressions"], errors="coerce").astype("Int64")
    df["clicks"]      = pd.to_numeric(df["clicks"], errors="coerce").astype("Int64")

    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]

    return df[["date", "channel", "region", "city", "campaign", "spend", "impressions", "clicks"]]
