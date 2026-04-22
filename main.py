"""
main.py  ·  Frankfurt Theaterlust Telegram Bot
══════════════════════════════════════════════

Run:  python main.py

Setup:
  1. Create a bot with @BotFather on Telegram and copy the token.
  2. Put  TELEGRAM_BOT_TOKEN=your_token  in a .env file next to this script.
  3. pip install python-telegram-bot python-dotenv
  4. python main.py

Commands the bot understands:
  /start       - Welcome message
  /hilfe       - Help + list of theatres
  /heute       - Today's programme
  TT.MM.JJ     - Programme for a specific date  (e.g. 19.04.25)
  TT.MM.JJJJ  - Also accepted               (e.g. 19.04.2025)
"""

import asyncio
import logging
import os
import re
from datetime import date
from pathlib import Path
from scraper import fetch_all, format_results
from theatres import THEATRES

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# -- Load .env ----------------------------------------------------------------
# Looks for .env in the same folder as bot.py
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

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


# -- Handlers -----------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🎭 *Willkommen bei Theaterlust – deinem Frankfurter Theater-Bot!*\n\n"
        "Schick mir ein Datum im Format *TT.MM.JJ* "
        "(z.B. `19.04.25`) und ich zeige dir alle Vorstellungen in Frankfurt.\n\n"
        "Oder tippe /heute für das heutige Programm.\n"
        "Mit /hilfe bekommst du weitere Infos.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    theatre_list = "\n".join(f"• {t['name']}" for t in THEATRES)
    await update.message.reply_text(
        "ℹ️ *Hilfe*\n\n"
        "Sende einfach ein Datum: `TT.MM.JJ` oder `TT.MM.JJJJ`\n"
        "Beispiel: `19.04.25`\n\n"
        "*/heute*  – Heutiges Programm\n"
        "*/hilfe*  – Diese Nachricht\n\n"
        f"*Durchsuchte Theater:*\n{theatre_list}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_heute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_programme(update, date.today())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parsed = _parse_date(update.message.text or "")
    if parsed is None:
        await update.message.reply_text(
            "❓ Datum nicht erkannt.\n"
            "Bitte im Format *TT.MM.JJ* senden, z.B. `19.04.25`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    await _send_programme(update, parsed)


async def _send_programme(update: Update, target: date) -> None:
    await update.message.reply_text(
        f"⏳ Suche Vorstellungen für den {target.strftime('%d.%m.%Y')} ..."
    )
    results = fetch_all(THEATRES, target)
    message = format_results(target, results)
    for chunk in _split(message):
        await update.message.reply_text(
            chunk,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )


def _split(text: str, limit: int = 4000) -> list[str]:
    """Split long messages to stay within Telegram's 4096-char limit."""
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


# -- Main ---------------------------------------------------------------------

async def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "Kein Bot-Token gefunden.\n"
            "Bitte TELEGRAM_BOT_TOKEN in der .env-Datei setzen."
        )

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler(["help", "hilfe"], cmd_help))
    app.add_handler(CommandHandler("heute", cmd_heute))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot läuft. Abbruch mit Ctrl-C.")

    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await asyncio.Event().wait()   # run forever until Ctrl-C
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
