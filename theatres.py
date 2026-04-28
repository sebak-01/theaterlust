"""
theatres.py  ·  Frankfurt Theaterlust Bot – Theatre Configuration
═════════════════════════════════════════════════════════════════

THIS IS THE ONLY FILE YOU NEED TO EDIT to add or remove theatres.

Each entry in THEATRES is a dict with three keys:

  name    – Display name shown in the Telegram message
  url     – The programme/schedule page to scrape
  parser  – Which parsing strategy to use.

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
        "name":   "Volksbühne im Großen Hirschgraben",
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
    {   "name":   "Neues Theater Höchst",
        "url":    "https://www.neues-theater.de/tickets/alle-veranstaltungen",
        "parser": "neues_theater_hoechst",
    },
    # {
    #     "name":   "Die Komödie",
    #     "url":    "https://diekomoedie.de/tickets/",
    #     "parser": "komoedie",
    # },

    # ── Add new theatres below this line ────────────────────────────────────
    #
    # {
    #     "name":   "Mein Theater",
    #     "url":    "https://www.mein-theater.de/spielplan/",
    #     "parser": "volksbuehne",   # pick the closest matching parser
    # },




]
