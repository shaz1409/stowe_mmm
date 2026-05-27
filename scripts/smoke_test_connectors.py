"""
Smoke-test all media connectors and the Azure DW connector.

Fetches one month of data per source, prints a summary, and writes raw output
to data/raw/{channel}_smoke.csv for eyeballing.

Usage:
    python scripts/smoke_test_connectors.py

One month is used (DATE_START → 2024-01-31) for speed. Each connector is
wrapped in try/except so one failure does not kill the rest.
"""

import os
import sys

# Allow imports from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from config.dates import DATE_START

SMOKE_END = "2024-01-31"
RAW_DIR   = "data/raw"

os.makedirs(RAW_DIR, exist_ok=True)


def summarise(name: str, df: pd.DataFrame) -> None:
    if df.empty:
        print(f"  [WARN] {name}: returned empty DataFrame")
        return
    spend_col  = "spend" if "spend" in df.columns else None
    date_col   = "date"  if "date"  in df.columns else None
    camp_col   = "campaign" if "campaign" in df.columns else None

    rows       = len(df)
    date_range = f"{df[date_col].min().date()} → {df[date_col].max().date()}" if date_col else "n/a"
    total_spend = f"£{df[spend_col].sum():,.2f}" if spend_col else "n/a"
    n_campaigns = df[camp_col].nunique() if camp_col else "n/a"

    print(f"  rows        : {rows:,}")
    print(f"  date range  : {date_range}")
    print(f"  total spend : {total_spend}")
    print(f"  campaigns   : {n_campaigns}")


def run_connector(name: str, fetch_fn, out_path: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {name}")
    print(f"{'─' * 50}")
    try:
        df = fetch_fn()
        summarise(name, df)
        df.to_csv(out_path, index=False)
        print(f"  written     : {out_path}")
    except FileNotFoundError as e:
        print(f"  [SKIP] {e}")
    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")


# ── Connectors ────────────────────────────────────────────────────────────────

def _meta():
    from sources.media import meta
    return meta.fetch(DATE_START, SMOKE_END)

def _google_ads():
    from sources.media import google_ads
    return google_ads.fetch(DATE_START, SMOKE_END)

def _bing_ads():
    from sources.media import bing_ads
    return bing_ads.fetch(DATE_START, SMOKE_END)

def _stackadapt():
    from sources.media import stackadapt
    return stackadapt.fetch(start=DATE_START, end=SMOKE_END)

def _azure_dw():
    from sources.media import azure_dw
    return azure_dw.fetch(DATE_START, SMOKE_END)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Smoke-testing connectors  ({DATE_START} → {SMOKE_END})")

    run_connector("Meta",       _meta,       f"{RAW_DIR}/meta_smoke.csv")
    run_connector("Google Ads", _google_ads, f"{RAW_DIR}/google_ads_smoke.csv")
    run_connector("Bing Ads",   _bing_ads,   f"{RAW_DIR}/bing_ads_smoke.csv")
    run_connector("StackAdapt", _stackadapt, f"{RAW_DIR}/stackadapt_smoke.csv")
    run_connector("Azure DW",   _azure_dw,   f"{RAW_DIR}/azure_dw_smoke.csv")

    print(f"\n{'─' * 50}")
    print("Done. Check data/raw/*_smoke.csv for raw output.")
