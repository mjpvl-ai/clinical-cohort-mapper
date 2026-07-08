import json
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "local_vocab.db")


def init_db(overwrite=False):
    """Initializes the SQLite database with vocabulary concepts and relationships."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    if os.path.exists(DB_PATH) and not overwrite:
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS concepts (
        code TEXT PRIMARY KEY,
        vocabulary TEXT NOT NULL,
        display TEXT NOT NULL,
        domain TEXT NOT NULL,
        synonyms TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS relationships (
        source_code TEXT NOT NULL,
        target_code TEXT NOT NULL,
        relationship_type TEXT NOT NULL,
        PRIMARY KEY (source_code, target_code, relationship_type)
    )
    """)

    # Seed data
    concepts = [
        # Lab Measurements (LOINC)
        (
            "4548-4",
            "LOINC",
            "Hemoglobin A1c/Hemoglobin.total in Blood",
            "measurement",
            '["HbA1c", "A1c", "glycated hemoglobin", "glycohemoglobin"]',
        ),
        (
            "17856-6",
            "LOINC",
            "Hemoglobin A1c/Hemoglobin.total in Blood by HPLC",
            "measurement",
            '["HbA1c HPLC", "glycated hemoglobin by HPLC"]',
        ),
        (
            "1558-6",
            "LOINC",
            "Fasting Glucose in Serum or Plasma",
            "measurement",
            '["fasting glucose", "fasting blood sugar", "FPG"]',
        ),
        (
            "2345-7",
            "LOINC",
            "Glucose in Blood",
            "measurement",
            '["glucose", "blood sugar", "random glucose"]',
        ),
        (
            "13457-7",
            "LOINC",
            "LDL Cholesterol in Serum/Plasma",
            "measurement",
            '["LDL cholesterol", "LDL", "bad cholesterol"]',
        ),
        (
            "18262-6",
            "LOINC",
            "LDL Cholesterol calculated",
            "measurement",
            '["calculated LDL", "LDL-C calc"]',
        ),
        (
            "33914-3",
            "LOINC",
            "eGFR",
            "measurement",
            '["eGFR", "estimated glomerular filtration rate", "GFR"]',
        ),
        (
            "62238-1",
            "LOINC",
            "Glomerular filtration rate/1.73 sq M.predicted by Creatinine-based formula (CKD-EPI)",
            "measurement",
            '["eGFR CKD-EPI", "CKD-EPI GFR"]',
        ),
        (
            "8480-6",
            "LOINC",
            "Systolic blood pressure",
            "measurement",
            '["systolic BP", "systolic blood pressure", "SBP"]',
        ),
        (
            "89247-1",
            "LOINC",
            "ECOG Performance Status",
            "measurement",
            '["ECOG", "ECOG status", "performance status ECOG"]',
        ),
        (
            "39156-5",
            "LOINC",
            "Body mass index",
            "measurement",
            '["BMI", "body mass index", "BMI percentile"]',
        ),
        (
            "14302-4",
            "LOINC",
            "Pregnancy test urine",
            "measurement",
            '["urine pregnancy test", "pregnancy test urine", "uPreg"]',
        ),
        (
            "2106-3",
            "LOINC",
            "Pregnancy test serum",
            "measurement",
            '["serum pregnancy test", "hCG pregnancy test", "sPreg"]',
        ),
        # Conditions (ICD-10-CM)
        (
            "E11",
            "ICD-10-CM",
            "Type 2 diabetes mellitus",
            "condition",
            '["T2D", "type 2 diabetes", "non-insulin dependent diabetes"]',
        ),
        (
            "E11.9",
            "ICD-10-CM",
            "Type 2 diabetes mellitus without complications",
            "condition",
            '["T2D unspecified", "uncomplicated type 2 diabetes"]',
        ),
        (
            "N18.30",
            "ICD-10-CM",
            "Chronic kidney disease, stage 3 unspecified",
            "condition",
            '["CKD stage 3", "chronic kidney disease stage 3", "stage 3 CKD"]',
        ),
        (
            "N18.31",
            "ICD-10-CM",
            "Chronic kidney disease, stage 3a",
            "condition",
            '["CKD stage 3a", "stage 3a chronic kidney disease"]',
        ),
        (
            "N18.32",
            "ICD-10-CM",
            "Chronic kidney disease, stage 3b",
            "condition",
            '["CKD stage 3b", "stage 3b chronic kidney disease"]',
        ),
        (
            "N18.9",
            "ICD-10-CM",
            "Chronic kidney disease, unspecified",
            "condition",
            '["CKD unspecified", "chronic kidney disease unspecified", "kidney failure"]',
        ),
        (
            "I50.9",
            "ICD-10-CM",
            "Heart failure, unspecified",
            "condition",
            '["heart failure", "HF", "congestive heart failure", "CHF"]',
        ),
        (
            "J44.9",
            "ICD-10-CM",
            "Chronic obstructive pulmonary disease, unspecified",
            "condition",
            '["COPD", "chronic obstructive pulmonary disease", "COAD"]',
        ),
        (
            "M06.9",
            "ICD-10-CM",
            "Rheumatoid arthritis, unspecified",
            "condition",
            '["rheumatoid arthritis", "RA", "inflammatory arthritis"]',
        ),
        # Drugs (RxNorm)
        ("6809", "RxNorm", "metformin", "drug", '["metformin", "Glucophage", "Fortamet"]'),
        ("5856", "RxNorm", "insulin", "drug", '["insulin", "Novolog", "Humalog", "Lantus"]'),
        ("83367", "RxNorm", "atorvastatin", "drug", '["atorvastatin", "Lipitor"]'),
        # Procedures (SNOMED / ICD-10-CM)
        ("73761001", "SNOMED", "Colonoscopy", "procedure", '["colonoscopy", "endoscopy of colon"]'),
        (
            "367336001",
            "SNOMED",
            "Chemotherapy",
            "procedure",
            '["chemotherapy", "cancer chemo", "antineoplastic therapy"]',
        ),
        (
            "Z51.11",
            "ICD-10-CM",
            "Encounter for antineoplastic chemotherapy",
            "procedure",
            '["chemotherapy encounter", "admit for chemo"]',
        ),
    ]

    relationships = [
        # CKD hierarchy
        ("N18.9", "N18.30", "parent_of"),
        ("N18.30", "N18.31", "parent_of"),
        ("N18.30", "N18.32", "parent_of"),
        ("N18.31", "N18.30", "child_of"),
        ("N18.32", "N18.30", "child_of"),
        ("N18.30", "N18.9", "child_of"),
        # Diabetes hierarchy
        ("E11", "E11.9", "parent_of"),
        ("E11.9", "E11", "child_of"),
        # LOINC overlaps
        ("4548-4", "17856-6", "similar_to"),
        ("17856-6", "4548-4", "similar_to"),
        ("1558-6", "2345-7", "broader_than"),
        ("2345-7", "1558-6", "narrower_than"),
        # Procedure mappings
        ("367336001", "Z51.11", "mapped_to"),
        ("Z51.11", "367336001", "mapped_to"),
    ]

    cursor.executemany("INSERT OR REPLACE INTO concepts VALUES (?, ?, ?, ?, ?)", concepts)
    cursor.executemany("INSERT OR REPLACE INTO relationships VALUES (?, ?, ?)", relationships)

    conn.commit()
    conn.close()


