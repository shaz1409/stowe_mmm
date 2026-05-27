# pipeline/02_validate.py
# Validation gate — runs after 01_data_prep.py, before EDA/modelling.
# Fails loudly on bad data so problems don't silently propagate downstream.
#
# Usage:
#   python pipeline/02_validate.py
#   python pipeline/02_validate.py --strict
#   python pipeline/02_validate.py --init-schema

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from config.dates import DATE_START, DATE_END, TIME_GRAIN

INPUT_PATH   = "data/processed/mmm_input.csv"
SCHEMA_PATH  = "config/expected_schema.yaml"
VALIDATE_DIR = "outputs/validate"

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

# Media channel name prefixes — used to distinguish media cols from control cols
MEDIA_CHANNELS = ("meta", "google_ads", "bing_ads", "stackadapt")


# ── Individual checks ─────────────────────────────────────────────────────────
# Each returns (check_name: str, status: str, message: str)

def check_date_coverage(df: pd.DataFrame):
    expected = pd.date_range(start=DATE_START, end=DATE_END, freq=TIME_GRAIN)
    actual   = df.index

    duplicates = actual[actual.duplicated()].tolist()
    if duplicates:
        return (
            "DATE_COVERAGE", FAIL,
            f"{len(duplicates)} duplicate dates: {[str(d.date()) for d in duplicates[:5]]}",
        )

    missing = expected.difference(actual)
    if not missing.empty:
        return (
            "DATE_COVERAGE", FAIL,
            f"{len(missing)} missing weeks: {[str(d.date()) for d in missing[:5]]}",
        )

    extra = actual.difference(expected)
    if not extra.empty:
        return (
            "DATE_COVERAGE", FAIL,
            f"{len(extra)} out-of-range dates: {[str(d.date()) for d in extra[:5]]}",
        )

    return ("DATE_COVERAGE", PASS, f"{len(actual):,} weeks, {DATE_START} → {DATE_END}, no gaps")


def check_kpi_presence(df: pd.DataFrame):
    if "quality_leads" not in df.columns:
        return ("KPI_PRESENCE", FAIL, "Column 'quality_leads' not found in input")

    if df["quality_leads"].isna().all():
        return ("KPI_PRESENCE", WARN, "quality_leads is all-NaN — Azure DW not yet connected (expected pre-connection)")

    non_null = df["quality_leads"].notna().sum()
    return ("KPI_PRESENCE", PASS, f"quality_leads present, {non_null:,} non-null rows")


def check_media_present(df: pd.DataFrame):
    spend_cols = [c for c in df.columns if c.endswith("_spend")]
    if not spend_cols:
        return ("MEDIA_PRESENT", FAIL, "No *_spend columns found")

    active = [c for c in spend_cols if df[c].fillna(0).gt(0).any()]
    if not active:
        return ("MEDIA_PRESENT", FAIL, f"All spend columns are zero: {spend_cols}")

    return ("MEDIA_PRESENT", PASS, f"{len(active)}/{len(spend_cols)} spend columns have non-zero values")


def check_no_fully_null_cols(df: pd.DataFrame):
    # KPI is exempt (all-NaN is expected pre-DW-connection)
    to_check = [c for c in df.columns if c != "quality_leads"]
    fully_null = [c for c in to_check if df[c].isna().all()]

    if fully_null:
        return ("NO_FULLY_NULL_COLS", FAIL, f"Fully-NaN columns (non-KPI): {fully_null}")

    return ("NO_FULLY_NULL_COLS", PASS, "No fully-NaN columns (KPI exempted)")


def check_numeric_types(df: pd.DataFrame):
    metric_suffixes = ("_spend", "_impressions", "_clicks", "_conversions")
    metric_cols = [c for c in df.columns if any(c.endswith(s) for s in metric_suffixes)]

    non_numeric = [c for c in metric_cols if not pd.api.types.is_numeric_dtype(df[c])]
    if non_numeric:
        return ("NUMERIC_TYPES", FAIL, f"Non-numeric metric columns: {non_numeric}")

    return ("NUMERIC_TYPES", PASS, f"{len(metric_cols)} metric columns all numeric")


