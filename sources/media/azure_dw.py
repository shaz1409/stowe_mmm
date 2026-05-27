# sources/media/azure_dw.py
# Pull KPI and supporting data from Stowe's Azure Data Warehouse (Clef lead system).
#
# Tables/views this module will pull once schema is confirmed with Stowe's data team:
#
#   1. Quality leads  (primary MMM KPI)
#      Grain: one row per enquiry
#      Key columns: enquiry_date, region, is_quality_lead, lead_source, enquiry_type, office
#      Placeholder table name: clef.quality_leads  ← TODO confirm
#
#   2. Lead-to-instruction conversion  (secondary KPI / sense-check)
#      Grain: one row per instruction, joinable to quality leads via enquiry_id
#      Key columns: enquiry_id, enquiry_date, instruction_date, region
#      Placeholder table name: clef.instructions  ← TODO confirm (may not exist)
#
#   3. Revenue by month  (model validation / £-per-lead calibration)
#      Grain: monthly
#      Key columns: month, new_instruction_revenue, new_instructions
#      Placeholder table name: finance.monthly_revenue  ← TODO confirm (if shareable)
#
# See docs/data_request_stowe.md for the full data request sent to Stowe's data team.
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
# All names are placeholders. Confirm against DW schema — see docs/data_request_stowe.md.

CLEF_TABLE    = "clef.quality_leads"       # TODO: confirm actual table/view name
REVENUE_TABLE = "finance.monthly_revenue"  # TODO: confirm — may not exist or may be named differently

# --- Expected schema ---------------------------------------------------------
# Columns we anticipate in CLEF_TABLE. Used by validate_schema() to catch
# mismatches early rather than surfacing confusing pandas errors downstream.
# Update keys here once the DW schema is confirmed; add/remove columns as needed.

CLEF_EXPECTED_COLUMNS = {
    # Column names are best-guess. Update once Stowe's data team confirms the schema.
    # See docs/data_request_stowe.md for the full list of columns requested.
    "enquiry_date":    "datetime64[ns]",  # TODO: confirm column name (may be "created_date", "received_date", etc.)
    "region":          "object",          # TODO: confirm values — NUTS-1 or Stowe's own regional categorisation
    "enquiry_type":    "object",          # TODO: confirm — may not exist; divorce | financial_remedy | children | other
    "lead_source":     "object",          # TODO: confirm — may not exist; web_form | phone | chat | referral
    "is_quality_lead": "int64",           # TODO: confirm column name and flag values (1/0 or True/False)
    "office":          "object",          # TODO: confirm — may not exist at this grain
}

# --- Query -------------------------------------------------------------------

# Pulls one row per enquiry so Python handles all aggregation.
# ALL column names are placeholders — update SELECT aliases once schema is confirmed.
# See CLEF_EXPECTED_COLUMNS above and docs/data_request_stowe.md.
CLEF_QUERY = """
    SELECT
        enquiry_date,       -- TODO: confirm column name
        region,             -- TODO: confirm column name and value set
        enquiry_type,       -- TODO: confirm column name; omit if not available
        lead_source,        -- TODO: confirm column name; omit if not available
        is_quality_lead,    -- TODO: confirm column name and flag encoding
        office              -- TODO: confirm column name; omit if not available
    FROM {table}
    WHERE
        enquiry_date BETWEEN :start AND :end
    ORDER BY
        enquiry_date ASC
"""

# Revenue query — only available if Stowe shares finance data (see data request, table 3).
# Placeholder: confirm table name, column names, and date column type.
REVENUE_QUERY = """
    SELECT
        month,                      -- TODO: confirm column name (first of month)
        new_instruction_revenue,    -- TODO: confirm column name; may be total_revenue
        new_instructions            -- TODO: confirm column name
    FROM {table}
    WHERE
        month BETWEEN :start AND :end
    ORDER BY
        month ASC
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


def fetch_revenue(start: str, end: str) -> pd.DataFrame:
    """
    Monthly revenue and new instruction count from the finance DW table.
    Optional secondary KPI — used to validate the model's implied £/lead figure.

    Returns: month | new_instruction_revenue | new_instructions

    NOT IMPLEMENTED — requires:
      1. Stowe to confirm the revenue table exists and is shareable (see docs/data_request_stowe.md)
      2. REVENUE_TABLE and REVENUE_QUERY column names confirmed and updated above
      3. DW credentials set in .env
    """
    raise NotImplementedError(
        "Revenue data not yet available. "
        "See docs/data_request_stowe.md (table 3) for the outstanding data request."
    )


# --- Main --------------------------------------------------------------------

def fetch(start: str, end: str) -> pd.DataFrame:
    """Entry point called by 01_data_prep.py. Returns national daily quality leads."""
    raise NotImplementedError(
        "Azure DW schema not yet confirmed with Stowe's data team. "
        "See docs/data_request_stowe.md for the outstanding data request. "
        "Once credentials and column names are confirmed: "
        "remove this error and the function will delegate to fetch_clef_national()."
    )
