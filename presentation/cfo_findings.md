# Executive Briefing & CFO Findings — Indus Weave Textiles
**PeopleOps Data Hackathon 2026 | Comprehensive Pipeline Case Study**  
**Presented to:** Chief Financial Officer (CFO) & Executive Committee  
**Prepared by:** PeopleOps Data Engineering & Analytics Team  
**Period Analyzed:** 1 April 2026 – 30 September 2026 (6 Months)  
**Database:** Trusted Data Warehouse (Star Schema — Ingested & Verified)  

---

## Executive Summary

Over the past six months, Indus Weave Textiles has faced rising overtime costs and conflicting reports between HR attendance and Payroll. Our team built an end-to-end Python + SQL data pipeline that ingested **345,280 biometric punches**, **53,617 payroll lines**, **36,402 roster entries**, and **5,372 leave requests**, reconciling all six HCM modules into a single trusted star-schema warehouse.

Our analysis answers the CFO's core question: **"Why does the overtime bill keep rising while HR attendance looks normal?"**

The short answer: **Payroll pays overtime strictly from manager-approved OT request forms, completely disconnected from biometric turnstile punches.** Furthermore, we uncovered systemic payroll leakage including **PKR 1.95M in Zombie Payroll** (paying separated staff) and a **+1-hour hardware clock jump** at SITE Plant that went undetected by IT.

---

## Finding 1 — The Overtime Disconnect: Stitching Department Rampant Over-Approval

### The Core Problem
HR attendance reports look normal because biometric attendance captures actual presence. However, Payroll does **not** look at turnstiles — it pays whatever supervisors approve in `overtime_requests.csv`. 

### The Evidence
Across the 6 months, our pipeline matched actual biometric overtime (Rule 14 & 15: minutes worked after shift end rounded down to 30 min) against approved requests and paid payroll units. 

The epicenter of overtime inflation is the **Stitching Department at Faisalabad Plant**:

| Pay Month | Department | Plant | Biometric OT (Hours) | Paid OT (Hours) | Excess Hours Paid | Inflation % Over Actual | Paid OT Cost (PKR) |
|---|---|---|---|---|---|---|---|
| **2026-05** | Stitching | Faisalabad Plant | 857.0 | 1,006.5 | **+149.5 hrs** | **+17.4%** | PKR 425,745 |
| **2026-06** | Stitching | Faisalabad Plant | 825.0 | 1,123.5 | **+298.5 hrs** | **+36.2%** | PKR 476,364 |
| **2026-07** | Stitching | Faisalabad Plant | 901.5 | 1,440.5 | **+539.0 hrs** | **+59.8%** | PKR 612,213 |
| **2026-08** | Stitching | Faisalabad Plant | 925.0 | 1,548.5 | **+623.5 hrs** | **+67.4%** | PKR 659,661 |
| **2026-09** | Stitching | Faisalabad Plant | 876.5 | 1,778.5 | **+902.0 hrs** | **+102.9%** | PKR 759,420 |
| **Total** | **Stitching** | **Faisalabad Plant** | **4,385.0** | **6,897.5** | **+2,512.5 hrs** | **+57.3% avg** | **PKR 2,933,403** |

*In September alone, paid OT hours in Stitching exceeded actual worked biometric hours by more than 100%!*

### Root Cause
Supervisors in Stitching routinely approve inflated manual overtime slips regardless of when operators actually clock out. Because Payroll directly ingests approved requests, Indus Weave paid for **2,512.5 unworked overtime hours** in just this single department.

---

## Finding 2 — "Zombie Payroll": PKR 1.95 Million Paid Post-Separation

### The Evidence
Query `q08_pay_after_separation.sql` identified **5 employees** who continued receiving full salaries for up to 5 months after their official separation date:

| Employee ID | Full Name | Department | Plant | Separation Date | Months Paid Post-Separation | Unearned Payroll Paid (PKR) |
|---|---|---|---|---|---|---|
| **E10471** | Raheel Gill | Sales & Marketing | Head Office | 2026-04-23 | May, Jun, Jul, Aug, Sep (5 mo) | **PKR 660,000** |
| **E11222** | Hamza Rizvi | Dyeing | SITE Plant | 2026-05-16 | Jun, Jul, Aug, Sep (4 mo) | **PKR 418,100** |
| **E10332** | Maryam Chaudhry | Production Planning | Korangi Plant | 2026-05-14 | Jun, Jul, Aug, Sep (4 mo) | **PKR 322,000** |
| **E10989** | Haris Farooq | Dyeing | SITE Plant | 2026-05-18 | Jun, Jul, Aug, Sep (4 mo) | **PKR 294,100** |
| **E10295** | Hamza Qureshi | Finishing | SITE Plant | 2026-05-11 | Jun, Jul, Aug, Sep (4 mo) | **PKR 253,800** |
| **TOTAL** | — | — | — | — | **21 Pay Cycles** | **PKR 1,948,000** |