def check_channel_completeness(df: pd.DataFrame):
    spend_cols = [c for c in df.columns if c.endswith("_spend")]
    if not spend_cols:
        return ("CHANNEL_COMPLETENESS", WARN, "No spend columns to check")

    issues = []
    for col in spend_cols:
        pct_zero = (df[col].fillna(0) == 0).mean() * 100
        if pct_zero > 70:
            issues.append(f"{col}: {pct_zero:.0f}% zero-spend weeks")

    if not issues:
        return ("CHANNEL_COMPLETENESS", PASS, "All channels have ≥30% active weeks")
    return (
        "CHANNEL_COMPLETENESS", WARN,
        "Channels likely not modellable as-is (>70% zero weeks): " + "; ".join(issues),
    )


def check_high_missingness(df: pd.DataFrame):
    # Controls only — media and KPI have their own checks
    non_media_non_kpi = [
        c for c in df.columns
        if c != "quality_leads"
        and not any(c.startswith(f"{ch}_") for ch in MEDIA_CHANNELS)
    ]
    if not non_media_non_kpi:
        return ("HIGH_MISSINGNESS", PASS, "No control columns to check")

    high = {
        c: df[c].isna().mean() * 100
        for c in non_media_non_kpi
        if df[c].isna().mean() > 0.20
    }
    if not high:
        return ("HIGH_MISSINGNESS", PASS, "All controls ≤20% NaN")

    detail = "; ".join(f"{c}: {p:.0f}%" for c, p in sorted(high.items(), key=lambda x: -x[1])[:5])
    return ("HIGH_MISSINGNESS", WARN, f"{len(high)} control(s) >20% NaN: {detail}")


def check_vif(df: pd.DataFrame):
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    numeric = df.select_dtypes(include=[np.number])
    # Use columns that are <20% NaN and have variance
    usable  = numeric.loc[:, numeric.isna().mean() < 0.20]
    usable  = usable.fillna(usable.mean())
    usable  = usable.loc[:, usable.std() > 0]

    if usable.shape[1] < 2:
        return ("VIF", PASS, "Not enough columns for VIF computation")

    X = usable.values.astype(float)
    vif_scores: dict[str, float] = {}
    for i, col in enumerate(usable.columns):
        try:
            vif_scores[col] = variance_inflation_factor(X, i)
        except Exception:
            pass

    if not vif_scores:
        return ("VIF", PASS, "VIF computation produced no results")

    ranked   = sorted(vif_scores.items(), key=lambda x: -x[1])
    top5_str = ", ".join(f"{k}={v:.1f}" for k, v in ranked[:5])
    high     = [(k, v) for k, v in ranked if v > 10]

    if not high:
        return ("VIF", PASS, f"No VIF > 10. Top 5: {top5_str}")
    return ("VIF", WARN, f"{len(high)} column(s) VIF > 10. Top 5: {top5_str}")


def check_stationarity(df: pd.DataFrame):
    from statsmodels.tsa.stattools import adfuller

    # Test KPI and controls; skip media spend — non-stationarity in spend is expected
    media_cols = {c for ch in MEDIA_CHANNELS for c in df.columns if c.startswith(f"{ch}_")}
    test_cols  = [c for c in df.columns if c not in media_cols]

    non_stationary: list[str] = []
    for col in test_cols:
        s = df[col].dropna()
        if len(s) < 20:
            continue
        try:
            _, p_val, *_ = adfuller(s, autolag="AIC")
            if p_val > 0.05:
                non_stationary.append(f"{col} (p={p_val:.3f})")
        except Exception:
            pass

    if not non_stationary:
        return ("STATIONARITY", PASS, "All tested columns stationary at p ≤ 0.05 (media spend excluded)")

    detail = "; ".join(non_stationary[:5])
    suffix = f" ... (+{len(non_stationary)-5} more)" if len(non_stationary) > 5 else ""
    return (
        "STATIONARITY", WARN,
        f"{len(non_stationary)} non-stationary column(s): {detail}{suffix}",
    )


