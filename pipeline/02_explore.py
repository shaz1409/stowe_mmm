# 02_explore.py
# Exploratory data analysis and feature selection.
#
# Inputs:  data/mmm_ready.csv
# Outputs: notes / selected feature list (data/selected_features.txt)
#
# Steps (to implement):
#   1. Load mmm_ready.csv
#   2. Summary stats — nulls, distributions, time coverage per channel
#   3. Correlation analysis (media vs KPI)
#   4. Spend/impression trend plots
#   5. Adstock / saturation sense checks
#   6. Flag low-signal or collinear channels
#   7. Output final list of features to carry into modelling

import pandas as pd

def load_data() -> pd.DataFrame:
    return pd.read_csv("data/processed/mmm_ready.csv", parse_dates=["date"])

def run_eda(df: pd.DataFrame):
    """Summary stats, plots, correlation matrix."""
    raise NotImplementedError

def select_features(df: pd.DataFrame) -> list[str]:
    """Return list of column names selected for modelling."""
    raise NotImplementedError

def main():
    df = load_data()
    run_eda(df)
    features = select_features(df)
    with open("data/processed/selected_features.txt", "w") as f:
        f.write("\n".join(features))
    print(f"Selected {len(features)} features.")

if __name__ == "__main__":
    main()
