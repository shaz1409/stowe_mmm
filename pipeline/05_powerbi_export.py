# 05_powerbi_export.py
# Flatten model outputs into Power BI-friendly flat files.
#
# Inputs:  outputs/robyn/ or outputs/meridian/ (whichever was run)
# Outputs: outputs/powerbi/contributions.csv
#          outputs/powerbi/roi_summary.csv
#          outputs/powerbi/model_fit.csv
#
# Steps (to implement):
#   1. Load selected model results
#   2. Build channel contribution table (date × channel × contribution)
#   3. Build ROI / effectiveness summary table
#   4. Build model fit table (actual vs predicted over time)
#   5. Save all three to outputs/powerbi/

import argparse
import pandas as pd

def build_contributions() -> pd.DataFrame:
    raise NotImplementedError

def build_roi_summary() -> pd.DataFrame:
    raise NotImplementedError

def build_model_fit() -> pd.DataFrame:
    raise NotImplementedError

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["robyn", "meridian"], required=True)
    args = parser.parse_args()

    contributions = build_contributions()
    roi = build_roi_summary()
    fit = build_model_fit()

    contributions.to_csv("outputs/powerbi/contributions.csv", index=False)
    roi.to_csv("outputs/powerbi/roi_summary.csv", index=False)
    fit.to_csv("outputs/powerbi/model_fit.csv", index=False)
    print("Power BI exports saved to outputs/powerbi/")

if __name__ == "__main__":
    main()
