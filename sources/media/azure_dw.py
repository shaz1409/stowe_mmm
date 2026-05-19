# sources/azure_dw.py
# Pull data from Stowe's Azure Data Warehouse.
#
# Sources:
#   - Clef quality leads (KPI) — daily leads by region
#   - Any additional first-party data available in the DW
#
# Outputs:
#   - kpi DataFrame: date | region | quality_leads
#   - (extend with additional tables as schema becomes known)
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
# Update these once the DW schema is confirmed with Stowe's data team

CLEF_TABLE = "clef.quality_leads"   # placeholder — confirm actual table name

# --- Queries -----------------------------------------------------------------

CLEF_QUERY = """
    SELECT
        enquiry_date    AS date,
        region,
        COUNT(*)        AS quality_leads
    FROM {table}
    WHERE
        enquiry_date BETWEEN :start AND :end
        AND is_quality_lead = 1
    GROUP BY
        enquiry_date,
        region
    ORDER BY
        enquiry_date ASC,
        region ASC
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


# --- Fetch -------------------------------------------------------------------

def fetch_clef(start: str, end: str) -> pd.DataFrame:
    """
    Pull daily quality leads from Clef by region.

    Returns:
        date | region | quality_leads

    Note: column names, table name, and filter logic (is_quality_lead)
    need confirming against the actual DW schema.
    """
    from sqlalchemy import text

    engine = get_engine()
    query  = CLEF_QUERY.format(table=CLEF_TABLE)

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params={"start": start, "end": end})

    df["date"]          = pd.to_datetime(df["date"])
    df["quality_leads"] = df["quality_leads"].astype(int)

    return df


def fetch_clef_national(start: str, end: str) -> pd.DataFrame:
    """
    Aggregate Clef leads to national level (sum across regions).
    Use this as the MMM KPI when modelling nationally.
    """
    df = fetch_clef(start, end)
    return (
        df.groupby("date", as_index=False)["quality_leads"]
        .sum()
        .rename(columns={"quality_leads": "kpi_quality_leads"})
    )


# --- Main --------------------------------------------------------------------

def fetch(start: str, end: str) -> pd.DataFrame:
    """
    Entry point called by 01_data_prep.py.
    Returns national daily quality leads as the MMM KPI.
    Swap for fetch_clef() if regional modelling is needed later.
    """
    raise NotImplementedError(
        "Azure DW credentials not yet configured. "
        "Set AZURE_CONNECTION_STRING (or individual components) in .env "
        "and confirm table/column names against the DW schema."
    )
