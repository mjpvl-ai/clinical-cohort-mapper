import re
from typing import Optional, List, Dict
from mapper.schemas import ClinicalIntent, Constraint

class MedicalLinguist:
    """Parses natural language cohort queries into structured clinical intent."""

    def __init__(self):
        # Mappings of query keywords to clinical domains
        self.domain_mappings = {
            'measurement': [
                'hba1c', 'a1c', 'glucose', 'cholesterol', 'ldl', 'egfr', 'gfr',
                'blood pressure', 'systolic', 'sbp', 'ecog', 'bmi', 'pregnancy test'
            ],
            'condition': [
                'diabetes', 't2d', 'kidney disease', 'ckd', 'heart failure',
                'copd', 'rheumatoid arthritis', 'arthritis'
            ],
            'drug': [
                'metformin', 'insulin', 'glp-1', 'atorvastatin', 'corticosteroid',
                'taking', 'prescribed', 'on'
            ],
            'procedure': [
                'colonoscopy', 'chemotherapy', 'chemo', 'treated with'
            ]
        }
        
        # Override domains for specific queries to handle overlaps
        self.exact_phrase_domains = {
            'colonoscopy': 'procedure',
            'chemotherapy': 'procedure',
            'prior chemotherapy': 'procedure',
            'currently taking metformin': 'drug',
            'treated with insulin': 'drug',
            'on glp-1 receptor agonists': 'drug',
            'prescribed atorvastatin': 'drug',
            'exposed to systemic corticosteroids': 'drug',
        }

    def parse(self, query: str, critique: Optional[Dict] = None) -> ClinicalIntent:
        """Parses a query by first running heuristics, then refining with medgemma."""
        # 1. Run baseline heuristic parsing
        intent = self._heuristic_parse(query, critique)
        
        # 2. LLM refinement using call_llm
        try:
            import json
            from mapper.llm import call_llm
            
            prompt = f"""You are a Medical Linguist agent. Refine this structured clinical intent parsed from the patient cohort query.
            
            Query: "{query}"
            Initial Extracted Entities: {intent.clinical_entities}
            Initial Extracted Synonyms: {intent.synonyms}
            Initial Domain: {intent.domain}
            Initial Constraint: {json.dumps(intent.constraint.dict() if intent.constraint else None)}
            Initial Status: {intent.status}
            
            {f"Critique from previous attempt: {json.dumps(critique)}" if critique else ""}
            
            Output a refined JSON object matching this schema exactly:
            {{
              "clinical_entities": ["refined main clinical entity names"],
              "synonyms": ["refined list of synonyms/abbreviations/related terms"],
              "domain": "one of: 'measurement', 'condition', 'drug', 'procedure'",
              "constraint": {{
                "operator": "'>' or '<' or '>=' or '<=' or '==' or 'in' or null",
                "value": number or list or string value or null,
                "unit": "unit string e.g. '%', 'mg/dL', 'mmHg', 'mL/min/1.73m²' or null"
              }},
              "status": "'current', 'prior', or 'any'"
            }}
            
            Rules:
            1. Ensure clinical accuracy.
            2. If critique suggests domain corrections or exclusions, apply them.
            3. Do not include excluded terms/synonyms.
            """
            
            content = call_llm(prompt, json_mode=True)
            data = json.loads(content)
            
            # Map back to Pydantic objects
            entities = data.get('clinical_entities', intent.clinical_entities)
            synonyms = data.get('synonyms', intent.synonyms)
            domain_raw = data.get('domain', intent.domain)
            
            # Normalize domain to match allowed literal types
            domain = "condition"
            if domain_raw:
                dom_lower = str(domain_raw).lower()
                if "measurement" in dom_lower or "lab" in dom_lower:
                    domain = "measurement"
                elif "condition" in dom_lower or "disease" in dom_lower or "diagnosis" in dom_lower:
                    domain = "condition"
                elif "drug" in dom_lower or "medication" in dom_lower:
                    domain = "drug"
                elif "procedure" in dom_lower or "surgery" in dom_lower:
                    domain = "procedure"
                elif "observation" in dom_lower:
                    domain = "observation"
                else:
                    domain = intent.domain
            else:
                domain = intent.domain
            constraint_data = data.get('constraint')
            
            constraint = None
            if constraint_data and constraint_data.get('operator'):
                from mapper.schemas import Constraint
                constraint = Constraint(
                    operator=constraint_data['operator'],
                    value=constraint_data['value'],
                    unit=constraint_data.get('unit')
                )
            elif intent.constraint:
                constraint = intent.constraint
                
            status = data.get('status', intent.status)
            
            # Keep negative constraints from critique
            neg_constraints = critique.get('suggested_exclusions', []) if critique else []
            
            return ClinicalIntent(
                original_query=query,
                clinical_entities=entities,
                synonyms=synonyms,
                domain=domain,
                constraint=constraint,
                status=status,
                negative_constraints=neg_constraints
            )
        except Exception as e:
            # Fallback to heuristic intent if LLM call fails
            return intent

    def _heuristic_parse(self, query: str, critique: Optional[Dict] = None) -> ClinicalIntent:
        """Parses a clinical query into a ClinicalIntent object using heuristics."""
        query_clean = query.strip()
        query_lower = query_clean.lower()
        
        # Determine Domain
        domain = "condition"  # Default
        
        # Check exact phrase overrides first
        matched_override = False
        for phrase, d in self.exact_phrase_domains.items():
            if phrase in query_lower:
                domain = d
                matched_override = True
                break
                
        if not matched_override:
            # Score each domain by keyword presence
            scores = {d: 0 for d in self.domain_mappings.keys()}
            for d, keywords in self.domain_mappings.items():
                for kw in keywords:
                    if kw in query_lower:
                        scores[d] += 1
            best_domain = max(scores, key=scores.get)
            if scores[best_domain] > 0:
                domain = best_domain
        
        # Extract Entities
        entities = []
        synonyms = []
        
        # Specific entity mapping rules
        if 'hba1c' in query_lower or 'a1c' in query_lower:
            entities = ['HbA1c']
            synonyms = ['A1c', 'glycated hemoglobin', 'glycohemoglobin']
        elif 'fasting glucose' in query_lower:
            entities = ['fasting glucose']
            synonyms = ['fasting blood sugar', 'FPG']
        elif 'glucose' in query_lower:
            entities = ['glucose']
            synonyms = ['blood sugar']
        elif 'ldl' in query_lower:
            entities = ['LDL cholesterol']
            synonyms = ['LDL', 'bad cholesterol']
        elif 'egfr' in query_lower or 'glomerular filtration' in query_lower:
            entities = ['eGFR']
            synonyms = ['estimated glomerular filtration rate', 'GFR']
        elif 'systolic' in query_lower or 'blood pressure' in query_lower:
            entities = ['systolic blood pressure']
            synonyms = ['SBP', 'blood pressure systolic']
        elif 'ecog' in query_lower:
            entities = ['ECOG performance status']
            synonyms = ['ECOG', 'performance status']
        elif 'bmi' in query_lower or 'body mass index' in query_lower:
            entities = ['BMI']
            synonyms = ['body mass index']
        elif 'pregnancy test' in query_lower:
            entities = ['pregnancy test']
            synonyms = ['hCG test', 'urine pregnancy test']
        elif 'type 2 diabetes' in query_lower or 'diabetes' in query_lower:
            entities = ['type 2 diabetes']
            synonyms = ['T2D', 'type 2 diabetes mellitus']
        elif 'kidney disease' in query_lower or 'ckd' in query_lower:
            entities = ['chronic kidney disease stage 3'] if 'stage 3' in query_lower else ['chronic kidney disease']
            synonyms = ['CKD', 'kidney disease']
        elif 'heart failure' in query_lower:
            entities = ['heart failure']
            synonyms = ['congestive heart failure', 'HF', 'CHF']
        elif 'copd' in query_lower:
            entities = ['COPD']
            synonyms = ['chronic obstructive pulmonary disease', 'COAD']
        elif 'rheumatoid arthritis' in query_lower:
            entities = ['rheumatoid arthritis']
            synonyms = ['RA', 'inflammatory arthritis']
        elif 'metformin' in query_lower:
            entities = ['metformin']
            synonyms = ['Glucophage']
        elif 'insulin' in query_lower:
            entities = ['insulin']
            synonyms = ['insulin exposure']
        elif 'glp-1' in query_lower:
            entities = ['GLP-1 receptor agonists']
            synonyms = ['glucagon-like peptide-1 receptor agonist', 'GLP1']
        elif 'atorvastatin' in query_lower:
            entities = ['atorvastatin']
            synonyms = ['Lipitor']
        elif 'corticosteroid' in query_lower:
            entities = ['systemic corticosteroids']
            synonyms = ['glucocorticoids', 'corticosteroids']
        elif 'colonoscopy' in query_lower:
            entities = ['colonoscopy']
            synonyms = ['endoscopy of colon']
        elif 'chemotherapy' in query_lower:
            entities = ['chemotherapy']
            synonyms = ['antineoplastic therapy', 'cancer chemo']
        else:
            # Fallback simple extraction
            # Try to grab the noun phrase after 'with' or 'diagnosed with'
            match = re.search(r'(?:with|diagnosed with|taking|on|prescribed)\s+([^><=0-9]+)', query_clean, re.IGNORECASE)
            if match:
                entities = [match.group(1).strip()]
            else:
                entities = [query_clean]

        # Dynamic database-driven synonym expansion
        try:
            from mapper.db import query_local_concepts
            for ent in entities:
                db_res = query_local_concepts(ent, domain)
                for item in db_res:
                    for s in item.get('synonyms', []):
                        if s.lower() not in [x.lower() for x in synonyms] and s.lower() not in [x.lower() for x in entities]:
                            synonyms.append(s)
        except Exception as e:
            pass

        # Parse Constraints
        constraint = None
        
        # 1. Operators and values (numerical)
        # Match pattern: above/greater than/less than/below etc. followed by value
        op_match = re.search(r'(above|greater than|greater than or equal to|below|less than|less than or equal to|>|>=|<|<=)\s*(\d+(?:\.\d+)?)', query_lower)
        if op_match:
            op_str = op_match.group(1)
            val = float(op_match.group(2))
            # Normalize float to int if it's a whole number
            if val.is_integer():
                val = int(val)
                
            # Map operator
            if op_str in ['above', 'greater than', '>']:
                op = '>'
            elif op_str in ['greater than or equal to', '>=']:
                op = '>='
            elif op_str in ['below', 'less than', '<']:
                op = '<'
            elif op_str in ['less than or equal to', '<=']:
                op = '<='
            else:
                op = '=='
                
            # Extract unit
            unit = None
            unit_match = re.search(r'\d+(?:\.\d+)?\s*(%|mg/dl|ml/min/1.73m²|ml/min/1.73m2|mmhg|kg/m²|kg/m2)', query_lower)
            if unit_match:
                unit = unit_match.group(1)
                # Normalize unit strings
                if '1.73m' in unit:
                    unit = 'mL/min/1.73m²'
                elif 'kg/' in unit:
                    unit = 'kg/m²'
                elif 'mg/dl' in unit:
                    unit = 'mg/dL'
                elif 'mmhg' in unit:
                    unit = 'mmHg'
            constraint = Constraint(operator=op, value=val, unit=unit)
            
        # 2. Categorical Constraints
        elif 'ecog' in query_lower and ('0 or 1' in query_lower or '0-1' in query_lower):
            constraint = Constraint(operator='in', value=[0, 1])
        elif 'positive' in query_lower:
            constraint = Constraint(operator='==', value='positive')
        elif 'negative' in query_lower:
            constraint = Constraint(operator='==', value='negative')

        # Determine Status
        status = "any"
        if any(w in query_lower for w in ['currently', 'current', 'taking', 'prescribed', 'active']):
            status = "current"
        elif any(w in query_lower for w in ['prior', 'past', 'history of', 'had a']):
            status = "prior"

        # Apply critique-based negative constraints or domain overrides on retry
        negative_constraints = []
        if critique:
            if 'suggested_domain' in critique and critique['suggested_domain']:
                raw_dom = str(critique['suggested_domain']).lower()
                if 'drug' in raw_dom or 'medication' in raw_dom:
                    domain = 'drug'
                elif 'condition' in raw_dom or 'disease' in raw_dom:
                    domain = 'condition'
                elif 'measurement' in raw_dom or 'lab' in raw_dom:
                    domain = 'measurement'
                elif 'procedure' in raw_dom or 'surgery' in raw_dom:
                    domain = 'procedure'
                elif 'observation' in raw_dom:
                    domain = 'observation'
                else:
                    domain = 'condition'
            if 'suggested_exclusions' in critique:
                negative_constraints = critique['suggested_exclusions']
                # Filter out synonyms/entities that might clash
                synonyms = [s for s in synonyms if s.lower() not in [x.lower() for x in negative_constraints]]

        return ClinicalIntent(
            original_query=query_clean,
            clinical_entities=entities,
            synonyms=synonyms,
            domain=domain,
            constraint=constraint,
            status=status,
            negative_constraints=negative_constraints
        )
