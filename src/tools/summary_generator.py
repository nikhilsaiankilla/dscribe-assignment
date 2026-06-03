from pathlib import Path
from openai import OpenAI
from memory.patient_memory import PatientMemory
import json
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MISSING = "MISSING - CLINICIAN REVIEW REQUIRED"
CONFLICT = "CONFLICT DETECTED - CLINICIAN REVIEW REQUIRED"

MAX_REFINEMENT_STEPS = 3


class SummaryGenerator:

    def __init__(self):
        self.summary_prompt = Path(
            "src/prompts/summary.txt"
        ).read_text(encoding="utf-8")

    def generate(self, memory: PatientMemory) -> str:
        data = memory.to_dict()

        # Build fact block
        fact_block = self._build_fact_block(data)

        # Step 1: Ask agent what it needs before generating
        plan = self._plan(fact_block)
        print(f"\n  [Summary Agent] Plan: {plan['assessment']}")

        # Step 2: If agent flagged gaps, replan up to MAX_REFINEMENT_STEPS
        refinement = 0
        while plan.get("needs_clarification") and refinement < MAX_REFINEMENT_STEPS:
            refinement += 1
            print(
                f"  [Summary Agent] Refinement step {refinement}: {plan['missing']}")
            fact_block = self._resolve_gaps(fact_block, plan["missing"], data)
            plan = self._plan(fact_block)

        # Step 3: Generate final detailed summary
        summary = self._generate_summary(fact_block)
        return summary

    def _plan(self, fact_block: str) -> dict:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a clinical summary planning agent. "
                        "Review the facts and identify any critical gaps "
                        "before generating a discharge summary. "
                        "Respond in JSON only with keys: "
                        "assessment (string), needs_clarification (bool), missing (list of strings)."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Review these patient facts and identify critical gaps:\n\n{fact_block}\n\n"
                        "Critical fields: diagnoses, medications, admission_date, discharge_condition, pending_results.\n"
                        "Return JSON only."
                    )
                }
            ],
            response_format={"type": "json_object"}
        )
        try:
            return json.loads(response.choices[0].message.content)
        except Exception:
            return {
                "assessment": "Could not parse plan",
                "needs_clarification": False,
                "missing": []
            }

    def _resolve_gaps(self, fact_block: str, missing: list, data: dict) -> str:
        missing_notes = "\n".join(
            f"- {m}: {MISSING}" for m in missing
        )
        return fact_block + f"\n\nAGENT RESOLUTION NOTES:\n{missing_notes}"

    def _build_fact_block(self, data: dict) -> str:
        demo = data.get("demographics", {})
        diagnoses = self._format_list(data["diagnoses"], "value")
        medications = self._format_meds(data["medications"])
        allergies = self._format_list(data["allergies"], "value")
        labs = self._format_labs(data["labs"])
        pending = self._format_pending(data.get("pending_results", []))
        procedures = self._format_procedures(data.get("procedures", []))
        conflicts = data["conflicts"]
        missing = data["missing_fields"]
        recon = data.get("reconciliation", {})
        recon_block = self._format_reconciliation(recon)
        interactions = self._format_interactions(
            data.get("drug_interactions", {})
        )

        conflict_note = ""
        if conflicts:
            lines = [f"  - {c['field']}: {c['values']}" for c in conflicts]
            conflict_note = "CONFLICTS DETECTED:\n" + "\n".join(lines)

        return f"""
PATIENT DEMOGRAPHICS:
- Name: {demo.get('patient_name') or MISSING}
- Age: {demo.get('age') or MISSING}
- Gender: {demo.get('gender') or MISSING}
- Admission Date: {demo.get('admission_date') or MISSING}
- Discharge Date: {demo.get('discharge_date') or MISSING}
- Discharge Condition: {demo.get('discharge_condition') or MISSING}

DIAGNOSES:
{diagnoses or MISSING}

PROCEDURES:
{procedures or MISSING}

DISCHARGE MEDICATIONS:
{medications or MISSING}

ALLERGIES:
{allergies or MISSING}

LAB RESULTS:
{labs or MISSING}

PENDING RESULTS:
{pending or MISSING}

MEDICATION RECONCILIATION:
{recon_block or "Not performed"}
 
DRUG INTERACTIONS:
{interactions or "No known interactions detected"}

{conflict_note}

FLAGGED MISSING FIELDS:
{chr(10).join(missing) if missing else "None"}
""".strip()

    def _generate_summary(self, fact_block: str) -> str:
        prompt = self.summary_prompt.format(fact_block=fact_block)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior clinical documentation specialist. "
                        "Never hallucinate. Never infer. Only use provided facts."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        return response.choices[0].message.content

    def _format_list(self, items: list, key: str) -> str:
        if not items:
            return ""
        return "\n".join(
            f"- {item[key]} (source: {item.get('source', 'unknown')})"
            for item in items
        )

    def _format_meds(self, meds: list) -> str:
        if not meds:
            return ""
        lines = []
        for m in meds:
            dose = f" {m['dosage']}" if m.get("dosage") else ""
            freq = f", {m['frequency']}" if m.get("frequency") else ""
            dur = f", {m['duration']}" if m.get("duration") else ""
            med_type = f" [{m['type']}]" if m.get("type") else ""
            lines.append(
                f"- {m['name']}{dose}{freq}{dur}{med_type} "
                f"(source: {m.get('source', 'unknown')})"
            )
        return "\n".join(lines)

    def _format_labs(self, labs: list) -> str:
        if not labs:
            return ""
        lines = []
        for lab in labs:
            status = f" [{lab['status']}]" if lab.get("status") else ""
            lines.append(
                f"- {lab['test_name']}: {lab.get('value', 'N/A')}{status} "
                f"(source: {lab.get('source', 'unknown')})"
            )
        return "\n".join(lines)

    def _format_pending(self, items: list) -> str:
        if not items:
            return ""
        return "\n".join(
            f"- {item['test_name']}: {item['reason']} "
            f"(source: {item.get('source', 'unknown')})"
            for item in items
        )

    def _format_procedures(self, items: list) -> str:
        if not items:
            return ""
        if isinstance(items[0], str):
            return "\n".join(f"- {p}" for p in items)
        return "\n".join(
            f"- {item.get('name', item)} (source: {item.get('source', 'unknown')})"
            for item in items
        )

    def _format_reconciliation(self, recon: dict) -> str:
        if not recon:
            return ""
        lines = []
        for item in recon.get("added", []):
            lines.append(f"- ADDED: {item['name']} — {item['note']}")
        for item in recon.get("removed", []):
            lines.append(f"- STOPPED: {item['name']} — {item['note']}")
        for item in recon.get("changed", []):
            lines.append(
                f"- CHANGED: {item['name']} "
                f"({item['admission_dosage']} → {item['discharge_dosage']}) — {item['note']}"
            )
        for item in recon.get("untagged", []):
            lines.append(f"- UNTAGGED: {item['name']} — {item['note']}")
        return "\n".join(lines) if lines else "No changes detected"

    def _format_interactions(self, interactions: dict) -> str:
        if not interactions or not interactions.get("flagged"):
            return ""
        lines = []
        for item in interactions["flagged"]:
            lines.append(
                f"- {item['drug_a']} + {item['drug_b']}: "
                f"[{item['severity']}] {item['description']} — {item['action']}"
            )
        return "\n".join(lines)