def query_local_concepts(term, domain=None):
    """Searches the local SQLite database for concepts matching term."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    term_lower = f"%{term.lower()}%"

    if domain:
        cursor.execute(
            """
        SELECT code, vocabulary, display, domain, synonyms 
        FROM concepts 
        WHERE (LOWER(display) LIKE ? OR LOWER(code) LIKE ? OR LOWER(synonyms) LIKE ?) AND domain = ?
        """,
            (term_lower, term_lower, term_lower, domain),
        )
    else:
        cursor.execute(
            """
        SELECT code, vocabulary, display, domain, synonyms 
        FROM concepts 
        WHERE LOWER(display) LIKE ? OR LOWER(code) LIKE ? OR LOWER(synonyms) LIKE ?
        """,
            (term_lower, term_lower, term_lower),
        )

    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append(
            {
                "code": r[0],
                "vocabulary": r[1],
                "display": r[2],
                "domain": r[3],
                "synonyms": json.loads(r[4]),
            }
        )
    return results


def get_concept_relationships(code):
    """Retrieves relationships associated with a code."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
    SELECT r.target_code, c.vocabulary, c.display, c.domain, r.relationship_type
    FROM relationships r
    JOIN concepts c ON r.target_code = c.code
    WHERE r.source_code = ?
    """,
        (code,),
    )

    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append(
            {
                "code": r[0],
                "vocabulary": r[1],
                "display": r[2],
                "domain": r[3],
                "relationship_type": r[4],
            }
        )
    return results


if __name__ == "__main__":
    init_db(overwrite=True)
    print("Database initialized and populated successfully.")
    print("Test Search 'HbA1c':", query_local_concepts("HbA1c"))
    print("Test Relationships 'N18.30':", get_concept_relationships("N18.30"))
