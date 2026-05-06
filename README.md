# 🎭 Frankfurt Theaterlust Telegram Bot


## Files

| File | Purpose |
|---|---|
| **`theatres.py`** | ← **The only file you edit** to add/remove theatres |
| `scraper.py` | All scraping functions + parallel runner + message formatter |
| `main.py` | Telegram bot (commands, message handling) |
| `requirements.txt` | Python dependencies |

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your Telegram bot token (from @BotFather)
export TELEGRAM_BOT_TOKEN="123456789:ABCdef..."

# 3. Run
python main.py
```

Then send `13.04.25` to your bot in Telegram.

## Adding a theatre

Open `theatres.py` and add an entry to the `THEATRES` list:

```python
{
    "name": "Mein Theater",
    "url":  "https://mein-theater.de/spielplan/",
    "parser": "volksbuehne",   # pick the closest matching parser
},
```

Available parsers (see `theatres.py` for full descriptions):
`schauspiel_frankfurt`, `volksbuehne`, `kellertheater`,
`dramatische_buehne`, `english_theatre`

If none fits, add a new `parse_xyz()` function in `scraper.py` and
reference it by name in `theatres.py`.

## Removing a theatre

Delete or comment out its entry in `theatres.py`.

## Theatres included in Frankfurt Theaterlust

| Theatre | URL scraped |
|---|---|
| Schauspiel Frankfurt | schauspielfrankfurt.de/spielplan/kalender/ |
| Volksbühne im Großen Hirschgraben | volksbuehne.net/termine |
| Kellertheater Frankfurt | kellertheater-frankfurt.de/ |
| Die Dramatische Bühne | diedramatischebuehne.de/programm/ |
| English Theatre Frankfurt | english-theatre.de/tickets/buy-online/ |
| Stalburg Theater | stalburg.de/programm |
| Oper Frankfurt | oper-frankfurt.de/de/spielplan/ |
| Neues Theater Höchst | neues-theater.de/tickets/alle-veranstaltungen |
| Die Komödie | diekomoedie.de/tickets/ |
| Die Schmiere | die-schmiere.de/veranstaltungen |
| Internationales Theater Frankfurt | internationales-theater.de/programm-ticketkauf |