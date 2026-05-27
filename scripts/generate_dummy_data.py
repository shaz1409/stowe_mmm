"""
Generate dummy source data for pipeline development and testing.

Produces three files in data/raw/:
  - azure_dw_clef_raw.csv      — one row per enquiry (Clef quality leads system)
  - azure_dw_revenue_raw.csv   — monthly revenue and instruction counts
  - stackadapt_export.csv      — daily StackAdapt campaign report

All figures are plausible for a UK divorce firm of Stowe's size but are
entirely synthetic. Replace with real data once DW access and StackAdapt
API credentials are confirmed.

Run from the repo root:
  python scripts/generate_dummy_data.py
"""

import os
import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

DATE_START = "2023-01-01"
DATE_END   = "2024-12-31"

RAW_DIR = "data/raw"
os.makedirs(RAW_DIR, exist_ok=True)

# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

REGIONS = [
    "London",
    "South East",
    "South West",
    "East of England",
    "East Midlands",
    "West Midlands",
    "Yorkshire and The Humber",
    "North West",
    "North East",
]

# Rough share of Stowe's enquiry volume by region (weights must sum to 1)
REGION_WEIGHTS = [0.24, 0.16, 0.09, 0.10, 0.07, 0.09, 0.08, 0.12, 0.05]


def divorce_day_spike(date: pd.Timestamp) -> float:
    """Return a multiplier for 'Divorce Day' — first Monday of January."""
    if date.month == 1 and date.weekday() == 0 and date.day <= 7:
        return 3.5
    return 1.0


def seasonal_factor(date: pd.Timestamp) -> float:
    """
    Rough enquiry seasonality for a UK divorce firm:
      - January peak (New Year resolutions)
      - September secondary peak (post-summer)
      - August / December troughs
    """
    month = date.month
    factors = {
        1: 1.40, 2: 1.10, 3: 1.05, 4: 1.00, 5: 1.00, 6: 0.95,
        7: 0.90, 8: 0.75, 9: 1.15, 10: 1.05, 11: 0.95, 12: 0.80,
    }
    return factors[month]


# --------------------------------------------------------------------------- #
# 1. Azure DW — Clef quality leads (one row per enquiry)
# --------------------------------------------------------------------------- #

ENQUIRY_TYPES  = ["divorce", "financial_remedy", "child_arrangements", "cohabitation", "other"]
ENQUIRY_WEIGHTS = [0.55, 0.20, 0.14, 0.06, 0.05]

LEAD_SOURCES  = ["web_form", "phone", "chat", "referral"]
LEAD_WEIGHTS  = [0.52, 0.28, 0.12, 0.08]

OFFICES = [
    "London City", "London Kensington", "Birmingham", "Manchester",
    "Leeds", "Bristol", "Sheffield", "Nottingham", "Newcastle",
]
OFFICE_WEIGHTS = [0.12, 0.10, 0.10, 0.11, 0.09, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08]


def generate_clef_raw() -> pd.DataFrame:
    dates = pd.date_range(DATE_START, DATE_END, freq="D")

    rows = []
    for date in dates:
        # Base ~55 enquiries/day nationally, with seasonality + Divorce Day
        base = 55 * seasonal_factor(date) * divorce_day_spike(date)
        n_enquiries = max(1, int(RNG.poisson(base)))

        for _ in range(n_enquiries):
            region  = RNG.choice(REGIONS, p=REGION_WEIGHTS)
            enq_type = RNG.choice(ENQUIRY_TYPES, p=ENQUIRY_WEIGHTS)
            source  = RNG.choice(LEAD_SOURCES, p=LEAD_WEIGHTS)

            # Quality lead rate: ~38% overall; slightly higher for web_form / divorce
            base_quality = 0.38
            if source == "web_form":
                base_quality = 0.44
            if enq_type == "divorce":
                base_quality += 0.04
            is_quality = int(RNG.random() < base_quality)

            # Assign office correlated with region (simplified)
            region_office_map = {
                "London":                  ["London City", "London Kensington"],
                "South East":              ["London Kensington"],
                "South West":              ["Bristol"],
                "East of England":         ["London City"],
                "East Midlands":           ["Nottingham"],
                "West Midlands":           ["Birmingham"],
                "Yorkshire and The Humber": ["Leeds", "Sheffield"],
                "North West":              ["Manchester"],
                "North East":              ["Newcastle"],
            }
            office_choices = region_office_map.get(region, OFFICES[:5])
            office = RNG.choice(office_choices)

            rows.append({
                "enquiry_date":    date,
                "region":          region,
                "enquiry_type":    enq_type,
                "lead_source":     source,
                "is_quality_lead": is_quality,
                "office":          office,
            })

    df = pd.DataFrame(rows)
    df["enquiry_date"] = df["enquiry_date"].dt.strftime("%Y-%m-%d")
    return df


