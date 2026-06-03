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

    # Step 1: Get all PDFs
    pdf_files = [
        f for f in os.listdir(PATIENT_DIR)
        if f.lower().endswith(".pdf")
    ]

    if not pdf_files:
        print("[ERROR] No PDFs found in", PATIENT_DIR)
        return

    # Step 2: PDF → OCR → Facts → Memory
    for file_name in pdf_files:
        pdf_path = os.path.join(PATIENT_DIR, file_name)
        print(f"\n[1] Reading: {file_name}")

        result = PDFReader.read(pdf_path)
        if not result:
            print(f"[SKIP] {file_name} failed to read")
            continue

        docs.append({
            "file": file_name,
            "text": result["full_text"]
        })

        print(f"[2] Extracting facts from: {file_name}")
        facts = extractor.extract(result["full_text"], source=file_name)

        print(f"    name : {facts.patient_name}")
        print(f"    diagnoses  : {len(facts.diagnoses)}")
        print(f"    medications: {len(facts.medications)}")
        print(f"    allergies  : {len(facts.allergies)}")
        print(f"    labs       : {len(facts.labs)}")

        memory.merge(facts, source=file_name)

    # Step 3: Check missing
    memory.check_missing()

    # Step 4: Print full memory
    print("\n========== PATIENT MEMORY ==========\n")
    print(json.dumps(memory.to_dict(), indent=2))

    # Step 5: Conflict summary
    if memory.conflicts:
        print(f"\n[!] {len(memory.conflicts)} CONFLICT(S) DETECTED")
        for c in memory.conflicts:
            print(f"    - {c.field}")
    else:
        print("\n[✓] No conflicts detected")

    # Step 6: Missing fields
    if memory.missing_fields:
        print(f"\n[!] {len(memory.missing_fields)} MISSING FIELD(S)")
        for m in memory.missing_fields:
            print(f"    - {m}")
    else:
        print("[✓] No missing required fields")

    # Step 7: Agent loop → Summary
    print("\n========== AGENT LOOP ==========")
    agent = DischargeAgent()
    summary = agent.run(memory, docs)

    print("\n========== DISCHARGE SUMMARY ==========\n")
    print(summary)


if __name__ == "__main__":
    run()
