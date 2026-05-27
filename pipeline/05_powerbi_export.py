# pipeline/05_powerbi_export.py
# Flatten accepted model outputs into Power BI-friendly flat CSVs.
# Reads from the accepted model symlink; falls back to latest if no accepted model exists.
#
# Usage:
#   python pipeline/05_powerbi_export.py
#   python pipeline/05_powerbi_export.py --model meridian   # target a specific model
#
# Reads:
#   outputs/{model}/accepted/   (or outputs/{model}/latest/ as fallback)
#
# Writes (all flat, PBI-ready):
#   outputs/powerbi/contributions.csv    — weekly spend decomposition by channel
#   outputs/powerbi/roi_summary.csv      — channel ROI, CPA, spend share
#   outputs/powerbi/response_curves.csv  — saturation curves for viz
#   outputs/powerbi/model_fit.csv        — actual vs predicted over time
#   outputs/powerbi/export_metadata.csv  — model name, run date, metrics

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import yaml

POWERBI_DIR = "outputs/powerbi"
MODEL_DIRS  = {
    "meridian": "outputs/meridian",
    "robyn":    "outputs/robyn",
}


# ── Source resolution ─────────────────────────────────────────────────────────

def _resolve_model_dir(model: str) -> str:
    base     = MODEL_DIRS[model]
    accepted = os.path.join(base, "accepted")
    latest   = os.path.join(base, "latest")

    if os.path.islink(accepted) and os.path.exists(accepted):
        print(f"  Using accepted {model} run: {os.path.realpath(accepted)}")
        return os.path.realpath(accepted)

    if os.path.islink(latest) and os.path.exists(latest):
        print(f"  WARNING: No accepted {model} run — falling back to latest.")
        print(f"  Run 04_evaluate.py to promote a model before sharing outputs.")
        return os.path.realpath(latest)

    sys.exit(
        f"ERROR: No outputs found for {model}. Run 03_model.py first."
    )


def _pick_model() -> str:
    """Auto-pick: prefer the model that has an accepted symlink."""
    for m in ["meridian", "robyn"]:
        if os.path.islink(os.path.join(MODEL_DIRS[m], "accepted")):
            return m
    # Fall back to whichever has a latest symlink
    for m in ["meridian", "robyn"]:
        if os.path.islink(os.path.join(MODEL_DIRS[m], "latest")):
            return m
    sys.exit("ERROR: No model outputs found. Run 03_model.py first.")


# ── Builders ──────────────────────────────────────────────────────────────────

def build_contributions(model_dir: str, model: str) -> pd.DataFrame:
    """
    Long-format contributions table for Power BI.
    Columns: date | model | channel | contribution_leads
    """
    df = pd.read_csv(os.path.join(model_dir, "contributions.csv"), parse_dates=["date"])
    df = df.set_index("date")

    contrib_cols = [c for c in df.columns if c.endswith("_contrib") or c == "baseline"]
    long = (
        df[contrib_cols]
        .reset_index()
        .melt(id_vars="date", var_name="component", value_name="contribution_leads")
    )
    long["model"] = model
    long["channel"] = long["component"].str.replace("_contrib", "", regex=False)
    return long[["date", "model", "channel", "contribution_leads"]]


def build_roi_summary(model_dir: str, model: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(model_dir, "roi_table.csv"))
    total_spend = df["total_spend_gbp"].sum()
    df["spend_share_pct"] = (df["total_spend_gbp"] / total_spend * 100).round(1)
    df["model"] = model
    return df


def build_response_curves(model_dir: str, model: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(model_dir, "response_curves.csv"))
    df["model"] = model
    return df


def build_model_fit(model_dir: str, model: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(model_dir, "diagnostics.csv"), parse_dates=["date"])
    df["model"] = model
    return df[["date", "model", "actual", "predicted", "residual"]]


def build_metadata(model_dir: str, model: str) -> pd.DataFrame:
    card_path = os.path.join(model_dir, "model_card.yaml")
    with open(card_path) as fh:
        card = yaml.safe_load(fh)
    return pd.DataFrame([{
        "model":          model,
        "model_type":     card.get("model", model),
        "run_date":       card.get("run_date"),
        "export_date":    datetime.now().isoformat(),
        "r_squared":      card.get("r_squared"),
        "mape_pct":       card.get("mape_pct"),
        "mae":            card.get("mae"),
        "n_obs":          card.get("n_obs"),
        "source_dir":     model_dir,
    }])


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Export accepted model to Power BI flat files.")
    parser.add_argument(
        "--model",
        choices=["meridian", "robyn"],
        default=None,
        help="Model to export (default: auto-pick accepted model)",
    )
    args = parser.parse_args()

    model     = args.model or _pick_model()
    model_dir = _resolve_model_dir(model)

    os.makedirs(POWERBI_DIR, exist_ok=True)

    print(f"\nExporting {model} → {POWERBI_DIR}/")

    outputs = {
        "contributions.csv":   build_contributions(model_dir, model),
        "roi_summary.csv":     build_roi_summary(model_dir, model),
        "response_curves.csv": build_response_curves(model_dir, model),
        "model_fit.csv":       build_model_fit(model_dir, model),
        "export_metadata.csv": build_metadata(model_dir, model),
    }

    for fname, df in outputs.items():
        path = os.path.join(POWERBI_DIR, fname)
        df.to_csv(path, index=False)
        print(f"  {fname:<26}  {len(df):>5,} rows")

    print(f"\nDone. All files in {POWERBI_DIR}/")


if __name__ == "__main__":
    main()
