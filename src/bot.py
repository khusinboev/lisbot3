"""
Telegram Bot using aiogram 3.x
"""
import asyncio
import os
from typing import Optional
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from loguru import logger

from database import Database, Certificate
from parser_v3 import LicenseParserV3 as LicenseParser
from bot_helpers import to_db_certificate, send_pdf_document
from settings import (
    TARGET_ACTIVITY_TYPE,
    DOWNLOAD_DIR,
    SCRAPE_UPDATE_EVERY_PAGES,
    UPDATE_PROGRESS_EVERY_ITEMS,
    DOWNLOAD_PROGRESS_EVERY_ITEMS,
    UPDATE_ITEM_DELAY_SECONDS,
    DOWNLOAD_ITEM_DELAY_SECONDS,
    parse_admin_ids,
)

# Load environment variables
load_dotenv()

# Bot token from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

# Admin user IDs (comma-separated)
ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", ""))

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Initialize database
db = Database()

# Initialize parser
parser: Optional[LicenseParser] = None

# Scraping state
scrape_lock = asyncio.Lock()


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Get main menu keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📥 Барча сертфикатларни йиғиш", callback_data="scrape_all"),
    )
    builder.row(
        InlineKeyboardButton(text="🔍 Саралаш (Олий таълим)", callback_data="filter_activity"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Маълумотларни янгилаш", callback_data="update_filtered"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
        InlineKeyboardButton(text="📄 PDF юклаш", callback_data="download_pdfs"),
    )
    return builder.as_markup()


def get_confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """Get confirmation keyboard"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Ҳа", callback_data=f"confirm_{action}"),
        InlineKeyboardButton(text="❌ Йўқ", callback_data="cancel"),
    )
    return builder.as_markup()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command"""
    user_id = message.from_user.id
    
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await message.answer(
            "❌ Сизда бу ботдан фойдаланиш ҳуқуқи йўқ.\n"
            "Админ билан боғланинг."
        )
        return
    
    await message.answer(
        f"👋 Ассалому алайкум, {message.from_user.full_name}!\n\n"
        f"📋 <b>Лицензия бот</b>га хуш келибсиз!\n\n"
        f"Бу бот орқали сиз:\n"
        f"• Барча сертфикатларни йиғишингиз\n"
        f"• «Олий таълим хизматлари» бўйича саралашингиз\n"
        f"• Маълумотларни янгилашингиз\n"
        f"• PDF файлларни юклаб олишингиз мумкин\n\n"
        f"Танловни амалга оширинг:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command"""
    await message.answer(
        "📖 <b>Ёрдам</b>\n\n"
        "<b>Буйруқлар:</b>\n"
        "/start - Ботни ишга тушириш\n"
        "/help - Ёрдам кўрсатиш\n"
        "/stats - Статистика кўрсатиш\n"
        "/scrape - Барча сертфикатларни йиғиш\n"
        "/filter - «Олий таълим хизматлари» бўйича саралаш\n"
        "/update - Саралган маълумотларни янгилаш\n"
        "/pdfs - PDF файлларни юклаш\n\n"
        "<b>Тугмалар:</b>\n"
        "• 📥 Барча сертфикатларни йиғиш - Сайтдан барча маълумотларни олиш\n"
        "• 🔍 Саралаш - Фаолият тури бўйича саралаш\n"
        "• 🔄 Янгилаш - Маълумотларни қайта оқиш\n"
        "• 📊 Статистика - Умумий статистика\n"
        "• 📄 PDF юклаш - Саралганларнинг PDFларини юклаш",
        parse_mode=ParseMode.HTML
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Handle /stats command"""
    stats = await db.get_stats()
    
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"📋 Жами сертфикатлар: <b>{stats['total_certificates']}</b>\n"
        f"🎓 Саралганлар (Олий таълим): <b>{stats['filtered_certificates']}</b>\n\n"
        f"Танловни амалга оширинг:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


@dp.callback_query(F.data == "stats")
async def callback_stats(callback: CallbackQuery):
    """Handle stats callback"""
    await callback.answer()
    stats = await db.get_stats()
    
    await callback.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"📋 Жами сертфикатлар: <b>{stats['total_certificates']}</b>\n"
        f"🎓 Саралганлар (Олий таълим): <b>{stats['filtered_certificates']}</b>\n\n"
        f"Танловни амалга оширинг:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


@dp.callback_query(F.data == "scrape_all")
async def callback_scrape(callback: CallbackQuery):
    """Handle scrape all callback"""
    await callback.answer()
    
    if scrape_lock.locked():
        await callback.message.answer(
            "⚠️ Йиғиш жараёни давом этмоқда. Кутинг..."
        )
        return
    
    await callback.message.edit_text(
        "📥 <b>Барча сертфикатларни йиғиш</b>\n\n"
        "Бу жараён кўп вақт олиши мумкин.\n"
        "Давом эттиришни хоҳлайсизми?",
        parse_mode=ParseMode.HTML,
        reply_markup=get_confirm_keyboard("scrape")
    )


@dp.callback_query(F.data == "confirm_scrape")
async def confirm_scrape(callback: CallbackQuery):
    """Confirm scraping"""
    await callback.answer()
    global parser
    
    # Send initial message
    progress_msg = await callback.message.edit_text(
        "🚀 <b>Йиғиш бошланди...</b>\n\n"
        "📄 Саҳифа: <b>0/0</b>\n"
        "📋 Жами йигилди: <b>0</b>\n\n"
        "⏳ Кутинг...",
        parse_mode=ParseMode.HTML
    )
    
    async with scrape_lock:
        try:
            # Initialize parser
            parser = LicenseParser()
            await parser.init_browser(headless=True)

            total_collected = 0
            current_page = 0
            total_pages = 0

            async def progress_callback(page: int, total: int, collected: int):
                """Update progress"""
                nonlocal total_collected, current_page, total_pages
                total_collected += collected
                current_page = page
                total_pages = total

                if page % SCRAPE_UPDATE_EVERY_PAGES == 0 or page == total:
                    try:
                        await progress_msg.edit_text(
                            f"🚀 <b>Йиғиш давом этмоқда...</b>\n\n"
                            f"📄 Саҳифа: <b>{page}/{total}</b>\n"
                            f"📋 Жами йигилди: <b>{total_collected}</b>\n\n"
                            f"⏳ Кутинг...",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass

            # Scrape all certificates
            certificates = await parser.scrape_all(progress_callback)

            # Save to database
            saved_count = 0
            for cert in certificates:
                await db.add_certificate(to_db_certificate(cert))
                saved_count += 1

            # Update stats
            total_in_db = await db.count_certificates()
            await db.update_stats(total=total_in_db)

            # Send completion message
            await progress_msg.edit_text(
                f"✅ <b>Йиғиш якунланди!</b>\n\n"
                f"📄 Саҳифалар: <b>{current_page}/{total_pages}</b>\n"
                f"📋 Жами йигилди: <b>{len(certificates)}</b>\n"
                f"💾 Сақланди: <b>{saved_count}</b>\n"
                f"📊 Базада жами: <b>{total_in_db}</b>\n\n"
                f"Танловни амалга оширинг:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )

        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            await progress_msg.edit_text(
                f"❌ <b>Хатолик юз берди!</b>\n\n"
                f"{str(e)}\n\n"
                f"Қайта уриниб кўринг:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )

        finally:
            if parser:
                await parser.close()
                parser = None


@dp.callback_query(F.data == "filter_activity")
async def callback_filter(callback: CallbackQuery):
    """Handle filter callback"""
    await callback.answer()
    
    await callback.message.edit_text(
        f"🔍 <b>Саралаш</b>\n\n"
        f"Фаолият тури: <b>«{TARGET_ACTIVITY_TYPE}»</b>\n\n"
        f"Базадаги барча сертфикатлар орасидан бу турга тегишлиларини\n"
        f"саралаб олишни хоҳлайсизми?",
        parse_mode=ParseMode.HTML,
        reply_markup=get_confirm_keyboard("filter")
    )


@dp.callback_query(F.data == "confirm_filter")
async def confirm_filter(callback: CallbackQuery):
    """Confirm filtering"""
    await callback.answer()
    
    # Send initial message
    progress_msg = await callback.message.edit_text(
        "🔍 <b>Саралаш бошланди...</b>\n\n"
        "⏳ Кутинг...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Get all certificates
        all_certs = await db.get_all_certificates(limit=100000)
        
        # Filter by activity type
        filtered_count = 0
        for cert in all_certs:
            if cert.activity_type and TARGET_ACTIVITY_TYPE.lower() in cert.activity_type.lower():
                await db.add_filtered_certificate(cert)
                filtered_count += 1
        
        # Update stats
        total_filtered = await db.count_filtered_certificates()
        await db.update_stats(filtered=total_filtered)
        
        # Send completion message
        await progress_msg.edit_text(
            f"✅ <b>Саралаш якунланди!</b>\n\n"
            f"📋 Кўрилди: <b>{len(all_certs)}</b>\n"
            f"🎓 Саралганлар: <b>{filtered_count}</b>\n"
            f"📊 Жами саралганлар: <b>{total_filtered}</b>\n\n"
            f"Танловни амалга оширинг:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error during filtering: {e}")
        await progress_msg.edit_text(
            f"❌ <b>Хатолик юз берди!</b>\n\n"
            f"{str(e)}\n\n"
            f"Қайта уриниб кўринг:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )


@dp.callback_query(F.data == "update_filtered")
async def callback_update(callback: CallbackQuery):
    """Handle update callback"""
    await callback.answer()
    
    await callback.message.edit_text(
        "🔄 <b>Маълумотларни янгилаш</b>\n\n"
        "Саралган сертфикатларнинг тўлиқ маълумотларини\n"
        "сайтдан қайта оқишни хоҳлайсизми?\n\n"
        "⚠️ Бу жараён кўп вақт олиши мумкин!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_confirm_keyboard("update")
    )


@dp.callback_query(F.data == "confirm_update")
async def confirm_update(callback: CallbackQuery):
    """Confirm update"""
    await callback.answer()
    global parser
    
    # Send initial message
    progress_msg = await callback.message.edit_text(
        "🔄 <b>Янгилаш бошланди...</b>\n\n"
        "⏳ Кутинг...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Get filtered certificates
        filtered_certs = await db.get_filtered_certificates(limit=100000)
        
        if not filtered_certs:
            await progress_msg.edit_text(
                "⚠️ <b>Саралган сертфикатлар топилмади!</b>\n\n"
                "Аввал саралашни амалга оширинг:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )
            return
        
        # Initialize parser
        parser = LicenseParser()
        await parser.init_browser(headless=True)
        
        updated_count = 0
        total = len(filtered_certs)
        
        for i, cert in enumerate(filtered_certs, 1):
            if cert.document_id:
                # Get updated details
                updated_cert = await parser.get_certificate_details(cert.document_id)
                
                if updated_cert:
                    # Update in database
                    db_cert = to_db_certificate(updated_cert)
                    db_cert.uuid = updated_cert.uuid or cert.uuid
                    db_cert.pdf_url = updated_cert.pdf_url or cert.pdf_url
                    await db.add_certificate(db_cert)
                    updated_count += 1
                
                # Update progress every 10 items
                if i % UPDATE_PROGRESS_EVERY_ITEMS == 0 or i == total:
                    try:
                        await progress_msg.edit_text(
                            f"🔄 <b>Янгилаш давом этмоқда...</b>\n\n"
                            f"📄 {i}/{total} - <b>{i*100//total}%</b>\n\n"
                            f"⏳ Кутинг...",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass
                
                # Small delay
                await asyncio.sleep(UPDATE_ITEM_DELAY_SECONDS)
        
        # Send completion message
        await progress_msg.edit_text(
            f"✅ <b>Янгилаш якунланди!</b>\n\n"
            f"📋 Жами: <b>{total}</b>\n"
            f"🔄 Янгиланди: <b>{updated_count}</b>\n\n"
            f"Танловни амалга оширинг:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error during update: {e}")
        await progress_msg.edit_text(
            f"❌ <b>Хатолик юз берди!</b>\n\n"
            f"{str(e)}\n\n"
            f"Қайта уриниб кўринг:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
    
    finally:
        if parser:
            await parser.close()
            parser = None


@dp.callback_query(F.data == "download_pdfs")
async def callback_download(callback: CallbackQuery):
    """Handle download PDFs callback"""
    await callback.answer()
    
    await callback.message.edit_text(
        "📄 <b>PDF юклаш</b>\n\n"
        "Саралган сертфикатларнинг PDF файлларини\n"
        "юклаб олишни хоҳлайсизми?\n\n"
        "⚠️ Бу жараён кўп вақт олиши мумкин!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_confirm_keyboard("download")
    )


@dp.callback_query(F.data == "confirm_download")
async def confirm_download(callback: CallbackQuery):
    """Confirm download"""
    await callback.answer()
    global parser
    
    # Send initial message
    progress_msg = await callback.message.edit_text(
        "📄 <b>PDF юклаш бошланди...</b>\n\n"
        "⏳ Кутинг...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Get filtered certificates
        filtered_certs = await db.get_filtered_certificates(limit=100000)
        
        if not filtered_certs:
            await progress_msg.edit_text(
                "⚠️ <b>Саралган сертфикатлар топилмади!</b>\n\n"
                "Аввал саралашни амалга оширинг:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard()
            )
            return
        
        # Initialize parser
        parser = LicenseParser()
        await parser.init_browser(headless=True)
        
        # Create downloads directory
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        
        downloaded_count = 0
        total = len(filtered_certs)
        
        for i, cert in enumerate(filtered_certs, 1):
            if cert.uuid:
                # Download PDF
                output_path = f"{DOWNLOAD_DIR}/{cert.uuid}.pdf"
                
                if await parser.download_pdf(cert.uuid, output_path):
                    downloaded_count += 1

                    try:
                        await send_pdf_document(callback.message, output_path, cert)
                    except Exception as e:
                        logger.error(f"Error sending PDF: {e}")
                
                # Update progress
                if i % DOWNLOAD_PROGRESS_EVERY_ITEMS == 0 or i == total:
                    try:
                        await progress_msg.edit_text(
                            f"📄 <b>PDF юклаш давом этмоқда...</b>\n\n"
                            f"📄 {i}/{total} - <b>{i*100//total}%</b>\n"
                            f"✅ Юкланди: <b>{downloaded_count}</b>\n\n"
                            f"⏳ Кутинг...",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass
                
                # Small delay
                await asyncio.sleep(DOWNLOAD_ITEM_DELAY_SECONDS)
        
        # Send completion message
        await progress_msg.edit_text(
            f"✅ <b>PDF юклаш якунланди!</b>\n\n"
            f"📋 Жами: <b>{total}</b>\n"
            f"✅ Юкланди: <b>{downloaded_count}</b>\n\n"
            f"Танловни амалга оширинг:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error during download: {e}")
        await progress_msg.edit_text(
            f"❌ <b>Хатолик юз берди!</b>\n\n"
            f"{str(e)}\n\n"
            f"Қайта уриниб кўринг:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
    
    finally:
        if parser:
            await parser.close()
            parser = None


@dp.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery):
    """Handle cancel callback"""
    await callback.answer("Бекор қилинди")
    
    await callback.message.edit_text(
        "❌ Бекор қилинди.\n\n"
        "Танловни амалга оширинг:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


async def main():
    """Main function"""
    # Initialize database
    await db.init_db()
    logger.info("Database initialized")
    
    # Start bot
    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
