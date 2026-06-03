# Discharge Summary Agent

An agentic AI system that reads raw clinical source notes (PDFs) for a patient and produces a structured discharge summary draft for clinician review. The output is always a draft — never auto-finalized.

---

## What it does

Given a folder of patient PDFs (admission notes, progress notes, lab results, medication records), the agent:

1. Extracts text from each PDF using vision-based OCR
2. Parses structured clinical facts from the extracted text
3. Merges facts across all documents into a single patient memory
4. Detects conflicts and missing fields during the merge
5. Reconciles admission vs. discharge medications
6. Checks for drug interactions
7. Generates a structured discharge summary with all gaps and flags clearly marked

---

## Agent loop design

The planner is a **state-machine** — not an LLM replanning on every step. It inspects the current memory state and decides the next tool to call based on what is still incomplete.

The decision order is:

```
No diagnoses?         → extract_facts
No medications?       → flag_missing
Reconciliation done?  → reconcile_medications
Drug check done?      → check_drug_interactions
Otherwise             → generate_summary
```

A hard cap of **10 iterations** is enforced. If the agent hits this limit without completing, it writes a fallback message and exits — it never loops forever.

Every step emits a structured trace:

```
reasoning → tool chosen → inputs → result → next decision
```

Traces are saved to `outputs/trace.json` for full observability.

---

## PDF ingestion

PDFs are converted page-by-page to images using `pdfium`, then base64-encoded and sent to **Claude Haiku** (vision model) for text extraction.

Why vision instead of local OCR (e.g. Tesseract): the source documents include handwritten nurse charts and scanned forms. Local OCR models were too RAM-heavy and caused the machine to stall. Claude Haiku handles these reliably and keeps the pipeline fast.

Extracted text is cached per patient so the same PDF is never re-processed on re-runs.

---

## Fact extraction

Extracted text is passed to **GPT-4o-mini** using structured output parsing. Every fact (diagnosis, medication, allergy, lab result) is tagged with its source filename at extraction time, so the summary always knows which document a claim came from.

---

## No-fabrication guardrail

This is the most important safety property. The system enforces it at two levels:

**Prompt level** — the fact extraction prompt explicitly instructs the model never to infer, guess, or fill in missing values. If a field is not present in the document, it must be left null.

**Code level** — after extraction, `PatientMemory.check_missing()` scans all required fields. Any field that is null or absent is added to `missing_fields` with the label:

```
MISSING - CLINICIAN REVIEW REQUIRED
```

These flags appear verbatim in the final summary. The summary generator is also prompted to surface all flags and never resolve them silently.

---

## Conflict detection

When facts from multiple PDFs are merged into `PatientMemory`, the `_merge_list` method compares incoming values against existing ones by a unique key. If the same item exists in two documents with different field values (e.g. two different discharge diagnoses), a `ConflictRecord` is created and stored.

Conflicts are surfaced in the summary as-is — the agent never picks one version over the other.

---

## Medication reconciliation

`MedicationReconciliation` compares admission medications against discharge medications and produces four lists:

- **Added** — present at discharge, no admission record
- **Removed** — present at admission, absent at discharge
- **Changed** — same medication, different dosage
- **Untagged** — medication type could not be determined

Any medication in the first three lists gets flagged for clinician review with a note that no documented reason was found. The agent does not silently resolve these.

---

## Drug interaction checker

`DrugInteractionChecker` runs against the final discharge medication list. It uses a mocked interaction database for this submission. If a high-severity interaction is found, the agent escalates it — the interaction appears prominently in the summary and is not buried in a footnote.

---

## Failure handling

Every tool call is wrapped in a `try/except`. If a tool fails:

- The error is logged in the trace
- A `MISSING - CLINICIAN REVIEW REQUIRED` flag is added to memory for that field
- The agent continues planning — it does not crash or behave as if the call succeeded

Summary generation failure writes a hard fallback:

```
SUMMARY GENERATION FAILED — CLINICIAN REVIEW REQUIRED
```

---

## Output

For each patient the system produces:

- `outputs/summary.txt` — the structured discharge summary draft
- `outputs/trace.json` — the full step-by-step agent trace

---

## How to run

```bash
# Install dependencies
pip install -r requirements.txt

# Set your API keys
export OPENAI_API_KEY=your_key
export ANTHROPIC_API_KEY=your_key

# Point to a patient folder and run
# Edit PATIENT_DIR in main.py to your patient folder path
python main.py
```

Patient PDFs should be placed in a folder under `data/`, e.g. `data/patient_001/`.

---

## Stack

| Component        | Technology                        |
| ---------------- | --------------------------------- |
| PDF → image      | pdfium                            |
| OCR / vision     | Claude Haiku (`claude-haiku-4-5`) |
| Fact extraction  | GPT-4o-mini (structured outputs)  |
| Drug interaction | Mocked database                   |
| Language         | Python                            |
| Frameworks       | None — built from scratch         |

---

## Part 2 — Learning from doctor edits

Not attempted in this submission. See "What I'd do with more time" below.

---

## Limitations

**Rule-based planner** — the planner uses `if/else` logic on memory state rather than dynamic LLM replanning. This means it follows a fixed execution order and cannot adapt mid-loop if, for example, a late-stage document changes an earlier conclusion. A proper agentic planner would re-evaluate the full state after each step.

**Single patient at a time** — the system currently runs on one `PATIENT_DIR` at a time. Batch processing across a patient set is not implemented.

**Mocked drug interactions** — the interaction checker uses hardcoded data. A production system would call a real pharmacological database (e.g. DrugBank, OpenFDA).

**No cross-patient memory** — the agent has no memory across patients. Each run starts fresh.

**OCR quality** — for heavily degraded or low-resolution scans, Claude Haiku may miss or misread content. There is no confidence score or fallback for low-quality extractions.

---

## What I'd do with more time

- Replace the rule-based planner with an LLM-driven replanner that re-evaluates state after each step
- Add batch patient support with a summary report across all patients
- Integrate a real drug interaction API
- Add a confidence score to extracted facts, with low-confidence items auto-flagged
- Implement Part 2: a simulated doctor reviewer that generates (draft, edited) pairs, with edit distance as the reward signal and a correction-memory mechanism injected into future prompts
- Add an evaluation harness to measure section accuracy across patients
