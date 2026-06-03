import json
from pathlib import Path
from memory.patient_memory import PatientMemory
from agent.planner import Planner
from tools.fact_extractor import FactExtractor
from tools.summary_generator import SummaryGenerator
from traces.trace_logger import TraceLogger
from tools.medication_reconciliation import MedicationReconciliation
from tools.drug_interaction import DrugInteractionChecker

MAX_ITERATIONS = 10


class DischargeAgent:

    def __init__(self):
        self.planner = Planner()
        self.extractor = FactExtractor()
        self.generator = SummaryGenerator()
        self.reconciler = MedicationReconciliation()
        self.drug_checker = DrugInteractionChecker()

    def run(self, memory: PatientMemory, documents: list[dict], output_dir: Path = Path("outputs")) -> str:
        iteration = 0
        output_dir.mkdir(exist_ok=True, parents=True)

        # Instantiate trace logger explicitly targeted inside this patient's layout
        logger = TraceLogger(output_dir=output_dir)

        while iteration < MAX_ITERATIONS:
            iteration += 1
            plan = self.planner.plan(memory)

            print(f"\n[Agent Step {iteration}] Tool: {plan['tool']}")
            print(f"  Reason: {plan['reason']}")

            tool_input = {}
            tool_result = {}
            next_decision = ""

            if plan["tool"] == "extract_facts":
                tool_input = {"documents": [d["file"] for d in documents]}
                extracted = []
                for doc in documents:
                    try:
                        facts = self.extractor.extract(
                            doc["text"], source=doc["file"]
                        )
                        memory.merge(facts, source=doc["file"])
                        extracted.append({
                            "file": doc["file"],
                            "diagnoses": len(facts.diagnoses),
                            "medications": len(facts.medications),
                            "labs": len(facts.labs),
                        })
                    except Exception as e:
                        extracted.append({
                            "file": doc["file"],
                            "error": str(e)
                        })
                memory.check_missing()
                tool_result = {"extracted": extracted}
                next_decision = "Re-evaluate memory state after extraction"

            elif plan["tool"] == "flag_missing":
                field = plan.get("field", "unknown")
                tool_input = {"field": field}
                if field not in memory.missing_fields:
                    memory.missing_fields.append(
                        f"{field} — MISSING - CLINICIAN REVIEW REQUIRED"
                    )
                tool_result = {"flagged": field}
                next_decision = "Continue planning with updated missing fields"

            elif plan["tool"] == "flag_conflict":
                tool_input = {"conflicts": plan.get("conflicts", [])}
                tool_result = {
                    "conflicts_noted": len(plan.get("conflicts", [])),
                    "action": "Conflicts will be surfaced in summary"
                }
                next_decision = "Proceed to summary with conflicts flagged"

            elif plan["tool"] == "reconcile_medications":
                tool_input = {
                    "medication_count": len(memory.medications),
                    "medications": [m.get("name") for m in memory.medications]
                }
                try:
                    result = self.reconciler.reconcile(memory.medications)
                    memory.reconciliation = result
                    memory.reconciliation_done = True
                    tool_result = {
                        "added": len(result["added"]),
                        "removed": len(result["removed"]),
                        "changed": len(result["changed"]),
                        "untagged": len(result["untagged"]),
                        "requires_review": result["requires_review"],
                        "detail": result
                    }
                    next_decision = (
                        "Reconciliation complete — proceed to summary"
                        if not result["requires_review"]
                        else "Reconciliation flagged issues — surface in summary"
                    )
                    if result["requires_review"]:
                        print(
                            f"  [!] Reconciliation flagged "
                            f"{len(result['added'])} added, "
                            f"{len(result['removed'])} removed, "
                            f"{len(result['changed'])} changed, "
                            f"{len(result['untagged'])} untagged"
                        )
                except Exception as e:
                    tool_result = {"error": str(e)}
                    next_decision = "Reconciliation failed — flag for clinician review"
                    memory.missing_fields.append(
                        "medication_reconciliation — FAILED - CLINICIAN REVIEW REQUIRED"
                    )

            elif plan["tool"] == "check_drug_interactions":
                tool_input = {
                    "medication_count": len(memory.medications),
                    "medications": [m.get("name") for m in memory.medications]
                }
                try:
                    result = self.drug_checker.check(memory.medications)
                    memory.drug_interactions = result
                    memory.drug_interaction_done = True

                    if result["requires_escalation"]:
                        print(
                            f"  [!!!] HIGH severity interaction found — escalating")
                    elif result["interactions_found"] > 0:
                        print(
                            f"  [!] {result['interactions_found']} interaction(s) flagged")
                    else:
                        print(f"  [✓] No known interactions found")

                    tool_result = result
                    next_decision = (
                        "HIGH severity interaction — escalate to clinician before summary"
                        if result["requires_escalation"]
                        else "Interactions logged — proceed to summary"
                    )
                except Exception as e:
                    tool_result = {"error": str(e)}
                    next_decision = "Drug interaction check failed — flag for clinician review"
                    memory.missing_fields.append(
                        "drug_interaction_check — FAILED - CLINICIAN REVIEW REQUIRED"
                    )

                logger.log({
                    "step": iteration,
                    "reasoning": plan["reason"],
                    "tool": plan["tool"],
                    "input": tool_input,
                    "result": tool_result,
                    "next_decision": next_decision,
                })

            elif plan["tool"] == "generate_summary":
                tool_input = {
                    "memory_keys": list(memory.to_dict().keys()),
                    "diagnoses_count": len(memory.diagnoses),
                    "medications_count": len(memory.medications),
                    "missing_fields": memory.missing_fields,
                    "conflicts_count": len(memory.conflicts),
                    "pending_results_count": len(memory.pending_results),
                }
                try:
                    summary = self.generator.generate(memory)
                    summary_path = output_dir / "summary.txt"
                    summary_path.write_text(summary, encoding="utf-8")
                    print(f"\n[✓] Summary saved to {summary_path}")
                    tool_result = {
                        "status": "success",
                        "saved_to": str(summary_path),
                        "sections_generated": 10
                    }
                    next_decision = "Summary complete — agent loop done"

                    logger.log({
                        "step": iteration,
                        "reasoning": plan["reason"],
                        "tool": plan["tool"],
                        "input": tool_input,
                        "result": tool_result,
                        "next_decision": next_decision,
                    })
                    logger.save()
                    return summary

                except Exception as e:
                    tool_result = {"error": str(e)}
                    next_decision = "Summary generation failed — retry or escalate"
                    summary_path = output_dir / "summary.txt"
                    summary_path.write_text(
                        "SUMMARY GENERATION FAILED — CLINICIAN REVIEW REQUIRED",
                        encoding="utf-8"
                    )

            logger.log({
                "step": iteration,
                "reasoning": plan["reason"],
                "tool": plan["tool"],
                "input": tool_input,
                "result": tool_result,
                "next_decision": next_decision,
            })

        logger.save()
        fallback = "AGENT LOOP EXCEEDED MAX ITERATIONS — CLINICIAN REVIEW REQUIRED"
        (output_dir / "summary.txt").write_text(fallback, encoding="utf-8")
        return fallback
