# sources/bing_ads.py
# Pull paid media data from Microsoft Advertising (Bing Ads) Reporting API.
#
# Outputs a daily DataFrame with spend, impressions, clicks, conversions
# at the campaign level, ready for MMM ingestion.
#
# Requires:
#   pip install bingads
#   Microsoft Advertising developer token + OAuth2 credentials
#   Register an app at: https://apps.microsoft.com/advertisingapi

import os
import time
import zipfile
import io
import pandas as pd
from bingads.service_client import ServiceClient
from bingads.authorization import AuthorizationData, OAuthWebAuthCodeGrant
from bingads.v13.reporting import *

# --- Config ------------------------------------------------------------------

BING_DEVELOPER_TOKEN = os.environ.get("BING_DEVELOPER_TOKEN", "")
BING_CLIENT_ID       = os.environ.get("BING_CLIENT_ID", "")
BING_CLIENT_SECRET   = os.environ.get("BING_CLIENT_SECRET", "")
BING_REFRESH_TOKEN   = os.environ.get("BING_REFRESH_TOKEN", "")
BING_ACCOUNT_ID      = os.environ.get("BING_ACCOUNT_ID", "")    # numeric account ID
BING_CUSTOMER_ID     = os.environ.get("BING_CUSTOMER_ID", "")   # numeric customer ID

BING_ENVIRONMENT     = "production"
BING_POLL_INTERVAL   = 5    # seconds between report status checks
BING_POLL_MAX_TRIES  = 60   # max poll attempts before timeout

# UserLocationPerformanceReportRequest breaks metrics down by physical user location.
# State maps to UK region (e.g. "England", "Scotland") — verify actual values against reports.
BING_REPORT_COLUMNS = [
    "TimePeriod",
    "CampaignName",
    "CampaignType",
    "Country",
    "State",   # UK region
    "City",    # city level
    "Spend",
    "Impressions",
    "Clicks",
    "Conversions",
    "AllConversions",
]

# --- Auth --------------------------------------------------------------------

def get_auth() -> AuthorizationData:
    """
    Build Microsoft Advertising AuthorizationData from environment variables.

    Required env vars:
        BING_DEVELOPER_TOKEN
        BING_CLIENT_ID
        BING_CLIENT_SECRET
        BING_REFRESH_TOKEN
        BING_ACCOUNT_ID
        BING_CUSTOMER_ID
    """
    oauth = OAuthWebAuthCodeGrant(
        client_id=BING_CLIENT_ID,
        client_secret=BING_CLIENT_SECRET,
        redirection_uri="https://login.microsoftonline.com/common/oauth2/nativeclient",
        env=BING_ENVIRONMENT,
    )
    oauth.request_oauth_tokens_by_refresh_token(BING_REFRESH_TOKEN)

    return AuthorizationData(
        developer_token=BING_DEVELOPER_TOKEN,
        authentication=oauth,
        account_id=int(BING_ACCOUNT_ID),
        customer_id=int(BING_CUSTOMER_ID),
    )


# --- Fetch -------------------------------------------------------------------

def _build_report_request(auth: AuthorizationData, start: str, end: str):
    """Build a CampaignPerformanceReportRequest SOAP object."""
    reporting_service = ServiceClient(
        service="ReportingService",
        version=13,
        authorization_data=auth,
        environment=BING_ENVIRONMENT,
    )

    request = reporting_service.factory.create("UserLocationPerformanceReportRequest")
    request.Format          = "Csv"
    request.ReportName      = "MMM_Geo_Report"
    request.ReturnOnlyCompleteData = False
    request.Aggregation     = "Daily"

    scope = reporting_service.factory.create("AccountThroughCampaignReportScope")
    scope.AccountIds        = {"long": [int(BING_ACCOUNT_ID)]}
    request.Scope           = scope

    time_period  = reporting_service.factory.create("ReportTime")
    start_date   = reporting_service.factory.create("Date")
    end_date_obj = reporting_service.factory.create("Date")

    s = start.split("-")
    e = end.split("-")
    start_date.Year, start_date.Month, start_date.Day       = int(s[0]), int(s[1]), int(s[2])
    end_date_obj.Year, end_date_obj.Month, end_date_obj.Day = int(e[0]), int(e[1]), int(e[2])

    time_period.CustomDateRangeStart = start_date
    time_period.CustomDateRangeEnd   = end_date_obj
    request.Time = time_period

    columns = reporting_service.factory.create("ArrayOfUserLocationPerformanceReportColumn")
    columns.UserLocationPerformanceReportColumn = BING_REPORT_COLUMNS
    request.Columns = columns

    return reporting_service, request