def check_outliers(df: pd.DataFrame):
    numeric = df.select_dtypes(include=[np.number])
    issues: list[str] = []

    for col in numeric.columns:
        s = numeric[col].dropna()
        if len(s) < 10:
            continue
        mean, std = s.mean(), s.std()
        if std == 0:
            continue
        outlier_idx = numeric.index[
            numeric[col].notna() & (np.abs(numeric[col] - mean) > 5 * std)
        ]
        if len(outlier_idx) > 0:
            dates = [str(d.date()) for d in outlier_idx[:3]]
            issues.append(f"{col}: {len(outlier_idx)} row(s) >5σ at {dates}")

    if not issues:
        return ("OUTLIERS", PASS, "No values > 5σ from column mean")

    detail = "; ".join(issues[:5])
    suffix = f" ... (+{len(issues)-5} more)" if len(issues) > 5 else ""
    return ("OUTLIERS", WARN, f"Extreme outliers detected — {detail}{suffix}")


def check_trailing_nan(df: pd.DataFrame):
    issues: list[str] = []

    for col in df.columns:
        s = df[col]
        if s.isna().sum() == 0:
            continue
        last_valid = s.last_valid_index()
        if last_valid is None:
            continue  # all-NaN handled by check_no_fully_null_cols
        trailing = int(s.loc[last_valid:].isna().sum())
        if trailing > 0:
            issues.append(f"{col}: {trailing} trailing week(s)")

    if not issues:
        return ("TRAILING_NAN", PASS, "No trailing NaN sequences")

    detail = "; ".join(issues[:5])
    suffix = f" ... (+{len(issues)-5} more)" if len(issues) > 5 else ""
    return (
        "TRAILING_NAN", WARN,
        f"Publication lag likely — {detail}{suffix}",
    )


def check_media_correlation(df: pd.DataFrame):
    spend_cols = [c for c in df.columns if c.endswith("_spend")]
    if len(spend_cols) < 2:
        return ("MEDIA_CORRELATION", PASS, "Fewer than 2 spend columns — nothing to correlate")

    corr = df[spend_cols].fillna(0).corr()
    high_pairs = []
    for i, c1 in enumerate(spend_cols):
        for c2 in spend_cols[i + 1:]:
            r = corr.loc[c1, c2]
            if abs(r) > 0.70:
                label = f"{c1.replace('_spend','')}↔{c2.replace('_spend','')} r={r:.2f}"
                high_pairs.append(label)

    if not high_pairs:
        return ("MEDIA_CORRELATION", PASS, "No spend column pairs with |r| > 0.70")
    return (
        "MEDIA_CORRELATION", WARN,
        "Correlated spend pairs (|r|>0.70) — shared budget cycles inflate apparent ROI for weaker channel: "
        + "; ".join(high_pairs),
    )


def check_zero_runs(df: pd.DataFrame):
    """Flag channels with long consecutive zero-spend streaks that contaminate adstock warmup."""
    spend_cols = [c for c in df.columns if c.endswith("_spend")]
    issues = []
    for col in spend_cols:
        s = (df[col].fillna(0) == 0).values
        max_run, run = 0, 0
        for v in s:
            run = run + 1 if v else 0
            max_run = max(max_run, run)
        if max_run > 4:
            issues.append(f"{col.replace('_spend','')}: {max_run} consecutive zero weeks")

    if not issues:
        return ("ZERO_RUNS", PASS, "No channel has >4 consecutive zero-spend weeks")
    return (
        "ZERO_RUNS", WARN,
        "Long pauses reset adstock carry-over unrealistically — consider channel exclusion or "
        "spend-floor imputation: " + "; ".join(issues),
    )


