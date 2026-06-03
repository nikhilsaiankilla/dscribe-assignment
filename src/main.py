from tools.pdf_reader import PDFReader
from tools.fact_extractor import FactExtractor
from memory.patient_memory import PatientMemory
from agent.discharge_agent import DischargeAgent
from pathlib import Path
import os

PATIENT_DIR = "data/patient_001"


def run():
    # Dynamically extract the patient subfolder name
    patient_path = Path(PATIENT_DIR)
    patient_id = patient_path.name  # Extracts 'patient_001'

    # Build separated dynamic cache and output paths
    cache_dir = Path("cache") / patient_id
    output_dir = Path("outputs") / patient_id

    extractor = FactExtractor()
    memory = PatientMemory()
    docs = []

    if not patient_path.exists():
        print(f"[ERROR] Directory {PATIENT_DIR} does not exist.")
        return

    pdf_files = [
        f for f in os.listdir(PATIENT_DIR)
        if f.lower().endswith(".pdf")
    ]

    if not pdf_files:
        print(f"[ERROR] No PDFs found in {PATIENT_DIR}")
        return

    for file_name in pdf_files:
        pdf_path = patient_path / file_name

        # Explicitly passing patient specific cache directory down
        result = PDFReader.read(str(pdf_path), cache_dir=cache_dir)
        if not result:
            print(f"[WARNING] Failed to read {file_name}")
            continue

        docs.append({
            "file": file_name,
            "text": result["full_text"]
        })

        facts = extractor.extract(
            result["full_text"],
            source=file_name
        )

        memory.merge(
            facts,
            source=file_name
        )

    memory.check_missing()

    if memory.conflicts:
        print(f"\n[WARNING] {len(memory.conflicts)} conflict(s) detected")

    if memory.missing_fields:
        print(
            f"\n[WARNING] Missing fields: {', '.join(memory.missing_fields)}")

    # Execute Discharge Agent with the patient's exclusive output target directory
    agent = DischargeAgent()
    summary = agent.run(memory, docs, output_dir=output_dir)

    print("\n========== DISCHARGE SUMMARY ==========\n")
    print(summary)


if __name__ == "__main__":
    run()
