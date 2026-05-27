# pipeline/04_evaluate.py
# Compare Meridian and Robyn outputs; run publish gate; promote winner to accepted.
#
# Usage:
#   python pipeline/04_evaluate.py
#   python pipeline/04_evaluate.py --promote meridian   # skip gate, force promote
#
# Reads:
#   outputs/meridian/latest/
#   outputs/robyn/latest/
#
# Writes:
#   outputs/compare/{ts}/comparison_report.md
#   outputs/compare/{ts}/comparison_metrics.csv
#   outputs/{winner}/accepted  symlink  (if publish gate passes)

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import yaml

COMPARE_DIR = "outputs/compare"
MODEL_DIRS  = {
    "meridian": "outputs/meridian",
    "robyn":    "outputs/robyn",
}

# Publish gate thresholds
MIN_R2             = 0.50
MAX_MAPE           = 30.0
MAX_ROI_DIVERGENCE = 0.50  # flag if channel ROI estimates diverge >50% between models


# ── Loaders ───────────────────────────────────────────────────────────────────

def _latest_dir(model: str) -> str:
    base   = MODEL_DIRS[model]
    latest = os.path.join(base, "latest")
    if os.path.islink(latest) and os.path.exists(latest):
        return os.path.realpath(latest)
    sys.exit(
        f"ERROR: no outputs found for {model} at {latest}. "
        "Run 03_model.py first."
    )


def _load_card(model_dir: str) -> dict:
    path = os.path.join(model_dir, "model_card.yaml")
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} not found")
    with open(path) as fh:
        return yaml.safe_load(fh)


def _load_roi(model_dir: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(model_dir, "roi_table.csv"))


# ── Comparison ────────────────────────────────────────────────────────────────

def compare_fit_metrics(cards: dict[str, dict]) -> pd.DataFrame:
    rows = []
    has_oot = any(c.get("oot_r2") is not None for c in cards.values())
    for model, card in cards.items():
        row: dict = {
            "model":     model,
            "r_squared": card.get("r_squared"),
            "mape_pct":  card.get("mape_pct"),
            "mae":       card.get("mae"),
            "n_obs":     card.get("n_obs"),
        }
        if has_oot:
            row["oot_r2"]    = card.get("oot_r2")
            row["oot_mape"]  = card.get("oot_mape")
            row["oot_weeks"] = card.get("oot_weeks")
        rows.append(row)
    return pd.DataFrame(rows)


