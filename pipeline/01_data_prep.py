# pipeline/01_data_prep.py
# Pull every source, align to weekly Monday, and write data/processed/mmm_input.csv.
#
# Usage:
#   python pipeline/01_data_prep.py
#   python pipeline/01_data_prep.py --no-media-refresh
#   python pipeline/01_data_prep.py --start 2022-01-01 --end 2023-12-31

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from config.dates import DATE_START, DATE_END, TIME_GRAIN
from sources.controls import main as build_controls

RAW_DIR              = "data/raw"
PROCESSED_DIR        = "data/processed"
CONTROLS_PATH        = os.path.join(PROCESSED_DIR, "control_vars.csv")
OUTPUT_PATH          = os.path.join(PROCESSED_DIR, "mmm_input.csv")
CONTROLS_MAX_AGE_SEC = 86_400  # 24 h

# Lazy-loaded to avoid crashing when an optional platform SDK isn't installed.
# Channels with missing SDKs are skipped with a warning rather than aborting.
MEDIA_MODULE_PATHS = [
    ("meta",       "sources.media.meta"),
    ("google_ads", "sources.media.google_ads"),
    ("bing_ads",   "sources.media.bing_ads"),
    ("stackadapt", "sources.media.stackadapt"),
]

# Metrics summed per channel when aggregating to weekly grain.
# Channel-specific extras (reach, frequency, search_impression_share, …) are
# intentionally excluded here — they live in the raw CSVs for later use.
NUMERIC_COLS = ["spend", "impressions", "clicks", "conversions"]


# ── Media ─────────────────────────────────────────────────────────────────────

def fetch_all_media(
    start: str, end: str, refresh: bool = True
) -> dict[str, pd.DataFrame]:
    """
    Fetch (or load from cache) daily data for every media channel.

    When refresh=False, reads from data/raw/{channel}_raw.csv instead of
    calling the API. Sources that raise FileNotFoundError or any other exception
    are skipped with a warning so one failure doesn't abort the run.
    """
    import importlib

    os.makedirs(RAW_DIR, exist_ok=True)
    result: dict[str, pd.DataFrame] = {}

    for name, mod_path in MEDIA_MODULE_PATHS:
        try:
            mod = importlib.import_module(mod_path)
        except ImportError as e:
            print(f"  [{name}] SKIP  missing SDK — {e}")
            continue
        raw_path = os.path.join(RAW_DIR, f"{name}_raw.csv")

        if not refresh and os.path.exists(raw_path):
            print(f"  [{name}] loading from cache  {raw_path}")
            result[name] = pd.read_csv(raw_path, parse_dates=["date"])
            continue

        try:
            print(f"  [{name}] fetching {start} → {end}")
            df = mod.fetch(start, end)
            df.to_csv(raw_path, index=False)
            print(f"  [{name}] {len(df):,} rows  → {raw_path}")
            result[name] = df
        except FileNotFoundError as e:
            print(f"  [{name}] SKIP  {e}")
        except Exception as e:
            print(f"  [{name}] WARN  {type(e).__name__}: {e}")

    return result