# --------------------------------------------------------------------------- #
# 2. Azure DW — monthly revenue
# --------------------------------------------------------------------------- #

def generate_revenue_raw() -> pd.DataFrame:
    months = pd.date_range(DATE_START, DATE_END, freq="MS")

    # Base: ~220 new instructions/month, ~£8,500 avg revenue per instruction
    rows = []
    for month in months:
        sf = seasonal_factor(month)
        instructions = max(1, int(RNG.normal(220 * sf, 20)))
        avg_value = RNG.normal(8_500, 600)
        revenue = round(instructions * avg_value, 2)

        rows.append({
            "month":                    month.strftime("%Y-%m-%d"),
            "new_instruction_revenue":  revenue,
            "new_instructions":         instructions,
        })

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 3. StackAdapt — daily campaign report
# --------------------------------------------------------------------------- #

STACKADAPT_CAMPAIGNS = [
    "Stowe_Prospecting_Divorce_UK",
    "Stowe_Retargeting_All_UK",
    "Stowe_FinancialRemedy_Prospecting",
    "Stowe_BrandAwareness_UK",
]

# Rough daily budget split across campaigns (must sum to 1)
CAMPAIGN_BUDGET_SPLIT = [0.40, 0.30, 0.20, 0.10]

# Total StackAdapt monthly budget: ~£35k → ~£1,150/day
DAILY_BUDGET = 1_150


def generate_stackadapt_export() -> pd.DataFrame:
    dates = pd.date_range(DATE_START, DATE_END, freq="D")

    rows = []
    for date in dates:
        sf = seasonal_factor(date)

        for campaign, budget_share in zip(STACKADAPT_CAMPAIGNS, CAMPAIGN_BUDGET_SPLIT):
            # Small campaigns may not run every day
            if campaign == "Stowe_BrandAwareness_UK" and RNG.random() < 0.15:
                continue

            spend = round(
                float(RNG.normal(DAILY_BUDGET * budget_share * sf, DAILY_BUDGET * budget_share * 0.12)),
                2,
            )
            spend = max(0.0, spend)

            # CPM ~£8, CTR ~0.12%
            impressions = int(spend / 8 * 1_000)
            clicks = int(RNG.binomial(impressions, 0.0012))

            region = RNG.choice(REGIONS, p=REGION_WEIGHTS)
            city   = f"{region.split()[0]} area"  # simplified city proxy

            rows.append({
                "Date":        date.strftime("%Y-%m-%d"),
                "Campaign":    campaign,
                "Region":      region,
                "City":        city,
                "Spend":       spend,
                "Impressions": impressions,
                "Clicks":      clicks,
            })

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 4. Google Ads — daily campaign report
# --------------------------------------------------------------------------- #

GOOGLE_CAMPAIGNS = [
    ("Brand - National_Mix",         "SEARCH", 0.30),
    ("Non-Brand - Divorce",          "SEARCH", 0.25),
    ("Non-Brand - Financial Remedy", "SEARCH", 0.20),
    ("Non-Brand - Child Custody",    "SEARCH", 0.10),
    ("Non-Brand - Broad Divorce",    "SEARCH", 0.10),
    ("Display - Remarketing",        "DISPLAY", 0.05),
]