def check_structural_breaks(df: pd.DataFrame):
    """
    Check for the COVID demand shock and scan for any other non-COVID structural shift.
    Also verifies that calendar dummies (divorce_day, covid_lockdown) are present.
    """
    kpi = df.get("quality_leads")
    if kpi is None or kpi.isna().all():
        return ("STRUCTURAL_BREAKS", WARN, "quality_leads not available — skipping break detection")

    series = kpi.dropna()
    n = len(series)
    if n < 30:
        return ("STRUCTURAL_BREAKS", WARN, f"Only {n} non-null KPI obs — need ≥30 for break detection")

    issues = []

    # ── Verify calendar dummies are present ──
    for col in ("covid_lockdown", "divorce_day"):
        if col not in df.columns:
            issues.append(f"{col} column missing — re-run 01_data_prep.py")

    # ── Chow-style mean-shift scan, excluding the COVID window ──
    arr   = series.values
    dates = series.index
    covid_window = (dates >= "2020-03-23") & (dates <= "2021-03-08")
    sigma = series.std()

    best_shift, best_date = 0.0, None
    for i in range(10, n - 10):
        if covid_window[i]:
            continue
        left_mean  = arr[:i].mean()
        right_mean = arr[i:].mean()
        shift = abs(left_mean - right_mean) / (sigma + 1e-9)
        if shift > best_shift:
            best_shift = shift
            best_date  = dates[i]

    if best_date is not None and best_shift > 1.5:
        issues.append(
            f"Non-COVID mean shift ≈{best_shift:.1f}σ detected at {best_date.date()} "
            f"— check for agency change, brand rebrand, or pricing event"
        )

    if not issues:
        return (
            "STRUCTURAL_BREAKS", PASS,
            "divorce_day + covid_lockdown dummies present; no unexpected structural shift detected",
        )
    return ("STRUCTURAL_BREAKS", WARN, " | ".join(issues))


# ── Schema drift ──────────────────────────────────────────────────────────────

def _write_schema(df: pd.DataFrame) -> None:
    import yaml
    schema = {
        "date_start":  str(df.index.min().date()),
        "date_end":    str(df.index.max().date()),
        "columns":     {c: str(df[c].dtype) for c in df.columns},
    }
    with open(SCHEMA_PATH, "w") as fh:
        yaml.dump(schema, fh, default_flow_style=False, sort_keys=True)
    print(f"  Schema written → {SCHEMA_PATH}")


def check_schema_drift(df: pd.DataFrame, init_schema: bool = False):
    import yaml

    if init_schema or not os.path.exists(SCHEMA_PATH):
        _write_schema(df)
        action = "re-initialised" if os.path.exists(SCHEMA_PATH) else "written"
        return ("SCHEMA_DRIFT", PASS, f"Schema {action} at {SCHEMA_PATH}")

    with open(SCHEMA_PATH) as fh:
        expected = yaml.safe_load(fh)

    expected_cols = set(expected.get("columns", {}).keys())
    actual_cols   = set(df.columns)

    missing  = sorted(expected_cols - actual_cols)
    new_cols = sorted(actual_cols   - expected_cols)

    if missing:
        return (
            "SCHEMA_DRIFT", FAIL,
            f"Columns dropped vs expected schema (connector regression?): {missing}",
        )
    if new_cols:
        return (
            "SCHEMA_DRIFT", WARN,
            f"New columns not in schema: {new_cols}. Run --init-schema after review.",
        )
    return ("SCHEMA_DRIFT", PASS, "Schema matches expected")


# ── Orchestration ─────────────────────────────────────────────────────────────

def run_all_checks(df: pd.DataFrame, init_schema: bool = False) -> list[tuple]:
    return [
        check_date_coverage(df),
        check_kpi_presence(df),
        check_media_present(df),
        check_no_fully_null_cols(df),
        check_numeric_types(df),
        check_schema_drift(df, init_schema=init_schema),
        check_channel_completeness(df),
        check_zero_runs(df),
        check_high_missingness(df),
        check_outliers(df),
        check_trailing_nan(df),
        check_media_correlation(df),
        check_vif(df),
        check_stationarity(df),
        check_structural_breaks(df),
    ]


