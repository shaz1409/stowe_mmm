# sources/meta.py
# Pull paid media data from Meta Marketing API (Facebook / Instagram).
#
# Outputs a daily DataFrame with spend, impressions, clicks, reach, frequency
# at the campaign level, ready for MMM ingestion.
#
# Requires:
#   pip install facebook-business
#   Meta app with Marketing API access + Ad Account ID
#   Use a System User token (Business Manager) for long-lived access —
#   regular user tokens expire after 60 days.

import os
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount

# --- Config ------------------------------------------------------------------

# Use .get() so importing this module doesn't raise KeyError when creds aren't set.
# Errors surface at authenticate() / fetch() time instead.
META_APP_ID       = os.environ.get("META_APP_ID", "")
META_APP_SECRET   = os.environ.get("META_APP_SECRET", "")
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT   = f"act_{os.environ.get('META_AD_ACCOUNT', '')}"
META_API_VERSION  = "v19.0"

META_FIELDS = [
    "date_start",
    "campaign_name",
    "objective",
    "spend",
    "impressions",
    "clicks",
    "outbound_clicks",
    "reach",
    "frequency",
    "actions",                      # conversions, leads, form submissions
    "video_p25_watched_actions",    # video view quartiles
    "video_p75_watched_actions",
    "video_p100_watched_actions",
]

# Supported geo breakdowns for fetch(). Meta returns the value as a plain string.
# "region" → broad UK region (England, Scotland, Wales, Northern Ireland)
# "city"   → city level (London, Manchester, etc.) — sparse for smaller markets
# "country" → country only, useful as a sanity check
GEO_BREAKDOWNS = ("region", "city", "country")

# --- Auth --------------------------------------------------------------------

def authenticate():
    """Initialise the Meta FacebookAdsApi session. Must be called before any API request."""
    FacebookAdsApi.init(
        app_id=META_APP_ID,
        app_secret=META_APP_SECRET,
        access_token=META_ACCESS_TOKEN,
        api_version=META_API_VERSION,
    )


# --- Fetch -------------------------------------------------------------------

def _fetch_month(account, month_start: date, month_end: date, level: str, geo_breakdown: str) -> list:
    """Pull one month of insights, handling cursor pagination."""
    params = {
        "time_range": {"since": str(month_start), "until": str(month_end)},
        "time_increment": 1,
        "level": level,
        "breakdowns": [geo_breakdown],
        "limit": 500,
    }
    cursor = account.get_insights(fields=META_FIELDS, params=params)
    rows = []
    while True:
        rows.extend([dict(row) for row in cursor])
        if not cursor.load_next_page():
            break
    return rows


def fetch_insights(start: str, end: str, level: str = "campaign", geo_breakdown: str = "region") -> pd.DataFrame:
    """
    Pull daily ad insights from META_AD_ACCOUNT for the given date range.
    Chunks requests monthly to avoid Meta's data size limits.

    Args:
        geo_breakdown: one of GEO_BREAKDOWNS ("region", "city", "country")
    """
    if geo_breakdown not in GEO_BREAKDOWNS:
        raise ValueError(f"geo_breakdown must be one of {GEO_BREAKDOWNS}, got '{geo_breakdown}'")

    account   = AdAccount(META_AD_ACCOUNT)
    cursor    = date.fromisoformat(start)
    end_date  = date.fromisoformat(end)
    all_rows  = []

    while cursor <= end_date:
        month_end = min(cursor + relativedelta(months=1) - relativedelta(days=1), end_date)
        print(f"  Fetching {cursor} → {month_end} [{geo_breakdown}]")
        all_rows.extend(_fetch_month(account, cursor, month_end, level, geo_breakdown))
        cursor += relativedelta(months=1)

    return pd.DataFrame(all_rows)


def _extract_actions(actions_list: list | float, action_type: str) -> int:
    """Pull a single action type value out of Meta's nested actions list."""
    if not isinstance(actions_list, list):
        return 0
    for a in actions_list:
        if a.get("action_type") == action_type:
            return int(float(a.get("value", 0)))
    return 0


def normalise(raw: pd.DataFrame, geo_breakdown: str = "region") -> pd.DataFrame:
    """
    Normalise raw Meta insights to the standard MMM schema.
    Actions (conversions, leads) are unpacked from Meta's nested list format.
    Outputs both region and city columns; the one matching geo_breakdown is populated,
    the other is None.
    """
    if raw.empty:
        return pd.DataFrame()

    df = raw.rename(columns={"date_start": "date", "campaign_name": "campaign"})
    df["date"]    = pd.to_datetime(df["date"])
    df["channel"] = "meta"
    df["region"]  = df[geo_breakdown] if geo_breakdown == "region" and "region" in df.columns else None
    df["city"]    = df[geo_breakdown] if geo_breakdown == "city"   and "city"   in df.columns else None
    df["spend"]       = df["spend"].astype(float)
    df["impressions"] = pd.to_numeric(df["impressions"], errors="coerce").astype("Int64")
    df["clicks"]      = pd.to_numeric(df["clicks"],      errors="coerce").astype("Int64")
    df["reach"]       = pd.to_numeric(df["reach"],       errors="coerce").astype("Int64")
    df["frequency"]   = df["frequency"].astype(float)

    # outbound_clicks also comes back as a nested list
    df["outbound_clicks"] = df["outbound_clicks"].apply(
        lambda x: int(float(x[0]["value"])) if isinstance(x, list) and x else 0
    )

    # Unpack key action types from the nested actions list
    df["leads"]       = df["actions"].apply(lambda x: _extract_actions(x, "lead"))
    df["conversions"] = df["actions"].apply(lambda x: _extract_actions(x, "offsite_conversion.fb_pixel_lead"))
    df["form_submissions"] = df["actions"].apply(lambda x: _extract_actions(x, "onsite_conversion.lead_grouped"))

    # Video quartile views
    for col, field in [
        ("video_views_25", "video_p25_watched_actions"),
        ("video_views_75", "video_p75_watched_actions"),
        ("video_views_100", "video_p100_watched_actions"),
    ]:
        df[col] = df[field].apply(lambda x: int(float(x[0]["value"])) if isinstance(x, list) and x else 0)

    return df[[
        "date", "channel", "region", "city", "campaign", "objective",
        "spend", "impressions", "clicks", "outbound_clicks", "reach", "frequency",
        "leads", "conversions", "form_submissions",
        "video_views_25", "video_views_75", "video_views_100",
    ]]


# --- Main --------------------------------------------------------------------

def fetch(start: str, end: str, geo_breakdown: str = "region") -> pd.DataFrame:
    """Entry point called by 01_data_prep.py. Returns normalised daily DataFrame."""
    authenticate()
    raw = fetch_insights(start, end, geo_breakdown=geo_breakdown)
    return normalise(raw, geo_breakdown=geo_breakdown)
