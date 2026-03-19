"""Shared helper functions for bot handlers."""
from typing import Any

from aiogram.enums import ParseMode
from aiogram.types import FSInputFile, Message

from database import Certificate


def to_db_certificate(cert: Any) -> Certificate:
    """Map parsed certificate-like object into DB model."""
    return Certificate(
        document_id=getattr(cert, "document_id", None),
        document_number=getattr(cert, "document_number", None),
        status=getattr(cert, "status", None),
        issue_date=getattr(cert, "issue_date", None),
        inserted_date=getattr(cert, "inserted_date", None),
        organization_name=getattr(cert, "organization_name", None),
        address=getattr(cert, "address", None),
        stir=getattr(cert, "stir", None),
        expiry_date=getattr(cert, "expiry_date", None),
        activity_type=getattr(cert, "activity_type", None),
        uuid=getattr(cert, "uuid", None),
        pdf_url=getattr(cert, "pdf_url", None),
    )


def certificate_caption(cert: Certificate) -> str:
    """Build unified PDF caption text."""
    return (
        "📄 <b>Сертфикат</b>\n\n"
        f"🏢 Ташкилот: {cert.organization_name or 'Номаълум'}\n"
        f"📋 Ҳужжат рақами: {cert.document_number or 'Номаълум'}\n"
        f"📅 Тақдим этилган сана: {cert.issue_date or 'Номаълум'}\n"
        f"🏠 Манзил: {cert.address or 'Номаълум'}\n"
        f"🔢 СТИР: {cert.stir or 'Номаълум'}\n"
        f"📆 Амал қилиш муддати: {cert.expiry_date or 'Номаълум'}\n"
        f"🔖 Фаолият тури: {cert.activity_type or 'Номаълум'}"
    )


async def safe_edit_text(message: Message, text: str):
    """Edit a message and ignore transient Telegram edit errors."""
    try:
        await message.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        return


async def send_pdf_document(message: Message, output_path: str, cert: Certificate):
    """Send generated PDF document with a consistent caption format."""
    await message.answer_document(
        document=FSInputFile(output_path),
        caption=certificate_caption(cert),
        parse_mode=ParseMode.HTML,
    )
