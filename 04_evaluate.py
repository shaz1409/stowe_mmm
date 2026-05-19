# 04_evaluate.py
# Model evaluation — behaviour differs by model.
#
# Usage:
#   python 04_evaluate.py --model robyn
#   python 04_evaluate.py --model meridian
#
# Robyn outputs:
#   Top 20 models ranked by R² and decomp RSSD → outputs/robyn/top20_models.csv
#
# Meridian outputs:
#   Key metrics (MAPE, R², RHAT convergence) + recommended model → outputs/meridian/eval_summary.csv

import argparse

# --- Robyn -------------------------------------------------------------------

def evaluate_robyn():
    """
    Load all Robyn trial models.
    Rank by R² (desc) then decomp RSSD (asc).
    Save top 20 to outputs/robyn/top20_models.csv.
    """
    raise NotImplementedError

# --- Meridian ----------------------------------------------------------------

def evaluate_meridian():
    """
    Compute posterior predictive checks, MAPE, R², RHAT.
    Flag best model and save summary to outputs/meridian/eval_summary.csv.
    """
    raise NotImplementedError

# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["robyn", "meridian"], required=True)
    args = parser.parse_args()

    if args.model == "robyn":
        evaluate_robyn()
    else:
        evaluate_meridian()

if __name__ == "__main__":
    main()
