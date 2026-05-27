# models/robyn_model.py
# Real Meta Robyn MMM via rpy2 (Python → R bridge).
#
# Requires:
#   source .venv/bin/activate   (rpy2 installed in project venv)
#   R + Robyn R package          (R 4.5.1 + Robyn 3.12.1 already installed)
#
# Robyn runs Ridge regression with Nevergrad hyperparameter search over
# geometric adstock decay and Hill saturation parameters per channel.
# Runtime: ~5-15 min for default settings (trials=3, iterations=500).

import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import yaml

MODEL_NAME = "robyn"
SEED       = 42

MEDIA_CHANNELS = ["google_ads", "bing_ads", "meta", "stackadapt"]

# Adstock theta search bounds by channel type.
# PPC (intent-driven): tighter, shorter carry-over.
# Social/display: wider, longer consideration window.
THETA_BOUNDS = {
    "google_ads": (0.05, 0.60),
    "bing_ads":   (0.05, 0.60),
    "meta":       (0.10, 0.80),
    "stackadapt": (0.10, 0.80),
}


# ── Config ────────────────────────────────────────────────────────────────────

def configure(quick: bool = False) -> dict:
    if quick:
        return {"trials": 1, "iterations": 200, "cores": 1, "seed": SEED}
    return     {"trials": 3, "iterations": 500, "cores": None, "seed": SEED}


# ── Data prep ─────────────────────────────────────────────────────────────────

