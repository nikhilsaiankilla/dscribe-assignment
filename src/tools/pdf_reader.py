import base64
import hashlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic
import pypdfium2 as pdfium
import io

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

CACHE_DIR = Path("./cache")
CACHE_DIR.mkdir(exist_ok=True)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


class PDFReader:
    _client = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            cls._client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            )
        return cls._client

    @classmethod
    def get_cache_key(cls, pdf_path: Path) -> str:
        stat = pdf_path.stat()
        unique = f"{pdf_path.name}-{stat.st_size}-{stat.st_mtime}"
        return hashlib.md5(unique.encode()).hexdigest()

    @classmethod
    def load_cache(cls, cache_key: str) -> dict | None:
        cache_file = CACHE_DIR / f"{cache_key}.json"
        if cache_file.exists():
            logging.info("Cache hit — loading from disk")
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"Cache read failed, re-extracting: {e}")
                return None
        return None

    @classmethod
    def save_cache(cls, cache_key: str, data: dict):
        cache_file = CACHE_DIR / f"{cache_key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logging.info(f"Saved to cache: {cache_file}")
        except Exception as e:
            logging.warning(f"Cache save failed: {e}")

    @classmethod
    def page_to_base64(cls, page) -> str:
        bitmap = page.render(scale=2)
        image = bitmap.to_pil()
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")

    @classmethod
    def extract_page_text(cls, page_idx: int, pdf_path: str) -> tuple[int, str]:
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                doc = pdfium.PdfDocument(pdf_path)
                page = doc[page_idx]
                image_b64 = cls.page_to_base64(page)
                doc.close()

                client = cls.get_client()
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=4096,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": image_b64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": "Extract all text from this scanned document page. Output only the extracted text, no commentary.",
                                },
                            ],
                        }
                    ],
                )

                text = response.content[0].text.strip()
                logging.info(f"Done page {page_idx + 1}")
                return page_idx, text

            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    logging.warning(
                        f"Page {page_idx + 1} attempt {attempt} failed: {e} — retrying in {RETRY_DELAY}s"
                    )
                    time.sleep(RETRY_DELAY)
                else:
                    logging.error(
                        f"Page {page_idx + 1} failed after {MAX_RETRIES} attempts: {e}"
                    )

        return page_idx, ""

    @classmethod
    def read(cls, pdf_path: str) -> dict | None:
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            logging.error(f"PDF not found: {pdf_path}")
            return None

        # Check cache first — avoids duplicate Claude calls
        cache_key = cls.get_cache_key(pdf_path)
        cached = cls.load_cache(cache_key)
        if cached:
            return cached

        logging.info(f"Reading {pdf_path}")

        try:
            doc = pdfium.PdfDocument(str(pdf_path))
            page_count = len(doc)
            doc.close()
        except Exception as e:
            logging.error(f"Failed to open PDF {pdf_path}: {e}")
            return None

        pages = [None] * page_count
        failed_pages = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(
                    cls.extract_page_text, idx, str(pdf_path)
                ): idx
                for idx in range(page_count)
            }

            for future in as_completed(futures):
                try:
                    idx, text = future.result()
                    pages[idx] = {
                        "page": idx + 1,
                        "method": "claude-vision",
                        "text": text,
                    }
                    if not text:
                        failed_pages.append(idx + 1)
                except Exception as e:
                    idx = futures[future]
                    logging.error(f"Unexpected error on page {idx + 1}: {e}")
                    pages[idx] = {
                        "page": idx + 1,
                        "method": "claude-vision",
                        "text": "",
                    }
                    failed_pages.append(idx + 1)

        # Replace any None slots with empty page
        for i, p in enumerate(pages):
            if p is None:
                pages[i] = {"page": i + 1,
                            "method": "claude-vision", "text": ""}
                failed_pages.append(i + 1)

        full_text = "\n\n".join(
            f"PAGE {p['page']}\n{p['text']}" for p in pages if p["text"]
        )

        if not full_text.strip():
            logging.error(
                f"No text extracted from {pdf_path} — all pages failed")
            return None

        if failed_pages:
            logging.warning(
                f"{len(failed_pages)} page(s) failed and were skipped: {failed_pages}"
            )

        result = {
            "file_name": pdf_path.name,
            "page_count": page_count,
            "pages_failed": failed_pages,
            "pages": pages,
            "full_text": full_text,
        }

        cls.save_cache(cache_key, result)
        return result
