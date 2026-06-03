import json
from openai import OpenAI
from memory.patient_memory import PatientMemory
import os
from dotenv import load_dotenv

load_dotenv()

AVAILABLE_TOOLS = [
    "extract_facts",
    "flag_missing",
    "flag_conflict",
    "reconcile_medications",
    "check_drug_interactions",
    "generate_summary",
]

SYSTEM_PROMPT = """You are a clinical AI agent planner. Your job is to decide the next tool to call based on the current patient memory state and what steps have already been taken.

Available tools:
- extract_facts: Extract clinical facts from raw PDF documents. Use this first if diagnoses are missing.
- flag_missing: Flag a required field as missing for clinician review. Requires "field" in your response.
- flag_conflict: Flag detected conflicts between documents for clinician review.
- reconcile_medications: Compare admission vs discharge medications and surface changes. Run after facts are extracted.
- check_drug_interactions: Check discharge medications for known drug interactions. Run after reconciliation.
- generate_summary: Generate the final discharge summary. Only call this when facts are extracted, reconciliation is done, and drug interactions are checked.

Rules:
- Never skip reconcile_medications or check_drug_interactions before generating the summary.
- Never fabricate or assume missing clinical data — flag it instead.
- If a conflict exists in memory and has not been flagged yet, call flag_conflict.
- If medications are missing entirely, call flag_missing with field="medications".
- Look at the step history to avoid repeating a tool that already succeeded.
- Always think step by step before deciding.

Respond ONLY with a valid JSON object. No explanation outside the JSON.
Format:
{
  "thinking": "<your step-by-step reasoning here>",
  "tool": "<tool name>",
  "reason": "<one sentence explanation for the agent trace>",
  "field": "<only include if tool is flag_missing>"
}"""


class Planner:

    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
        self.history: list[dict] = []

    def plan(self, memory: PatientMemory) -> dict | None:
        data = memory.to_dict()

        memory_summary = {
            "has_diagnoses": len(data.get("diagnoses", [])) > 0,
            "diagnoses_count": len(data.get("diagnoses", [])),
            "has_medications": len(data.get("medications", [])) > 0,
            "medications_count": len(data.get("medications", [])),
            "has_allergies": len(data.get("allergies", [])) > 0,
            "has_labs": len(data.get("labs", [])) > 0,
            "pending_results_count": len(data.get("pending_results", [])),
            "conflicts_count": len(data.get("conflicts", [])),
            "missing_fields": data.get("missing_fields", []),
            "reconciliation_done": data.get("reconciliation_done", False),
            "drug_interaction_done": data.get("drug_interaction_done", False),
            "demographics": {
                k: bool(v) for k, v in data.get("demographics", {}).items()
            },
        }

        user_message = f"""Current patient memory state:
{json.dumps(memory_summary, indent=2)}

Step history (what has already been done):
{json.dumps(self.history, indent=2) if self.history else "No steps taken yet."}

Decide the next tool to call."""

        print("\n[Planner] Thinking ", end="", flush=True)

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content
            result = json.loads(raw)

            thinking = result.get("thinking", "")
            tool = result.get("tool", "")
            reason = result.get("reason", "")

            # Print thinking like a streaming planner log
            print(f"\n[Planner] {thinking}")
            print(f"[Planner] → Decided: {tool}")
            print(f"[Planner] → Reason : {reason}")

            # Validate tool name
            if tool not in AVAILABLE_TOOLS:
                print(
                    f"[Planner] WARNING: Unknown tool '{tool}' — falling back to generate_summary")
                tool = "generate_summary"
                reason = "Planner returned unknown tool — falling back to summary"

            plan = {"tool": tool, "reason": reason}
            if result.get("field"):
                plan["field"] = result["field"]

            # Record this step in history for future planning context
            self.history.append({
                "tool": tool,
                "reason": reason,
            })

            return plan

        except Exception as e:
            print(f"\n[Planner] ERROR: LLM planning failed — {e}")
            print("[Planner] Falling back to rule-based plan")
            return self._fallback(data)

    def _fallback(self, data: dict) -> dict:
        """Rule-based fallback if LLM planner fails."""
        if not data.get("diagnoses"):
            return {"tool": "extract_facts", "reason": "Fallback: no diagnoses in memory"}
        if not data.get("medications"):
            return {"tool": "flag_missing", "reason": "Fallback: no medications in memory", "field": "medications"}
        if not data.get("reconciliation_done"):
            return {"tool": "reconcile_medications", "reason": "Fallback: reconciliation not done"}
        if not data.get("drug_interaction_done"):
            return {"tool": "check_drug_interactions", "reason": "Fallback: drug check not done"}
        return {"tool": "generate_summary", "reason": "Fallback: memory complete enough"}