GOOGLE_DAILY_BUDGET = 10_500  # ~£320k/month


def generate_google_ads_raw() -> pd.DataFrame:
    dates = pd.date_range(DATE_START, DATE_END, freq="D")
    rows  = []
    for date in dates:
        sf = seasonal_factor(date) * divorce_day_spike(date)
        for campaign, ch_type, share in GOOGLE_CAMPAIGNS:
            spend = float(RNG.normal(GOOGLE_DAILY_BUDGET * share * sf,
                                     GOOGLE_DAILY_BUDGET * share * 0.10))
            spend = max(0.0, round(spend, 2))
            cpc   = RNG.uniform(3.5, 7.0) if ch_type == "SEARCH" else RNG.uniform(0.4, 1.2)
            clicks = int(spend / cpc)
            impressions = int(clicks / RNG.uniform(0.04, 0.08)) if ch_type == "SEARCH" \
                else int(clicks / RNG.uniform(0.001, 0.003))
            cvr   = RNG.uniform(0.04, 0.10) if ch_type == "SEARCH" else RNG.uniform(0.005, 0.02)
            convs = round(clicks * cvr, 1)
            sis   = round(RNG.uniform(0.55, 0.90), 4) if ch_type == "SEARCH" else 0.0
            rows.append({
                "date":                   date.strftime("%Y-%m-%d"),
                "channel":                "google_ads",
                "campaign":               campaign,
                "channel_type":           ch_type,
                "spend":                  spend,
                "impressions":            impressions,
                "clicks":                 clicks,
                "conversions":            convs,
                "all_conversions":        round(convs * RNG.uniform(1.1, 1.4), 1),
                "search_impression_share": sis,
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 5. Meta — daily campaign report
# --------------------------------------------------------------------------- #

META_CAMPAIGNS = [
    ("Top Funnel - Prospecting - Reach and Recall", "OUTCOME_AWARENESS",    0.35),
    ("Mid Funnel - Consideration - Divorce",         "OUTCOME_TRAFFIC",      0.30),
    ("Bottom Funnel - Retargeting - Leads",          "OUTCOME_LEADS",        0.25),
    ("Brand - Video Views",                          "OUTCOME_AWARENESS",    0.10),
]

META_DAILY_BUDGET = 1_300  # ~£40k/month


def generate_meta_raw() -> pd.DataFrame:
    dates = pd.date_range(DATE_START, DATE_END, freq="D")
    rows  = []
    for date in dates:
        sf = seasonal_factor(date)
        for campaign, objective, share in META_CAMPAIGNS:
            spend = float(RNG.normal(META_DAILY_BUDGET * share * sf,
                                     META_DAILY_BUDGET * share * 0.12))
            spend = max(0.0, round(spend, 2))
            cpm   = RNG.uniform(6.0, 12.0)
            impressions = int(spend / cpm * 1_000)
            ctr   = RNG.uniform(0.008, 0.025)
            clicks = int(impressions * ctr)
            outbound_clicks = int(clicks * RNG.uniform(0.7, 0.9))
            reach = int(impressions / RNG.uniform(1.1, 1.8))
            freq  = round(impressions / max(reach, 1), 3)
            leads = int(clicks * RNG.uniform(0.01, 0.04)) if objective == "OUTCOME_LEADS" else 0
            convs = leads
            rows.append({
                "date":              date.strftime("%Y-%m-%d"),
                "channel":           "meta",
                "campaign":          campaign,
                "objective":         objective,
                "spend":             spend,
                "impressions":       impressions,
                "clicks":            clicks,
                "outbound_clicks":   outbound_clicks,
                "reach":             reach,
                "frequency":         freq,
                "leads":             leads,
                "conversions":       convs,
                "form_submissions":  leads,
                "video_views_25":    int(impressions * RNG.uniform(0.1, 0.3)),
                "video_views_75":    int(impressions * RNG.uniform(0.03, 0.1)),
                "video_views_100":   int(impressions * RNG.uniform(0.01, 0.04)),
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 6. Bing Ads — daily campaign report
# --------------------------------------------------------------------------- #

BING_CAMPAIGNS = [
    ("Brand - UK National",             "SEARCH", 0.35),
    ("Non-Brand - Divorce Solicitor",   "SEARCH", 0.35),
    ("Non-Brand - Family Law",          "SEARCH", 0.20),
    ("Remarketing - All Visitors",      "AUDIENCE", 0.10),
]

BING_DAILY_BUDGET = 2_900  # ~£90k/month


def generate_bing_ads_raw() -> pd.DataFrame:
    dates = pd.date_range(DATE_START, DATE_END, freq="D")
    rows  = []
    for date in dates:
        sf = seasonal_factor(date) * divorce_day_spike(date)
        for campaign, ch_type, share in BING_CAMPAIGNS:
            spend = float(RNG.normal(BING_DAILY_BUDGET * share * sf,
                                     BING_DAILY_BUDGET * share * 0.10))
            spend = max(0.0, round(spend, 2))
            cpc   = RNG.uniform(4.0, 8.5) if ch_type == "SEARCH" else RNG.uniform(0.5, 1.5)
            clicks = int(spend / cpc)
            impressions = int(clicks / RNG.uniform(0.03, 0.07)) if ch_type == "SEARCH" \
                else int(clicks / RNG.uniform(0.002, 0.005))
            cvr   = RNG.uniform(0.03, 0.09)
            convs = round(clicks * cvr, 1)
            region = RNG.choice(REGIONS, p=REGION_WEIGHTS)
            city   = f"{region.split()[0]} area"
            rows.append({
                "date":           date.strftime("%Y-%m-%d"),
                "channel":        "bing_ads",
                "region":         region,
                "city":           city,
                "campaign":       campaign,
                "channel_type":   ch_type,
                "spend":          spend,
                "impressions":    impressions,
                "clicks":         clicks,
                "conversions":    convs,
                "all_conversions": round(convs * RNG.uniform(1.05, 1.3), 1),
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    print("Generating dummy data for 2023-01-01 → 2024-12-31 ...")

    print("  Building Clef quality leads (one row per enquiry) ...")
    clef = generate_clef_raw()
    path = os.path.join(RAW_DIR, "azure_dw_clef_raw.csv")
    clef.to_csv(path, index=False)
    quality = clef["is_quality_lead"].sum()
    print(f"    Saved {len(clef):,} rows ({quality:,} quality leads) → {path}")

    print("  Building revenue table ...")
    revenue = generate_revenue_raw()
    path = os.path.join(RAW_DIR, "azure_dw_revenue_raw.csv")
    revenue.to_csv(path, index=False)
    print(f"    Saved {len(revenue):,} rows → {path}")

    print("  Building StackAdapt export ...")
    sa = generate_stackadapt_export()
    path = os.path.join(RAW_DIR, "stackadapt_export.csv")
    sa.to_csv(path, index=False)
    total_spend = sa["Spend"].sum()
    print(f"    Saved {len(sa):,} rows (£{total_spend:,.0f} total spend) → {path}")

    print("  Building Google Ads raw ...")
    gads = generate_google_ads_raw()
    path = os.path.join(RAW_DIR, "google_ads_raw.csv")
    gads.to_csv(path, index=False)
    print(f"    Saved {len(gads):,} rows (£{gads['spend'].sum():,.0f} total spend) → {path}")

    print("  Building Meta raw ...")
    meta = generate_meta_raw()
    path = os.path.join(RAW_DIR, "meta_raw.csv")
    meta.to_csv(path, index=False)
    print(f"    Saved {len(meta):,} rows (£{meta['spend'].sum():,.0f} total spend) → {path}")

    print("  Building Bing Ads raw ...")
    bing = generate_bing_ads_raw()
    path = os.path.join(RAW_DIR, "bing_ads_raw.csv")
    bing.to_csv(path, index=False)
    print(f"    Saved {len(bing):,} rows (£{bing['spend'].sum():,.0f} total spend) → {path}")

    print("Done.")
