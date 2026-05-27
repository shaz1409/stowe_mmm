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
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    df, features = _load_inputs()

    if args.model in ("meridian", "both"):
        print("\nFitting Meridian ...")
        outdir = os.path.join("outputs", "meridian", ts)
        meridian_model.run(df, features, outdir, quick=args.quick)
        _update_symlink(os.path.join("outputs", "meridian"), outdir)

    if args.model in ("robyn", "both"):
        print("\nFitting Robyn ...")
        outdir = os.path.join("outputs", "robyn", ts)
        robyn_model.run(df, features, outdir, quick=args.quick)
        _update_symlink(os.path.join("outputs", "robyn"), outdir)

    print("\nDone. Run 04_evaluate.py to compare and promote a model.")


if __name__ == "__main__":
    main()
