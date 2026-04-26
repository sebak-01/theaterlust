"""
main.py  -  Frankfurt Theaterlust Telegram Bot
"""

import asyncio
import logging
import os
import re
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, Response
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
        today = date.today()
        try:
            candidate = date(today.year, month, day)
        except ValueError:
            return None
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
    return ReplyKeyboardMarkup(
        [["/heute", "/morgen"], ["/hilfe"]],
        resize_keyboard=True
    )


async def send_reply(update: Update, text: str):
    hint = "\n\n👉 Schicke ein Datum (TT.MM.JJ) oder nutze die Buttons unten."
    await update.message.reply_text(
        text + hint,
        reply_markup=get_main_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )


# -- Caching ------------------------------------------------------------------
_db = None

def get_db():
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def _cache_key(target: date) -> str:
    return f"programme_{target.isoformat()}"


def _cache_expires(target: date) -> datetime:
    expires = target + timedelta(days=2)
    return datetime(expires.year, expires.month, expires.day, tzinfo=timezone.utc)


def get_cached(target: date) -> str | None:
    doc = get_db().collection("cache").document(_cache_key(target)).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    if datetime.now(timezone.utc) > data["expires"]:
        return None
    return data["message"]


def set_cached(target: date, message: str) -> None:
    get_db().collection("cache").document(_cache_key(target)).set({
        "message": message,
        "expires": _cache_expires(target),
    })


# -- Handlers -----------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎭 *Willkommen bei Theaterlust – deinem Theater-Bot für Frankfurt!*\n\n"
        "Schick mir ein Datum – z.B. `30.4.`, `1.5.26` oder `01.05.2026`"
    )
    await send_reply(update, text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    theatre_list = "\n".join(f"• {t['name']}" for t in THEATRES)
    text = (
        "ℹ️ *Hilfe*\n\n"
        "Sende einfach ein Datum in einem dieser Formate:\n"
        "`1.1.` · `1.1.26` · `1.1.2026` · `01.01.2026`\n\n"
        "Ohne Jahresangabe wird automatisch das nächste\n"
        "Vorkommen dieses Datums verwendet.\n\n"
        "*/heute*  – Heutiges Programm\n"
        "*/morgen* – Morgiges Programm\n"
        "*/hilfe*  – Diese Nachricht\n\n"
        f"*Durchsuchte Theater:*\n{theatre_list}"
    )
    await send_reply(update, text)


async def cmd_heute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_programme(update, date.today())


async def cmd_morgen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_programme(update, date.today() + timedelta(days=1))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    cached = get_cached(target)
    if cached:
        message = cached
    else:
        results = fetch_all(THEATRES, target)
        message = format_results(target, results)
        set_cached(target, message)
    for chunk in _split(message):
        await update.message.reply_text(
            chunk,
            parse_mode=ParseMode.MARKDOWN,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )


def _split(text: str, limit: int = 4000) -> list[str]:
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


# -- Telegram App  ------------------------------------------------------
_ptb_app = None
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)


def get_ptb_app():
    global _ptb_app
    if _ptb_app is None:
        _ptb_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        _ptb_app.add_handler(CommandHandler("start", cmd_start))
        _ptb_app.add_handler(CommandHandler(["help", "hilfe"], cmd_help))
        _ptb_app.add_handler(CommandHandler("heute", cmd_heute))
        _ptb_app.add_handler(CommandHandler("morgen", cmd_morgen))
        _ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        _loop.run_until_complete(_ptb_app.initialize())
    return _ptb_app


# -- Flask (Cloud Run HTTP Server) --------------------------------------------
app = Flask(__name__)


@app.post("/webhook")
def webhook():
    ptb = get_ptb_app()
    update = Update.de_json(request.get_json(force=True), ptb.bot)
    _loop.run_until_complete(ptb.process_update(update))
    return Response(status=200)


@app.get("/healthz")
def health():
    return "ok", 200


# -- Start --------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)