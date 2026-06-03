MISSING = "MISSING - CLINICIAN REVIEW REQUIRED"


class MedicationReconciliation:

    def reconcile(self, medications: list[dict]) -> dict:
        admission_meds = {
            m["name"].upper(): m
            for m in medications
            if m.get("type") == "admission"
        }
        discharge_meds = {
            m["name"].upper(): m
            for m in medications
            if m.get("type") == "discharge"
        }

        added = []
        removed = []
        changed = []
        unchanged = []
        untagged = []

        # Meds only in discharge — newly added
        for name, med in discharge_meds.items():
            if name not in admission_meds:
                added.append({
                    "name": med["name"],
                    "dosage": med.get("dosage"),
                    "note": "New at discharge — no admission record. Flag for reconciliation.",
                    "source": med.get("source")
                })

        # Meds only in admission — stopped at discharge
        for name, med in admission_meds.items():
            if name not in discharge_meds:
                removed.append({
                    "name": med["name"],
                    "dosage": med.get("dosage"),
                    "note": "On admission but not at discharge — stopped. Flag for reconciliation.",
                    "source": med.get("source")
                })

        # Meds in both — check for changes
        for name in admission_meds:
            if name in discharge_meds:
                adm = admission_meds[name]
                dis = discharge_meds[name]
                if adm.get("dosage") != dis.get("dosage"):
                    changed.append({
                        "name": adm["name"],
                        "admission_dosage": adm.get("dosage"),
                        "discharge_dosage": dis.get("dosage"),
                        "note": "Dosage changed — no reason documented. Flag for reconciliation.",
                        "source": dis.get("source")
                    })
                else:
                    unchanged.append({
                        "name": adm["name"],
                        "dosage": adm.get("dosage"),
                    })

        # Meds with no type tag
        for med in medications:
            if not med.get("type"):
                untagged.append({
                    "name": med["name"],
                    "note": "Medication type unknown (admission/discharge not identified). Flag for reconciliation.",
                    "source": med.get("source")
                })

        return {
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged,
            "untagged": untagged,
            "requires_review": len(added) + len(removed) + len(changed) + len(untagged) > 0
        }
