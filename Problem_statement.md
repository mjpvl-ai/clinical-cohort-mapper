# Clinical Cohort Mapper - Assignment Details

This repository contains the implementation for the clinical code mapping task, which maps free-form patient cohort queries to standardized medical codes. Below are the requirements, guidelines, and reference schemas extracted from the project documentation.

---

## 1. Take-Home Assignment: Clinical Code Mapping

### Objective
Build a prototype that maps free-form clinical queries to appropriate standardized clinical concepts and codes using public/reference vocabularies.
*   Please use publicly available resources only. Do not use any proprietary code systems.
*   We are intentionally leaving the implementation approach open-ended. We are more interested in your reasoning, trade-offs, evaluation design, and ability to avoid clinically incorrect mappings than in a specific technology choice.

### Sample Queries
Please test your approach on the following 20 examples:
1.  Patients with HbA1c above 7%
2.  Patients with fasting glucose greater than 126 mg/dL
3.  Patients with LDL cholesterol below 100 mg/dL
4.  Patients with eGFR less than 60 mL/min/1.73m²
5.  Patients with systolic blood pressure above 140 mmHg
6.  Patients diagnosed with type 2 diabetes
7.  Patients with chronic kidney disease stage 3
8.  Patients with heart failure
9.  Patients with COPD
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

### Assignment Requirements
For each query, your system should produce a structured mapping output that includes:
1.  The interpreted clinical meaning of the query.
2.  The relevant clinical entity or entities.
3.  Any value, unit, temporal, or status constraints.
4.  Candidate codes considered.
5.  Final selected codes.
6.  Codes or candidates rejected, with a brief reason.
7.  A confidence score or ranking for the selected candidates.

*The output format is up to you, but it should be easy to review programmatically.*

### Key Questions to Address in the Write-up
1.  How you interpreted the free-form query.
2.  How you handled synonyms and alternative clinical phrasing.
3.  How you retrieved candidate codes.
4.  How you ranked and filtered candidates.
5.  How you avoided clinically incorrect mappings.
6.  How you evaluated the quality of your mappings.
7.  What limitations remain in your approach.

### Deliverables
1.  A short technical write-up.
2.  A working prototype, script, notebook, or small application.
3.  Instructions to run the code.
4.  Structured results for the 20 sample queries.
5.  A small evaluation table.
6.  A brief section on limitations and production improvements.

### Evaluation Criteria
*   **Query interpretation**: Can the system understand the clinical intent behind the free-form query?
*   **Code retrieval**: Does the system retrieve relevant candidate concepts with good recall?
*   **Final mapping quality**: Are the final selected codes clinically appropriate?
*   **Precision**: Does the system avoid misleading or overly broad mappings?
*   **Synonym handling**: Does the system handle abbreviations, variants, and related terminology?
*   **Explainability**: Can a reviewer understand why codes were selected or rejected?
*   **Evaluation design**: Is there a sensible way to measure mapping quality?
*   **Scalability**: Could the approach reasonably extend to larger vocabularies and more query types?

### Public Resources You May Use
1.  OMOP Athena Vocabulary Search: https://athena.ohdsi.org/
2.  OHDSI OMOP Standardized Vocabularies: https://ohdsi.github.io/TheBookOfOhdsi/StandardizedVocabularies.html
3.  UMLS Documentation: https://documentation.uts.nlm.nih.gov/
4.  LOINC Search: https://loinc.org/search/
5.  RxNorm API Documentation: https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html
6.  SNOMED CT Browser: https://browser.ihtsdotools.org/
7.  ICD-10-CM Browser, CDC: https://www.cdc.gov/nchs/icd/icd-10-cm/browser-tool.htm

### Final Discussion Question
Assume that a proprietary clinical code system is later added, where each code includes:
*   Code ID
*   Display name
*   Domain or category
*   Synonyms, if available
*   Parent/child relationships, if available
*   Mapping to public vocabularies, if available

Briefly explain how your system would adapt to support this additional vocabulary while maintaining both high recall and high precision.

---

## 2. Reference Output Format Examples

Below are three examples of the level of detail expected from the prototype output.

