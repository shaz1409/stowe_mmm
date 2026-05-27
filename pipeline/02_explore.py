# pipeline/02_explore.py
# EDA, feature selection, and adstock guidance.
#
# Usage:
#   python pipeline/02_explore.py
#
# Reads:  data/processed/mmm_input.csv
# Writes: outputs/explore/{ts}/  +  config/features.yaml

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import yaml

INPUT_PATH   = "data/processed/mmm_input.csv"
EXPLORE_DIR  = "outputs/explore"
FEATURES_OUT = "config/features.yaml"

MEDIA_CHANNELS = ["google_ads", "meta", "bing_ads", "stackadapt"]
CHANNEL_TYPE   = {
    "google_ads": "ppc",
    "bing_ads":   "ppc",
    "meta":       "social",
    "stackadapt": "display",
}
# Domain-knowledge adstock theta bounds and defaults by channel type.
# PPC has shorter carry-over (intent-driven); social/display has longer.
THETA_BOUNDS   = {"ppc": (0.30, 0.50), "social": (0.40, 0.65), "display": (0.40, 0.65)}
THETA_DEFAULTS = {"ppc": 0.40, "social": 0.52, "display": 0.50}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _spend_cols(df: pd.DataFrame) -> list[str]:
    return [
        c for c in df.columns
        if c.endswith("_spend") and any(c.startswith(ch) for ch in MEDIA_CHANNELS)
    ]


def _control_cols(df: pd.DataFrame) -> list[str]:
    media_prefixed = {
        c for c in df.columns
        if any(c.startswith(f"{ch}_") for ch in MEDIA_CHANNELS)
    }
    return [c for c in df.columns if c != "quality_leads" and c not in media_prefixed]


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    if not os.path.exists(INPUT_PATH):
        sys.exit(f"ERROR: {INPUT_PATH} not found — run 01_data_prep.py first")
    df = pd.read_csv(INPUT_PATH, parse_dates=["date"])
    df = df.set_index("date")
    df.index = pd.to_datetime(df.index)
    print(f"Loaded {len(df):,} rows × {len(df.columns)} columns  "
          f"({df.index.min().date()} → {df.index.max().date()})")
    return df


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame) -> None:
    print(f"\n{'─'*60}")
    print("  SUMMARY")
    print(f"{'─'*60}")

    kpi_col = "quality_leads"
    if kpi_col in df.columns and df[kpi_col].notna().any():
        ql = df[kpi_col].dropna()
        print(f"  KPI  quality_leads: mean={ql.mean():.1f}  std={ql.std():.1f}  "
              f"min={ql.min():.0f}  max={ql.max():.0f}")
    else:
        print("  KPI  quality_leads: NOT AVAILABLE (DW not connected)")

    spend_cols = _spend_cols(df)
    print(f"\n  MEDIA SPEND  ({len(spend_cols)} channels)")
    for col in spend_cols:
        s = df[col].fillna(0)
        active = (s > 0).mean() * 100
        print(f"    {col:<30}  total=£{s.sum():>12,.0f}  active={active:.0f}% of weeks")

    ctrl = _control_cols(df)
    high_nan = [(c, df[c].isna().mean() * 100) for c in ctrl if df[c].isna().mean() > 0.20]
    print(f"\n  CONTROLS  ({len(ctrl)} cols, {len(high_nan)} with >20% NaN)")
    for c, p in sorted(high_nan, key=lambda x: -x[1])[:5]:
        print(f"    {c:<40}  {p:.0f}% NaN")
    print(f"{'─'*60}")


# ── Adstock theta suggestion ──────────────────────────────────────────────────

def suggest_theta(df: pd.DataFrame, spend_col: str) -> float:
    """
    Estimate adstock theta from cross-correlation of spend with the KPI.
    Falls back to domain-knowledge defaults when KPI is unavailable.
    """
    ch    = next((ch for ch in MEDIA_CHANNELS if spend_col.startswith(ch)), None)
    ctype = CHANNEL_TYPE.get(ch, "ppc")
    lo, hi = THETA_BOUNDS[ctype]
    default = THETA_DEFAULTS[ctype]

    kpi = "quality_leads"
    if kpi not in df.columns or df[kpi].isna().all() or df[spend_col].fillna(0).std() == 0:
        return default

    spend = df[spend_col].fillna(0)
    kpi_s = df[kpi].fillna(df[kpi].mean())

    s_norm = (spend - spend.mean()) / spend.std()
    k_norm = (kpi_s - kpi_s.mean()) / kpi_s.std()
    n = len(s_norm)

    xcorr = [
        float(s_norm.iloc[:n - lag].values @ k_norm.iloc[lag:].values / n)
        for lag in range(9)
    ]
    peak_lag = int(np.argmax(xcorr))
    if peak_lag == 0:
        return default

    theta = 0.5 ** (1.0 / peak_lag)
    return round(float(np.clip(theta, lo, hi)), 3)


# ── Correlation analysis ──────────────────────────────────────────────────────

def correlation_table(df: pd.DataFrame) -> pd.DataFrame:
    spend_cols = _spend_cols(df)
    kpi = "quality_leads"
    if kpi not in df.columns or df[kpi].isna().all():
        return pd.DataFrame()

    rows = []
    for col in spend_cols:
        r = df[col].fillna(0).corr(df[kpi])
        rows.append({"channel": col.replace("_spend", ""), "pearson_r_vs_kpi": round(r, 3)})
    return pd.DataFrame(rows).sort_values("pearson_r_vs_kpi", ascending=False)


