# scripts/plot_model_outputs.py
# Generate response curve, marginal ROI, and marginal CPA plots from model outputs.
#
# Usage:
#   python scripts/plot_model_outputs.py                  # uses outputs/meridian/accepted
#   python scripts/plot_model_outputs.py --model robyn    # uses outputs/robyn/accepted
#   python scripts/plot_model_outputs.py --dir outputs/meridian/2026-05-27_1221
#
# Writes PNGs to outputs/visualise/{YYYY-MM-DD_HHMM}/

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ── Style ─────────────────────────────────────────────────────────────────────

CHANNEL_COLORS = {
    "google_ads":  "#4285F4",
    "bing_ads":    "#00B2FF",
    "meta":        "#1877F2",
    "stackadapt":  "#FF6B35",
}
DEFAULT_COLOR = "#888888"

CHANNEL_LABELS = {
    "google_ads":  "Google Ads",
    "bing_ads":    "Bing Ads",
    "meta":        "Meta",
    "stackadapt":  "StackAdapt",
}

plt.rcParams.update({
    "font.family":       "sans-serif",
    "font.size":         11,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.grid":         True,
    "grid.alpha":        0.3,
    "grid.linestyle":    "--",
    "figure.dpi":        150,
})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _color(ch: str) -> str:
    return CHANNEL_COLORS.get(ch, DEFAULT_COLOR)


def _label(ch: str) -> str:
    return CHANNEL_LABELS.get(ch, ch.replace("_", " ").title())


def _gbp(x, _pos=None):
    if x >= 1_000:
        return f"£{x/1_000:.0f}k"
    return f"£{x:.0f}"


