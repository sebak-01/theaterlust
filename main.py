"""
main.py  ·  Frankfurt Theaterlust Telegram Bot
══════════════════════════════════════════════

Google Cloud Run / Cloud Functions Version (Webhook-Modus)
"""

import logging
import os
import re
from datetime import date, timedelta
from pathlib import Path
import asyncio

from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from scraper import fetch_all, format_results
from theatres import THEATRES

# -- Load .env ----------------------------------------------------------------
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

WEBHOOK_URL = os.environ.get("https://theaterlust-105161913183.europe-west1.run.app", "")

# -- Logging ------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -- Date parsing -------------------------------------------------------------
_DATE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s*$")


def _parse_date(text: str) -> date | None:
    m = _DATE_RE.match(text or "")
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


# -- UI Helpers ---------------------------------------------------------------

def get_main_keyboard():
    keyboard = [
        ["/heute", "/morgen"],
        ["/hilfe"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def send_reply(update: Update, text: str):
    hint = "\n\n👉 Schicke ein Datum (TT.MM.JJ) oder nutze die Buttons unten."
    await update.message.reply_text(
        text + hint,
        reply_markup=get_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )


# -- Handlers -----------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎭 *Willkommen bei Theaterlust – deinem Theater-Bot für Frankfurt!*\n\n"
        "Schick mir ein Datum im Format *TT.MM.JJ* "
        "(z. B. `19.04.25`)."
    )
    await send_reply(update, text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    theatre_list = "\n".join(f"• {t['name']}" for t in THEATRES)

    text = (
        "ℹ️ *Hilfe*\n\n"
        "Sende ein Datum: `TT.MM.JJ`\n"
        "Beispiel: `19.04.25`\n\n"
        f"*Theater:*\n{theatre_list}"
    )
    await send_reply(update, text)


async def cmd_heute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_programme(update, date.today())


async def cmd_morgen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_programme(update, date.today() + timedelta(days=1))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parsed = _parse_date(update.message.text or "")

    if parsed is None:
        await send_reply(
            update,
            "❓ Datum nicht erkannt.\nBitte Format *TT.MM.JJ* verwenden."
        )
        return

    await _send_programme(update, parsed)


async def _send_programme(update: Update, target: date):
    await update.message.reply_text(
        f"⏳ Suche Vorstellungen für den {target.strftime('%d.%m.%Y')} ..."
    )

    # Run blocking scraper in thread
    results = await asyncio.to_thread(fetch_all, THEATRES, target)
    message = format_results(target, results)

    chunks = _split(message)

    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            await send_reply(update, chunk)
        else:
            await update.message.reply_text(
                chunk,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )


def _split(text: str, limit: int = 4000):
    if len(text) <= limit:
        return [text]

    chunks, buf, buf_len = [], [], 0
    for line in text.splitlines(keepends=True):
        if buf_len + len(line) > limit:
            chunks.append("".join(buf))
            buf, buf_len = [], 0
        buf.append(line)
        buf_len += len(line)

    if buf:
        chunks.append("".join(buf))

    return chunks


# -- Main (Webhook for Cloud Run) --------------------------------------------

async def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN fehlt")

    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL fehlt")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler(["help", "hilfe"], cmd_help))
    app.add_handler(CommandHandler("heute", cmd_heute))
    app.add_handler(CommandHandler("morgen", cmd_morgen))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    port = int(os.environ.get("PORT", 8080))

    await app.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=WEBHOOK_URL,
    )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
