# sources/media/azure_dw.py
# Pull enquiry/KPI data from Stowe's Azure Data Warehouse (Clef lead system).
#
# Outputs:
#   - national daily quality leads  (default MMM KPI)
#   - regional daily quality leads  (for regional modelling)
#   - daily leads by enquiry type   (for product-split modelling)
#
# Requires:
#   pip install pyodbc pandas sqlalchemy
#   Azure SQL connection string or individual credentials in .env

import os
import pandas as pd

# --- Config ------------------------------------------------------------------

# Option A: full connection string (preferred)
AZURE_CONNECTION_STRING = os.environ.get("AZURE_CONNECTION_STRING", "")

# Option B: individual components (if connection string not available)
AZURE_SERVER   = os.environ.get("AZURE_SERVER", "")    # e.g. stowe-dw.database.windows.net
AZURE_DATABASE = os.environ.get("AZURE_DATABASE", "")
AZURE_USERNAME = os.environ.get("AZURE_USERNAME", "")
AZURE_PASSWORD = os.environ.get("AZURE_PASSWORD", "")

# --- Table/view names --------------------------------------------------------
# Confirm actual names against DW schema with Stowe's data team

CLEF_TABLE = "clef.quality_leads"   # placeholder — confirm actual table/view name

# --- Expected schema ---------------------------------------------------------
# Columns we anticipate in CLEF_TABLE. Used by validate_schema() to catch
# mismatches early rather than surfacing confusing pandas errors downstream.
# Update keys here once the DW schema is confirmed; add/remove columns as needed.

CLEF_EXPECTED_COLUMNS = {
    "enquiry_date":    "datetime64[ns]",  # date of enquiry
    "region":          "object",          # UK region (e.g. "North West", "South East")
    "enquiry_type":    "object",          # divorce | child_arrangements | financial_remedy | cohabitation | other
    "lead_source":     "object",          # web_form | phone | chat | referral | other
    "is_quality_lead": "int64",           # 1 = quality lead, 0 = not
    "office":          "object",          # specific Stowe office name — confirm granularity
}

# --- Query -------------------------------------------------------------------

# Pulls one row per enquiry so Python handles all aggregation.
# Confirmed column names may differ — update SELECT aliases to match.
CLEF_QUERY = """
    SELECT
        enquiry_date,
        region,
        enquiry_type,
        lead_source,
        is_quality_lead,
        office
    FROM {table}
    WHERE
        enquiry_date BETWEEN :start AND :end
    ORDER BY
        enquiry_date ASC
"""

# --- Connection --------------------------------------------------------------

def get_engine():
    """
    Return a SQLAlchemy engine connected to the Azure DW.

    Tries AZURE_CONNECTION_STRING first, falls back to individual components.
    Requires: pyodbc, sqlalchemy  (pip install pyodbc sqlalchemy)
    """
    from sqlalchemy import create_engine

    if AZURE_CONNECTION_STRING:
        return create_engine(f"mssql+pyodbc:///?odbc_connect={AZURE_CONNECTION_STRING}")

    if not all([AZURE_SERVER, AZURE_DATABASE, AZURE_USERNAME, AZURE_PASSWORD]):
        raise ValueError(
            "Set either AZURE_CONNECTION_STRING or all of "
            "AZURE_SERVER, AZURE_DATABASE, AZURE_USERNAME, AZURE_PASSWORD in .env"
        )

    conn_str = (
        f"mssql+pyodbc://{AZURE_USERNAME}:{AZURE_PASSWORD}"
        f"@{AZURE_SERVER}/{AZURE_DATABASE}"
        f"?driver=ODBC+Driver+18+for+SQL+Server"
    )
    return create_engine(conn_str)


# --- Schema validation -------------------------------------------------------

def validate_schema(df: pd.DataFrame) -> None:
    """
    Raise ValueError if any expected columns are missing from the query result.
    Call this immediately after fetching raw data, before any aggregation.
    """
    missing = set(CLEF_EXPECTED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"Azure DW schema mismatch — expected columns not found: {sorted(missing)}. "
            f"Update CLEF_EXPECTED_COLUMNS or the SELECT in CLEF_QUERY to match the actual DW schema."
        )


# --- Fetch -------------------------------------------------------------------

def _fetch_raw(start: str, end: str) -> pd.DataFrame:
    """Pull raw unaggregated Clef rows and validate schema."""
    from sqlalchemy import text

    engine = get_engine()
    query  = CLEF_QUERY.format(table=CLEF_TABLE)

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params={"start": start, "end": end})

    validate_schema(df)

    df["enquiry_date"]    = pd.to_datetime(df["enquiry_date"])
    df["is_quality_lead"] = df["is_quality_lead"].astype(int)

    return df


def fetch_clef(start: str, end: str) -> pd.DataFrame:
    """
    Daily quality leads by region.

    Returns: date | region | quality_leads
    """
    df = _fetch_raw(start, end)
    return (
        df[df["is_quality_lead"] == 1]
        .groupby(["enquiry_date", "region"], as_index=False)
        .size()
        .rename(columns={"enquiry_date": "date", "size": "quality_leads"})
    )


def fetch_clef_national(start: str, end: str) -> pd.DataFrame:
    """
    Daily quality leads aggregated nationally.
    Default MMM KPI — swap for fetch_clef() if regional modelling is needed.

    Returns: date | kpi_quality_leads
    """
    df = _fetch_raw(start, end)
    return (
        df[df["is_quality_lead"] == 1]
        .groupby("enquiry_date", as_index=False)
        .size()
        .rename(columns={"enquiry_date": "date", "size": "kpi_quality_leads"})
    )


def fetch_clef_by_enquiry_type(start: str, end: str) -> pd.DataFrame:
    """
    Daily quality leads split by enquiry type.
    Useful for product-level MMM or as a segmentation check.

    Returns: date | enquiry_type | quality_leads

    Expected enquiry_type values (confirm with Stowe's data team):
      divorce | child_arrangements | financial_remedy | cohabitation | other
    """
    df = _fetch_raw(start, end)
    return (
        df[df["is_quality_lead"] == 1]
        .groupby(["enquiry_date", "enquiry_type"], as_index=False)
        .size()
        .rename(columns={"enquiry_date": "date", "size": "quality_leads"})
    )


# --- Main --------------------------------------------------------------------

def fetch(start: str, end: str) -> pd.DataFrame:
    """Entry point called by 01_data_prep.py. Returns national daily quality leads."""
    return fetch_clef_national(start, end)