### Root Cause
Core HR separation dates in `employees.csv` are not integrated with the Payroll execution module. When employee contracts end or resignations occur, no automated stop-order is issued, leading to straight financial losses totaling **PKR 1.95M**.

---

## Finding 3 — Ghost Payroll: 14 Employees Paid with Zero Monthly Attendance

### The Evidence
Query `q07_paid_zero_attendance.sql` revealed **14 employees** across **60 employee-months** who were issued monthly payslips despite recording **zero present attendance days** in biometric punches.
- While some reflect long-term separated employees (above), others represent active headcount drawing salaries without biometric trace.
- Immediate audit is required on cost centers associated with these IDs.

---

## Finding 4 — Biometric Device Clock Drift (Technical Finding: Rule 11)

### The Discovery
During our ingestion analysis of raw biometric timestamps, we detected a severe device clock drift on device **`DEV-SITE-01`** at the **SITE Plant**:
- **Date of Incident:** 2026-07-01 at 00:00:00
- **Nature of Drift:** Clock jumped forward by exactly **+1 hour (60 minutes)**.
  - June 30: Morning punches centered at 05:40–06:10.
  - July 1: Morning punches abruptly jumped to 06:40–07:10.
- **Impact:** **48,146 punches** were shifted by +1 hour. Without correction, every DAY shift worker appeared 1 hour late, and NIGHT shift workers appeared to have worked 1 hour excess overtime.
- **Pipeline Remedy:** Our automated cleaning module (`clean_punches.py`) dynamically identified this offset and shifted all punches for `DEV-SITE-01` on or after 2026-07-01 back by 1 hour (`- pd.Timedelta(hours=1)`), flagging them with `clock_corrected = 1`.

---

## Finding 5 — Annual Leave Overuse (Rule 18)

### The Evidence
Query `q10_leave_overuse.sql` cross-referenced individual employee full-year leave entitlements against approved annual leave days taken in the 6-month window (Rule 16 & 17):
- **20 employees** have already completely exhausted and exceeded their full-year annual leave entitlement by month 6.
- Top violators:
  - `E10770` (Danish Iqbal, Maintenance): Took **28 days** (Entitlement: 14 days — **+14 days over**)
  - `E10826` (Ahmed Mirza, Utilities): Took **27 days** (Entitlement: 14 days — **+13 days over**)
  - `E10748` (Asif Ansari, Dyeing): Took **25 days** (Entitlement: 14 days — **+11 days over**)

---

## Strategic Recommendations for the CFO

1. **Automate a Biometric Gate for Overtime Payouts:**
   - Configure Payroll to calculate overtime strictly as `MIN(approved_ot_hours, biometric_ot_hours)`.
   - Any manual overtime claim exceeding biometric presence by >15 minutes must require dual sign-off by Plant GM and Finance.
   - **Projected Annual Savings:** ~PKR 6M–8M annually.

2. **Automate Hard Stop on Payroll upon HR Separation:**
   - Implement an automated database foreign-key/event trigger between HCM Core and Payroll.
   - Run `q08_pay_after_separation.sql` as a mandatory pre-payroll execution audit check.
   - **Immediate Financial Recovery:** Initiate legal recovery for **PKR 1,948,000** paid to the 5 separated employees.

3. **Deploy NTP Time Synchronization on Biometric Turnstiles:**
   - Implement local Network Time Protocol (NTP) servers at all three manufacturing plants to prevent hardware clock jumps like the July 1 incident at SITE Plant.

4. **Bi-Monthly Leave Balance Sync:**
   - Block manager approval workflows in Polarapt HCM when an employee's requested leave exceeds remaining accrued balance.

---
*All queries, DDL, pipeline stages, and test suites are fully automated and reproducible via `python run_pipeline.py`.*
