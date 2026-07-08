# Evaluation & Sample Queries

This document contains the evaluation details and results for the Clinical Cohort Query Mapper against the 20 assignment sample queries.

## The 20 Assignment Sample Queries

The system is tested and evaluated on the following 20 core assignment queries:

1. Patients with HbA1c above 7%
2. Patients with fasting glucose greater than 126 mg/dL
3. Patients with LDL cholesterol below 100 mg/dL
4. Patients with eGFR less than 60 mL/min/1.73m²
5. Patients with systolic blood pressure above 140 mmHg
6. Patients diagnosed with type 2 diabetes
7. Patients with chronic kidney disease stage 3
8. Patients with heart failure
9. Patients with COPD
10. Patients with rheumatoid arthritis
11. Patients currently taking metformin
12. Patients treated with insulin
13. Patients on GLP-1 receptor agonists
14. Patients prescribed atorvastatin
15. Patients exposed to systemic corticosteroids
16. Patients who had a colonoscopy
17. Patients with prior chemotherapy
18. Patients with ECOG performance status 0 or 1
19. Patients with BMI above 30
20. Patients with a positive pregnancy test

---

## Evaluation Results Matrix

The system has mapped all 20 sample queries from the take-home assignment successfully. Below is the summary evaluation table generated from `results.json`:

| # | Query | Domain | Selected Code(s) | Attempts | Latency | Status |
|---|---|---|---|---|---|---|
| 1 | Patients with HbA1c above 7% | measurement | `LOINC:4548-4` (Hemoglobin A1c/Hemoglobin.total in Blood), `LOINC:17856-6` (Hemoglobin A1c/Hemoglobin.total in Blood by HPLC) | 2 | 32.34s | success |
| 2 | Patients with fasting glucose greater than 126 mg/dL | measurement | `LOINC:1558-6` (Fasting Glucose in Serum or Plasma), `LOINC:35184-1` (Glucose p fast SerPl-msCnc) (+3 more) | 0 | 7.19s | success |
| 3 | Patients with LDL cholesterol below 100 mg/dL | measurement | `LOINC:13457-7` (LDL Cholesterol in Serum/Plasma), `LOINC:18262-6` (LDL Cholesterol calculated) (+3 more) | 0 | 8.52s | success |
| 4 | Patients with eGFR less than 60 mL/min/1.73m² | measurement | `LOINC:62238-1` (Glomerular filtration rate/1.73 sq M.predicted by Creatinine-based formula (CKD-EPI)), `LOINC:33914-3` (eGFR) | 0 | 8.04s | success |
| 5 | Patients with systolic blood pressure above 140 mmHg | measurement | `LOINC:8480-6` (Systolic blood pressure), `LOINC:96608-5` (BP Sys Avg) | 0 | 7.41s | success |
| 6 | Patients diagnosed with type 2 diabetes | condition | `ICD-10-CM:E11` (Type 2 diabetes mellitus), `ICD-10-CM:E11.9` (Type 2 diabetes mellitus without complications) (+5 more) | 0 | 13.03s | success |
| 7 | Patients with chronic kidney disease stage 3 | condition | `ICD-10-CM:N18.30` (Chronic kidney disease, stage 3 unspecified), `ICD-10-CM:N18.31` (Chronic kidney disease, stage 3a) (+1 more) | 1 | 19.23s | success |
| 8 | Patients with heart failure | condition | `ICD-10-CM:I50.9` (Heart failure, unspecified), `ICD-10-CM:I50.814` (Right heart failure due to left heart failure) (+4 more) | 0 | 11.34s | success |
| 9 | Patients with COPD | condition | `ICD-10-CM:J44.9` (Chronic obstructive pulmonary disease, unspecified), `ICD-10-CM:J44.89` (Other specified chronic obstructive pulmonary disease) (+2 more) | 0 | 7.79s | success |
| 10 | Patients with rheumatoid arthritis | condition | `ICD-10-CM:M06.9` (Rheumatoid arthritis, unspecified), `ICD-10-CM:M05.9` (Rheumatoid arthritis with rheumatoid factor, unspecified) (+5 more) | 0 | 11.64s | success |
| 11 | Patients currently taking metformin | drug | `RxNorm:6809` (metformin), `RxNorm:1161611` (metformin Pill) (+2 more) | 0 | 24.24s | success |
| 12 | Patients treated with insulin | drug | `RxNorm:5856` (insulin), `RxNorm:253182` (Insulin) | 0 | 6.78s | success |
| 13 | Patients on GLP-1 receptor agonists | drug | `RxNorm:1440051` (lixisenatide), `RxNorm:1551291` (dulaglutide) (+4 more) | 0 | 13.03s | success |
| 14 | Patients prescribed atorvastatin | drug | `RxNorm:83367` (atorvastatin), `RxNorm:1158285` (atorvastatin Pill) (+5 more) | 0 | 18.99s | success |
| 15 | Patients exposed to systemic corticosteroids | drug | `RxNorm:1514` (betamethasone), `RxNorm:3264` (dexamethasone) (+4 more) | 1 | 28.45s | success |
| 16 | Patients who had a colonoscopy | procedure | `SNOMED:73761001` (Colonoscopy) | 0 | 4.90s | success |
| 17 | Patients with prior chemotherapy | procedure | `SNOMED:367336001` (Chemotherapy), `ICD-10-CM:Z51.11` (Encounter for antineoplastic chemotherapy) | 0 | 4.85s | success |
| 18 | Patients with ECOG performance status 0 or 1 | observation | `LOINC:89247-1` (ECOG Performance Status) | 2 | 354.64s | success |
| 19 | Patients with BMI above 30 | measurement | `LOINC:39156-5` (Body mass index), `LOINC:97057-4` (Body mass index) | 0 | 13.77s | success |
| 20 | Patients with a positive pregnancy test | measurement | `LOINC:14302-4` (Pregnancy test urine), `LOINC:2106-3` (Pregnancy test serum) | 2 | 25.05s | success |

> [!NOTE]
> Latencies reflect synchronous REST API roundtrips to NIH/NLM databases and LLM parsing speeds. Queries with 1 or 2 attempts indicate that the Clinical Auditor rejected the initial candidates (e.g., unspecified codes like `N18.9` for CKD) and successfully forced a correction.