def aggregate_media_to_weekly(media_dict: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Aggregate each channel's daily DataFrame to weekly Monday, then pivot wide.

    Output columns are {channel}_{metric} (e.g. google_ads_spend, meta_clicks).
    Weeks with no data become 0, not NaN — no spend genuinely means zero spend.
    """
    frames = []

    for channel, df in media_dict.items():
        if df.empty:
            continue

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        agg_cols   = [c for c in NUMERIC_COLS if c in df.columns]

        weekly = (
            df.groupby(pd.Grouper(key="date", freq=TIME_GRAIN))[agg_cols]
            .sum()
        )
        weekly.columns = [f"{channel}_{c}" for c in weekly.columns]
        frames.append(weekly)

    if not frames:
        return pd.DataFrame()

    wide = pd.concat(frames, axis=1).fillna(0)
    wide.index.name = "date"
    return wide


# ── KPI ───────────────────────────────────────────────────────────────────────

def fetch_kpi(start: str, end: str) -> pd.DataFrame:
    """
    Pull national daily quality leads from Clef/Azure DW and resample to weekly Monday.

    Returns a single-column DataFrame named quality_leads indexed by week-start date.
    Returns an empty frame (all-NaN after reindex) if DW credentials are not yet
    configured — this is expected during development.
    """
    _empty = pd.DataFrame(
        {"quality_leads": pd.array([], dtype="Int64")},
        index=pd.DatetimeIndex([], name="date"),
    )

    try:
        import importlib
        azure_dw = importlib.import_module("sources.media.azure_dw")
        print(f"  [azure_dw] fetching {start} → {end}")
        df = azure_dw.fetch_clef_national(start, end)
        df["date"] = pd.to_datetime(df["date"])
        weekly = (
            df.set_index("date")
            .rename(columns={"kpi_quality_leads": "quality_leads"})
            .resample(TIME_GRAIN)
            .sum()
        )
        print(f"  [azure_dw] {len(weekly):,} weekly rows")
        return weekly

    except NotImplementedError as e:
        print(f"  [azure_dw] WARN  KPI not yet available — {e}")
        return _empty
    except Exception as e:
        print(f"  [azure_dw] WARN  {type(e).__name__}: {e}")
        return _empty


# ── Controls ──────────────────────────────────────────────────────────────────

def _maybe_rebuild_controls(refresh: bool) -> None:
    if not refresh:
        return
    stale = (
        not os.path.exists(CONTROLS_PATH)
        or (time.time() - os.path.getmtime(CONTROLS_PATH)) > CONTROLS_MAX_AGE_SEC
    )
    if stale:
        print("Rebuilding control variables ...")
        os.makedirs(PROCESSED_DIR, exist_ok=True)
        build_controls()
    else:
        age_h = (time.time() - os.path.getmtime(CONTROLS_PATH)) / 3600
        print(f"Control variables up-to-date ({age_h:.1f} h old, threshold 24 h).")


# ── Calendar features ─────────────────────────────────────────────────────────

def _add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add Stowe-specific calendar dummies that can't come from external data sources.

    divorce_day    — first Monday of January each year.  Historically the single
                     largest weekly inquiry spike for UK divorce solicitors; without
                     an explicit dummy the model absorbs this into whichever channel
                     was active that week, inflating its coefficient.

    covid_lockdown — UK national lockdown 2020-03-23 → 2021-03-08.  A continuous
                     4-quarter demand shock that Prophet's holiday component won't
                     fully absorb; without a dummy, adstock decay estimates are
                     contaminated across all channels active in this period.
    """
    df = df.copy()

    # First Monday of January each year
    divorce_mondays: set = set()
    for year in range(df.index.min().year, df.index.max().year + 1):
        jan1 = pd.Timestamp(year, 1, 1)
        days_ahead = (0 - jan1.weekday()) % 7   # 0 = Monday; 0 if already Monday
        divorce_mondays.add(jan1 + pd.Timedelta(days=days_ahead))
    df["divorce_day"] = df.index.isin(divorce_mondays).astype(int)

    # UK COVID lockdowns: first national lockdown → end of main legal restrictions
    df["covid_lockdown"] = (
        (df.index >= "2020-03-23") & (df.index <= "2021-03-08")
    ).astype(int)

    n_divorce = df["divorce_day"].sum()
    n_covid   = df["covid_lockdown"].sum()
    print(f"  Calendar dummies: divorce_day={n_divorce} weeks, covid_lockdown={n_covid} weeks")

    return df


# ── Assembly ──────────────────────────────────────────────────────────────────

def build_modelling_table(
    start:            str  = DATE_START,
    end:              str  = DATE_END,
    media_refresh:    bool = True,
    controls_refresh: bool = True,
) -> pd.DataFrame:
    """
    Fetch all sources, align to weekly Monday grain, and join into one wide DataFrame.

    Column order: date | quality_leads | <media cols sorted> | <control cols>
    """
    # ── Controls
    print("\nChecking control variables ...")
    _maybe_rebuild_controls(controls_refresh)

    if not os.path.exists(CONTROLS_PATH):
        print("  WARNING: control_vars.csv not found — controls will be absent from output")
        controls = pd.DataFrame()
    else:
        controls = pd.read_csv(CONTROLS_PATH, index_col="date", parse_dates=True)
        controls.index = pd.to_datetime(controls.index)
        print(f"  Loaded {len(controls):,} rows × {len(controls.columns)} control cols")

    # ── Media
    print("\nFetching media ...")
    media_dict = fetch_all_media(start, end, refresh=media_refresh)
    media_wide = aggregate_media_to_weekly(media_dict)

    # ── KPI
    print("\nFetching KPI ...")
    kpi = fetch_kpi(start, end)

    # ── Join to a gapless weekly spine
    print("\nAssembling modelling table ...")
    spine = pd.date_range(start=start, end=end, freq=TIME_GRAIN)

    kpi_aligned   = kpi.reindex(spine)
    media_aligned = (
        media_wide.reindex(spine).fillna(0) if not media_wide.empty
        else pd.DataFrame(index=spine)
    )
    ctrl_aligned  = (
        controls.reindex(spine).ffill() if not controls.empty
        else pd.DataFrame(index=spine)
    )

    df = pd.concat([kpi_aligned, media_aligned, ctrl_aligned], axis=1)
    df.index.name = "date"

    # ── Calendar dummies (Divorce Day + COVID lockdown)
    df = _add_calendar_features(df)

    # ── Column order
    ch_names     = [ch for ch, _ in MEDIA_MODULE_PATHS]
    media_cols   = sorted(c for c in df.columns if any(c.startswith(f"{ch}_") for ch in ch_names))
    control_cols = [c for c in df.columns if c not in ["quality_leads"] + media_cols]
    ordered      = ["quality_leads"] + media_cols + control_cols
    df = df[[c for c in ordered if c in df.columns]]

    return df


# ── Summary ───────────────────────────────────────────────────────────────────

def _print_summary(df: pd.DataFrame) -> None:
    print(f"\n{'─' * 62}")
    print(f"  mmm_input  {df.index.min().date()} → {df.index.max().date()}")
    print(f"  rows  {len(df):>5,}   cols  {len(df.columns):>3}")

    nan_pct = df.isna().mean().mul(100)
    problem = nan_pct[nan_pct > 0]
    if problem.empty:
        print("  NaN   none")
    else:
        for col, pct in problem.items():
            note = ""
            if col == "quality_leads" and pct == 100:
                note = "  ← DW not yet connected (expected)"
            print(f"  NaN   {col:<42} {pct:5.1f}%{note}")
    print(f"{'─' * 62}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(
    start:            str  = DATE_START,
    end:              str  = DATE_END,
    media_refresh:    bool = True,
    controls_refresh: bool = True,
) -> None:
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    df = build_modelling_table(
        start=start,
        end=end,
        media_refresh=media_refresh,
        controls_refresh=controls_refresh,
    )

    out = df.reset_index()  # date becomes first column, not the index
    out.to_csv(OUTPUT_PATH, index=False)

    _print_summary(df)
    print(f"\nSaved → {OUTPUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the MMM modelling input table.")
    parser.add_argument(
        "--start", default=DATE_START,
        help=f"Override start date  (default: {DATE_START})",
    )
    parser.add_argument(
        "--end", default=DATE_END,
        help=f"Override end date    (default: {DATE_END})",
    )
    parser.add_argument(
        "--no-media-refresh", action="store_true",
        help="Load media from cached data/raw/ CSVs — skip API calls",
    )
    parser.add_argument(
        "--no-controls-refresh", action="store_true",
        help="Skip controls rebuild even if control_vars.csv is stale",
    )
    args = parser.parse_args()

    main(
        start=args.start,
        end=args.end,
        media_refresh=not args.no_media_refresh,
        controls_refresh=not args.no_controls_refresh,
    )