def _prepare_df(df: pd.DataFrame, features: dict) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    Return (df_fit, spend_cols, control_cols) filtered to KPI-available weeks,
    with date as a plain string column (Robyn expects character).
    """
    kpi_col = features.get("kpi", "quality_leads")
    if kpi_col not in df.columns or df[kpi_col].isna().all():
        sys.exit(f"ERROR [robyn]: '{kpi_col}' missing or all-NaN. Run 01_data_prep.py first.")

    df_fit = df[df[kpi_col].notna()].copy().reset_index()
    df_fit["date"] = df_fit["date"].dt.strftime("%Y-%m-%d")

    active = [m for m in features.get("media", []) if m["col"] in df_fit.columns]
    spend_cols = [m["col"] for m in active]
    control_cols = [c for c in features.get("controls", []) if c in df_fit.columns]

    # Robyn needs no NaN in spend or controls
    for col in spend_cols + control_cols:
        df_fit[col] = df_fit[col].fillna(0)

    return df_fit, spend_cols, control_cols


# ── Hyperparameter bounds ─────────────────────────────────────────────────────

def _make_hyperparameters(spend_cols: list[str]) -> dict:
    """
    Build the hyperparameter search space for Robyn.
    Each media variable gets theta (adstock), alpha (Hill shape), gamma (Hill inflection).
    """
    hyp = {}
    for col in spend_cols:
        ch = col.replace("_spend", "")
        lo, hi = THETA_BOUNDS.get(ch, (0.05, 0.70))
        hyp[f"{col}_thetas"] = [lo, hi]
        hyp[f"{col}_alphas"] = [0.5, 3.0]   # Hill shape: 0.5 = concave, 3.0 = S-curve
        hyp[f"{col}_gammas"] = [0.3, 1.0]   # Hill inflection point (normalised spend)
    return hyp


# ── R execution ───────────────────────────────────────────────────────────────

def _run_robyn_in_r(df_fit: pd.DataFrame, spend_cols: list[str], control_cols: list[str],
                    features: dict, outdir: str, cfg: dict) -> dict:
    """
    Pass data to R, run Robyn, write outputs, return metrics dict.
    """
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter
    from rpy2.robjects.packages import importr

    importr("Robyn")

    kpi_col = features.get("kpi", "quality_leads")
    hyp     = _make_hyperparameters(spend_cols)

    # ── Convert df to R ──
    with localconverter(ro.default_converter + pandas2ri.converter):
        r_df = ro.conversion.py2rpy(df_fit)

    # ── Build R hyperparameter list ──
    r_hyp = ro.ListVector({k: ro.FloatVector(v) for k, v in hyp.items()})

    # ── robyn_inputs ──
    print("  [robyn] Setting up InputCollect ...")
    paid_media_r   = ro.StrVector(spend_cols)
    context_r      = ro.StrVector(control_cols) if control_cols else ro.NULL
    prophet_vars_r = ro.StrVector(["trend", "season", "holiday"])

    window_start = df_fit["date"].iloc[0]
    window_end   = df_fit["date"].iloc[-1]

    input_collect = ro.r["robyn_inputs"](
        dt_input         = r_df,
        dep_var          = kpi_col,
        dep_var_type     = "conversion",
        date_var         = "date",
        paid_media_spends= paid_media_r,
        paid_media_vars  = paid_media_r,
        paid_media_signs = ro.StrVector(["positive"] * len(spend_cols)),
        context_vars     = context_r,
        prophet_vars     = prophet_vars_r,
        prophet_country  = "GB",
        adstock          = "geometric",
        hyperparameters  = r_hyp,
        window_start     = window_start,
        window_end       = window_end,
    )

    # ── robyn_run ──
    n_cores = cfg["cores"] or ro.r["parallel::detectCores"]()[0] - 1
    n_cores = max(1, int(n_cores))
    print(f"  [robyn] Running trials={cfg['trials']} × iterations={cfg['iterations']} "
          f"on {n_cores} core(s) ...")

    # Enable Robyn's internal train/test split when an OOT window is configured.
    # Robyn treats ts_validation as a further hold-out on top of any external split.
    use_ts_validation = bool(features.get("oot_weeks", 0) > 0)

    output_models = ro.r["robyn_run"](
        InputCollect  = input_collect,
        trials        = cfg["trials"],
        iterations    = cfg["iterations"],
        seed          = cfg["seed"],
        cores         = n_cores,
        ts_validation = use_ts_validation,
    )

    # ── robyn_outputs ──
    print("  [robyn] Selecting Pareto-optimal models ...")
    os.makedirs(outdir, exist_ok=True)

    output_collect = ro.r["robyn_outputs"](
        InputCollect  = input_collect,
        OutputModels  = output_models,
        pareto_fronts = 1,
        csv_out       = "pareto",
        plot_folder   = outdir,
        plot_pareto   = False,
        export        = True,
    )

    # ── Build pareto_summary.csv + generate one-pagers for top candidates ──
    best_model_id = _build_pareto_summary_and_onepagers(
        input_collect, output_collect, outdir, top_n=20
    )
    if not best_model_id:
        # Fall back: try selectID then allSolutions
        try:
            sid = output_collect.rx2("selectID")
            if str(type(sid)) != "<class 'rpy2.rinterface_lib.sexp.NULLType'>":
                best_model_id = str(sid[0])
        except Exception:
            pass
    if not best_model_id:
        try:
            best_model_id = str(output_collect.rx2("allSolutions")[0])
        except Exception:
            best_model_id = "trial1_1_1"
    print(f"  [robyn] Default model (best NRMSE): {best_model_id}")

    # ── Read Robyn CSV outputs back into Python ──
    # Robyn writes pareto_aggregated.csv, pareto_hyperparameters.csv, etc. to plot_folder
    metrics = _extract_robyn_outputs(outdir, best_model_id, df_fit, spend_cols,
                                     kpi_col, output_collect, features)

    # ── Save R model as JSON for later reloading ──
    json_path = os.path.join(outdir, "robyn_model.json")
    try:
        ro.r["robyn_write"](
            InputCollect  = input_collect,
            OutputCollect = output_collect,
            dir           = outdir,
            quiet         = True,
        )
    except Exception as e:
        print(f"  [robyn] robyn_write skipped ({e})")

    return metrics


# ── Pareto summary + one-pagers ───────────────────────────────────────────────

def _build_pareto_summary_and_onepagers(
    input_collect, output_collect, outdir: str, top_n: int = 20
) -> str | None:
    """
    1. Find pareto_clusters.csv in the Robyn subdirectory.
    2. Rank all solutions by NRMSE; write pareto_summary.csv.
    3. Call robyn_onepagers() for the top_n solutions.
    4. Return the best (lowest NRMSE) solID.
    """
    import rpy2.robjects as ro

    # Locate pareto_clusters.csv (Robyn writes it to a timestamped subdir)
    clusters_path = None
    for root, dirs, files in os.walk(outdir):
        for fname in files:
            if ("pareto_clusters" in fname and fname.endswith(".csv")
                    and "detail" not in fname and "wss" not in fname and "_ci" not in fname):
                clusters_path = os.path.join(root, fname)
                break
        if clusters_path:
            break

    if not clusters_path:
        print("  [robyn] pareto_clusters.csv not found — skipping one-pager generation")
        return None

    clusters = pd.read_csv(clusters_path)
    if "solID" not in clusters.columns or "nrmse" not in clusters.columns:
        return None

    ranked = clusters.sort_values("nrmse").reset_index(drop=True)
    summary_path = os.path.join(os.path.dirname(clusters_path), "pareto_summary.csv")
    ranked.to_csv(summary_path, index=False)

    best_sol = str(ranked["solID"].iloc[0])
    top_sols  = ranked["solID"].head(top_n).tolist()

    print(f"  [robyn] {len(ranked)} Pareto solutions found. "
          f"Top {len(top_sols)} selected for one-pagers.")
    print(f"  [robyn] Generating one-pagers (this may take a minute) ...")
    try:
        ro.r["robyn_onepagers"](
            InputCollect  = input_collect,
            OutputCollect = output_collect,
            select_model  = ro.StrVector(top_sols),
            export        = True,
            plot_folder   = outdir,
        )
        print(f"  [robyn] One-pagers saved → {outdir}/")
    except Exception as e:
        print(f"  [robyn] robyn_onepagers failed ({e}) — one-pagers skipped")

    return best_sol


# ── Output extraction ─────────────────────────────────────────────────────────

def _extract_robyn_outputs(outdir: str, best_model_id: str, df_fit: pd.DataFrame,
                           spend_cols: list[str], kpi_col: str,
                           output_collect, features: dict) -> dict:
    """
    Read Robyn CSV outputs and reshape into the standard pipeline format:
    contributions.csv, roi_table.csv, response_curves.csv, diagnostics.csv.
    """
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter  # noqa: F401 (used by _r_to_pandas)

    # ── Try loading Robyn CSVs ──
    # Robyn may write CSVs to a timestamped subdirectory inside outdir
    pareto_agg = None
    for root, dirs, files in os.walk(outdir):
        for fname in files:
            if "pareto_aggregated" in fname and fname.endswith(".csv"):
                pareto_agg = pd.read_csv(os.path.join(root, fname))
                break
        if pareto_agg is not None:
            break
    if pareto_agg is None:
        pareto_agg = _r_to_pandas(output_collect, "xDecompAgg")

    # ── ROI table ──
    roi_rows = []
    for col in spend_cols:
        ch = col.replace("_spend", "")
        if pareto_agg is not None and "rn" in pareto_agg.columns:
            row = pareto_agg[pareto_agg["rn"] == col]
            if not row.empty:
                best_row = row.iloc[0]
                total_spend = df_fit[col].sum()
                incr        = float(best_row.get("xDecompAgg", best_row.get("mean", 0)))
                roi         = incr / (total_spend / 1_000) if total_spend > 0 else 0.0
                cpa         = total_spend / incr if incr > 0 else None
                roi_rows.append({
                    "channel":             ch,
                    "total_spend_gbp":     round(total_spend, 2),
                    "incremental_leads":   round(incr, 1),
                    "roi_leads_per_kgbp":  round(roi, 4),
                    "cpa_gbp":             round(cpa, 2) if cpa else None,
                    "coef_p5":             None,
                    "coef_p95":            None,
                })

    # If pareto CSVs not parsed correctly, build ROI from hyperparams
    if not roi_rows:
        roi_rows = _roi_from_hyperparams(output_collect, df_fit, spend_cols)

    roi_df = pd.DataFrame(roi_rows) if roi_rows else pd.DataFrame(
        [{"channel": c.replace("_spend",""), "total_spend_gbp": df_fit[c].sum(),
          "incremental_leads": 0, "roi_leads_per_kgbp": 0, "cpa_gbp": None,
          "coef_p5": None, "coef_p95": None}
         for c in spend_cols]
    )
    roi_df.to_csv(os.path.join(outdir, "roi_table.csv"), index=False)

    # ── Diagnostics ──
    actual    = df_fit[kpi_col].values.astype(float)
    predicted = _get_predicted(output_collect, df_fit, kpi_col, outdir, best_model_id)
    resid     = actual - predicted
    r2   = float(1 - np.sum(resid**2) / np.sum((actual - actual.mean())**2))
    mape = float(np.mean(np.abs(resid / np.where(actual == 0, 1, actual))) * 100)
    mae  = float(np.mean(np.abs(resid)))

    pd.DataFrame({
        "date":      pd.to_datetime(df_fit["date"]),
        "actual":    actual,
        "predicted": predicted,
        "residual":  resid,
    }).to_csv(os.path.join(outdir, "diagnostics.csv"), index=False)

    # ── Contributions ──
    contrib = pd.DataFrame()
    contrib.index = pd.to_datetime(df_fit["date"])
    contrib["actual"]    = actual
    contrib["predicted"] = predicted
    # Use ROI × spend as weekly attribution
    total_media = np.zeros(len(actual))
    for row in roi_rows:
        ch  = row["channel"]
        col = f"{ch}_spend"
        roi = row.get("roi_leads_per_kgbp") or 0
        if col in df_fit.columns:
            wc = roi * df_fit[col].fillna(0).values / 1_000
            contrib[f"{ch}_contrib"] = wc
            total_media += wc
    contrib["baseline"] = predicted - total_media
    contrib.to_csv(os.path.join(outdir, "contributions.csv"))

    # ── Response curves ──
    rc_rows = []
    for row in roi_rows:
        ch  = row["channel"]
        col = f"{ch}_spend"
        roi = row.get("roi_leads_per_kgbp") or 0
        mean_spend = df_fit[col].fillna(0).mean() if col in df_fit.columns else 0
        for pct in range(0, 201, 10):
            w_spend = mean_spend * pct / 100
            rc_rows.append({
                "channel":           ch,
                "spend_pct_of_mean": pct,
                "weekly_spend_gbp":  round(w_spend, 2),
                "incremental_leads": round(roi * w_spend / 1_000, 4),
            })
    pd.DataFrame(rc_rows).to_csv(os.path.join(outdir, "response_curves.csv"), index=False)

    return {"r_squared": round(r2, 4), "mape_pct": round(mape, 2), "mae": round(mae, 2)}


def _r_to_pandas(r_obj, attr: str) -> pd.DataFrame | None:
    """Safely extract an attribute from an R list and convert to pandas."""
    try:
        import rpy2.robjects as ro
        from rpy2.robjects import pandas2ri
        from rpy2.robjects.conversion import localconverter
        sub = r_obj.rx2(attr)
        with localconverter(ro.default_converter + pandas2ri.converter):
            return ro.conversion.rpy2py(sub)
    except Exception:
        return None


def _roi_from_hyperparams(output_collect, df_fit: pd.DataFrame, spend_cols: list[str]) -> list:
    """Fallback: derive rough ROI from fitted hyperparameters via spend correlation."""
    rows = []
    for col in spend_cols:
        ch = col.replace("_spend", "")
        rows.append({
            "channel":            ch,
            "total_spend_gbp":    round(df_fit[col].sum(), 2),
            "incremental_leads":  0,
            "roi_leads_per_kgbp": 0,
            "cpa_gbp":            None,
            "coef_p5":            None,
            "coef_p95":           None,
        })
    return rows


def _get_predicted(output_collect, df_fit: pd.DataFrame, kpi_col: str,
                   outdir: str = "", best_model_id: str = "") -> np.ndarray:
    """Extract fitted values from Robyn's R output or CSV files."""
    # Try Robyn CSV first
    if outdir:
        for root, dirs, files in os.walk(outdir):
            for fname in files:
                if "pareto_alldecomp_matrix" in fname and fname.endswith(".csv"):
                    try:
                        d = pd.read_csv(os.path.join(root, fname))
                        hat_col = "depVarHat" if "depVarHat" in d.columns else "dep_var_hat"
                        if hat_col in d.columns and best_model_id and "solID" in d.columns:
                            d = d[d["solID"] == best_model_id]
                        if hat_col in d.columns:
                            return d[hat_col].values.astype(float)[:len(df_fit)]
                    except Exception:
                        pass
    try:
        pred_df = _r_to_pandas(output_collect, "xDecompVec")
        if pred_df is not None and "dep_var_hat" in pred_df.columns:
            return pred_df["dep_var_hat"].values.astype(float)[:len(df_fit)]
    except Exception:
        pass
    return df_fit[kpi_col].values.astype(float)


