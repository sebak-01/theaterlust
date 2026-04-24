"""
theatres.py  ·  Frankfurt Theaterlust Bot – Theatre Configuration
═════════════════════════════════════════════════════════════════

THIS IS THE ONLY FILE YOU NEED TO EDIT to add or remove theatres.

Each entry in THEATRES is a dict with three keys:

  name    – Display name shown in the Telegram message
  url     – The programme/schedule page to scrape
  parser  – Which parsing strategy to use (see list below)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AVAILABLE PARSERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  "schauspiel_frankfurt"
      Page:   /spielplan/kalender/YYYY-MM/
      Format: "So., 19.04., 18.00" as plain text, title in <h3><a>

  "volksbuehne"
      Page:   /termine
      Format: date in <h4> ("So 19.04.2026"), time in next <h4>

  "kellertheater"
      Page:   homepage
      Format: day number + German month name in plain text

  "komoedie"
      Page:   /tickets/
      Format: day number + month abbreviation in block containers

  "dramatische_buehne"
      Page:   /programm/
      Format: "18. April 2026 - 20:00 Uhr" in <h1>

#   "stalburg"
#       Page:   /programm/
#       Format: date in <strong>, time as "um HH:MM Uhr", title in <h3><a>

#   "english_theatre"
#       Page:   /tickets/
#       Format: plain HTML <table>: date (DD.MM.YYYY) | time | event title

#   "oper_frankfurt"
#       Page: /de/spielplan
#       Format: tbd

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO ADD A THEATRE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Find the theatre's programme/schedule page URL.
2. Pick the closest matching parser from the list above,
   or ask for a new parser function to be added to scraper.py.
3. Add an entry to the THEATRES list below.
4. Done – no other file needs to change.

HOW TO REMOVE A THEATRE
━━━━━━━━━━━━━━━━━━━━━━━━
Delete or comment out its entry in the list below.
"""

THEATRES = [
    {
        "name":   "Schauspiel Frankfurt",
        "url":    "https://www.schauspielfrankfurt.de/spielplan/kalender/",
        "parser": "schauspiel_frankfurt",
    },
    {
        "name":   "Volksbühne",
        "url":    "https://volksbuehne.net/termine",
        "parser": "volksbuehne",
    },
    {
        "name":   "Kellertheater Frankfurt",
        "url":    "https://kellertheater-frankfurt.de/kalender.php",
        "parser": "kellertheater",
    },
    {
        "name":   "English Theatre Frankfurt",
        "url":    "https://english-theatre.de/tickets/",
        "parser": "english_theatre",
    },
    {
        "name":   "Die Dramatische Bühne",
        "url":    "https://www.diedramatischebuehne.de/programm/",
        "parser": "dramatische_buehne",
    },
    {
        "name":   "Stalburg Theater",
        "url":    "https://stalburg.de/programm",
        "parser": "stalburg",
    },
    {
        "name":   "Oper Frankfurt",
        "url":    "https://oper-frankfurt.de/de/spielplan/",
        "parser": "oper_frankfurt",
    },


    # ── Add new theatres below this line ────────────────────────────────────
    #
    # {
    #     "name":   "Mein Theater",
    #     "url":    "https://www.mein-theater.de/spielplan/",
    #     "parser": "volksbuehne",   # pick the closest matching parser
    # },

    # {
    #     "name":   "Die Komödie",
    #     "url":    "https://diekomoedie.de/tickets/",
    #     "parser": "komoedie",
    # },


]
