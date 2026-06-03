from pathlib import Path
import os
from openai import OpenAI

from models.facts import ExtractedFacts
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))


class FactExtractor:

    def __init__(self):
        self.prompt = Path(
            "src/prompts/fact_extraction.txt"
        ).read_text(
            encoding="utf-8"
        )

    def extract(
        self,
        text: str,
        source: str
    ) -> ExtractedFacts:

        prompt = self.prompt.format(
            document=text
        )

        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a medical fact extraction system."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format=ExtractedFacts
        )

        facts = response.choices[0].message.parsed

        for diagnosis in facts.diagnoses:
            diagnosis.source = source

        for med in facts.medications:
            med.source = source

        for allergy in facts.allergies:
            allergy.source = source

        for lab in facts.labs:
            lab.source = source

        for item in facts.pending_results:
            item.source = source

        return facts
