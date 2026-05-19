# sources/google_ads.py
# Pull paid media data from Google Ads API.
#
# Outputs a daily DataFrame with spend, impressions, clicks, conversions
# at the campaign level, ready for MMM ingestion.
#
# Requires:
#   pip install google-ads python-dateutil
#   Google Ads developer token + OAuth2 credentials

import os
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
from google.ads.googleads.client import GoogleAdsClient

# --- Config ------------------------------------------------------------------

GOOGLE_ADS_CUSTOMER_ID   = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")

GAQL = """
    SELECT
        segments.date,
        campaign.name,
        campaign.advertising_channel_type,
        metrics.cost_micros,
        metrics.impressions,
        metrics.clicks,
        metrics.conversions,
        metrics.all_conversions,
        metrics.search_impression_share
    FROM campaign
    WHERE
        segments.date BETWEEN '{start}' AND '{end}'
        AND campaign.status != 'REMOVED'
    ORDER BY segments.date ASC
"""

# --- Auth --------------------------------------------------------------------

def get_client() -> GoogleAdsClient:
    """
    Initialise Google Ads client from environment variables.

    Required env vars:
        GOOGLE_ADS_DEVELOPER_TOKEN
        GOOGLE_ADS_CLIENT_ID
        GOOGLE_ADS_CLIENT_SECRET
        GOOGLE_ADS_REFRESH_TOKEN
        GOOGLE_ADS_CUSTOMER_ID
    """
    credentials = {
        "developer_token":    os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id":          os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret":      os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token":      os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id":  os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
        "use_proto_plus":     True,
    }
    return GoogleAdsClient.load_from_dict(credentials)


# --- Fetch -------------------------------------------------------------------

def _fetch_month(client: GoogleAdsClient, month_start: date, month_end: date) -> list:
    """Run GAQL for a single month, return list of row dicts."""
    service = client.get_service("GoogleAdsService")
    query   = GAQL.format(start=month_start, end=month_end)
    stream  = service.search_stream(customer_id=GOOGLE_ADS_CUSTOMER_ID, query=query)

    rows = []
    for batch in stream:
        for row in batch.results:
            rows.append({
                "date":                    str(row.segments.date),
                "campaign":                row.campaign.name,
                "channel_type":            str(row.campaign.advertising_channel_type.name),
                "cost_micros":             row.metrics.cost_micros,
                "impressions":             row.metrics.impressions,
                "clicks":                  row.metrics.clicks,
                "conversions":             row.metrics.conversions,
                "all_conversions":         row.metrics.all_conversions,
                "search_impression_share": row.metrics.search_impression_share,
            })
    return rows


def fetch_campaign_report(client: GoogleAdsClient, start: str, end: str) -> pd.DataFrame:
    """
    Pull daily campaign report chunked monthly to avoid query limits.

    Args:
        start: ISO date string, e.g. "2023-01-01"
        end:   ISO date string, e.g. "2023-12-31"
    """
    cursor   = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    all_rows = []

    while cursor <= end_date:
        month_end = min(cursor + relativedelta(months=1) - relativedelta(days=1), end_date)
        print(f"  Fetching {cursor} -> {month_end}")
        all_rows.extend(_fetch_month(client, cursor, month_end))
        cursor += relativedelta(months=1)

    return pd.DataFrame(all_rows)


def normalise(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise raw Google Ads report to the standard MMM schema:
      date | channel | campaign | channel_type | spend | impressions | clicks |
      conversions | all_conversions | search_impression_share
    """
    if raw.empty:
        return pd.DataFrame()

    df = raw.copy()
    df["date"]                    = pd.to_datetime(df["date"])
    df["channel"]                 = "google_ads"
    df["spend"]                   = df["cost_micros"] / 1_000_000
    df["impressions"]             = df["impressions"].astype(int)
    df["clicks"]                  = df["clicks"].astype(int)
    df["conversions"]             = df["conversions"].astype(float)
    df["all_conversions"]         = df["all_conversions"].astype(float)
    df["search_impression_share"] = pd.to_numeric(df["search_impression_share"], errors="coerce")

    return df[[
        "date", "channel", "campaign", "channel_type",
        "spend", "impressions", "clicks",
        "conversions", "all_conversions", "search_impression_share",
    ]]


# --- Main --------------------------------------------------------------------

def fetch(start: str, end: str) -> pd.DataFrame:
    """Entry point called by 01_data_prep.py. Returns normalised daily DataFrame."""
    client = get_client()
    raw    = fetch_campaign_report(client, start, end)
    return normalise(raw)