# ── Report ────────────────────────────────────────────────────────────────────

_STATUS_ICON = {PASS: "✅", WARN: "⚠️ ", FAIL: "❌"}


def _build_report(results: list[tuple], df: pd.DataFrame, ts: str) -> str:
    lines = [
        "# Validation Report",
        "",
        f"**Run:** {ts}  ",
        f"**Input:** {INPUT_PATH}  ",
        f"**Date range:** {df.index.min().date()} → {df.index.max().date()}  ",
        f"**Rows:** {len(df):,} | **Columns:** {len(df.columns)}",
        "",
        "## Summary",
        "",
        "| Check | Status | Message |",
        "|---|---|---|",
    ]

    for name, status, message in results:
        icon = _STATUS_ICON[status]
        lines.append(f"| {name} | {icon} {status} | {message} |")

    issues = [(n, s, m) for n, s, m in results if s in (WARN, FAIL)]
    if issues:
        lines += ["", "## Issues", ""]
        for name, status, message in issues:
            icon = _STATUS_ICON[status]
            lines += [f"### {icon} {name} ({status})", "", message, ""]

    return "\n".join(lines)


def write_report(results: list[tuple], df: pd.DataFrame) -> str:
    ts     = datetime.now().strftime("%Y-%m-%d_%H%M")
    outdir = os.path.join(VALIDATE_DIR, ts)
    os.makedirs(outdir, exist_ok=True)

    report_path = os.path.join(outdir, "validation_report.md")
    with open(report_path, "w") as fh:
        fh.write(_build_report(results, df, ts))

    # Update outputs/validate/latest symlink
    latest = os.path.join(VALIDATE_DIR, "latest")
    if os.path.islink(latest):
        os.remove(latest)
    os.symlink(os.path.abspath(outdir), latest)

    return outdir


def print_summary(results: list[tuple]) -> None:
    counts = {PASS: 0, WARN: 0, FAIL: 0}
    for _, status, _ in results:
        counts[status] += 1

    print(f"\n{'─' * 56}")
    print(
        f"  Validation  "
        f"PASS {counts[PASS]}  "
        f"WARN {counts[WARN]}  "
        f"FAIL {counts[FAIL]}"
    )
    if counts[FAIL]:
        print("  Status: FAILED")
        for name, status, msg in results:
            if status == FAIL:
                print(f"  ❌ {name}: {msg}")
    elif counts[WARN]:
        print("  Status: PASSED WITH WARNINGS")
        for name, status, msg in results:
            if status == WARN:
                print(f"  ⚠️  {name}: {msg}")
    else:
        print("  Status: PASSED")
    print(f"{'─' * 56}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(strict: bool = False, init_schema: bool = False) -> None:
    if not os.path.exists(INPUT_PATH):
        print(f"ERROR: {INPUT_PATH} not found — run 01_data_prep.py first")
        sys.exit(1)

    print(f"Loading {INPUT_PATH} ...")
    df = pd.read_csv(INPUT_PATH, parse_dates=["date"])
    df = df.set_index("date")
    df.index = pd.to_datetime(df.index)
    print(f"  {len(df):,} rows × {len(df.columns)} columns")

    print("\nRunning checks ...")
    results = run_all_checks(df, init_schema=init_schema)

    if strict:
        results = [
            (n, FAIL if s == WARN else s, m)
            for n, s, m in results
        ]

    outdir = write_report(results, df)
    print_summary(results)
    print(f"\nReport → {outdir}/validation_report.md")

    n_fails = sum(1 for _, s, _ in results if s == FAIL)
    sys.exit(1 if n_fails else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate the MMM input table.")
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat warnings as failures (useful in CI)",
    )
    parser.add_argument(
        "--init-schema", action="store_true",
        help="(Re)write config/expected_schema.yaml from current input",
    )
    args = parser.parse_args()

    main(strict=args.strict, init_schema=args.init_schema)