def compare_roi(roi_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    merged = None
    for model, df in roi_tables.items():
        df = df[["channel", "roi_leads_per_kgbp", "cpa_gbp"]].copy()
        df = df.rename(columns={
            "roi_leads_per_kgbp": f"roi_{model}",
            "cpa_gbp":            f"cpa_{model}",
        })
        merged = df if merged is None else merged.merge(df, on="channel", how="outer")

    if merged is None or len(roi_tables) < 2:
        return merged if merged is not None else pd.DataFrame()

    models = list(roi_tables.keys())
    m1, m2 = models[0], models[1]
    r1  = merged[f"roi_{m1}"].fillna(0)
    r2  = merged[f"roi_{m2}"].fillna(0)
    avg = (r1 + r2) / 2
    merged["roi_divergence_pct"] = (
        (r1 - r2).abs() / avg.replace(0, np.nan) * 100
    ).round(1)
    return merged


def run_publish_gate(
    fit_metrics: pd.DataFrame,
    roi_cmp: pd.DataFrame,
) -> tuple[bool, str, str | None]:
    """Returns (passed, reason, recommended_model). recommended_model is None on failure."""
    issues = []

    for _, row in fit_metrics.iterrows():
        model = row["model"]
        if row["r_squared"] is not None and row["r_squared"] < MIN_R2:
            issues.append(f"{model} R²={row['r_squared']:.3f} < {MIN_R2}")
        if row["mape_pct"] is not None and row["mape_pct"] > MAX_MAPE:
            issues.append(f"{model} MAPE={row['mape_pct']:.1f}% > {MAX_MAPE}%")

    if not roi_cmp.empty and "roi_divergence_pct" in roi_cmp.columns:
        high = roi_cmp[roi_cmp["roi_divergence_pct"] > MAX_ROI_DIVERGENCE * 100]
        if not high.empty:
            issues.append(
                f"ROI diverges >50% for channels: {high['channel'].tolist()} — "
                "manual review needed before client presentation"
            )

    # OOT overfit check (advisory — does not fail the gate, surfaced as a warning)
    oot_warnings = []
    for _, row in fit_metrics.iterrows():
        if row.get("oot_r2") is not None and row.get("r_squared") is not None:
            gap = float(row["r_squared"]) - float(row["oot_r2"])
            if gap > 0.20:
                oot_warnings.append(
                    f"{row['model']} in-sample/OOT R² gap = {gap:.2f} "
                    f"(train {row['r_squared']:.3f} vs OOT {row['oot_r2']:.3f}) — possible overfit"
                )

    if issues:
        reason = "; ".join(issues)
        if oot_warnings:
            reason += "  [OOT advisory: " + "; ".join(oot_warnings) + "]"
        return False, reason, None

    best = fit_metrics.sort_values("mape_pct").iloc[0]
    reason = "All gate checks passed"
    if oot_warnings:
        reason += "  [OOT advisory: " + "; ".join(oot_warnings) + "]"
    return True, reason, str(best["model"])


# ── Symlink promotion ─────────────────────────────────────────────────────────

def promote(model: str) -> None:
    src    = _latest_dir(model)
    target = os.path.join(MODEL_DIRS[model], "accepted")
    if os.path.islink(target):
        os.remove(target)
    os.symlink(src, target)
    print(f"  Promoted {model} → {target}")


# ── Report ────────────────────────────────────────────────────────────────────

def _write_report(
    ts: str,
    outdir: str,
    fit_metrics: pd.DataFrame,
    roi_cmp: pd.DataFrame,
    gate_passed: bool,
    gate_reason: str,
    winner: str | None,
    model_dirs: dict[str, str],
) -> str:
    lines = [
        "# Model Comparison Report",
        "",
        f"**Run:** {ts}",
        "",
        "## Fit Metrics",
        "",
        fit_metrics.to_markdown(index=False),
        "",
        "### Publish gate thresholds",
        f"- R² ≥ {MIN_R2}",
        f"- MAPE ≤ {MAX_MAPE}%",
        f"- ROI divergence ≤ {MAX_ROI_DIVERGENCE*100:.0f}% per channel",
        "",
        "## ROI Comparison (leads per £1k spend)",
        "",
        roi_cmp.to_markdown(index=False) if not roi_cmp.empty else "_No ROI data_",
        "",
        "## Publish Gate",
        "",
        f"**Result:** {'✅ PASSED' if gate_passed else '❌ FAILED'}",
        f"**Reason:** {gate_reason}",
    ]
    if winner:
        accepted_path = os.path.join(MODEL_DIRS[winner], "accepted")
        lines += [
            f"**Winner:** {winner}",
            f"**Promoted to:** `{accepted_path}`",
        ]
    lines += ["", "## Model Run Directories", ""]
    for model, d in model_dirs.items():
        lines.append(f"- **{model}**: `{d}`")

    path = os.path.join(outdir, "comparison_report.md")
    with open(path, "w") as fh:
        fh.write("\n".join(lines))
    return path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Compare models and run publish gate.")
    parser.add_argument(
        "--promote",
        choices=["meridian", "robyn"],
        default=None,
        help="Skip gate and force-promote this model to accepted",
    )
    args = parser.parse_args()

    ts     = datetime.now().strftime("%Y-%m-%d_%H%M")
    outdir = os.path.join(COMPARE_DIR, ts)
    os.makedirs(outdir, exist_ok=True)

    available_models = {}
    for m in MODEL_DIRS:
        base   = MODEL_DIRS[m]
        latest = os.path.join(base, "latest")
        if os.path.islink(latest) and os.path.exists(latest):
            available_models[m] = os.path.realpath(latest)
        else:
            print(f"  [{m}] no outputs found — skipping (run 03_model.py --model {m} to include)")

    if not available_models:
        sys.exit("ERROR: no model outputs found. Run 03_model.py first.")

    model_dirs = available_models
    cards      = {m: _load_card(d)  for m, d in model_dirs.items()}
    roi_tables = {m: _load_roi(d)   for m, d in model_dirs.items()}

    fit_metrics = compare_fit_metrics(cards)
    roi_cmp     = compare_roi(roi_tables)

    print("\nFit metrics:")
    print(fit_metrics.to_string(index=False))
    print("\nROI comparison (leads per £1k spend):")
    print(roi_cmp.to_string(index=False) if not roi_cmp.empty else "  (no data)")

    if args.promote:
        gate_passed = True
        gate_reason = f"Force-promoted via --promote {args.promote}"
        winner      = args.promote
    else:
        gate_passed, gate_reason, winner = run_publish_gate(fit_metrics, roi_cmp)

    print(f"\nPublish gate: {'PASSED' if gate_passed else 'FAILED'}  — {gate_reason}")

    if gate_passed and winner:
        promote(winner)
    else:
        print("  No model promoted. Fix issues then re-run 03_model.py + 04_evaluate.py.")

    fit_metrics.to_csv(os.path.join(outdir, "comparison_metrics.csv"), index=False)
    if not roi_cmp.empty:
        roi_cmp.to_csv(os.path.join(outdir, "roi_comparison.csv"), index=False)

    report_path = _write_report(
        ts, outdir, fit_metrics, roi_cmp,
        gate_passed, gate_reason, winner, model_dirs,
    )

    latest = os.path.join(COMPARE_DIR, "latest")
    if os.path.islink(latest):
        os.remove(latest)
    os.symlink(os.path.abspath(outdir), latest)

    print(f"\nReport → {report_path}")
    sys.exit(0 if gate_passed else 1)


if __name__ == "__main__":
    main()
