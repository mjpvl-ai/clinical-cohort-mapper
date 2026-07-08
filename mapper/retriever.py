import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from mapper.db import query_local_concepts
from mapper.schemas import CandidateCode, ClinicalIntent

logger = logging.getLogger(__name__)


class MedicalInformatician:
    """Retrieves terminology candidates from local database and public NLM/RxNorm APIs."""

    def __init__(self):
        self.user_agent = "Clinical-Mapper-Prototype/0.1"

    def _http_get(self, url: str) -> dict[str, Any] | None:
        """Performs a GET request and returns parsed JSON or None on failure."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"HTTP GET failed for {url}: {e}")
            return None

    def retrieve_candidates(self, intent: ClinicalIntent) -> list[CandidateCode]:
        """Orchestrates candidate retrieval, running programmatic search followed by LLM filtering."""
        unique_candidates = self._retrieve_candidates_programmatic(intent)

        # LLM Candidate Filtering using call_llm
        try:
            import json

            from mapper.llm import call_llm

            candidates_data = [
                {"vocabulary": c.vocabulary, "code": c.code, "display": c.display}
                for c in unique_candidates
            ]
            prompt = f"""You are a Medical Informatician agent. Review these retrieved candidate codes for the patient cohort query.
            
            Query: "{intent.original_query}"
            Clinical Intent Domain: {intent.domain}
            
            Retrieved Candidate Codes:
            {json.dumps(candidates_data, indent=2)}
            
            Return a JSON object containing a filtered list of only the clinically relevant candidate codes:
            {{
              "relevant_codes": [
                {{
                  "vocabulary": "vocabulary name",
                  "code": "code value",
                  "display": "display name"
                }}
              ]
            }}
            
            Rules:
            1. Keep only codes that directly relate to the clinical entities and domain.
            2. Remove obvious metadata or device/software description codes (e.g. 'HbA1c Measurement Device Serial #').
            3. Do not add any new codes; only filter the list provided.
            """

            content = call_llm(prompt, json_mode=True)
            data = json.loads(content)
            filtered_codes = data.get("relevant_codes", [])

            # Map back to CandidateCode objects
            refined_candidates = []
            seen = set()
            for fc in filtered_codes:
                k = (fc["vocabulary"], fc["code"])
                if k not in seen:
                    # Find original candidate to preserve exact details if needed
                    orig = next(
                        (
                            c
                            for c in unique_candidates
                            if c.vocabulary == fc["vocabulary"] and c.code == fc["code"]
                        ),
                        None,
                    )
                    if orig:
                        refined_candidates.append(orig)
                    else:
                        refined_candidates.append(
                            CandidateCode(
                                vocabulary=fc["vocabulary"],
                                code=fc["code"],
                                display=fc["display"],
                                rank=len(refined_candidates) + 1,
                            )
                        )
                    seen.add(k)

            # If refinement list is not empty, use it
            if refined_candidates:
                # Assign ranks
                for idx, c in enumerate(refined_candidates, 1):
                    c.rank = idx
                return refined_candidates
        except Exception:
            pass

        return unique_candidates

    def _retrieve_candidates_programmatic(self, intent: ClinicalIntent) -> list[CandidateCode]:
        """Orchestrates candidate retrieval based on domain and parsed entities using local DB and public APIs."""
        candidates = []
        seen_codes = set()

        # Expand search terms and synonyms to include base concepts (e.g. stage-stripped terms)
        import re

        search_terms = []
        for entity in intent.clinical_entities:
            search_terms.append(entity)
            if "stage" in entity.lower():
                base = re.sub(r"\bstage\s+\w+\b", "", entity, flags=re.IGNORECASE).strip()
                base = re.sub(r"\s+", " ", base)
                if base and base not in search_terms:
                    search_terms.append(base)

        expanded_syns = []
        for syn in intent.synonyms:
            expanded_syns.append(syn)
            if "stage" in syn.lower():
                base = re.sub(r"\bstage\s+\w+\b", "", syn, flags=re.IGNORECASE).strip()
                base = re.sub(r"\s+", " ", base)
                if base and base not in expanded_syns:
                    expanded_syns.append(base)

        # 1. Search local SQLite vocabulary cache first
        for entity in search_terms:
            local_results = query_local_concepts(entity, intent.domain)
            for item in local_results:
                code_key = (item["vocabulary"], item["code"])
                if code_key not in seen_codes:
                    seen_codes.add(code_key)
                    candidates.append(
                        CandidateCode(
                            vocabulary=item["vocabulary"],
                            code=item["code"],
                            display=item["display"],
                            rank=len(candidates) + 1,
                        )
                    )

            # Also search by synonyms locally
            for syn in expanded_syns:
                local_results = query_local_concepts(syn, intent.domain)
                for item in local_results:
                    code_key = (item["vocabulary"], item["code"])
                    if code_key not in seen_codes:
                        seen_codes.add(code_key)
                        candidates.append(
                            CandidateCode(
                                vocabulary=item["vocabulary"],
                                code=item["code"],
                                display=item["display"],
                                rank=len(candidates) + 1,
                            )
                        )

        # 2. Query Public APIs if needed or for additional coverage
        if intent.domain == "drug":
            candidates.extend(self._retrieve_drugs(intent, seen_codes))
        elif intent.domain == "condition":
            candidates.extend(self._retrieve_conditions(intent, seen_codes))
        elif intent.domain == "measurement":
            candidates.extend(self._retrieve_measurements(intent, seen_codes))

        # Deduplicate and sort by rank
        unique_candidates = []
        seen = set()
        for c in candidates:
            k = (c.vocabulary, c.code)
            if k not in seen:
                seen.add(k)
                c.rank = len(unique_candidates) + 1
                unique_candidates.append(c)

        return unique_candidates

    def _retrieve_drugs(self, intent: ClinicalIntent, seen_codes: set) -> list[CandidateCode]:
        """Queries RxNorm and RxClass APIs for drug codes."""
        candidates = []

        for entity in intent.clinical_entities:
            # Check if it looks like a class (e.g. GLP-1 receptor agonists, corticosteroids)
            is_class = any(
                w in entity.lower()
                for w in ["agonist", "corticosteroid", "inhibitor", "blocker", "class"]
            )

            if is_class:
                # 1. Search for Class ID using RxClass
                class_search_term = entity
                # Clean class term for search
                if "systemic" in class_search_term.lower():
                    class_search_term = class_search_term.lower().replace("systemic", "").strip()
                if "receptor" in class_search_term.lower():
                    class_search_term = class_search_term.lower().replace("receptor", "").strip()

                if "corticosteroid" in class_search_term.lower():
                    concepts = [
                        {
                            "classId": "N0000175576",
                            "className": "Corticosteroid",
                            "classType": "EPC",
                        }
                    ]
                elif "glp-1" in class_search_term.lower():
                    concepts = [
                        {
                            "classId": "N0000178480",
                            "className": "GLP-1 Receptor Agonist",
                            "classType": "EPC",
                        }
                    ]
                else:
                    url = f"https://rxnav.nlm.nih.gov/REST/rxclass/class/byName.json?className={urllib.parse.quote(class_search_term)}"
                    data = self._http_get(url)
                    concepts = (
                        data.get("rxclassMinConceptList", {}).get("rxclassMinConcept", [])
                        if data
                        else []
                    )

                for c in concepts:
                    class_id = c["classId"]
                    class_type = c["classType"]
                    # Map classType to the correct relaSource (typically FDASPL or ATC)
                    rela_source = "FDASPL" if class_type == "EPC" else "ATC"

                    # Fetch class members
                    members_url = f"https://rxnav.nlm.nih.gov/REST/rxclass/classMembers.json?classId={class_id}&relaSource={rela_source}"
                    members_data = self._http_get(members_url)

                    members = (
                        members_data.get("drugMemberGroup", {}).get("drugMember", [])
                        if members_data
                        else []
                    )

                    # If empty with FDASPL, try ATC
                    if not members and rela_source == "FDASPL":
                        members_url = f"https://rxnav.nlm.nih.gov/REST/rxclass/classMembers.json?classId={class_id}&relaSource=ATC"
                        members_data = self._http_get(members_url)
                        members = (
                            members_data.get("drugMemberGroup", {}).get("drugMember", [])
                            if members_data
                            else []
                        )

                    for m in members:
                        rxcui = m["minConcept"]["rxcui"]
                        name = m["minConcept"]["name"]
                        code_key = ("RxNorm", rxcui)
                        if code_key not in seen_codes:
                            seen_codes.add(code_key)
                            candidates.append(
                                CandidateCode(
                                    vocabulary="RxNorm",
                                    code=rxcui,
                                    display=name,
                                    rank=len(candidates) + 1,
                                )
                            )
            else:
                # 2. Specific Drug lookup in RxNorm (approximateTerm)
                url = f"https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term={urllib.parse.quote(entity)}&maxResults=5"
                data = self._http_get(url)

                candidates_list = (
                    data.get("approximateGroup", {}).get("candidate", []) if data else []
                )
                for c in candidates_list:
                    rxcui = c.get("rxcui")
                    name = c.get("name")
                    # If name is missing, query properties
                    if not name and rxcui:
                        prop_url = f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json"
                        prop_data = self._http_get(prop_url)
                        name = (
                            prop_data.get("properties", {}).get("name", "Unknown drug")
                            if prop_data
                            else "Unknown drug"
                        )

                    if rxcui and name:
                        code_key = ("RxNorm", rxcui)
                        if code_key not in seen_codes:
                            seen_codes.add(code_key)
                            candidates.append(
                                CandidateCode(
                                    vocabulary="RxNorm",
                                    code=rxcui,
                                    display=name,
                                    rank=len(candidates) + 1,
                                )
                            )

        return candidates

    def _retrieve_conditions(self, intent: ClinicalIntent, seen_codes: set) -> list[CandidateCode]:
        """Queries NLM Clinical Tables search for ICD-10-CM codes."""
        candidates = []

        import re

        search_terms = []
        for entity in intent.clinical_entities:
            search_terms.append(entity)
            if "stage" in entity.lower():
                base = re.sub(r"\bstage\s+\w+\b", "", entity, flags=re.IGNORECASE).strip()
                base = re.sub(r"\s+", " ", base)
                if base and base not in search_terms:
                    search_terms.append(base)

        for entity in search_terms:
            # Query ICD-10-CM search API
            # Match code first, then name
            url = f"https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search?terms={urllib.parse.quote(entity)}&sf=code,name&maxResults=5"
            data = self._http_get(url)

            if data and len(data) >= 4:
                codes_list = data[1]
                displays_list = data[3]
                for code, display_arr in zip(codes_list, displays_list, strict=False):
                    desc = display_arr[1] if len(display_arr) > 1 else display_arr[0]
                    code_key = ("ICD-10-CM", code)
                    if code_key not in seen_codes:
                        seen_codes.add(code_key)
                        candidates.append(
                            CandidateCode(
                                vocabulary="ICD-10-CM",
                                code=code,
                                display=desc,
                                rank=len(candidates) + 1,
                            )
                        )

        return candidates

    def _retrieve_measurements(
        self, intent: ClinicalIntent, seen_codes: set
    ) -> list[CandidateCode]:
        """Queries NLM Clinical Tables search for LOINC codes."""
        candidates = []

        for entity in intent.clinical_entities:
            # Query LOINC search API
            url = f"https://clinicaltables.nlm.nih.gov/api/loinc_items/v3/search?terms={urllib.parse.quote(entity)}&maxResults=5"
            data = self._http_get(url)

            if data and len(data) >= 4:
                codes_list = data[1]
                displays_list = data[3]
                for code, display_arr in zip(codes_list, displays_list, strict=False):
                    desc = display_arr[0]
                    code_key = ("LOINC", code)
                    if code_key not in seen_codes:
                        seen_codes.add(code_key)
                        candidates.append(
                            CandidateCode(
                                vocabulary="LOINC",
                                code=code,
                                display=desc,
                                rank=len(candidates) + 1,
                            )
                        )

        return candidates
