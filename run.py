import argparse
import json
import os
import sys
from typing import List

# Add current directory to path to ensure mapper module imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mapper.engine import MappingEngine

# Sample Queries from the Take-Home Assignment
SAMPLE_QUERIES = [
    "Patients with HbA1c above 7%",
    "Patients with fasting glucose greater than 126 mg/dL",
    "Patients with LDL cholesterol below 100 mg/dL",
    "Patients with eGFR less than 60 mL/min/1.73m²",
    "Patients with systolic blood pressure above 140 mmHg",
    "Patients diagnosed with type 2 diabetes",
    "Patients with chronic kidney disease stage 3",
    "Patients with heart failure",
    "Patients with COPD",
    "Patients with rheumatoid arthritis",
    "Patients currently taking metformin",
    "Patients treated with insulin",
    "Patients on GLP-1 receptor agonists",
    "Patients prescribed atorvastatin",
    "Patients exposed to systemic corticosteroids",
    "Patients who had a colonoscopy",
    "Patients with prior chemotherapy",
    "Patients with ECOG performance status 0 or 1",
    "Patients with BMI above 30",
    "Patients with a positive pregnancy test"
]

def serialize_result(result):
    """Utility to convert a MappingResult model into a standard JSON-compatible dict."""
    try:
        # Pydantic v2
        return json.loads(result.model_dump_json())
    except AttributeError:
        # Pydantic v1
        return json.loads(result.json())

def run_batch(engine: MappingEngine, output_file: str):
    """Runs mapping on all 20 sample queries, saves to JSON, and prints a summary."""
    print("=" * 60)
    print(f"Running CDGR Pipeline on {len(SAMPLE_QUERIES)} Sample Queries...")
    print("=" * 60)
    
    results = []
    
    # Print table header
    print(f"\n| # | Query | Domain | Target Vocab | Selected Code(s) | Conf | Logic |")
    print(f"|---|---|---|---|---|---|---|")
    
    import time
    for idx, query in enumerate(SAMPLE_QUERIES, 1):
        result = engine.map_query(query)
        serialized = serialize_result(result)
        results.append(serialized)
        
        # Sleep to respect Gemini API free tier rate limits (15 RPM)
        time.sleep(3)
        
        # Format list of selected codes for stdout display
        selected_codes_str = ", ".join([
            f"{c['vocabulary']}:{c['code']}" for c in serialized['selected_codes']
        ])
        if len(selected_codes_str) > 30:
            selected_codes_str = selected_codes_str[:27] + "..."
            
        vocab = serialized['selected_codes'][0]['vocabulary'] if serialized['selected_codes'] else "N/A"
        conf = serialized['selected_codes'][0]['confidence'] if serialized['selected_codes'] else 0.0
        
        # Display logic summary
        logic_summary = f"{serialized['final_logic']['concept']}: {serialized['final_logic']['condition']}"
        if len(logic_summary) > 30:
            logic_summary = logic_summary[:27] + "..."
            
        print(f"| {idx} | {query} | {serialized['interpreted_meaning']['domain']} | {vocab} | {selected_codes_str} | {conf} | {logic_summary} |")

    # Save to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
        
    print("=" * 60)
    print(f"Batch mapping complete. Detailed results saved to: {output_file}")
    print("=" * 60)

from mapper.telemetry import init_telemetry, shutdown_telemetry

def main():
    parser = argparse.ArgumentParser(description="Clinical Cohort Query Mapper (CDGR)")
    parser.add_argument('--query', type=str, help="Single natural language cohort query to map")
    parser.add_argument('--batch', action='store_true', help="Run mapping on all 20 sample assignment queries")
    parser.add_argument('--output', type=str, default='results.json', help="File path to save JSON results (for batch mode)")
    
    args = parser.parse_args()
    
    init_telemetry()
    try:
        engine = MappingEngine()
        if args.query:
            result = engine.map_query(args.query)
            serialized = serialize_result(result)
            print(json.dumps(serialized, indent=2))
        elif args.batch:
            run_batch(engine, args.output)
        else:
            parser.print_help()
    finally:
        shutdown_telemetry()

if __name__ == '__main__':
    main()
