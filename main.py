"""
main.py  ·  Frankfurt Theaterlust Telegram Bot
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

from google.cloud import firestore
from datetime import date, timedelta, datetime, timezone

from scraper import fetch_all, format_results
from theatres import THEATRES

# -- Load .env ----------------------------------------------------------------
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# -- Logging ------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -- Date parsing -------------------------------------------------------------

_DATE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.?(\d{2,4})?\s*$")


def _parse_date(text: str) -> date | None:
    m = _DATE_RE.match(text or "")
    if not m:
        return None

    day, month = int(m.group(1)), int(m.group(2))
    year_str = m.group(3)

    if year_str is None:
        # Kein Jahr angegeben → nächstes Vorkommen dieses Datums bestimmen
        today = date.today()
        try:
            candidate = date(today.year, month, day)
        except ValueError:
            return None
        # Liegt das Datum heute oder in der Zukunft? Sonst nächstes Jahr.
        if candidate < today:
            try:
                candidate = date(today.year + 1, month, day)
            except ValueError:
                return None
        return candidate

    year = int(year_str)
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


# -- Caching -----------------------------------------------------------------

db = firestore.Client()

def _cache_key(target: date) -> str:
    return f"programme_{target.isoformat()}"  # z.B. "programme_2026-04-25"

def _cache_expires(target: date) -> datetime:
    """Gültig bis Ende des Folgetages."""
    expires = target + timedelta(days=2)
    return datetime(expires.year, expires.month, expires.day, tzinfo=timezone.utc)

def get_cached(target: date) -> str | None:
    doc = db.collection("cache").document(_cache_key(target)).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    if datetime.now(timezone.utc) > data["expires"]:
        return None
    return data["message"]

def set_cached(target: date, message: str) -> None:
    db.collection("cache").document(_cache_key(target)).set({
        "message": message,
        "expires": _cache_expires(target),
    })

# -- Handlers -----------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎭 *Willkommen bei Theaterlust – deinem Theater-Bot für Frankfurt!*\n\n"
        "Schick mir ein Datum – z.B. `30.4.`, `1.5.26` oder `01.05.2026`\n"
    )
    await send_reply(update, text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    theatre_list = "\n".join(f"• {t['name']}" for t in THEATRES)
    await update.message.reply_text(
        "ℹ️ *Hilfe*\n\n"
        "Sende einfach ein Datum in einem dieser Formate:\n"
        "`1.1.` · `1.1.26` · `1.1.2026` · `01.01.2026`\n\n"
        "Ohne Jahresangabe wird automatisch das nächste\n"
        "Vorkommen dieses Datums verwendet.\n\n"
        "*/heute*  – Heutiges Programm\n"
        "*/hilfe*  – Diese Nachricht\n\n"
        f"*Durchsuchte Theater:*\n{theatre_list}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_heute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_programme(update, date.today())


async def cmd_morgen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_programme(update, date.today() + timedelta(days=1))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parsed = _parse_date(update.message.text or "")
    if parsed is None:
        await update.message.reply_text(
            "❓ Datum nicht erkannt.\n"
            "Folgende Formate funktionieren:\n"
            "`1.1.` · `1.1.26` · `1.1.2026` · `01.01.2026`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    await _send_programme(update, parsed)


async def _send_programme(update: Update, target: date) -> None:
    await update.message.reply_text(
        f"⏳ Suche Vorstellungen für den {target.strftime('%d.%m.%Y')} ..."
    )

    # Cache prüfen
    cached = get_cached(target)
    if cached:
        message = cached
    else:
        results = fetch_all(THEATRES, target)
        message = format_results(target, results)
        set_cached(target, message)  # speichern

    for chunk in _split(message):
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
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler(["help", "hilfe"], cmd_help))
    app.add_handler(CommandHandler("heute", cmd_heute))
    app.add_handler(CommandHandler("morgen", cmd_morgen))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    PORT = int(os.environ.get("PORT", 8080))
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL Umgebungsvariable fehlt")

    await app.initialize()
    await app.bot.set_webhook(WEBHOOK_URL)

    # Webhook-Updates manuell über Flask verarbeiten
    from flask import Flask, request, Response
    flask_app = Flask(__name__)

    @flask_app.post("/")
    def webhook():
        update = Update.de_json(request.get_json(force=True), app.bot)
        asyncio.run(app.process_update(update))
        return Response(status=200)

    @flask_app.get("/healthz")
    def health():
        return "ok", 200

    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    asyncio.run(main())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