# ── Plots ─────────────────────────────────────────────────────────────────────

def make_plots(df: pd.DataFrame, outdir: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("  matplotlib not installed — skipping plots")
        return

    spend_cols = _spend_cols(df)
    kpi_available = "quality_leads" in df.columns and df["quality_leads"].notna().any()

    # 1. Weekly spend per channel
    n = len(spend_cols)
    fig, axes = plt.subplots(n, 1, figsize=(13, 3 * n), sharex=True)
    if n == 1:
        axes = [axes]
    for ax, col in zip(axes, spend_cols):
        ax.fill_between(df.index, df[col].fillna(0) / 1_000, alpha=0.65)
        ax.set_ylabel("£k / week")
        ax.set_title(col.replace("_spend", "").replace("_", " ").title())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    fig.suptitle("Weekly Spend by Channel", fontsize=13, y=1.01)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "spend_trends.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)

    # 2. KPI over time
    if kpi_available:
        fig, ax = plt.subplots(figsize=(13, 3))
        ax.plot(df.index, df["quality_leads"], lw=1.3, color="steelblue")
        ax.set_ylabel("quality_leads / week")
        ax.set_title("KPI: Weekly Quality Leads")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "kpi_trend.png"), dpi=120)
        plt.close(fig)

    # 3. Spend vs KPI scatter
    if kpi_available and spend_cols:
        cols_per_row = min(len(spend_cols), 2)
        rows_needed  = (len(spend_cols) + cols_per_row - 1) // cols_per_row
        fig, axes = plt.subplots(rows_needed, cols_per_row,
                                 figsize=(7 * cols_per_row, 4 * rows_needed))
        axes_flat = np.array(axes).flatten()
        for ax, col in zip(axes_flat, spend_cols):
            ax.scatter(df[col].fillna(0) / 1_000, df["quality_leads"],
                       alpha=0.4, s=14, edgecolors="none")
            ax.set_xlabel(f"{col.replace('_spend','').replace('_',' ').title()} (£k)")
            ax.set_ylabel("quality_leads")
        for ax in axes_flat[len(spend_cols):]:
            ax.set_visible(False)
        fig.suptitle("Spend vs Quality Leads (weekly)", fontsize=13)
        fig.tight_layout()
        fig.savefig(os.path.join(outdir, "spend_vs_kpi.png"), dpi=120)
        plt.close(fig)

    print(f"  Plots saved → {outdir}/")


# ── Feature selection ─────────────────────────────────────────────────────────

def select_features(df: pd.DataFrame) -> dict:
    """
    Build config/features.yaml:
      - Media: all spend cols with ≥30% active weeks, with suggested adstock thetas
      - Controls: cols with <50% NaN
      - Dropped: everything excluded and why
    """
    spend_cols = _spend_cols(df)
    ctrl_cols  = _control_cols(df)

    media   = []
    dropped = []

    for col in spend_cols:
        active_pct = (df[col].fillna(0) > 0).mean() * 100
        if active_pct < 30:
            dropped.append({"col": col, "reason": f"only {active_pct:.0f}% active weeks — not modellable"})
            continue
        ch    = next((ch for ch in MEDIA_CHANNELS if col.startswith(ch)), col)
        theta = suggest_theta(df, col)
        media.append({
            "col":           col,
            "adstock_theta": theta,
            "channel_type":  CHANNEL_TYPE.get(ch, "unknown"),
        })

    controls = []
    for c in ctrl_cols:
        nan_pct = df[c].isna().mean() * 100
        if nan_pct >= 50:
            dropped.append({"col": c, "reason": f"{nan_pct:.0f}% NaN — too sparse"})
        else:
            controls.append(c)

    return {
        "kpi":      "quality_leads",
        "date":     "date",
        "media":    media,
        "controls": controls,
        "dropped":  dropped,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ts     = datetime.now().strftime("%Y-%m-%d_%H%M")
    outdir = os.path.join(EXPLORE_DIR, ts)
    os.makedirs(outdir, exist_ok=True)
    os.makedirs("config", exist_ok=True)

    df = load_data()
    print_summary(df)

    corr = correlation_table(df)
    if not corr.empty:
        print("\nCorrelation (spend → quality_leads):")
        print(corr.to_string(index=False))
        corr.to_csv(os.path.join(outdir, "correlations.csv"), index=False)

    print("\nGenerating plots ...")
    make_plots(df, outdir)

    print("\nSelecting features ...")
    features = select_features(df)

    os.makedirs("config", exist_ok=True)
    with open(FEATURES_OUT, "w") as fh:
        yaml.dump(features, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)

    n_m = len(features["media"])
    n_c = len(features["controls"])
    n_d = len(features["dropped"])
    print(f"  {n_m} media cols  |  {n_c} controls  |  {n_d} dropped")
    print(f"  features.yaml → {FEATURES_OUT}")

    # latest symlink
    latest = os.path.join(EXPLORE_DIR, "latest")
    if os.path.islink(latest):
        os.remove(latest)
    os.symlink(os.path.abspath(outdir), latest)

    print(f"\nDone → {outdir}/")


if __name__ == "__main__":
    main()
