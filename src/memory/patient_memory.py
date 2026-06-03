from dataclasses import dataclass, field
from models.facts import ExtractedFacts


@dataclass
class ConflictRecord:
    field: str
    values: list[dict]  # [{"value": ..., "source": ...}]


@dataclass
class PatientMemory:
    demographics: dict = field(default_factory=dict)
    diagnoses: list[dict] = field(default_factory=list)
    medications: list[dict] = field(default_factory=list)
    allergies: list[dict] = field(default_factory=list)
    labs: list[dict] = field(default_factory=list)
    pending_results: list[dict] = field(default_factory=list)
    procedures: list = field(default_factory=list)        # ADD THIS
    conflicts: list[ConflictRecord] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    reconciliation: dict = field(default_factory=dict)
    reconciliation_done: bool = False
    drug_interactions: dict = field(default_factory=dict)
    drug_interaction_done: bool = False

    def merge(self, facts: ExtractedFacts, source: str = ""):
        # Demographics
        incoming_demo = {
            "patient_name": facts.patient_name,
            "age": facts.age,
            "gender": facts.gender,
            "admission_date": facts.admission_date,
            "discharge_date": facts.discharge_date,
        }
        for key, value in incoming_demo.items():
            if value and not self.demographics.get(key):
                self.demographics[key] = value

        self._merge_list("diagnoses", facts.diagnoses)
        self._merge_list("medications", facts.medications)
        self._merge_list("allergies", facts.allergies)
        self._merge_list("labs", facts.labs)

        # Pending results — always append, no dedup needed
        for item in facts.pending_results:
            item_dict = item.model_dump()
            if not item_dict.get("source"):
                item_dict["source"] = source
            self.pending_results.append(item_dict)

        if facts.discharge_condition and not self.demographics.get("discharge_condition"):
            self.demographics["discharge_condition"] = facts.discharge_condition

        for proc in (facts.procedures or []):
            if proc not in self.procedures:
                self.procedures.append(proc)

    def _merge_list(self, field_name: str, incoming: list):
        existing = getattr(self, field_name)

        for item in incoming:
            item_dict = item.model_dump()

            # Build a unique key per field type
            if field_name == "labs":
                key = f"{item_dict.get('test_name')}_{item_dict.get('value')}"
            else:
                key = item_dict.get("name") or item_dict.get("value")

            match = next(
                (e for e in existing
                 if (
                     f"{e.get('test_name')}_{e.get('value')}" if field_name == "labs"
                     else (e.get("name") or e.get("value"))
                 ) == key),
                None
            )

            if match is None:
                existing.append(item_dict)
            else:
                conflict_fields = [
                    k for k in item_dict
                    if k != "source"
                    and item_dict[k] != match.get(k)
                    and item_dict[k] is not None
                ]

                if conflict_fields:
                    self.conflicts.append(ConflictRecord(
                        field=f"{field_name}.{key}",
                        values=[
                            {k: match.get(k), "source": match.get("source")}
                            for k in conflict_fields
                        ] + [
                            {k: item_dict[k],
                                "source": item_dict.get("source")}
                            for k in conflict_fields
                        ]
                    ))

    def check_missing(self):
        # Demographics
        required_demo = ["patient_name", "age",
                         "gender", "admission_date", "discharge_date"]
        for field in required_demo:
            if not self.demographics.get(field):
                self.missing_fields.append(
                    f"demographics.{field} — MISSING - CLINICIAN REVIEW REQUIRED"
                )

        # Clinical fields
        required = ["diagnoses", "medications", "allergies"]
        for field in required:
            if not getattr(self, field):
                self.missing_fields.append(
                    f"{field} — MISSING - CLINICIAN REVIEW REQUIRED"
                )

    def to_dict(self) -> dict:
        return {
            "demographics": self.demographics,
            "diagnoses": self.diagnoses,
            "medications": self.medications,
            "allergies": self.allergies,
            "labs": self.labs,
            "pending_results": self.pending_results,
            "procedures": self.procedures,              # ADD THIS
            "conflicts": [
                {"field": c.field, "values": c.values}
                for c in self.conflicts
            ],
            "missing_fields": self.missing_fields,
            "reconciliation": self.reconciliation,
            "reconciliation_done": self.reconciliation_done,
            "drug_interactions": self.drug_interactions,
            "drug_interaction_done": self.drug_interaction_done,
        }
