"""
main.py  ·  Frankfurt Theaterlust Telegram Bot
══════════════════════════════════════════════

Google Cloud Run / Cloud Functions Version (Webhook-Modus)

Setup:
  1. Bot-Token via Secret Manager oder Umgebungsvariable TELEGRAM_BOT_TOKEN
  2. Nach dem Deploy Webhook registrieren:
     https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<DEINE_URL>/webhook
  3. pip install python-telegram-bot python-dotenv flask
"""

import asyncio
import logging
import os
import re
from datetime import date

from flask import Flask, request, Response
from telegram import Update
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

# -- Logging ------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -- Config -------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN Umgebungsvariable fehlt.")

# -- App-Initialisierung (einmalig beim Kaltstart) ----------------------------
app_builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
telegram_app = app_builder.build()

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


# -- Telegram Handler ---------------------------------------------------------

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


# -- Handler registrieren -----------------------------------------------------
telegram_app.add_handler(CommandHandler("start", cmd_start))
telegram_app.add_handler(CommandHandler(["help", "hilfe"], cmd_help))
telegram_app.add_handler(CommandHandler("heute", cmd_heute))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# -- Flask Web-Server (für Cloud Run / Cloud Functions) ----------------------
# No proper Flask App yet
app = Flask(__name__)


@app.post("/webhook")
async def webhook():
    """Telegram schickt jeden Update per POST hierher."""
    # Wir prüfen, ob die App initialisiert ist. 
    if not telegram_app.running:
        await telegram_app.initialize()
        await telegram_app.start()
    
    # Update einlesen
    update_data = request.get_json(force=True)
    update = Update.de_json(update_data, telegram_app.bot)
    
    # Update verarbeiten
    await telegram_app.process_update(update)
    
    return Response(status=200)

@app.get("/healthz")
def health():
    return "ok", 200


# -- Start -----------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)