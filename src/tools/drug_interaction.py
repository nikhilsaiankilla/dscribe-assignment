KNOWN_INTERACTIONS = {
    frozenset(["WARFARIN", "ASPIRIN"]): {
        "severity": "HIGH",
        "description": "Increased bleeding risk when combined.",
    },
    frozenset(["METFORMIN", "CONTRAST DYE"]): {
        "severity": "HIGH",
        "description": "Risk of lactic acidosis. Hold metformin before contrast.",
    },
    frozenset(["OFLOXACIN", "ANTACID"]): {
        "severity": "MODERATE",
        "description": "Antacids reduce absorption of ofloxacin. Separate by 2 hours.",
    },
    frozenset(["LOPIRAMIDE", "CLARITHROMYCIN"]): {
        "severity": "MODERATE",
        "description": "Increased loperamide levels — risk of cardiac effects.",
    },
    frozenset(["RACIPER", "CLOPIDOGREL"]): {
        "severity": "MODERATE",
        "description": "Proton pump inhibitors may reduce antiplatelet effect of clopidogrel.",
    },
    frozenset(["EMESET", "TRAMADOL"]): {
        "severity": "MODERATE",
        "description": "Combined serotonergic effect — monitor for serotonin syndrome.",
    },
}


class DrugInteractionChecker:

    def check(self, medications: list[dict]) -> dict:
        """
        Check all medication pairs for known interactions.
        Returns flagged interactions with severity and description.
        """
        names = [
            m.get("name", "").upper().replace(
                "TAB.", "").replace("TAB", "").strip()
            for m in medications
        ]

        flagged = []
        checked_pairs = set()

        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a = names[i]
                b = names[j]
                pair = frozenset([a, b])

                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)

                # Check direct match
                if pair in KNOWN_INTERACTIONS:
                    interaction = KNOWN_INTERACTIONS[pair]
                    flagged.append({
                        "drug_a": medications[i]["name"],
                        "drug_b": medications[j]["name"],
                        "severity": interaction["severity"],
                        "description": interaction["description"],
                        "action": "ESCALATE — CLINICIAN REVIEW REQUIRED"
                    })
                    continue

                # Check partial match (e.g. OFLOX TZ contains OFLOXACIN)
                for known_pair, interaction in KNOWN_INTERACTIONS.items():
                    known_list = list(known_pair)
                    match_a = any(k in a for k in known_list)
                    match_b = any(k in b for k in known_list)
                    if match_a and match_b:
                        flagged.append({
                            "drug_a": medications[i]["name"],
                            "drug_b": medications[j]["name"],
                            "severity": interaction["severity"],
                            "description": interaction["description"],
                            "action": "ESCALATE — CLINICIAN REVIEW REQUIRED"
                        })
                        break

        return {
            "interactions_found": len(flagged),
            "requires_escalation": any(
                f["severity"] == "HIGH" for f in flagged
            ),
            "flagged": flagged
        }