### Example 1: Lab Measurement ("Patients with HbA1c above 7%")
```json
{
  "query": "Patients with HbA1c above 7%",
  "interpreted_meaning": {
    "entity": "HbA1c",
    "domain": "measurement",
    "constraint": {
      "operator": ">",
      "value": 7,
      "unit": "%"
    }
  },
  "candidate_codes": [
    {
      "vocabulary": "LOINC",
      "code": "4548-4",
      "display": "Hemoglobin A1c/Hemoglobin.total in Blood",
      "rank": 1
    },
    {
      "vocabulary": "LOINC",
      "code": "17856-6",
      "display": "Hemoglobin A1c/Hemoglobin.total in Blood by HPLC",
      "rank": 2
    }
  ],
  "selected_codes": [
    {
      "vocabulary": "LOINC",
      "code": "4548-4",
      "display": "Hemoglobin A1c/Hemoglobin.total in Blood",
      "confidence": 0.94,
      "reason": "Represents HbA1c measurement and is compatible with percentage-based threshold logic."
    }
  ],
  "rejected_candidates": [
    {
      "vocabulary": "ICD-10-CM",
      "code": "E11",
      "display": "Type 2 diabetes mellitus",
      "reason": "Diagnosis concept; the query asks for a lab measurement threshold."
    }
  ],
  "final_logic": {
    "concept": "HbA1c measurement",
    "condition": "value > 7%"
  }
}
```

### Example 2: Drug Exposure ("Patients currently taking metformin")
```json
{
  "query": "Patients currently taking metformin",
  "interpreted_meaning": {
    "entity": "metformin",
    "domain": "drug",
    "status": "current"
  },
  "candidate_codes": [
    {
      "vocabulary": "RxNorm",
      "code": "6809",
      "display": "metformin",
      "rank": 1
    },
    {
      "vocabulary": "RxNorm",
      "code": "860975",
      "display": "metformin 500 MG Oral Tablet",
      "rank": 2
    }
  ],
  "selected_codes": [
    {
      "vocabulary": "RxNorm",
      "code": "6809",
      "display": "metformin",
      "confidence": 0.92,
      "reason": "Ingredient-level concept suitable for identifying patients exposed to metformin across dose forms."
    }
  ],
  "rejected_candidates": [
    {
      "vocabulary": "ICD-10-CM",
      "code": "E11.9",
      "display": "Type 2 diabetes mellitus without complications",
      "reason": "Condition concept; the query asks for medication exposure."
    }
  ],
  "final_logic": {
    "concept": "metformin exposure",
    "condition": "current medication use"
  }
}
```

### Example 3: Condition/Diagnosis ("Patients with chronic kidney disease stage 3")
```json
{
  "query": "Patients with chronic kidney disease stage 3",
  "interpreted_meaning": {
    "entity": "chronic kidney disease stage 3",
    "domain": "condition"
  },
  "candidate_codes": [
    {
      "vocabulary": "ICD-10-CM",
      "code": "N18.30",
      "display": "Chronic kidney disease, stage 3 unspecified",
      "rank": 1
    },
    {
      "vocabulary": "ICD-10-CM",
      "code": "N18.31",
      "display": "Chronic kidney disease, stage 3a",
      "rank": 2
    },
    {
      "vocabulary": "ICD-10-CM",
      "code": "N18.32",
      "display": "Chronic kidney disease, stage 3b",
      "rank": 3
    }
  ],
  "selected_codes": [
    {
      "vocabulary": "ICD-10-CM",
      "code": "N18.30",
      "display": "Chronic kidney disease, stage 3 unspecified",
      "confidence": 0.9,
      "reason": "Closest direct match for CKD stage 3 when subtype 3a or 3b is not specified."
    },
    {
      "vocabulary": "ICD-10-CM",
      "code": "N18.31",
      "display": "Chronic kidney disease, stage 3a",
      "confidence": 0.86,
      "reason": "More specific subtype under CKD stage 3; may be included depending on cohort definition."
    },
    {
      "vocabulary": "ICD-10-CM",
      "code": "N18.32",
      "display": "Chronic kidney disease, stage 3b",
      "confidence": 0.86,
      "reason": "More specific subtype under CKD stage 3; may be included depending on cohort definition."
    }
  ],
  "rejected_candidates": [
    {
      "vocabulary": "ICD-10-CM",
      "code": "N18.9",
      "display": "Chronic kidney disease, unspecified",
      "reason": "Too broad because the query specifically asks for stage 3."
    }
  ],
  "final_logic": {
    "concept": "chronic kidney disease stage 3",
    "condition": "diagnosis present"
  }
}
```
