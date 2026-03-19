"""
src/bot.py
Har bir page dan keyin darrov bazaga kiritiladi.
Xato bo'lsa oldingi pagelar saqlanib qoladi.
"""
import asyncio
import os
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from loguru import logger

from database import Database, Certificate
from parser_v3 import LicenseParserV3 as LicenseParser
from bot_helpers import send_pdf_document
from settings import (
    TARGET_ACTIVITY_TYPE,
    DOWNLOAD_DIR,
    SCRAPE_UPDATE_EVERY_PAGES,
    DOWNLOAD_PROGRESS_EVERY_ITEMS,
    DOWNLOAD_ITEM_DELAY_SECONDS,
    parse_admin_ids,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi")

ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", ""))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()

parser: Optional[LicenseParser] = None
scrape_lock = asyncio.Lock()


# ── Keyboards ─────────────────────────────────────────────────────────────────

def get_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📥 Барча сертификатларни йиғиш", callback_data="scrape_all"
    ))
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="stats"))
    builder.row(InlineKeyboardButton(
        text="📄 PDF юклаш (саралганлар)", callback_data="download_pdfs"
    ))
    return builder.as_markup()


def get_confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Ҳа", callback_data=f"confirm_{action}"),
        InlineKeyboardButton(text="❌ Йўқ", callback_data="cancel"),
    )
    return builder.as_markup()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_admin(user_id: int) -> bool:
    return not ADMIN_IDS or user_id in ADMIN_IDS


