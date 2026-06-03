from tools.pdf_reader import PDFReader
from tools.fact_extractor import FactExtractor
from memory.patient_memory import PatientMemory
from agent.discharge_agent import DischargeAgent
import json
import os

PATIENT_DIR = "data/patient_001"


def run():
    extractor = FactExtractor()
    memory = PatientMemory()
    docs = []

    pdf_files = [
        f for f in os.listdir(PATIENT_DIR)
        if f.lower().endswith(".pdf")
    ]

    if not pdf_files:
        print(f"[ERROR] No PDFs found in {PATIENT_DIR}")
        return

    for file_name in pdf_files:
        pdf_path = os.path.join(PATIENT_DIR, file_name)

        result = PDFReader.read(pdf_path)
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

    agent = DischargeAgent()
    summary = agent.run(memory, docs)

    print("\n========== DISCHARGE SUMMARY ==========\n")
    print(summary)


if __name__ == "__main__":
    run()