def _load(model_dir: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    rc  = pd.read_csv(os.path.join(model_dir, "response_curves.csv"))
    roi = pd.read_csv(os.path.join(model_dir, "roi_table.csv"))
    try:
        import yaml
        with open(os.path.join(model_dir, "model_card.yaml")) as f:
            card = yaml.safe_load(f)
    except Exception:
        card = {}

    # Meridian response_curves() returns cumulative leads over the full modeled
    # period, not weekly leads. Normalise by n_obs (weeks) so the y-axis becomes
    # "average weekly incremental leads at this spend level", which is consistent
    # with the roi_table ROI figures (leads per £1k weekly spend).
    n_obs = card.get("n_obs", None)
    if n_obs is None:
        try:
            diag  = pd.read_csv(os.path.join(model_dir, "diagnostics.csv"))
            n_obs = len(diag)
        except Exception:
            n_obs = 1
    for col in ["incremental_leads", "ci_lo_90", "ci_hi_90"]:
        if col in rc.columns:
            rc[col] = rc[col] / n_obs

    return rc, roi, card


# ── Plot 1: Response curves (all channels, 2×2 grid) ─────────────────────────

def plot_response_curves(rc: pd.DataFrame, roi: pd.DataFrame, outdir: str) -> str:
    channels = rc["channel"].unique()
    n = len(channels)
    ncols = 2
    nrows = (n + 1) // 2

    fig, axes = plt.subplots(nrows, ncols, figsize=(14, 5 * nrows))
    axes = np.array(axes).flatten()

    roi_lookup = roi.set_index("channel")["roi_leads_per_kgbp"].to_dict()

    for ax, ch in zip(axes, channels):
        df = rc[rc["channel"] == ch].sort_values("weekly_spend_gbp")
        color = _color(ch)

        ax.plot(df["weekly_spend_gbp"], df["incremental_leads"],
                color=color, linewidth=2.5, label=_label(ch))

        # CI band if available
        if "ci_lo_90" in df.columns and df["ci_lo_90"].notna().any():
            ax.fill_between(df["weekly_spend_gbp"],
                            df["ci_lo_90"], df["ci_hi_90"],
                            color=color, alpha=0.15, label="90% CI")

        # Mark current mean weekly spend
        mean_spend = df.loc[df["spend_pct_of_mean"] == 100, "weekly_spend_gbp"]
        if not mean_spend.empty:
            sx = float(mean_spend.iloc[0])
            sy = float(df.loc[df["spend_pct_of_mean"] == 100, "incremental_leads"].iloc[0])
            ax.axvline(sx, color=color, linestyle=":", linewidth=1.2, alpha=0.7)
            ax.scatter([sx], [sy], color=color, zorder=5, s=60)
            ax.annotate("current\nspend", xy=(sx, sy),
                        xytext=(8, -20), textcoords="offset points",
                        fontsize=9, color=color)

        ax.set_title(_label(ch), fontweight="bold", pad=8)
        ax.set_xlabel("Weekly spend")
        ax.set_ylabel("Incremental quality leads (weekly avg)")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(_gbp))
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        if "ci_lo_90" in df.columns and df["ci_lo_90"].notna().any():
            ax.legend(fontsize=9)

    # Hide unused axes
    for ax in axes[n:]:
        ax.set_visible(False)

    fig.suptitle("Response Curves — Incremental Quality Leads vs Weekly Spend",
                 fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()

    path = os.path.join(outdir, "response_curves.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


# ── Plot 2: Marginal ROI curves ───────────────────────────────────────────────

def plot_marginal_roi(rc: pd.DataFrame, roi: pd.DataFrame, outdir: str) -> str:
    channels = rc["channel"].unique()
    n = len(channels)
    ncols = 2
    nrows = (n + 1) // 2

    fig, axes = plt.subplots(nrows, ncols, figsize=(14, 5 * nrows))
    axes = np.array(axes).flatten()

    for ax, ch in zip(axes, channels):
        df = rc[rc["channel"] == ch].sort_values("weekly_spend_gbp").copy()
        df = df[df["weekly_spend_gbp"] > 0]   # exclude zero-spend point
        color = _color(ch)

        # Numerical derivative: marginal leads per £ → scale to per £1k
        spend  = df["weekly_spend_gbp"].values
        leads  = df["incremental_leads"].values
        d_leads = np.gradient(leads, spend)
        marginal_roi = d_leads * 1_000          # leads per £1k marginal spend

        ax.plot(spend, marginal_roi, color=color, linewidth=2.5)
        ax.axhline(0, color="black", linewidth=0.8)

        # CI band on marginal ROI (propagate from CI if available)
        if "ci_lo_90" in df.columns and df["ci_lo_90"].notna().any():
            d_lo = np.gradient(df["ci_lo_90"].values, spend) * 1_000
            d_hi = np.gradient(df["ci_hi_90"].values, spend) * 1_000
            ax.fill_between(spend, d_lo, d_hi, color=color, alpha=0.15)

        # Current spend marker
        mean_spend = df.loc[df["spend_pct_of_mean"] == 100, "weekly_spend_gbp"]
        if not mean_spend.empty:
            sx = float(mean_spend.iloc[0])
            idx = np.searchsorted(spend, sx)
            idx = min(idx, len(marginal_roi) - 1)
            sy  = marginal_roi[idx]
            ax.axvline(sx, color=color, linestyle=":", linewidth=1.2, alpha=0.7)
            ax.scatter([sx], [sy], color=color, zorder=5, s=60)
            ax.annotate(f"{sy:.2f} leads/£1k\nat current spend",
                        xy=(sx, sy), xytext=(8, 6), textcoords="offset points",
                        fontsize=9, color=color)

        ax.set_title(_label(ch), fontweight="bold", pad=8)
        ax.set_xlabel("Weekly spend")
        ax.set_ylabel("Marginal ROI (weekly leads per £1k)")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(_gbp))

    for ax in axes[n:]:
        ax.set_visible(False)

    fig.suptitle("Marginal ROI — Additional Quality Leads per £1k Extra Spend",
                 fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()

    path = os.path.join(outdir, "marginal_roi.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


# ── Plot 3: Marginal CPA curves ───────────────────────────────────────────────

def plot_marginal_cpa(rc: pd.DataFrame, roi: pd.DataFrame, outdir: str) -> str:
    channels = rc["channel"].unique()
    n = len(channels)
    ncols = 2
    nrows = (n + 1) // 2

    fig, axes = plt.subplots(nrows, ncols, figsize=(14, 5 * nrows))
    axes = np.array(axes).flatten()

    for ax, ch in zip(axes, channels):
        df = rc[rc["channel"] == ch].sort_values("weekly_spend_gbp").copy()
        df = df[df["weekly_spend_gbp"] > 0]
        color = _color(ch)

        spend  = df["weekly_spend_gbp"].values
        leads  = df["incremental_leads"].values
        d_leads = np.gradient(leads, spend)

        # Marginal CPA = £ per marginal lead; clip extreme values for readability
        with np.errstate(divide="ignore", invalid="ignore"):
            marginal_cpa = np.where(d_leads > 1e-9, 1.0 / d_leads, np.nan)

        p95 = np.nanpercentile(marginal_cpa, 95)
        marginal_cpa = np.clip(marginal_cpa, 0, p95 * 1.5)   # trim outliers

        ax.plot(spend, marginal_cpa, color=color, linewidth=2.5)

        mean_spend = df.loc[df["spend_pct_of_mean"] == 100, "weekly_spend_gbp"]
        if not mean_spend.empty:
            sx = float(mean_spend.iloc[0])
            idx = min(np.searchsorted(spend, sx), len(marginal_cpa) - 1)
            sy  = marginal_cpa[idx]
            if np.isfinite(sy):
                ax.axvline(sx, color=color, linestyle=":", linewidth=1.2, alpha=0.7)
                ax.scatter([sx], [sy], color=color, zorder=5, s=60)
                ax.annotate(f"£{sy:,.0f}/lead\nat current spend",
                            xy=(sx, sy), xytext=(8, 6), textcoords="offset points",
                            fontsize=9, color=color)

        ax.set_title(_label(ch), fontweight="bold", pad=8)
        ax.set_xlabel("Weekly spend")
        ax.set_ylabel("Marginal CPA (£ per additional weekly lead)")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(_gbp))
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"£{x:,.0f}"))

    for ax in axes[n:]:
        ax.set_visible(False)

    fig.suptitle("Marginal CPA — Cost of Each Additional Quality Lead",
                 fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()

    path = os.path.join(outdir, "marginal_cpa.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


# ── Plot 4: ROI summary bar chart ─────────────────────────────────────────────

def plot_roi_summary(roi: pd.DataFrame, outdir: str) -> str:
    roi = roi.copy().sort_values("roi_leads_per_kgbp", ascending=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    colors = [_color(ch) for ch in roi["channel"]]
    labels = [_label(ch) for ch in roi["channel"]]

    # ROI bar
    bars = ax1.barh(labels, roi["roi_leads_per_kgbp"], color=colors, height=0.55)
    for bar, val in zip(bars, roi["roi_leads_per_kgbp"]):
        ax1.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                 f"{val:.2f}", va="center", fontsize=10)

    # CI whiskers if available
    if "coef_p5" in roi.columns and roi["coef_p5"].notna().any():
        ci_lo = roi["coef_p5"].values  * 1_000
        ci_hi = roi["coef_p95"].values * 1_000
        means = roi["roi_leads_per_kgbp"].values
        ax1.errorbar(means, range(len(means)),
                     xerr=[means - ci_lo, ci_hi - means],
                     fmt="none", color="black", capsize=4, linewidth=1.5)

    ax1.set_xlabel("Leads per £1k spend (posterior mean)")
    ax1.set_title("Average ROI by Channel", fontweight="bold")

    # CPA bar
    cpa = roi["cpa_gbp"].dropna()
    cpa_labels = [_label(ch) for ch in roi.loc[roi["cpa_gbp"].notna(), "channel"]]
    cpa_colors = [_color(ch) for ch in roi.loc[roi["cpa_gbp"].notna(), "channel"]]
    cpa_sorted = list(zip(cpa_labels, cpa.values, cpa_colors))
    cpa_sorted.sort(key=lambda x: x[1], reverse=True)

    c_labels, c_vals, c_colors = zip(*cpa_sorted) if cpa_sorted else ([], [], [])
    bars2 = ax2.barh(list(c_labels), list(c_vals), color=list(c_colors), height=0.55)
    for bar, val in zip(bars2, c_vals):
        ax2.text(bar.get_width() + 50, bar.get_y() + bar.get_height() / 2,
                 f"£{val:,.0f}", va="center", fontsize=10)

    ax2.set_xlabel("Average CPA (£ per quality lead)")
    ax2.set_title("Average CPA by Channel", fontweight="bold")
    ax2.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"£{x:,.0f}"))

    fig.suptitle("Channel ROI & CPA Summary", fontsize=14, fontweight="bold")
    fig.tight_layout()

    path = os.path.join(outdir, "roi_cpa_summary.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Plot MMM model outputs.")
    parser.add_argument("--model", default="meridian", choices=["meridian", "robyn"],
                        help="Which model's accepted outputs to plot (default: meridian)")
    parser.add_argument("--dir", default=None,
                        help="Override with a specific output directory path")
    args = parser.parse_args()

    if args.dir:
        model_dir = args.dir
    else:
        accepted = os.path.join("outputs", args.model, "accepted")
        latest   = os.path.join("outputs", args.model, "latest")
        if os.path.exists(accepted):
            model_dir = os.path.realpath(accepted)
        elif os.path.exists(latest):
            print(f"  [warn] No accepted model — falling back to latest")
            model_dir = os.path.realpath(latest)
        else:
            sys.exit(f"ERROR: No outputs found for {args.model}. Run 03_model.py first.")

    print(f"Loading outputs from: {model_dir}")
    rc, roi, card = _load(model_dir)

    ts     = datetime.now().strftime("%Y-%m-%d_%H%M")
    outdir = os.path.join("outputs", "visualise", ts)
    os.makedirs(outdir, exist_ok=True)

    print("  Plotting response curves ...")
    p1 = plot_response_curves(rc, roi, outdir)

    print("  Plotting marginal ROI ...")
    p2 = plot_marginal_roi(rc, roi, outdir)

    print("  Plotting marginal CPA ...")
    p3 = plot_marginal_cpa(rc, roi, outdir)

    print("  Plotting ROI/CPA summary ...")
    p4 = plot_roi_summary(roi, outdir)

    # Update latest symlink
    latest_link = os.path.join("outputs", "visualise", "latest")
    if os.path.islink(latest_link):
        os.remove(latest_link)
    os.symlink(os.path.abspath(outdir), latest_link)

    print(f"\nOutputs written to: {outdir}/")
    for p in [p1, p2, p3, p4]:
        print(f"  {os.path.basename(p)}")


if __name__ == "__main__":
    main()
