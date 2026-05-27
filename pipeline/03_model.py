# pipeline/03_model.py
# Fit one or both MMM models on the prepared input data.
#
# Usage:
#   python pipeline/03_model.py --model meridian
#   python pipeline/03_model.py --model robyn
#   python pipeline/03_model.py --model both
#
# Reads:
#   data/processed/mmm_input.csv
#   config/features.yaml          (produced by 02_explore.py)
#
# Writes:
#   outputs/meridian/{ts}/        + outputs/meridian/latest symlink
#   outputs/robyn/{ts}/           + outputs/robyn/latest symlink

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import yaml

from models import meridian_model, robyn_model

INPUT_PATH    = "data/processed/mmm_input.csv"
FEATURES_PATH = "config/features.yaml"


def _load_inputs() -> tuple[pd.DataFrame, dict]:
    if not os.path.exists(INPUT_PATH):
        sys.exit(f"ERROR: {INPUT_PATH} not found — run 01_data_prep.py first")
    if not os.path.exists(FEATURES_PATH):
        sys.exit(f"ERROR: {FEATURES_PATH} not found — run 02_explore.py first")

    df = pd.read_csv(INPUT_PATH, parse_dates=["date"])
    df = df.set_index("date")
    df.index = pd.to_datetime(df.index)

    with open(FEATURES_PATH) as fh:
        features = yaml.safe_load(fh)

    print(f"Input: {len(df):,} rows × {len(df.columns)} cols  "
          f"({df.index.min().date()} → {df.index.max().date()})")
    print(f"Media channels: {[m['col'] for m in features.get('media', [])]}")
    print(f"Controls: {len(features.get('controls', []))} cols")
    return df, features


def _update_symlink(base_dir: str, outdir: str) -> None:
    latest = os.path.join(base_dir, "latest")
    if os.path.islink(latest):
        os.remove(latest)
    os.symlink(os.path.abspath(outdir), latest)


def _compute_oot_metrics(model_dir: str, df_oot: pd.DataFrame, kpi_col: str) -> None:
    """
    Approximate OOT R² and MAPE using the linear ROI×spend decomposition from
    training outputs.  Baseline is held at its training-period mean per week.
    Updates model_card.yaml in place.
    """
    card_path    = os.path.join(model_dir, "model_card.yaml")
    roi_path     = os.path.join(model_dir, "roi_table.csv")
    contrib_path = os.path.join(model_dir, "contributions.csv")

    if not all(os.path.exists(p) for p in [card_path, roi_path, contrib_path]):
        return
    if kpi_col not in df_oot.columns or df_oot[kpi_col].isna().all():
        print(f"  OOT: KPI '{kpi_col}' not available in held-out period — skipping OOT metrics")
        return

    with open(card_path) as f:
        card = yaml.safe_load(f)

    roi_df  = pd.read_csv(roi_path)
    contrib = pd.read_csv(contrib_path)
    baseline_mean = float(contrib["baseline"].mean()) if "baseline" in contrib.columns else 0.0

    actual    = df_oot[kpi_col].values.astype(float)
    n_oot     = len(actual)
    predicted = np.full(n_oot, baseline_mean)

    for _, row in roi_df.iterrows():
        ch  = str(row["channel"])
        col = f"{ch}_spend"
        roi = float(row.get("roi_leads_per_kgbp") or 0)
        if col in df_oot.columns:
            predicted += roi * df_oot[col].fillna(0).values[:n_oot] / 1_000

    resid    = actual - predicted
    denom    = np.sum((actual - actual.mean()) ** 2)
    oot_r2   = float(1 - np.sum(resid ** 2) / denom) if denom > 0 else float("nan")
    oot_mape = float(np.mean(np.abs(resid / np.where(actual == 0, 1, actual))) * 100)

    card["oot_r2"]   = round(oot_r2, 4)
    card["oot_mape"] = round(oot_mape, 2)
    with open(card_path, "w") as f:
        yaml.dump(card, f, default_flow_style=False, sort_keys=False)

    print(f"  OOT ({n_oot} wks): R²={oot_r2:.3f}  MAPE={oot_mape:.1f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit MMM model(s).")
    parser.add_argument(
        "--model",
        choices=["meridian", "robyn", "both"],
        default="both",
        help="Which model to run (default: both)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Fast low-sample run for testing (Meridian ~2 min, Robyn ~3 min)",
    )
    parser.add_argument(
        "--oot-weeks",
        type=int,
        default=8,
        help="Hold out last N weeks for out-of-time evaluation (default: 8; 0 = train on all data)",
    )
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    df, features = _load_inputs()

    kpi_col = features.get("kpi", "quality_leads")

    # ── OOT split ──
    oot_weeks = args.oot_weeks
    if oot_weeks > 0:
        if oot_weeks >= len(df):
            sys.exit(f"ERROR: --oot-weeks {oot_weeks} >= total rows {len(df)}")
        df_train = df.iloc[:-oot_weeks].copy()
        df_oot   = df.iloc[-oot_weeks:].copy()
        print(
            f"\nOOT split: training on {len(df_train)} weeks "
            f"({df_train.index.min().date()} → {df_train.index.max().date()}), "
            f"holding out {oot_weeks} weeks "
            f"({df_oot.index.min().date()} → {df_oot.index.max().date()})"
        )
        features = dict(features)   # don't mutate the loaded dict
        features["oot_weeks"] = oot_weeks
        features["oot_start"] = str(df_oot.index.min().date())
    else:
        df_train = df
        df_oot   = None
        print("\nOOT split disabled (--oot-weeks 0) — training on full dataset")

    if args.model in ("meridian", "both"):
        print("\nFitting Meridian ...")
        outdir = os.path.join("outputs", "meridian", ts)
        meridian_model.run(df_train, features, outdir, quick=args.quick)
        if df_oot is not None:
            _compute_oot_metrics(outdir, df_oot, kpi_col)
        _update_symlink(os.path.join("outputs", "meridian"), outdir)

    if args.model in ("robyn", "both"):
        print("\nFitting Robyn ...")
        outdir = os.path.join("outputs", "robyn", ts)
        robyn_model.run(df_train, features, outdir, quick=args.quick)
        if df_oot is not None:
            _compute_oot_metrics(outdir, df_oot, kpi_col)
        _update_symlink(os.path.join("outputs", "robyn"), outdir)

    print("\nDone. Run 04_evaluate.py to compare and promote a model.")


if __name__ == "__main__":
    main()
