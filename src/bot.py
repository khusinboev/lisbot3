"""
src/bot.py
Har bir page dan keyin darrov bazaga kiritiladi.
Xato bo'lsa oldingi pagelar saqlanib qoladi.
"""
import asyncio
import os
import html
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
)
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from loguru import logger

from database import Database, Certificate
from parser_v4 import LicenseParserV4 as LicenseParser, PageFetchError  # ← v4 Camoufox
from bot_helpers import send_pdf_document, certificate_caption
from settings import (
    TARGET_ACTIVITY_TYPE,
    DOWNLOAD_DIR,
    SCRAPE_UPDATE_EVERY_PAGES,
    SCRAPE_START_PAGE,
    SCRAPE_CONTINUE_ON_PAGE_ERROR,
    SCRAPE_COOLDOWN_EVERY_PAGES,
    SCRAPE_COOLDOWN_SECONDS,
    DOWNLOAD_PROGRESS_EVERY_ITEMS,
    DOWNLOAD_ITEM_DELAY_SECONDS,
    AUTO_CHECK_ENABLED,
    AUTO_CHECK_INTERVAL_HOURS,
    AUTO_CHECK_MAX_PAGES,
    AUTO_CHECK_NOTIFY_EVERY_ITEMS,
    AUTO_UPDATE_ENABLED,
    AUTO_UPDATE_TZ,
    AUTO_UPDATE_HOUR,
    AUTO_UPDATE_MINUTE,
    AUTO_UPDATE_MAX_PAGES,
    AUTO_UPDATE_PROGRESS_EVERY_PAGES,
    AUTO_REQUEST_ITEM_DELAY_SECONDS,
    AUTO_NOTIFY_DELAY_SECONDS,
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
process_state_lock = asyncio.Lock()
active_process_name: Optional[str] = None
active_process_started_at: Optional[datetime] = None
background_tasks: list[asyncio.Task] = []


# ── Keyboards ─────────────────────────────────────────────────────────────────

# ── Keyboards ─────────────────────────────────────────────────────────────────
# Telegram Bot API v7.7+ button colors:
# 🟢 YASHIL (GREEN) - ijobiy amallari (confirm, yes)
# 🔵 KO'K (BLUE) - asosiy amallari (primary actions)
# 🔴 QIZIL (RED) - manfiy amallari (cancel, no, destructive)


def get_main_keyboard() -> InlineKeyboardMarkup:
    """
    Asosiy tugmalar - Telegram Bot API v7.7+ button colors bilan
    Tugmalar: 🔵 KO'K (PRIMARY color - asosiy amallari)
    """
    builder = InlineKeyboardBuilder()
    
    # 🔵 KO'K - asosiy scrape amali (PRIMARY)
    builder.row(InlineKeyboardButton(
        text="📥 Барча сертификатларни йиғиш", 
        callback_data="scrape_all"
    ))
    
    # 🔵 KO'K - statistika (PRIMARY)
    builder.row(InlineKeyboardButton(
        text="📊 Статистика", 
        callback_data="stats"
    ))
    
    # 🔵 KO'K - PDF yuklash (PRIMARY)
    builder.row(InlineKeyboardButton(
        text="📄 PDF юклаш (саралганлар)", 
        callback_data="download_pdfs"
    ))
    
    return builder.as_markup()


def get_confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """
    Tasdiqlash tugmalari - Telegram Bot API v7.7+ button colors bilan
    🟢 YASHIL - ijobiy amallari (confirm)
    🔴 QIZIL - manfiy amallari (cancel)
    """
    builder = InlineKeyboardBuilder()
    
    # 🟢 YASHIL tugma - "HA" (ijobiy amallari - GREEN)
    # 🔴 QIZIL tugma - "YO'Q" (manfiy amallari - RED)
    builder.row(
        InlineKeyboardButton(
            text="✅ Ҳа", 
            callback_data=f"confirm_{action}"
        ),
        InlineKeyboardButton(
            text="❌ Йўқ", 
            callback_data="cancel"
        ),
    )
    
    return builder.as_markup()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_admin(user_id: int) -> bool:
    return not ADMIN_IDS or user_id in ADMIN_IDS


def _normalize_number(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return raw


def _cert_signature(cert: Optional[Certificate]) -> tuple:
    if cert is None:
        return tuple()
    return (
        _normalize_number(cert.number),
        cert.register_number or "",
        cert.name or "",
        str(cert.tin or ""),
        cert.pin or "",
        cert.region_uz or "",
        cert.sub_region_uz or "",
        cert.address or "",
        cert.activity_addresses or "",
        cert.registration_date or "",
        cert.expiry_date or "",
        cert.revoke_date or "",
        cert.status or "",
        bool(cert.active),
        cert.specializations or "",
        cert.specialization_ids or "",
        bool(cert.is_filtered),
    )


def _current_process_label() -> str:
    global active_process_name, active_process_started_at
    if not active_process_name:
        return "noma'lum jarayon"
    if not active_process_started_at:
        return active_process_name
    elapsed = int((datetime.now() - active_process_started_at).total_seconds())
    return f"{active_process_name} ({elapsed}s)"


async def _try_start_process(process_name: str) -> bool:
    global active_process_name, active_process_started_at
    async with process_state_lock:
        if scrape_lock.locked():
            return False
        await scrape_lock.acquire()
        active_process_name = process_name
        active_process_started_at = datetime.now()
        return True


def _finish_process():
    global active_process_name, active_process_started_at
    active_process_name = None
    active_process_started_at = None
    if scrape_lock.locked():
        scrape_lock.release()


async def _send_screenshot(chat_id: int, screenshot_path: str, caption: str = ""):
    try:
        if os.path.exists(screenshot_path):
            await bot.send_photo(
                chat_id=chat_id,
                photo=FSInputFile(screenshot_path),
                caption=caption or "📸 Xato vaqtidagi ekran holati",
                parse_mode=ParseMode.HTML,
            )
        else:
            logger.warning(f"Screenshot fayli topilmadi: {screenshot_path}")
    except Exception as e:
        logger.error(f"Screenshot yuborishda xato: {e}")


def _admin_chat_ids() -> list[int]:
    return ADMIN_IDS.copy()


async def _notify_admins(text: str):
    targets = _admin_chat_ids()
    if not targets:
        logger.debug("ADMIN_IDS bo'sh, admin notification yuborilmadi")
        return

    for chat_id in targets:
        try:
            await asyncio.wait_for(
                bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML),
                timeout=10.0
            )
            await asyncio.sleep(AUTO_NOTIFY_DELAY_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(f"Admin notification timeout (chat_id={chat_id})")
        except Exception as e:
            logger.debug(f"Admin notification xato (chat_id={chat_id}): {e}")


async def _send_pdf_to_admins(output_path: str, cert: Certificate):
    targets = _admin_chat_ids()
    if not targets:
        return

    caption = certificate_caption(cert)
    for chat_id in targets:
        try:
            await asyncio.wait_for(
                bot.send_document(
                    chat_id=chat_id,
                    document=FSInputFile(output_path),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                ),
                timeout=20.0
            )
            await asyncio.sleep(AUTO_NOTIFY_DELAY_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(f"Admin PDF timeout (chat_id={chat_id}, uuid={cert.uuid})")
        except Exception as e:
            logger.debug(f"Admin PDF xato (chat_id={chat_id}, uuid={cert.uuid}): {e}")


def _resolve_timezone(tz_name: str):
    try:
        return ZoneInfo(tz_name)
    except Exception:
        logger.warning(f"TZ topilmadi: {tz_name}, UTC+5 ishlatiladi")
        return timezone(timedelta(hours=5))


def _seconds_until_next_daily_run(tz_name: str, hour: int, minute: int) -> float:
    tz = _resolve_timezone(tz_name)
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


async def _run_auto_check_once():
    if not await _try_start_process("auto-check"):
        await _notify_admins(
            f"⏭️ <b>Auto-check skip:</b> boshqa jarayon ketmoqda: <b>{html.escape(_current_process_label())}</b>"
        )
        return

    await _notify_admins(
        "🔎 <b>Auto-check boshlandi</b>\n\n"
        "Yangi sertifikatlar tekshirilmoqda..."
    )

    parser_local: Optional[LicenseParser] = None

    try:
        parser_local = LicenseParser()
        await parser_local.init_browser(headless=True)
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        existing_numbers = await db.get_existing_numbers_set()
        new_certs = await parser_local.fetch_new_since(
            existing_numbers=existing_numbers,
            max_pages=AUTO_CHECK_MAX_PAGES,
        )

        if not new_certs:
            await _notify_admins("✅ <b>Auto-check:</b> yangi sertifikat topilmadi")
            return

        inserted = 0
        filtered = 0
        pdf_ready = 0
        pdf_sent = 0
        failed = 0
        pdf_queue: list[tuple[str, Certificate]] = []

        total = len(new_certs)
        for idx, cert in enumerate(new_certs, 1):
            try:
                await db.upsert_certificate(cert)
                inserted += 1

                if cert.is_filtered and cert.uuid:
                    filtered += 1
                    output_path = os.path.join(DOWNLOAD_DIR, f"auto_{cert.uuid}.pdf")
                    if await parser_local.download_pdf(cert.uuid, output_path):
                        pdf_queue.append((output_path, cert))
                        pdf_ready += 1
            except Exception as e:
                failed += 1
                logger.error(f"Auto-check item xato (uuid={cert.uuid}): {e}")

            if idx % AUTO_CHECK_NOTIFY_EVERY_ITEMS == 0 or idx == total:
                await _notify_admins(
                    f"🔎 <b>Auto-check davom etmoqda</b>\n\n"
                    f"{idx}/{total}\n"
                    f"💾 Bazaga: <b>{inserted}</b>\n"
                    f"🎯 Filterga mos: <b>{filtered}</b>\n"
                    f"📄 PDF tayyor: <b>{pdf_ready}</b>\n"
                    f"⚠️ Xatolar: <b>{failed}</b>"
                )

            await asyncio.sleep(AUTO_REQUEST_ITEM_DELAY_SECONDS)

        await _notify_admins(
            f"✅ <b>Auto-check yakunlandi</b>\n\n"
            f"🆕 Topildi: <b>{total}</b>\n"
            f"💾 Bazaga: <b>{inserted}</b>\n"
            f"🎯 Filterga mos: <b>{filtered}</b>\n"
            f"📄 PDF tayyor: <b>{pdf_ready}</b>\n"
            f"⚠️ Xatolar: <b>{failed}</b>"
        )

        if pdf_queue:
            await _notify_admins("📨 <b>Auto-check:</b> saralanganlar uchun PDF yuborish boshlandi")
            for output_path, cert in pdf_queue:
                await _send_pdf_to_admins(output_path, cert)
                pdf_sent += 1
                await asyncio.sleep(AUTO_REQUEST_ITEM_DELAY_SECONDS)
            await _notify_admins(f"✅ <b>Auto-check:</b> PDF yuborildi: <b>{pdf_sent}</b>")
        else:
            await _notify_admins("ℹ️ <b>Auto-check:</b> yuborishga saralangan PDF topilmadi")

    except Exception as e:
        logger.error(f"Auto-check xato: {e}")
        await _notify_admins(
            f"❌ <b>Auto-check xato</b>\n\n<code>{html.escape(str(e))[:300]}</code>"
        )
    finally:
        if parser_local:
            await parser_local.close()
        _finish_process()


async def _run_auto_update_once():
    if not await _try_start_process("auto-update"):
        await _notify_admins(
            f"⏭️ <b>Auto-update skip:</b> boshqa jarayon ketmoqda: <b>{html.escape(_current_process_label())}</b>"
        )
        return

    parser_local: Optional[LicenseParser] = None

    try:
        targets = await db.get_filtered_numbers_set()
        if not targets:
            await _notify_admins("ℹ️ <b>Auto-update:</b> saralangan sertifikat topilmadi")
            return

        await _notify_admins(
            f"🔄 <b>Auto-update boshlandi</b>\n\n"
            f"Saralangan hujjatlar: <b>{len(targets)}</b>\n"
            f"Qidiruv URL: <code>https://license.gov.uz/registry?filter%5Bnumber%5D=...</code>\n"
            f"API: <code>/v1/register/open_source?number=...&page=0&size=10</code>"
        )

        parser_local = LicenseParser()
        await parser_local.init_browser(headless=True)

        async def on_progress(done: int, total: int, found: int, needed: int):
            if done % AUTO_UPDATE_PROGRESS_EVERY_PAGES == 0 or done == total:
                await _notify_admins(
                    f"🔄 <b>Auto-update qidiruv davom etmoqda</b>\n\n"
                    f"🔎 Tekshirildi: <b>{done}/{total}</b>\n"
                    f"🎯 Topildi: <b>{found}/{needed}</b>"
                )

        found_map = await parser_local.fetch_by_document_numbers(
            target_numbers=targets,
            max_pages=AUTO_UPDATE_MAX_PAGES,
            progress_callback=on_progress,
            continue_on_page_error=True,
            cooldown_every_pages=SCRAPE_COOLDOWN_EVERY_PAGES,
            cooldown_seconds=SCRAPE_COOLDOWN_SECONDS,
        )

        changed = 0
        unchanged = 0
        inserted = 0
        failed = 0
        processed = 0

        for number, cert in found_map.items():
            processed += 1
            try:
                old_cert = await db.get_certificate_by_number(number)
                has_old = old_cert is not None
                is_changed = _cert_signature(old_cert) != _cert_signature(cert)

                if has_old and not is_changed:
                    unchanged += 1
                else:
                    await db.upsert_certificate(cert)
                    if has_old:
                        changed += 1
                    else:
                        inserted += 1
            except Exception as e:
                failed += 1
                logger.error(f"Auto-update DB xato (number={number}, uuid={cert.uuid}): {e}")

            if (
                processed % AUTO_UPDATE_PROGRESS_EVERY_PAGES == 0
                or processed == len(found_map)
            ):
                await _notify_admins(
                    f"🔄 <b>Auto-update DB bosqichi</b>\n\n"
                    f"💾 Tekshirildi: <b>{processed}/{len(found_map)}</b>\n"
                    f"🆕 Yangi qo'shildi: <b>{inserted}</b>\n"
                    f"♻️ O'zgargani update qilindi: <b>{changed}</b>\n"
                    f"➖ O'zgarmagan: <b>{unchanged}</b>\n"
                    f"⚠️ Xatolar: <b>{failed}</b>"
                )

            await asyncio.sleep(AUTO_REQUEST_ITEM_DELAY_SECONDS)

        missing = max(0, len(targets) - len(found_map))

        await _notify_admins(
            f"✅ <b>Auto-update yakunlandi</b>\n\n"
            f"🧾 Target: <b>{len(targets)}</b>\n"
            f"🔎 API'dan topildi: <b>{len(found_map)}</b>\n"
            f"🆕 Yangi qo'shildi: <b>{inserted}</b>\n"
            f"♻️ O'zgargani update qilindi: <b>{changed}</b>\n"
            f"➖ O'zgarmagan: <b>{unchanged}</b>\n"
            f"❓ Topilmadi: <b>{missing}</b>\n"
            f"⚠️ Xatolar: <b>{failed}</b>"
        )

    except Exception as e:
        logger.error(f"Auto-update xato: {e}")
        await _notify_admins(
            f"❌ <b>Auto-update xato</b>\n\n<code>{html.escape(str(e))[:300]}</code>"
        )
    finally:
        if parser_local:
            await parser_local.close()
        _finish_process()


async def _auto_check_worker():
    interval_seconds = max(300.0, AUTO_CHECK_INTERVAL_HOURS * 3600.0)
    if _admin_chat_ids():
        await _notify_admins(
            f"⏱️ <b>Auto-check worker yoqildi</b>\n"
            f"Har <b>{AUTO_CHECK_INTERVAL_HOURS:g}</b> soatda ishlaydi."
        )
    else:
        logger.info(f"Auto-check worker yoqildi (ADMIN_IDS bo'sh, notification yubormaydi)")
    await asyncio.sleep(30)
    while True:
        await _run_auto_check_once()
        await asyncio.sleep(interval_seconds)


async def _auto_update_worker():
    if _admin_chat_ids():
        await _notify_admins(
            f"🕒 <b>Auto-update worker yoqildi</b>\n"
            f"Har kuni <b>{AUTO_UPDATE_HOUR:02d}:{AUTO_UPDATE_MINUTE:02d}</b> ({AUTO_UPDATE_TZ})."
        )
    else:
        logger.info(f"Auto-update worker yoqildi (ADMIN_IDS bo'sh, notification yubormaydi)")
    await asyncio.sleep(30)
    while True:
        wait_s = _seconds_until_next_daily_run(AUTO_UPDATE_TZ, AUTO_UPDATE_HOUR, AUTO_UPDATE_MINUTE)
        await asyncio.sleep(wait_s)
        await _run_auto_update_once()


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
    stats = await db.get_stats_by_activity(TARGET_ACTIVITY_TYPE)
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"Jami: <b>{stats['total_certificates']}</b>\n"
        f"Saralgan («{TARGET_ACTIVITY_TYPE}»): <b>{stats['filtered_certificates']}</b>\n"
        f"Faol (jami): <b>{stats['active_certificates']}</b>\n"
        f"Faol (saralgan): <b>{stats['active_filtered_certificates']}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


@dp.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery):
    try:
        await asyncio.wait_for(callback.answer(), timeout=5.0)
    except Exception as e:
        logger.debug(f"Callback answer xato: {e}")
    try:
        stats = await db.get_stats_by_activity(TARGET_ACTIVITY_TYPE)
        await callback.message.edit_text(
            f"📊 <b>Statistika</b>\n\n"
            f"Jami: <b>{stats['total_certificates']}</b>\n"
            f"Saralgan («{TARGET_ACTIVITY_TYPE}»): <b>{stats['filtered_certificates']}</b>\n"
            f"Faol (jami): <b>{stats['active_certificates']}</b>\n"
            f"Faol (saralgan): <b>{stats['active_filtered_certificates']}</b>\n\n"
            f"Amalni tanlang:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Stats callback xato: {e}")


@dp.callback_query(F.data == "scrape_all")
async def cb_scrape(callback: CallbackQuery):
    try:
        await asyncio.wait_for(callback.answer(), timeout=5.0)
    except Exception as e:
        logger.debug(f"Callback answer xato: {e}")
    if scrape_lock.locked():
        await callback.message.answer(
            f"⚠️ Jarayon davom etmoqda: <b>{html.escape(_current_process_label())}</b>",
            parse_mode=ParseMode.HTML,
        )
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
    try:
        await asyncio.wait_for(callback.answer(), timeout=5.0)
    except Exception as e:
        logger.debug(f"Callback answer xato: {e}")
    global parser

    if not await _try_start_process("manual-scrape"):
        await callback.message.answer(
            f"⚠️ Yangi jarayon boshlandi emas. Band jarayon: <b>{html.escape(_current_process_label())}</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    progress_msg = await callback.message.edit_text(
        "🚀 <b>Yig'ish boshlandi...</b>\n\n"
        "📄 Sahifa: <b>0/0</b>\n"
        "💾 Saqlandi: <b>0</b>\n"
        "🎓 Saralandi: <b>0</b>\n\n"
        "⏳ Kuting...",
        parse_mode=ParseMode.HTML
    )

    try:
        parser = LicenseParser()
        await parser.init_browser(headless=True)

        total_saved    = 0
        total_filtered = 0
        current_page   = 0
        total_pages    = 0
        skipped_pages  = 0
        failed_writes  = 0

        async def on_page_done(page: int, total: int, page_certs: list):
            nonlocal total_saved, total_filtered, current_page, total_pages, failed_writes
            current_page = page
            total_pages  = total

            for cert in page_certs:
                try:
                    await db.upsert_certificate(cert)
                    total_saved += 1
                except Exception as e:
                    failed_writes += 1
                    logger.error(f"DB upsert xato (uuid={cert.uuid}): {e}")

            total_filtered = await db.count_filtered_certificates()

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

        async def on_page_error(page: int, total: int, err: Exception):
            nonlocal skipped_pages, current_page, total_pages
            skipped_pages += 1
            current_page = page
            total_pages = total
            logger.warning(f"Sahifa skip qilindi: {page}/{total} ({err})")

        await parser.scrape_all(
            progress_callback=on_page_done,
            start_page_1indexed=SCRAPE_START_PAGE,
            continue_on_page_error=SCRAPE_CONTINUE_ON_PAGE_ERROR,
            error_callback=on_page_error,
            cooldown_every_pages=SCRAPE_COOLDOWN_EVERY_PAGES,
            cooldown_seconds=SCRAPE_COOLDOWN_SECONDS,
        )

        total_in_db    = await db.count_certificates()
        filtered_in_db = await db.count_filtered_certificates()

        await progress_msg.edit_text(
            f"✅ <b>Yig'ish yakunlandi!</b>\n\n"
            f"📄 Sahifalar: <b>{current_page}/{total_pages}</b>\n"
            f"💾 Saqlandi: <b>{total_saved}</b>\n"
            f"⏭️ Skip sahifalar: <b>{skipped_pages}</b>\n"
            f"⚠️ DB yozish xatolari: <b>{failed_writes}</b>\n"
            f"🎓 Saralandi («{TARGET_ACTIVITY_TYPE}»): <b>{filtered_in_db}</b>\n"
            f"📊 Bazada jami: <b>{total_in_db}</b>\n\n"
            f"Amalni tanlang:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )

    except PageFetchError as e:
            logger.error(f"PageFetchError: {e}")
            saved_so_far = await db.count_certificates()

            await progress_msg.edit_text(
                f"❌ <b>Sayt ma'lumot bermadi!</b>\n\n"
                f"<code>{html.escape(str(e))[:300]}</code>\n\n"
                f"💾 Xatogacha saqlangan: <b>{saved_so_far}</b> ta\n\n"
                f"📸 Ekran holati pastda 👇",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )

            if e.screenshot_path:
                await _send_screenshot(
                    chat_id=callback.message.chat.id,
                    screenshot_path=e.screenshot_path,
                    caption=(
                        "📸 <b>Xato vaqtidagi ekran</b>\n\n"
                        "Cloudflare yoki sayt muammosi bo'lishi mumkin.\n"
                        "Bir oz kutib qayta urining."
                    ),
                )

    except Exception as e:
            logger.error(f"Scraping xato: {e}")
            saved_so_far = await db.count_certificates()

            screenshot_path = None
            if parser:
                try:
                    screenshot_path = await parser.take_screenshot(label="scrape_error")
                except Exception:
                    pass

            await progress_msg.edit_text(
                f"❌ <b>Xatolik yuz berdi!</b>\n\n"
                f"<code>{html.escape(str(e))[:300]}</code>\n\n"
                f"💾 Xatogacha saqlangan: <b>{saved_so_far}</b> ta\n\n"
                + ("📸 Ekran holati pastda 👇" if screenshot_path else ""),
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )

            if screenshot_path:
                await _send_screenshot(
                    chat_id=callback.message.chat.id,
                    screenshot_path=screenshot_path,
                    caption="📸 <b>Xato vaqtidagi ekran holati</b>",
                )

    finally:
        if parser:
            await parser.close()
            parser = None
        _finish_process()


@dp.callback_query(F.data == "download_pdfs")
async def cb_download(callback: CallbackQuery):
    try:
        await asyncio.wait_for(callback.answer(), timeout=5.0)
    except Exception as e:
        logger.debug(f"Callback answer xato: {e}")
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
    try:
        await asyncio.wait_for(callback.answer(), timeout=5.0)
    except Exception as e:
        logger.debug(f"Callback answer xato: {e}")
    global parser

    if not await _try_start_process("manual-download"):
        await callback.message.answer(
            f"⚠️ Yangi jarayon boshlandi emas. Band jarayon: <b>{html.escape(_current_process_label())}</b>",
            parse_mode=ParseMode.HTML,
        )
        return

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
        downloaded_items: list[tuple[str, Certificate]] = []

        for i, cert in enumerate(filtered_certs, 1):
            if cert.uuid:
                output_path = os.path.join(DOWNLOAD_DIR, f"{cert.uuid}.pdf")
                if await parser.download_pdf(cert.uuid, output_path):
                    downloaded += 1
                    downloaded_items.append((output_path, cert))

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

        if downloaded_items:
            try:
                await progress_msg.edit_text(
                    f"📨 <b>PDF yuborish boshlandi...</b>\n\n"
                    f"Tayyor: <b>{len(downloaded_items)}</b>",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass

            for output_path, cert in downloaded_items:
                try:
                    await send_pdf_document(callback.message, output_path, cert)
                except Exception as e:
                    logger.error(f"PDF yuborish xato: {e}")
                await asyncio.sleep(DOWNLOAD_ITEM_DELAY_SECONDS)

        await progress_msg.edit_text(
            f"✅ <b>PDF yuklash yakunlandi!</b>\n\n"
            f"Jami: <b>{total}</b>\n"
            f"Yuklandi: <b>{downloaded}</b>\n"
            f"Yuborildi: <b>{len(downloaded_items)}</b>\n\n"
            f"Amalni tanlang:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )

    except Exception as e:
        logger.error(f"Download xato: {e}")
        await progress_msg.edit_text(
            f"❌ <b>Xatolik!</b>\n\n<code>{html.escape(str(e))[:300]}</code>\n\nQayta urining:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
    finally:
        if parser:
            await parser.close()
            parser = None
        _finish_process()


@dp.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery):
    try:
        await asyncio.wait_for(callback.answer("Bekor qilindi"), timeout=5.0)
    except Exception as e:
        logger.debug(f"Callback answer xato: {e}")
    await callback.message.edit_text(
        "❌ Bekor qilindi.\n\nAmalni tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


async def main():
    await db.init_db()
    logger.info("Database initialized")

    if AUTO_CHECK_ENABLED:
        background_tasks.append(asyncio.create_task(_auto_check_worker()))
    if AUTO_UPDATE_ENABLED:
        background_tasks.append(asyncio.create_task(_auto_update_worker()))

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())