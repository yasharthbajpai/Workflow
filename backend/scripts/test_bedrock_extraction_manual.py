"""Ad hoc manual test for app/services/bedrock_extraction.py — run directly to
see whether Bedrock actually gets called or falls back to regex, and why.
Doesn't touch the database (uses a FakeDocument stand-in), so it can be run
without app.database eagerly creating an engine.

Run with: backend/.venv/bin/python -m scripts.test_bedrock_extraction_manual
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.services.bedrock_extraction import extract_document

logging.basicConfig(level=logging.INFO)

PACK_DIR = Path(__file__).resolve().parents[2]


class FakeDocument:
    """Stand-in for app.models.Document."""

    def __init__(self, id, filename, sender=None, subject=None, raw_text=None, image_bytes=None, mime_type=None):
        self.id = id
        self.filename = filename
        self.sender = sender
        self.subject = subject
        self.raw_text = raw_text
        self.image_bytes = image_bytes
        self.mime_type = mime_type


def _plain_text_of_eml(path: Path) -> tuple[str, str, str]:
    import email

    with path.open("rb") as f:
        msg = email.message_from_binary_file(f)
    if msg.is_multipart():
        parts = []
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                parts.append(payload.decode("utf-8", errors="ignore"))
        text = "\n".join(parts)
    else:
        text = (msg.get_payload(decode=True) or b"").decode("utf-8", errors="ignore")
    return text, msg.get("From") or "", msg.get("Subject") or ""


def main() -> None:
    print(f"BEDROCK_MODEL_ID configured: {settings.bedrock_model_id!r}")
    print(f"AWS_REGION: {settings.aws_region}")
    print(f"AWS_ACCESS_KEY_ID set: {bool(settings.aws_access_key_id)}\n")

    cases = []

    eml_path = PACK_DIR / "sample_emails" / "12_hotel_invoice.eml"
    text, sender, subject = _plain_text_of_eml(eml_path)
    cases.append(FakeDocument(id=1, filename=eml_path.name, sender=sender, subject=subject, raw_text=text))

    png_path = PACK_DIR / "receipts" / "hotel_invoice_1188.png"
    cases.append(
        FakeDocument(
            id=2, filename=png_path.name, subject="hotel invoice 1188", image_bytes=png_path.read_bytes(), mime_type="image/png"
        )
    )

    dinner_eml = PACK_DIR / "sample_emails" / "11_dinner_bill.eml"
    text2, sender2, subject2 = _plain_text_of_eml(dinner_eml)
    cases.append(FakeDocument(id=3, filename=dinner_eml.name, sender=sender2, subject=subject2, raw_text=text2))

    for doc in cases:
        print(f"=== {doc.filename} (id={doc.id}) ===")
        ext, mode = extract_document(doc)
        print(f"mode={mode}")
        print(
            f"doc_type={ext.doc_type} discard={ext.discard} reason={ext.discard_reason} "
            f"gross={ext.gross_amount} subtotal={ext.subtotal} tax_total={ext.tax_total}"
        )
        for li in ext.line_items or []:
            print(f"  line: {li.label} = {li.amount}")
        print()


if __name__ == "__main__":
    main()
