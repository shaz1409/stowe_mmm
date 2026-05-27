# Data Request — Marketing Mix Model (Stowe)

**Requested by:** indigital  
**Date:** <!-- fill in -->  
**Contact:** <!-- Stowe data team contact -->

---

## Purpose

We are building a Marketing Mix Model (MMM) to quantify the contribution of Stowe's paid media channels (Google Ads, Microsoft Advertising, Meta, StackAdapt) to quality lead volume. The model requires historical lead data from the Clef system as its dependent variable. This document describes exactly what we need, in what format, and why.

---

## Required Data

### 1. Quality Leads — daily, by region *(required)*

This is the primary dependent variable for the model.

**Preferred grain:** one row per enquiry  
**Minimum grain:** daily aggregate by region

| Column | Type | Description |
|---|---|---|
| `enquiry_date` | date | Date the enquiry was received |
| `region` | varchar | Stowe's regional categorisation or NUTS-1 UK region (e.g. North West, East Midlands, London). Confirm the exact values used. |
| `is_quality_lead` | bit | Clef quality flag — 1 = quality, 0 = not. Please confirm what criteria determine this. |
| `lead_source` | varchar | How the enquiry arrived: web form, phone, live chat, referral, etc. — *if tracked in Clef* |
| `enquiry_type` | varchar | Case type: divorce, financial proceedings, children matters, cohabitation, other — *if available* |
| `office` | varchar | Stowe office name — *optional; useful for sub-regional sense checks* |
| `enquiry_id` | varchar | Hashed or anonymised enquiry identifier for deduplication — *no PII required* |

**Required filters:** `enquiry_date` between 2020-01-01 and most recent complete week  
**Must-have columns:** `enquiry_date`, `region`, `is_quality_lead`  
**Nice-to-have:** `lead_source`, `enquiry_type`

---

### 2. Lead-to-Instruction Conversion *(if available)*

A secondary KPI used to validate the quality lead definition and sense-check model outputs.

**Grain:** one row per instruction, joinable to enquiries

| Column | Type | Description |
|---|---|---|
| `enquiry_id` | varchar | Hashed enquiry identifier — to join to table 1 |
| `enquiry_date` | date | Date of originating enquiry |
| `instruction_date` | date | Date the instruction was opened |
| `region` | varchar | Region, consistent with table 1 |

**Required filters:** same date range as above  
**Note:** If a direct join is not possible, a simple monthly aggregate (instructions opened by month) is sufficient.

---

### 3. Revenue by Month *(if shareable)*

Used to validate the model's implied revenue-per-lead figure and sense-check channel ROI outputs before presenting to stakeholders.

**Grain:** one row per month

| Column | Type | Description |
|---|---|---|
| `month` | date | First day of month (e.g. 2023-01-01) |
| `new_instruction_revenue` | decimal | Revenue from new instructions opened that month — or total revenue if a split is not available |
| `new_instructions` | int | Count of new instructions opened |

**Note:** Approximate figures are fine. We do not need matter-level detail — monthly totals only.

---

### 4. Case-Type Breakdown *(optional — v2 only)*

Only needed if Stowe wants sub-model outputs by practice area (e.g. separate ROI for divorce vs financial proceedings). Can be deferred until v1 is validated.

If `enquiry_type` is available in table 1, this is already covered.

---

## Date Range

**Start:** 2020-01-01  
**End:** Most recent complete week (rolling)

Five years of history is needed to reliably estimate seasonality (including COVID-period confounding in 2020-Q2 through 2021-Q1) and long-horizon adstock decay.

---

## Delivery Options

Listed in order of preference:

1. **Read-only DW credentials** *(preferred)* — supports automated weekly refresh. We query only the views/tables listed above.
2. **Pre-built SQL views** — Stowe's data team creates views matching the schemas above; we connect read-only.
3. **One-time CSV export** — acceptable for v1 build, but requires a manual re-pull for each model refresh.

---

## Connection Details Required (if direct access)

If providing credentials or views, please share:

- Server hostname (e.g. `stowe-dw.database.windows.net`)
- Database name
- Schema name(s) containing the relevant tables/views
- Authentication method: SQL login, Azure Active Directory, or service principal
- Any IP allowlist or VPN requirement for external access
- Preferred ODBC driver version (we use ODBC Driver 18 for SQL Server)

---

## PII and Data Protection

We do not need any personally identifiable information. Specifically:

- No client names, addresses, or contact details
- Lead IDs should be hashed or anonymised — used only for deduplication
- Aggregated counts (daily by region) are sufficient for the model
- We will handle all data under the terms of the existing data processing agreement

If in doubt, please provide pre-aggregated counts (daily × region × quality flag) rather than row-level data.

---

## Timeline

> **TODO:** Insert agreed delivery date here.

To hit the v1 model build milestone, we need at minimum the quality leads data (table 1) by **[date]**. Revenue and conversion data can follow.

---

*Questions? Contact <!-- name --> at <!-- email -->.*