def _poll_report(reporting_service, request_id: str) -> bytes:
    """Submit and poll until report is ready, return raw CSV bytes."""
    for _ in range(BING_POLL_MAX_TRIES):
        status = reporting_service.GetReportStatus(ReportRequestId=request_id)
        if status.ReportRequestStatus.Status == "Success":
            url = status.ReportRequestStatus.ReportDownloadUrl
            import urllib.request
            with urllib.request.urlopen(url) as r:
                return r.read()
        if status.ReportRequestStatus.Status == "Error":
            raise RuntimeError("Bing Ads report generation failed.")
        time.sleep(BING_POLL_INTERVAL)

    raise TimeoutError("Bing Ads report timed out after polling.")


def fetch_campaign_report(start: str, end: str) -> pd.DataFrame:
    """
    Submit a CampaignPerformanceReport to Microsoft Advertising and download it.

    The report API is async: submit -> poll -> download -> parse CSV.
    Args:
        start: ISO date string, e.g. "2023-01-01"
        end:   ISO date string, e.g. "2023-12-31"
    """
    auth = get_auth()
    reporting_service, request = _build_report_request(auth, start, end)

    response   = reporting_service.SubmitGenerateReport(request)
    request_id = response.ReportRequestId
    print(f"  Report submitted (ID: {request_id}), polling...")

    raw_bytes = _poll_report(reporting_service, request_id)

    # Report comes back as a zipped CSV
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
        csv_name = z.namelist()[0]
        with z.open(csv_name) as f:
            # Bing prepends metadata rows — skip until the header row
            lines = f.read().decode("utf-8").splitlines()
            header_idx = next(i for i, l in enumerate(lines) if "TimePeriod" in l)
            csv_data = "\n".join(lines[header_idx:])

    return pd.read_csv(io.StringIO(csv_data))


def normalise(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise raw Bing Ads report to the standard MMM schema:
      date | channel | campaign | channel_type | spend | impressions | clicks | conversions
    """
    if raw.empty:
        return pd.DataFrame()

    df = raw.rename(columns={
        "TimePeriod":     "date",
        "CampaignName":   "campaign",
        "CampaignType":   "channel_type",
        "State":          "region",
        "City":           "city",
        "Spend":          "spend",
        "Impressions":    "impressions",
        "Clicks":         "clicks",
        "Conversions":    "conversions",
        "AllConversions": "all_conversions",
    })

    df = df[df["Country"] == "United Kingdom"]

    df["date"]            = pd.to_datetime(df["date"])
    df["channel"]         = "bing_ads"
    df["spend"]           = pd.to_numeric(df["spend"], errors="coerce")
    df["impressions"]     = pd.to_numeric(df["impressions"], errors="coerce").astype("Int64")
    df["clicks"]          = pd.to_numeric(df["clicks"], errors="coerce").astype("Int64")
    df["conversions"]     = pd.to_numeric(df["conversions"], errors="coerce")
    df["all_conversions"] = pd.to_numeric(df["all_conversions"], errors="coerce")

    return df[[
        "date", "channel", "region", "city", "campaign", "channel_type",
        "spend", "impressions", "clicks", "conversions", "all_conversions",
    ]]


# --- Main --------------------------------------------------------------------

def fetch(start: str, end: str) -> pd.DataFrame:
    """Entry point called by 01_data_prep.py. Returns normalised daily DataFrame."""
    raw = fetch_campaign_report(start, end)
    return normalise(raw)
