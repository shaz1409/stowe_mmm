"""
03b_robyn_select.py  —  Robyn model selection after 03_model.py --model robyn.

Steps:
  1. Prints ranked Pareto candidates (NRMSE order) from pareto_summary.csv
  2. Lists one-pager PNG paths for visual review
  3. Accepts --sol-id or prompts interactively
  4. Re-extracts standard pipeline outputs (roi_table, contributions, diagnostics)
     for the chosen solution and updates outputs/robyn/latest/
  5. Writes config/robyn_selection.yaml

Usage:
  python pipeline/03b_robyn_select.py
  python pipeline/03b_robyn_select.py --sol-id 1_132_1
  python pipeline/03b_robyn_select.py --robyn-dir outputs/robyn/2026-05-27_1200/
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROBYN_LATEST = os.path.join(ROOT, "outputs", "robyn", "latest")
SELECTION_YAML = os.path.join(ROOT, "config", "robyn_selection.yaml")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_csv(base_dir: str, pattern: str, exclude: list[str] | None = None) -> str | None:
    exclude = exclude or []
    for root, dirs, files in os.walk(base_dir):
        for fname in files:
            if pattern in fname and fname.endswith(".csv"):
                if not any(ex in fname for ex in exclude):
                    return os.path.join(root, fname)
    return None


def _load_pareto_summary(robyn_dir: str) -> pd.DataFrame | None:
    path = _find_csv(robyn_dir, "pareto_summary")
    if path is None:
        path = _find_csv(robyn_dir, "pareto_clusters",
                         exclude=["detail", "wss", "_ci"])
    if path is None:
        return None
    try:
        df = pd.read_csv(path)
        if "solID" in df.columns and "nrmse" in df.columns:
            return df.sort_values("nrmse").reset_index(drop=True)
    except Exception:
        pass
    return None


def _show_candidates(summary: pd.DataFrame, top_n: int = 20) -> None:
    display_cols = ["solID", "nrmse", "decomp.rssd", "mape", "cluster", "top_sol"]
    cols = [c for c in display_cols if c in summary.columns]
    top = summary.head(top_n)[cols]
    width = 60
    print(f"\n{'=' * width}")
    print(f"Top {len(top)} Robyn Pareto solutions  (sorted by NRMSE ↑ = better fit)")
    print(f"{'=' * width}")
    print(top.to_string(index=True))
    print(f"{'=' * width}\n")


def _list_onepagers(robyn_dir: str, sol_ids: list[str]) -> list[str]:
    found = []
    for root, dirs, files in os.walk(robyn_dir):
        for fname in files:
            if fname.endswith(".png"):
                stem = fname.replace(".png", "")
                if stem in sol_ids:
                    found.append(os.path.join(root, fname))
    return sorted(found)


# ── Re-extraction ─────────────────────────────────────────────────────────────

def _reextract(robyn_dir: str, sol_id: str) -> None:
    """
    Re-derive roi_table.csv, contributions.csv, diagnostics.csv, response_curves.csv
    and model_card.yaml for the chosen solID, writing to robyn_dir (= outputs/robyn/latest/).
    """
    card_path = os.path.join(robyn_dir, "model_card.yaml")
    if not os.path.exists(card_path):
        print("  [select] WARNING: model_card.yaml not found — cannot re-extract")
        return

    with open(card_path) as f:
        card = yaml.safe_load(f)

    spend_cols = card.get("media_cols", [])
    kpi_col    = card.get("kpi", "quality_leads")

    # ── Raw data ──
    raw_path = _find_csv(robyn_dir, "raw_data")
    if raw_path is None:
        print("  [select] WARNING: raw_data.csv not found — skipping re-extraction")
        return
    raw = pd.read_csv(raw_path)

    # ── Pareto aggregated ──
    agg_path = _find_csv(robyn_dir, "pareto_aggregated")
    if agg_path is None:
        print("  [select] WARNING: pareto_aggregated.csv not found")
        return
    pareto_agg = pd.read_csv(agg_path)
    sol_rows   = pareto_agg[pareto_agg["solID"] == sol_id]
    if sol_rows.empty:
        print(f"  [select] ERROR: solID '{sol_id}' not found in pareto_aggregated.csv")
        sys.exit(1)

    # ── ROI table ──
    roi_rows = []
    for col in spend_cols:
        ch = col.replace("_spend", "")
        media_row = sol_rows[sol_rows["rn"] == col]
        if media_row.empty:
            continue
        r = media_row.iloc[0]
        total_spend = float(r.get("total_spend", raw[col].sum() if col in raw.columns else 0))
        incr = float(r.get("xDecompAgg", 0))
        roi  = incr / (total_spend / 1_000) if total_spend > 0 else 0.0
        cpa  = total_spend / incr if incr > 0 else None
        roi_rows.append({
            "channel":            ch,
            "total_spend_gbp":    round(total_spend, 2),
            "incremental_leads":  round(incr, 1),
            "roi_leads_per_kgbp": round(roi, 4),
            "cpa_gbp":            round(cpa, 2) if cpa else None,
            "coef_p5":            round(float(r.get("ci_low", 0) or 0), 6),
            "coef_p95":           round(float(r.get("ci_up",  0) or 0), 6),
        })

    if roi_rows:
        pd.DataFrame(roi_rows).to_csv(os.path.join(robyn_dir, "roi_table.csv"), index=False)
        print(f"  [select] roi_table.csv updated")

    # ── Predicted values from alldecomp_matrix ──
    decomp_path = _find_csv(robyn_dir, "pareto_alldecomp_matrix")
    predicted = None
    if decomp_path:
        try:
            decomp = pd.read_csv(decomp_path)
            hat_col = "depVarHat" if "depVarHat" in decomp.columns else "dep_var_hat"
            if hat_col in decomp.columns and "solID" in decomp.columns:
                sol_decomp = decomp[decomp["solID"] == sol_id]
                if not sol_decomp.empty:
                    predicted = sol_decomp[hat_col].values.astype(float)
        except Exception as e:
            print(f"  [select] WARNING: could not read alldecomp_matrix ({e})")

    actual = raw[kpi_col].values.astype(float) if kpi_col in raw.columns else None

    if actual is not None and predicted is not None:
        n = min(len(actual), len(predicted))
        actual_t, predicted_t = actual[:n], predicted[:n]
        resid = actual_t - predicted_t
        r2   = float(1 - np.sum(resid**2) / np.sum((actual_t - actual_t.mean())**2))
        mape = float(np.mean(np.abs(resid / np.where(actual_t == 0, 1, actual_t))) * 100)
        mae  = float(np.mean(np.abs(resid)))

        date_col = raw["date"] if "date" in raw.columns else pd.RangeIndex(n)
        pd.DataFrame({
            "date":      date_col.values[:n],
            "actual":    actual_t,
            "predicted": predicted_t,
            "residual":  resid,
        }).to_csv(os.path.join(robyn_dir, "diagnostics.csv"), index=False)
        print(f"  [select] diagnostics.csv updated — R²={r2:.3f}  MAPE={mape:.1f}%")

        # Update contributions
        contrib = pd.DataFrame()
        contrib.index = pd.to_datetime(date_col.values[:n]) if "date" in raw.columns else pd.RangeIndex(n)
        contrib["actual"]    = actual_t
        contrib["predicted"] = predicted_t
        total_media = np.zeros(n)
        for row in roi_rows:
            ch  = row["channel"]
            col = f"{ch}_spend"
            roi = row.get("roi_leads_per_kgbp") or 0
            if col in raw.columns:
                wc = roi * raw[col].fillna(0).values[:n] / 1_000
                contrib[f"{ch}_contrib"] = wc
                total_media += wc
        contrib["baseline"] = predicted_t - total_media
        contrib.to_csv(os.path.join(robyn_dir, "contributions.csv"))
        print(f"  [select] contributions.csv updated")

        # Response curves (linear approx from xDecompAgg × spend)
        rc_rows = []
        for row in roi_rows:
            ch  = row["channel"]
            col = f"{ch}_spend"
            roi = row.get("roi_leads_per_kgbp") or 0
            mean_spend = raw[col].fillna(0).mean() if col in raw.columns else 0
            for pct in range(0, 201, 10):
                w = mean_spend * pct / 100
                rc_rows.append({
                    "channel":           ch,
                    "spend_pct_of_mean": pct,
                    "weekly_spend_gbp":  round(w, 2),
                    "incremental_leads": round(roi * w / 1_000, 4),
                })
        pd.DataFrame(rc_rows).to_csv(os.path.join(robyn_dir, "response_curves.csv"), index=False)
        print(f"  [select] response_curves.csv updated")

        # Update model card
        card["r_squared"]        = round(r2, 4)
        card["mape_pct"]         = round(mape, 2)
        card["mae"]              = round(mae, 2)
        card["selected_model_id"] = sol_id
        with open(card_path, "w") as f:
            yaml.dump(card, f, default_flow_style=False, sort_keys=False)
        print(f"  [select] model_card.yaml updated")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Select a Robyn Pareto solution and re-extract pipeline outputs"
    )
    ap.add_argument("--robyn-dir", default=ROBYN_LATEST,
                    help="Path to Robyn output directory (default: outputs/robyn/latest)")
    ap.add_argument("--sol-id", default=None,
                    help="Solution ID to select (skips interactive prompt)")
    ap.add_argument("--top-n", type=int, default=20,
                    help="Number of candidates to display (default: 20)")
    args = ap.parse_args()

    robyn_dir = args.robyn_dir
    if not os.path.isdir(robyn_dir):
        sys.exit(
            f"ERROR: Robyn output directory not found: {robyn_dir}\n"
            "Run pipeline/03_model.py --model robyn first."
        )

    summary = _load_pareto_summary(robyn_dir)
    if summary is None:
        sys.exit(
            "ERROR: No pareto_summary.csv or pareto_clusters.csv found.\n"
            "Re-run pipeline/03_model.py --model robyn to regenerate."
        )

    _show_candidates(summary, top_n=args.top_n)

    # One-pager locations
    sol_ids  = summary["solID"].head(args.top_n).tolist()
    onepagers = _list_onepagers(robyn_dir, sol_ids)
    if onepagers:
        print(f"One-pager PNGs ({len(onepagers)} found — open to compare):")
        for p in onepagers:
            print(f"  {p}")
    else:
        print("  No one-pager PNGs found in this run directory.")
        print("  (They are generated during robyn_outputs — re-run 03_model.py to create them)")
    print()

    # Get solID
    sol_id = args.sol_id
    if not sol_id:
        valid = set(summary["solID"].tolist())
        while True:
            sol_id = input("Enter solID to select (or 'q' to quit): ").strip()
            if sol_id.lower() == "q":
                sys.exit("Aborted.")
            if sol_id in valid:
                break
            print(f"  '{sol_id}' not found. Options: {sorted(valid)[:8]} ...")

    print(f"\n  Selecting {sol_id} ...")

    # Save selection config
    os.makedirs(os.path.dirname(SELECTION_YAML), exist_ok=True)
    with open(SELECTION_YAML, "w") as f:
        yaml.dump(
            {"selected_model_id": sol_id, "robyn_dir": robyn_dir},
            f, default_flow_style=False
        )
    print(f"  Saved → {SELECTION_YAML}")

    # Re-extract pipeline outputs for chosen model
    _reextract(robyn_dir, sol_id)

    print(f"\nDone. Model {sol_id} outputs written to {robyn_dir}/")
    print("Next step:  python pipeline/04_evaluate.py")


if __name__ == "__main__":
    main()