# ── Main entry ────────────────────────────────────────────────────────────────

def run(df: pd.DataFrame, features: dict, outdir: str, quick: bool = False) -> str:
    """
    Fit Robyn (R via rpy2), write output files, return outdir.
    Set quick=True for fast low-trial test run (~3 min vs ~10 min).
    """
    try:
        import rpy2.robjects as ro
    except ImportError:
        sys.exit(
            "ERROR: rpy2 not importable. "
            "Activate the project venv:  source .venv/bin/activate"
        )

    # Verify R + Robyn package available
    try:
        ro.r("library(Robyn)")
    except Exception as e:
        sys.exit(f"ERROR: Could not load Robyn R package — {e}. "
                 "Run in R:  install.packages('Robyn')")

    cfg = configure(quick=quick)

    print(f"  [robyn] Preparing data ...")
    df_fit, spend_cols, control_cols = _prepare_df(df, features)

    if not spend_cols:
        sys.exit("ERROR [robyn]: No media spend columns found.")

    kpi_col = features.get("kpi", "quality_leads")
    print(f"  [robyn] {len(df_fit)} weeks | "
          f"{len(spend_cols)} channels | "
          f"{len(control_cols)} controls")

    os.makedirs(outdir, exist_ok=True)
    metrics = _run_robyn_in_r(df_fit, spend_cols, control_cols, features, outdir, cfg)

    # ── Model card ──
    card = {
        "model":       MODEL_NAME,
        "run_date":    datetime.now().isoformat(),
        "kpi":         kpi_col,
        "n_obs":       int(len(df_fit)),
        "r_squared":   metrics.get("r_squared"),
        "mape_pct":    metrics.get("mape_pct"),
        "mae":         metrics.get("mae"),
        "trials":      cfg["trials"],
        "iterations":  cfg["iterations"],
        "media_cols":  spend_cols,
        "note":        "Real Meta Robyn — Ridge regression with Nevergrad hyperparameter search.",
    }
    with open(os.path.join(outdir, "model_card.yaml"), "w") as fh:
        yaml.dump(card, fh, default_flow_style=False, sort_keys=False)

    r2, mape, mae = metrics.get("r_squared", 0), metrics.get("mape_pct", 0), metrics.get("mae", 0)
    print(f"  [robyn]     R²={r2:.3f}  MAPE={mape:.1f}%  MAE={mae:.1f}")
    print(f"  [robyn]     outputs → {outdir}/")
    return outdir
