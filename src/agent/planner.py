from memory.patient_memory import PatientMemory


class Planner:

    def plan(self, memory: PatientMemory) -> dict | None:
        data = memory.to_dict()

        if not data["diagnoses"]:
            return {
                "tool": "extract_facts",
                "reason": "No diagnoses found in memory"
            }

        if not data["medications"]:
            return {
                "tool": "flag_missing",
                "reason": "No discharge medications found",
                "field": "medications"
            }

        if not data.get("reconciliation_done"):
            return {
                "tool": "reconcile_medications",
                "reason": "Medication reconciliation not yet performed"
            }

        if not data.get("drug_interaction_done"):
            return {
                "tool": "check_drug_interactions",
                "reason": "Drug interaction check not yet performed"
            }

        return {
            "tool": "generate_summary",
            "reason": "Memory complete enough for summary generation"
        }