# ── Handlers ──────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not _check_admin(message.from_user.id):
        await message.answer("❌ Ruxsat yo'q.")
        return
    stats = await db.get_stats()
    await message.answer(
        f"👋 Salom, {message.from_user.full_name}!\n\n"
        f"📋 <b>Litsenziya bot</b>\n\n"
        f"Hozirgi holat:\n"
        f"• Jami: <b>{stats['total_certificates']}</b> ta\n"
        f"• «{TARGET_ACTIVITY_TYPE}»: <b>{stats['filtered_certificates']}</b> ta\n"
        f"• Faol: <b>{stats['active_certificates']}</b> ta\n\n"
        f"Amalni tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not _check_admin(message.from_user.id):
        return
    stats = await db.get_stats()
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"Jami: <b>{stats['total_certificates']}</b>\n"
        f"Saralgan: <b>{stats['filtered_certificates']}</b>\n"
        f"Faol: <b>{stats['active_certificates']}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


@dp.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery):
    await callback.answer()
    stats = await db.get_stats()
    await callback.message.edit_text(
        f"📊 <b>Statistika</b>\n\n"
        f"Jami: <b>{stats['total_certificates']}</b>\n"
        f"Saralgan («{TARGET_ACTIVITY_TYPE}»): <b>{stats['filtered_certificates']}</b>\n"
        f"Faol: <b>{stats['active_certificates']}</b>\n\n"
        f"Amalni tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


@dp.callback_query(F.data == "scrape_all")
async def cb_scrape(callback: CallbackQuery):
    await callback.answer()
    if scrape_lock.locked():
        await callback.message.answer("⚠️ Jarayon davom etmoqda, kuting...")
        return
    await callback.message.edit_text(
        "📥 <b>Barcha sertifikatlarni yig'ish</b>\n\n"
        f"API dan barcha ma'lumotlar olinadi.\n"
        f"Har bir sahifadan keyin darrov bazaga yoziladi.\n"
        f"«{TARGET_ACTIVITY_TYPE}» bo'yicha avtomatik saralanadi.\n\n"
        "Davom ettirasizmi?",
        parse_mode=ParseMode.HTML,
        reply_markup=get_confirm_keyboard("scrape")
    )


@dp.callback_query(F.data == "confirm_scrape")
async def cb_confirm_scrape(callback: CallbackQuery):
    await callback.answer()
    global parser

    progress_msg = await callback.message.edit_text(
        "🚀 <b>Yig'ish boshlandi...</b>\n\n"
        "📄 Sahifa: <b>0/0</b>\n"
        "💾 Saqlandi: <b>0</b>\n"
        "🎓 Saralandi: <b>0</b>\n\n"
        "⏳ Kuting...",
        parse_mode=ParseMode.HTML
    )

    async with scrape_lock:
        try:
            parser = LicenseParser()
            await parser.init_browser(headless=True)

            # Kauntlar
            total_saved    = 0
            total_filtered = 0
            current_page   = 0
            total_pages    = 0

            async def on_page_done(page: int, total: int, page_certs: list):
                """Har bir page tugagach: DB ga yoz, progress yangilash."""
                nonlocal total_saved, total_filtered, current_page, total_pages
                current_page = page
                total_pages  = total

                # Shu page dagi sertifikatlarni darrov bazaga kiritamiz
                for cert in page_certs:
                    await db.upsert_certificate(cert)
                    total_saved += 1

                # Filtered soni
                total_filtered = await db.count_filtered_certificates()

                # Progress xabarini yangilash (har N sahifada yoki oxirida)
                if page % SCRAPE_UPDATE_EVERY_PAGES == 0 or page == total:
                    try:
                        await progress_msg.edit_text(
                            f"🚀 <b>Yig'ish davom etmoqda...</b>\n\n"
                            f"📄 Sahifa: <b>{page}/{total}</b>\n"
                            f"💾 Saqlandi: <b>{total_saved}</b>\n"
                            f"🎓 Saralandi: <b>{total_filtered}</b>\n\n"
                            f"⏳ Kuting...",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass

            # scrape_all endi har page uchun callback chaqiradi
            # callback ichida page_certs bo'lishi uchun parser_v3 ni moslashtirdik
            await parser.scrape_all(on_page_done)

            # Yakuniy statistika
            total_in_db    = await db.count_certificates()
            filtered_in_db = await db.count_filtered_certificates()

            await progress_msg.edit_text(
                f"✅ <b>Yig'ish yakunlandi!</b>\n\n"
                f"📄 Sahifalar: <b>{current_page}/{total_pages}</b>\n"
                f"💾 Saqlandi: <b>{total_saved}</b>\n"
                f"🎓 Saralandi («{TARGET_ACTIVITY_TYPE}»): <b>{filtered_in_db}</b>\n"
                f"📊 Bazada jami: <b>{total_in_db}</b>\n\n"
                f"Amalni tanlang:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )

        except Exception as e:
            logger.error(f"Scraping xato: {e}")
            # Xato bo'lsa ham saqlangan ma'lumotlar qoladi
            saved_so_far = await db.count_certificates()
            await progress_msg.edit_text(
                f"❌ <b>Xatolik yuz berdi!</b>\n\n"
                f"{e}\n\n"
                f"💾 Xatogacha saqlangan: <b>{saved_so_far}</b> ta\n\n"
                f"Qayta urinib ko'ring:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )
        finally:
            if parser:
                await parser.close()
                parser = None


@dp.callback_query(F.data == "download_pdfs")
async def cb_download(callback: CallbackQuery):
    await callback.answer()
    count = await db.count_filtered_certificates()
    await callback.message.edit_text(
        f"📄 <b>PDF yuklash</b>\n\n"
        f"Saralgan: <b>{count}</b> ta sertifikat\n\n"
        f"Barchasini PDF sifatida yuborasizmi?",
        parse_mode=ParseMode.HTML,
        reply_markup=get_confirm_keyboard("download")
    )


@dp.callback_query(F.data == "confirm_download")
async def cb_confirm_download(callback: CallbackQuery):
    await callback.answer()
    global parser

    progress_msg = await callback.message.edit_text(
        "📄 <b>PDF yuklash boshlandi...</b>\n\n⏳ Kuting...",
        parse_mode=ParseMode.HTML
    )

    try:
        filtered_certs = await db.get_filtered_certificates()

        if not filtered_certs:
            await progress_msg.edit_text(
                "⚠️ Saralgan sertifikatlar topilmadi!\n\n"
                "Avval yig'ish jarayonini boshlang:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )
            return

        parser = LicenseParser()
        await parser.init_browser(headless=True)
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        downloaded = 0
        total      = len(filtered_certs)

        for i, cert in enumerate(filtered_certs, 1):
            if cert.uuid:
                output_path = os.path.join(DOWNLOAD_DIR, f"{cert.uuid}.pdf")
                if await parser.download_pdf(cert.uuid, output_path):
                    downloaded += 1
                    try:
                        await send_pdf_document(callback.message, output_path, cert)
                    except Exception as e:
                        logger.error(f"PDF yuborish xato: {e}")

            if i % DOWNLOAD_PROGRESS_EVERY_ITEMS == 0 or i == total:
                try:
                    await progress_msg.edit_text(
                        f"📄 <b>PDF yuklash...</b>\n\n"
                        f"{i}/{total} — <b>{i * 100 // total}%</b>\n"
                        f"✅ Yuklandi: <b>{downloaded}</b>\n\n⏳ Kuting...",
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass

            await asyncio.sleep(DOWNLOAD_ITEM_DELAY_SECONDS)

        await progress_msg.edit_text(
            f"✅ <b>PDF yuklash yakunlandi!</b>\n\n"
            f"Jami: <b>{total}</b>\n"
            f"Yuklandi: <b>{downloaded}</b>\n\n"
            f"Amalni tanlang:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )

    except Exception as e:
        logger.error(f"Download xato: {e}")
        await progress_msg.edit_text(
            f"❌ <b>Xatolik!</b>\n\n{e}\n\nQayta urining:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
    finally:
        if parser:
            await parser.close()
            parser = None


@dp.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery):
    await callback.answer("Bekor qilindi")
    await callback.message.edit_text(
        "❌ Bekor qilindi.\n\nAmalni tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


async def main():
    await db.init_db()
    logger.info("Database initialized")
    logger.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())