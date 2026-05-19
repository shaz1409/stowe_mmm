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

GOOGLE_ADS_CUSTOMER_ID = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")

# geographic_view breaks metrics down by where users physically were (LOCATION_OF_PRESENCE).
# country_criterion_id 2826 = United Kingdom — verify against your account if needed.
GAQL = """
    SELECT
        segments.date,
        campaign.name,
        campaign.advertising_channel_type,
        segments.geo_target_region,
        metrics.cost_micros,
        metrics.impressions,
        metrics.clicks,
        metrics.conversions,
        metrics.all_conversions,
        metrics.search_impression_share
    FROM geographic_view
    WHERE
        segments.date BETWEEN '{start}' AND '{end}'
        AND campaign.status != 'REMOVED'
        AND geographic_view.country_criterion_id = 2826
        AND geographic_view.location_type = 'LOCATION_OF_PRESENCE'
    ORDER BY segments.date ASC
"""

# Resolves geo target constant resource names to human-readable names for all UK
# geo levels (Region, City, etc.) so city-targeted campaigns also get readable names.
GEO_CONSTANT_QUERY = """
    SELECT
        geo_target_constant.resource_name,
        geo_target_constant.name,
        geo_target_constant.target_type
    FROM geo_target_constant
    WHERE
        geo_target_constant.country_code = 'GB'
        AND geo_target_constant.status = 'ENABLED'
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

def _build_geo_map(client: GoogleAdsClient) -> dict[str, str]:
    """
    Build a resource_name -> name map for all UK geo constants (regions, cities, etc.).
    Called once per fetch to avoid repeated API round-trips.
    Falls back to the raw resource name for any unmapped constant.
    """
    service = client.get_service("GoogleAdsService")
    stream  = service.search_stream(customer_id=GOOGLE_ADS_CUSTOMER_ID, query=GEO_CONSTANT_QUERY)
    geo_map = {}
    for batch in stream:
        for row in batch.results:
            geo_map[row.geo_target_constant.resource_name] = row.geo_target_constant.name
    return geo_map


def _fetch_month(client: GoogleAdsClient, month_start: date, month_end: date, geo_map: dict) -> list:
    """Run GAQL for a single month, return list of row dicts."""
    service = client.get_service("GoogleAdsService")
    query   = GAQL.format(start=month_start, end=month_end)
    stream  = service.search_stream(customer_id=GOOGLE_ADS_CUSTOMER_ID, query=query)

    rows = []
    for batch in stream:
        for row in batch.results:
            raw_geo = str(row.segments.geo_target_region)
            rows.append({
                "date":                    str(row.segments.date),
                "campaign":                row.campaign.name,
                "channel_type":            str(row.campaign.advertising_channel_type.name),
                "region":                  geo_map.get(raw_geo, raw_geo),
                "city":                    None,
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
    Pull daily geographic campaign report chunked monthly to avoid query limits.

    Args:
        start: ISO date string, e.g. "2023-01-01"
        end:   ISO date string, e.g. "2023-12-31"
    """
    geo_map = _build_geo_map(client)
    cursor     = date.fromisoformat(start)
    end_date   = date.fromisoformat(end)
    all_rows   = []

    while cursor <= end_date:
        month_end = min(cursor + relativedelta(months=1) - relativedelta(days=1), end_date)
        print(f"  Fetching {cursor} -> {month_end}")
        all_rows.extend(_fetch_month(client, cursor, month_end, geo_map))
        cursor += relativedelta(months=1)

    return pd.DataFrame(all_rows)


def normalise(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise raw Google Ads geographic report to the standard MMM schema:
      date | channel | region | campaign | channel_type | spend | impressions | clicks |
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
        "date", "channel", "region", "city", "campaign", "channel_type",
        "spend", "impressions", "clicks",
        "conversions", "all_conversions", "search_impression_share",
    ]]


# --- Main --------------------------------------------------------------------

def fetch(start: str, end: str) -> pd.DataFrame:
    """Entry point called by 01_data_prep.py. Returns normalised daily DataFrame."""
    client = get_client()
    raw    = fetch_campaign_report(client, start, end)
    return normalise(raw)
