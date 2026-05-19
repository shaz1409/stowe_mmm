# 03_model.py
# Run either a Robyn or Meridian model on the MMM-ready data.
#
# Usage:
#   python 03_model.py --model robyn
#   python 03_model.py --model meridian
#
# Inputs:  data/processed/mmm_ready.csv, data/processed/selected_features.txt
# Outputs: outputs/robyn/  or  outputs/meridian/

import argparse
import pandas as pd
from models import robyn_model, meridian_model

def load_inputs() -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv("data/processed/mmm_ready.csv", parse_dates=["date"])
    with open("data/processed/selected_features.txt") as f:
        features = f.read().splitlines()
    return df, features

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["robyn", "meridian"], required=True)
    args = parser.parse_args()

    df, features = load_inputs()

    if args.model == "robyn":
        robyn_model.run(df, features)
    else:
        meridian_model.run(df, features)

if __name__ == "__main__":
    main()
