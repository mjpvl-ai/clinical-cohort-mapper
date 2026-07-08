from typing import Any

from mapper.schemas import CandidateCode, ClinicalIntent, RejectedCandidate, SelectedCode


class ClinicalAuditor:
    """Audits candidates, performs relationship reflexions, and assigns clinical confidence."""

    def __init__(self):
        pass

    def audit(
        self, intent: ClinicalIntent, candidates: list[CandidateCode]
    ) -> tuple[bool, list[SelectedCode], list[RejectedCandidate], dict[str, Any] | None]:
        """Evaluates candidates, running rule-based checks first, then performing LLM clinical auditing."""
        is_approved, selected, rejected, critique = self._rule_based_audit(intent, candidates)

        # LLM refinement using call_llm
        try:
            import json

            from mapper.llm import call_llm

            candidates_data = [
                {"vocabulary": c.vocabulary, "code": c.code, "display": c.display}
                for c in candidates
            ]

            prompt = f"""You are a Clinical Auditor agent. Audit the retrieved candidate codes against the patient cohort query.
            
            Query: "{intent.original_query}"
            Clinical Intent Domain: {intent.domain}
            Clinical Entities: {intent.clinical_entities}
            Constraint: {json.dumps(intent.constraint.dict() if intent.constraint else None)}
            Temporal Status: {intent.status}
            
            Candidate Codes:
            {json.dumps(candidates_data, indent=2)}
            
            Output a JSON object containing the audit decision matching this schema:
            {{
              "is_approved": true or false,
              "selected_codes": [
                {{
                  "vocabulary": "vocabulary name",
                  "code": "code value",
                  "display": "display name",
                  "confidence": number between 0.0 and 1.0,
                  "reason": "clinical justification for selection"
                }}
              ],
              "rejected_candidates": [
                {{
                  "vocabulary": "vocabulary name",
                  "code": "code value",
                  "display": "display name",
                  "reason": "clinical reason for rejection"
                }}
              ],
              "critique": {{
                "reason": "reason for failure or retry if not approved",
                "suggested_exclusions": ["list of display names or codes to exclude in next search"],
                "suggested_domain": "suggested domain to search"
              }} // or null if is_approved is true
            }}
            
            Rules:
            1. Validate clinical specificity. E.g., if query specifies 'chronic kidney disease stage 3' and candidates contain 'Chronic kidney disease, unspecified (N18.9)', reject it as too broad, suggest exclusions, and mark is_approved = false.
            2. Match values/units/status.
            3. Reject codes that represent devices, software metadata, or unrelated concepts.
            """

            content = call_llm(prompt, json_mode=True)
            data = json.loads(content)

            # Map back to SelectedCode / RejectedCandidate schemas
            llm_selected = []
            for item in data.get("selected_codes", []):
                # Ensure it was in original candidates list
                if any(c.code == item["code"] for c in candidates):
                    llm_selected.append(
                        SelectedCode(
                            vocabulary=item["vocabulary"],
                            code=item["code"],
                            display=item["display"],
                            confidence=item.get("confidence", 0.8),
                            reason=item.get("reason", "Relevant mapping"),
                        )
                    )

            llm_rejected = []
            for item in data.get("rejected_candidates", []):
                llm_rejected.append(
                    RejectedCandidate(
                        vocabulary=item["vocabulary"],
                        code=item["code"],
                        display=item["display"],
                        reason=item.get("reason", "Excluded"),
                    )
                )

            # If LLM selected list is not empty, use LLM results
            if llm_selected or llm_rejected:
                llm_approved = data.get("is_approved", is_approved)
                llm_critique = data.get("critique") if not llm_approved else None
                # Sort selected by confidence descending
                llm_selected.sort(key=lambda x: x.confidence, reverse=True)
                return llm_approved, llm_selected, llm_rejected, llm_critique
        except Exception:
            pass

        return is_approved, selected, rejected, critique

    def _rule_based_audit(
        self, intent: ClinicalIntent, candidates: list[CandidateCode]
    ) -> tuple[bool, list[SelectedCode], list[RejectedCandidate], dict[str, Any] | None]:
        """Evaluates candidates, performs ontology validation using heuristic rules, and returns decisions or critique."""
        selected = []
        rejected = []

        # Check for empty candidates
        if not candidates:
            # If no candidates retrieved, trigger correction to expand synonyms or change terms
            return (
                False,
                [],
                [],
                {
                    "reason": "No candidates found.",
                    "suggested_exclusions": intent.negative_constraints,
                },
            )

        # 1. Spec Specificity / Granularity Reflexion for CKD Stage 3
        is_ckd_stage_3_query = (
            "stage 3" in intent.original_query.lower() and "kidney" in intent.original_query.lower()
        )
        if is_ckd_stage_3_query:
            has_broad_candidate = any(c.code == "N18.9" for c in candidates)
            has_specific_candidate = any(
                c.code in ["N18.30", "N18.31", "N18.32"] for c in candidates
            )

            if has_broad_candidate and not has_specific_candidate:
                # Trigger self-correction: Reject N18.9 and fetch children of N18.30
                critique = {
                    "reason": "Candidate N18.9 is too broad; the query specifies stage 3.",
                    "suggested_exclusions": ["chronic kidney disease, unspecified", "N18.9"],
                    "suggested_domain": "condition",
                }
                return False, [], [], critique

        # 2. General Candidate Evaluation Loop
        for cand in candidates:
            # Domain checks
            if intent.domain == "drug" and cand.vocabulary not in ["RxNorm"]:
                rejected.append(
                    RejectedCandidate(
                        vocabulary=cand.vocabulary,
                        code=cand.code,
                        display=cand.display,
                        reason=f"Candidate code is from {cand.vocabulary} ({cand.domain if hasattr(cand, 'domain') else 'non-drug'}); the query asks for medication exposure.",
                    )
                )
                continue

            if intent.domain == "condition" and cand.vocabulary not in ["ICD-10-CM", "SNOMED"]:
                rejected.append(
                    RejectedCandidate(
                        vocabulary=cand.vocabulary,
                        code=cand.code,
                        display=cand.display,
                        reason=f"Candidate code is from {cand.vocabulary}; the query asks for a clinical diagnosis.",
                    )
                )
                continue

            if intent.domain == "measurement" and cand.vocabulary not in ["LOINC", "SNOMED"]:
                rejected.append(
                    RejectedCandidate(
                        vocabulary=cand.vocabulary,
                        code=cand.code,
                        display=cand.display,
                        reason=f"Candidate code is from {cand.vocabulary}; the query asks for a lab measurement or observation.",
                    )
                )
                continue

            # Specific clinical justifications and score adjustments
            confidence = 0.80  # Base confidence
            reason = "Relevant clinical concept mapping."

            # --- Measurement Specific Rules ---
            if intent.domain == "measurement":
                if "hba1c" in intent.original_query.lower():
                    if cand.code == "4548-4":
                        confidence = 0.94
                        reason = "Represents HbA1c measurement and is compatible with percentage-based threshold logic."
                    elif cand.code == "17856-6":
                        confidence = 0.88
                        reason = "Alternative HbA1c measurement (by HPLC) suitable for secondary analysis."
                elif "glucose" in intent.original_query.lower():
                    if "fasting" in intent.original_query.lower():
                        if cand.code == "1558-6":
                            confidence = 0.93
                            reason = "Direct match for Fasting Glucose in Serum or Plasma, matching the query threshold constraint."
                        else:
                            rejected.append(
                                RejectedCandidate(
                                    vocabulary=cand.vocabulary,
                                    code=cand.code,
                                    display=cand.display,
                                    reason="General glucose concept; query specifies fasting glucose.",
                                )
                            )
                            continue
                    else:
                        if cand.code == "2345-7":
                            confidence = 0.90
                            reason = "Standard blood glucose measurement concept."
                elif "ldl" in intent.original_query.lower():
                    if cand.code == "13457-7":
                        confidence = 0.92
                        reason = "Represents LDL Cholesterol in Serum/Plasma, compatible with mg/dL threshold logic."
                elif "egfr" in intent.original_query.lower():
                    if cand.code in ["62238-1", "33914-3"]:
                        confidence = 0.91
                        reason = "Standard eGFR measurement (CKD-EPI formula) suitable for filtration rate thresholding."
                elif "blood pressure" in intent.original_query.lower():
                    if cand.code == "8480-6":
                        confidence = 0.95
                        reason = "Represents systolic blood pressure measurement, matching the query vital sign constraint."
                elif "ecog" in intent.original_query.lower():
                    if cand.code == "89247-1":
                        confidence = 0.93
                        reason = "ECOG Performance Status assessment concept, matching observation query."
                elif "bmi" in intent.original_query.lower():
                    if cand.code == "39156-5":
                        confidence = 0.94
                        reason = "Direct match for Body Mass Index measurement."
                elif "pregnancy" in intent.original_query.lower():
                    if cand.code == "14302-4":
                        confidence = 0.91
                        reason = "Urine pregnancy test concept, ideal for qualitative positive/negative cohorts."
                    elif cand.code == "2106-3":
                        confidence = 0.89
                        reason = "Serum pregnancy test concept, alternative qualitative or quantitative screening."

            # --- Condition Specific Rules ---
            elif intent.domain == "condition":
                if "diabetes" in intent.original_query.lower():
                    if cand.code in ["E11", "E11.9"]:
                        confidence = 0.94
                        reason = "Closest direct match for Type 2 diabetes mellitus."
                elif "heart failure" in intent.original_query.lower():
                    if cand.code == "I50.9":
                        confidence = 0.92
                        reason = "Standard unspecified Heart Failure code, covering congestive and chronic HF."
                elif "copd" in intent.original_query.lower():
                    if cand.code == "J44.9":
                        confidence = 0.95
                        reason = (
                            "Standard code for Chronic obstructive pulmonary disease, unspecified."
                        )
                elif "arthritis" in intent.original_query.lower():
                    if cand.code == "M06.9":
                        confidence = 0.94
                        reason = "Standard code for Rheumatoid arthritis, unspecified."
                elif is_ckd_stage_3_query:
                    if cand.code == "N18.30":
                        confidence = 0.90
                        reason = "Closest direct match for CKD stage 3 when subtype 3a or 3b is not specified."
                    elif cand.code == "N18.31":
                        confidence = 0.86
                        reason = "More specific subtype under CKD stage 3 (stage 3a); may be included depending on cohort definition."
                    elif cand.code == "N18.32":
                        confidence = 0.86
                        reason = "More specific subtype under CKD stage 3 (stage 3b); may be included depending on cohort definition."
                    elif cand.code == "N18.9":
                        rejected.append(
                            RejectedCandidate(
                                vocabulary=cand.vocabulary,
                                code=cand.code,
                                display=cand.display,
                                reason="Too broad because the query specifically asks for stage 3.",
                            )
                        )
                        continue

            # --- Drug Specific Rules ---
            elif intent.domain == "drug":
                # Check for class members vs specific drug
                is_class_query = any(
                    w in intent.original_query.lower()
                    for w in ["agonist", "corticosteroid", "inhibitor", "blocker"]
                )

                if is_class_query:
                    if "glp-1" in intent.original_query.lower():
                        confidence = 0.90
                        reason = f"Active ingredient member of GLP-1 Receptor Agonist established pharmacologic class ({cand.display})."
                    elif "corticosteroid" in intent.original_query.lower():
                        confidence = 0.88
                        reason = f"Active ingredient member of Corticosteroid established pharmacologic class ({cand.display})."
                else:
                    if "metformin" in intent.original_query.lower() and cand.code == "6809":
                        confidence = 0.92
                        reason = "Ingredient-level concept suitable for identifying patients exposed to metformin across dose forms."
                    elif "insulin" in intent.original_query.lower() and cand.code == "5856":
                        confidence = 0.91
                        reason = "Ingredient-level concept for insulin exposure, capturing all formulations."
                    elif "atorvastatin" in intent.original_query.lower() and cand.code == "83367":
                        confidence = 0.93
                        reason = "Ingredient-level concept for atorvastatin exposure."

            # --- Procedure Specific Rules ---
            elif intent.domain == "procedure":
                if "colonoscopy" in intent.original_query.lower():
                    if cand.code == "73761001":
                        confidence = 0.95
                        reason = "Direct match for Colonoscopy procedure in SNOMED."
                elif "chemotherapy" in intent.original_query.lower():
                    if cand.code == "367336001":
                        confidence = 0.94
                        reason = "Direct SNOMED code representing Chemotherapy procedure."
                    elif cand.code == "Z51.11":
                        confidence = 0.89
                        reason = "ICD-10-CM encounter code for chemotherapy administration."

            # Add to selected
            selected.append(
                SelectedCode(
                    vocabulary=cand.vocabulary,
                    code=cand.code,
                    display=cand.display,
                    confidence=confidence,
                    reason=reason,
                )
            )

        # Check if we successfully mapped anything
        if not selected:
            return (
                False,
                [],
                rejected,
                {
                    "reason": "All candidates were rejected by domain or clinical safety rules.",
                    "suggested_exclusions": [c.display for c in candidates],
                },
            )

        # Sort selected by confidence descending
        selected.sort(key=lambda x: x.confidence, reverse=True)
        return True, selected, rejected, None
