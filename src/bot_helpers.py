"""src/bot_helpers.py — yangi Certificate schema uchun."""
import json
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile, Message
from database import Certificate


def certificate_caption(cert: Certificate) -> str:
    """Telegram xabar uchun sertifikat matni."""
    # Manzil
    parts = [p for p in [cert.region_uz, cert.sub_region_uz, cert.address] if p]
    manzil = ", ".join(parts) if parts else "Noma'lum"

    # Faoliyat manzili
    act_addr = ""
    if cert.activity_addresses:
        try:
            addrs = json.loads(cert.activity_addresses)
            act_addr = "\n".join(f"  • {a}" for a in addrs if a) or ""
        except Exception:
            act_addr = cert.activity_addresses

    # Faoliyat turlari
    specs = ""
    if cert.specializations:
        try:
            names = json.loads(cert.specializations)
            specs = "\n".join(f"  • {s}" for s in names if s) or ""
        except Exception:
            specs = cert.specializations

    # Holat emoji
    status_emoji = "✅" if cert.active else "❌"
    status_text = cert.status or ("Faol" if cert.active else "Nofaol")

    lines = [
        f"📄 <b>Sertifikat</b>",
        f"",
        f"🏢 <b>Tashkilot:</b> {cert.name or 'Noma\'lum'}",
        f"🔢 <b>STIR:</b> {cert.tin or 'Noma\'lum'}",
        f"📋 <b>Hujjat raqami:</b> {cert.number or 'Noma\'lum'}",
        f"🔖 <b>Reg raqam:</b> {cert.register_number or '—'}",
        f"📅 <b>Taqdim etilgan:</b> {cert.registration_date or 'Noma\'lum'}",
        f"📆 <b>Muddati:</b> {cert.expiry_date or 'Belgilanmagan'}",
        f"📍 <b>Manzil:</b> {manzil}",
    ]

    if act_addr:
        lines += [f"🏭 <b>Faoliyat manzili:</b>", act_addr]

    if specs:
        lines += [f"📚 <b>Faoliyat turlari:</b>", specs]

    lines += [f"{status_emoji} <b>Holat:</b> {status_text}"]

    return "\n".join(lines)


async def send_pdf_document(message: Message, output_path: str, cert: Certificate):
    await message.answer_document(
        document=FSInputFile(output_path),
        caption=certificate_caption(cert),
        parse_mode=ParseMode.HTML,
    )