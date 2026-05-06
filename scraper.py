"""
scraper.py  ·  Frankfurt Theaterlust Telegram Bot – All scrapers in one place
════════════════════════════════════════════════════════════════

One file, one function per theatre.  No separate scraper modules.
To add a new parser, add a function here and reference it in theatres.py.
"""

import logging
import re
import concurrent.futures
import json
from dataclasses import dataclass
from datetime import date
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

import time
import random

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# German month name → number
DE_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
    # English (for ETF)
    "january": 1, "february": 2, "march": 3,
    "june": 6, "july": 7, "october": 10, "december": 12,
}
DE_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mär": 3, "apr": 4, "mai": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12,
}


# ─────────────────────────────────────────────────────────────────────────────
# Data class
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Performance:
    theatre: str
    title: str
    time: str
    url: Optional[str] = None
    extra: Optional[str] = None   # stage, subtitle, location, etc.

    def format(self) -> str:
        lines = [f"🎭 *{self.title}*", f"🕐 {self.time}"]
        if self.extra:
            lines.append(f"ℹ️ {self.extra}")
        if self.url:
            lines.append(f"🔗 [Tickets / Details]({self.url})")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

TIMEOUT = (5, 15)  # connect, read

def _get_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

import re

def _find_time(text: str, date_token: str = None) -> str:
    """Extract start time (HH:MM) from a text string.
    Handles:
    - 20:00
    - 20.00
    - 20:00-21:30 / 20.00–21.30
    - 19 Uhr
    """

    if not text:
        return "?"

    # Remove explicit date token if provided
    if date_token:
        text = text.replace(date_token, " ")

    # Remove full dates like 25.04.2026 or 25.04.
    text = re.sub(r"\b\d{1,2}\.\d{1,2}\.(\d{2,4})?\b", " ", text)

    # Normalize separators
    text = text.replace(".", ":")

    # Normalize dashes (just in case you later extend logic)
    text = text.replace("–", "-").replace("—", "-")

    # Find valid times only (strict)
    matches = re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)

    if matches:
        h, m = matches[0]  # FIRST = start time
        return f"{int(h):02d}:{m}"

    # Fallback: "19 Uhr"
    m2 = re.search(r"\b([01]?\d|2[0-3])\s*Uhr\b", text, re.I)
    if m2:
        return f"{int(m2.group(1)):02d}:00"

    return "?"

def _dedupe(performances: List[Performance]) -> List[Performance]:
    seen = set()
    result = []
    for p in performances:
        # Normalize title: remove double spaces and strip
        clean_title = re.sub(r"\s+", " ", p.title.lower().strip())
        # The key is the combination of the clean title and the time
        key = (clean_title, p.time)
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Parser: Schauspiel Frankfurt
# ─────────────────────────────────────────────────────────────────────────────

def parse_schauspiel_frankfurt(theatre_name: str, base_url: str, target: date) -> List[Performance]:
    url = f"https://www.schauspielfrankfurt.de/spielplan/kalender/{target.year}-{target.month:02d}/"
    try:
        soup = _get_soup(url)
    except Exception as e:
        logger.error("SchauspielFrankfurt: %s", e)
        return []

    date_token = f"{target.day:02d}.{target.month:02d}."
    performances = []

    for h3 in soup.find_all("h3"):
        title_el = h3.find("a", href=True)
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        block = None
        for ancestor in h3.parents:
            if ancestor.name in ("html", "body"):
                break
            text = ancestor.get_text(" ", strip=True)
            if re.search(rf"{re.escape(date_token)}\s*,?\s*\d{{1,2}}[:.]\d{{2}}", text):
                block = ancestor
                break

        if not block:
            continue

        block_text = block.get_text(" ", strip=True)
        if block_text.count(date_token) != 1:
            continue

        time_str = _find_time(block_text, date_token)
        detail_url = urljoin("https://www.schauspielfrankfurt.de", title_el["href"])
        performances.append(Performance(theatre_name, title, time_str, detail_url))

    return _dedupe(performances)

# ─────────────────────────────────────────────────────────────────────────────
# Parser: Volksbühne
# ─────────────────────────────────────────────────────────────────────────────

def parse_volksbuehne(theatre_name: str, url: str, target: date) -> List[Performance]:
    try:
        soup = _get_soup(url)
    except Exception as e:
        logger.error("%s: %s", theatre_name, e)
        return []

    # Exakter Match: "9.05.2026" aber nicht "29.05.2026"
    target_str = f"{target.day}.{target.month:02d}.{target.year}"
    date_pattern = re.compile(rf"(?<!\d){re.escape(target_str)}(?!\d)")
    
    performances = []

    for li in soup.select("li"):
        headings = li.select("h4")
        if not headings:
            continue
        date_text = headings[0].get_text(strip=True)
        if not date_pattern.search(date_text):  # ← statt "not in"
            continue

        time_str = "?"
        if len(headings) > 1:
            h4_text = headings[1].get_text(strip=True)
            if re.search(r"\d", h4_text):
                time_str = _find_time(h4_text)

        title_el = li.select_one("h3")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        venue_text = None
        for p in li.find_all(["p", "div"]):
            t = p.get_text(" ", strip=True)
            if "Hirschgraben" in t or "Aschaffenburg" in t or "Frankfurt" in t:
                venue_text = t.split("\n")[0].strip()[:60]
                break

        ticket_el = li.find("a", href=re.compile(r"reservix|eventim|ticketmaster", re.I))
        info_el   = li.find("a", href=re.compile(r"volksbuehne\.net/programm"))
        ticket_url = ticket_el["href"] if ticket_el else \
                     (urljoin("https://volksbuehne.net", info_el["href"]) if info_el else url)

        performances.append(Performance(theatre_name, title, time_str, ticket_url, venue_text))

    return performances


# ─────────────────────────────────────────────────────────────────────────────
# Parser: Kellertheater Frankfurt
# ─────────────────────────────────────────────────────────────────────────────

def parse_kellertheater(theatre_name: str, url: str, target: date) -> List[Performance]:
    try:
        soup = _get_soup(url)
    except Exception as e:
        logger.error("%s: %s", theatre_name, e)
        return []

    performances = []

    target_day = str(target.day)
    target_month = [
        k for k, v in DE_MONTHS.items() if v == target.month and len(k) >= 3
    ][0].capitalize()

    # Exakter Monatsname als Wort-Grenze
    month_pattern = re.compile(rf"\b{re.escape(target_month)}\b", re.IGNORECASE)

    for row in soup.select("div.zeile"):
        # --- TAG: exakter Vergleich (war bereits korrekt) ---
        day_el = row.select_one(".news-day")
        if not day_el or day_el.get_text(strip=True) != target_day:
            continue

        # --- MONAT: mit Wort-Grenzen ---
        month_text = row.get_text(" ", strip=True)
        if not month_pattern.search(month_text):
            continue

        # --- UHRZEIT ---
        time_el = row.select_one(".news-content-left-colright b")
        time_str = _find_time(time_el.get_text(" ", strip=True)) if time_el else "?"

        # --- TITEL ---
        title_el = row.select_one(".beschreibung big")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        # --- LINK ---
        link_el = row.select_one(".beschreibung a[href]")
        ticket_url = urljoin(url, link_el["href"]) if link_el else url

        performances.append(Performance(theatre_name, title, time_str, ticket_url))

    return _dedupe(performances)

# ─────────────────────────────────────────────────────────────────────────────
# Parser: English Theatre Frankfurt
# ─────────────────────────────────────────────────────────────────────────────

def parse_english_theatre(theatre_name: str, url: str, target: date) -> List[Performance]:
    try:
        soup = _get_soup(url)
    except Exception as e:
        logger.error("%s: %s", theatre_name, e)
        return []

    target_str = target.strftime("%d.%m.%Y")
    performances = []

    table = soup.find("table")
    if not table:
        return performances

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        if cells[0].get_text(strip=True) != target_str:
            continue

        time_str = cells[1].get_text(strip=True)
        event_cell = cells[2]
        link_el = event_cell.find("a", href=True)

        if link_el:
            title = link_el.get_text(strip=True).title()
            ticket_url = link_el["href"]
        else:
            title = event_cell.get_text(strip=True).title()
            ticket_url = url

        desc = " ".join(
            (s.get_text(strip=True) if hasattr(s, "get_text") else str(s).strip())
            for s in (link_el.next_siblings if link_el else [])
        ).strip()
        if "We kindly ask" in desc:
            desc = desc[:desc.index("We kindly ask")].strip()
        extra = desc or None

        performances.append(Performance(theatre_name, title, time_str, ticket_url, extra))

    return performances


# ─────────────────────────────────────────────────────────────────────────────
# Parser: Die Dramatische Bühne
# ─────────────────────────────────────────────────────────────────────────────

def parse_dramatische_buehne(theatre_name: str, url: str, target: date) -> List[Performance]:
    try:
        soup = _get_soup(url)
    except Exception as e:
        logger.error("%s: %s", theatre_name, e)
        return []

    performances = []
    month_name = [k.capitalize() for k, v in DE_MONTHS.items() if v == target.month and len(k) >= 3][0]
      
    date_pattern = re.compile(
        rf"(?<!\d){target.day}\.\s*{month_name}\s*{target.year}(?!\d)",
        re.IGNORECASE
    )

    for element in soup.find_all(string=date_pattern):
        parent = element.parent
        full_text = parent.get_text(" ", strip=True)

        if not date_pattern.search(full_text):
            continue

        title_el = None
        curr = parent
        while curr and not title_el:
            title_el = curr.find_previous(["h2", "h3", "h1"])
            curr = curr.parent
            if curr and curr.name == "body":
                break

        if not title_el:
            continue

        title = title_el.get_text(strip=True)

        time_match = re.search(r"(\d{1,2}[:.]\d{2})\s*Uhr", full_text)
        time_str = time_match.group(1).replace(".", ":") if time_match else "?"

        extra = None
        if "Frankfurt" in full_text:
            parts = full_text.split(",")
            if len(parts) > 1:
                extra = parts[-1].replace(".", "").strip()

        link_el = title_el.find("a", href=True) or parent.find("a", href=True)
        detail_url = urljoin(url, link_el["href"]) if link_el else url

        performances.append(Performance(theatre_name, title, time_str, detail_url, extra))

    return _dedupe(performances)

# ─────────────────────────────────────────────────────────────────────────────
# Parser: Stalburg Theater
# ─────────────────────────────────────────────────────────────────────────────

def parse_stalburg(theatre_name: str, base_url: str, target: date) -> List[Performance]:
    url = f"https://stalburg.de/programm/year:{target.year}/month:{target.month:02d}"
    try:
        soup = _get_soup(url)
    except Exception as e:
        logger.error("%s: %s", theatre_name, e)
        return []
 
    # Target date token as it appears on the page, e.g. "23.04.2026"
    date_token = f"{target.day:02d}.{target.month:02d}.{target.year}"
    performances = []
 
    for li in soup.select("li"):
        # --- DATE: find <strong> whose text contains the date token ---
        strong = li.find("strong")
        if not strong:
            continue
        if date_token not in strong.get_text():
            continue
 
        # --- TITLE: <h3><a> ---
        h3 = li.find("h3")
        if not h3:
            continue
        title_el = h3.find("a", href=True)
        title = (title_el or h3).get_text(" ", strip=True)
        # Clean up extra whitespace from multiline text
        title = re.sub(r"\s+", " ", title).strip()
 
        # --- TIME: "um HH:MM Uhr" in the li text ---
        li_text = li.get_text(" ", strip=True)
        time_str = _find_time(li_text, date_token)
 
        # --- LINK: prefer ticket shop link, fall back to detail page ---
        ticket_el = li.find("a", href=re.compile(r"reservix|eventim|adticket", re.I))
        detail_el = title_el  # already found above
        if ticket_el:
            ticket_url = ticket_el["href"]
        elif detail_el:
            ticket_url = urljoin("https://stalburg.de", detail_el["href"])
        else:
            ticket_url = base_url
 
        performances.append(Performance(theatre_name, title, time_str, ticket_url))
 
    return _dedupe(performances)

# ─────────────────────────────────────────────────────────────────────────────
# Parser: Oper Frankfurt
# ─────────────────────────────────────────────────────────────────────────────

def parse_oper_frankfurt(theatre_name: str, base_url: str, target: date) -> List[Performance]:
    url = f"https://oper-frankfurt.de/de/spielplan/?datum={target.year}-{target.month:02d}&lang=100"
    try:
        soup = _get_soup(url)
    except Exception as e:
        logger.error("%s: %s", theatre_name, e)
        return []

    performances = []
    target_day_str = f"{target.day:02d}"

    for a in soup.find_all("a", href=re.compile(r"\?id_datum=\d+")):
        text = a.get_text(" ", strip=True)
        tokens = text.split()
        if len(tokens) < 2:
            continue
        if tokens[1] != target_day_str:
            continue

        # --- ZEIT ---
        time_str = _find_time(text)

        # --- VENUE & EXTRA ---
        venue_match = re.search(r"Uhr\s*,\s*(.+)", text)
        venue = venue_match.group(1).strip() if venue_match else None

        # --- TITEL ---
        title_match = re.match(
            r"^(?:Mo|Di|Mi|Do|Fr|Sa|So)\s+\d{2}\s+(?:\S.*?\s+)??([\w].+?)\s+\d{1,2}[.:]\d{2}\s*Uhr",
            text
        )
        if title_match:
            title = title_match.group(1).strip()
        else:
            # Fallback: Tokens 2..n-3 (ohne Wochentag, Tag, Zeit, Venue)
            title = " ".join(tokens[2:-3]).strip()

        # --- KOMPONIST aus <h4> (falls vorhanden) ---
        h4 = a.find("h4")
        extra = h4.get_text(strip=True) if h4 else venue

        # --- URL ---
        detail_url = urljoin("https://oper-frankfurt.de/de/spielplan/", a["href"])

        performances.append(Performance(theatre_name, title, time_str, detail_url, extra or venue))

    return _dedupe(performances)

# ─────────────────────────────────────────────────────────────────────────────
# Parser: Neues Theater Höchst
# ─────────────────────────────────────────────────────────────────────────────

def parse_neues_theater_hoechst(theatre_name: str, url: str, target: date) -> List[Performance]:
    try:
        soup = _get_soup(url)
    except Exception as e:
        logger.error("%s: %s", theatre_name, e)
        return []

    performances = []
    target_str = target.strftime("%d.%m.%Y")  # z. B. "03.05.2026"

    for row in soup.select("div.row.nth-content-list-item"):
        # --- DATUM: Suche nach dem Ziel-Datum ---
        date_span = row.select_one("span.nth-list-date")
        if not date_span:
            continue
        event_date = date_span.get_text(strip=True)
        if event_date != target_str:
            continue

        # --- UHRZEIT: Extrahiere Uhrzeit ---
        time_span = row.select_one("span.nth-list-time")
        time_str = _find_time(time_span.get_text(strip=True)) if time_span else "?"

        # --- TITEL: Künstler + Programm ---
        artist_el = row.select_one("h3.m-0")
        artist_text = artist_el.get_text(strip=True) if artist_el else "?"

        program_el = row.select_one("span.nth-list-event-program")
        program_text = program_el.get_text(strip=True) if program_el else ""

        # Titel kombinieren: Künstler + Programm (ohne HTML-Entities wie &quot;)
        title = f"{artist_text} – {program_text}" if program_text else artist_text
        title = title.replace("&quot;", '"')  # Ersetze HTML-Entities für Anführungszeichen

        # --- TICKET-LINK: Direkter Link zum Ticket-Shop ---
        ticket_link = None
        ticket_button = row.find("a", {"target": "shop"})
        if ticket_button and ticket_button.has_attr("href"):
            ticket_link = ticket_button["href"]

        # --- DETAIL-LINK: Link zur Veranstaltungseite (falls kein Ticket-Link) ---
        detail_link = None
        detail_button = row.find("a", href=re.compile(r"/tickets/alle-veranstaltungen/"))
        if detail_button and detail_button.has_attr("href"):
            detail_link = urljoin(url, detail_button["href"])

        # --- FÜGE PERFORMANCE HINZU (ohne extra-Feld) ---
        performances.append(
            Performance(
                theatre=theatre_name,
                title=title,
                time=time_str,
                url=ticket_link or detail_link,  # Kein Fallback auf url, um Preview-Links zu vermeiden
                extra=None  # Keine zusätzlichen Infos
            )
        )

    return _dedupe(performances)

# ─────────────────────────────────────────────────────────────────────────────
# Parser: Die Komödie
# ─────────────────────────────────────────────────────────────────────────────

def parse_komoedie(theatre_name: str, url: str, target: date) -> List[Performance]:
    try:
        soup = _get_soup(url)
    except Exception as e:
        logger.error(f"{theatre_name}: Fehler beim Laden der Seite: {e}")
        return []

    performances = []
    target_str = target.strftime("%d.%m.%Y")

    # --- 1. Versuche, die Daten aus dem statischen HTML zu extrahieren ---
    # Suche nach JSON-Daten in <script>-Tags (MEC speichert die Events oft als JSON im HTML)
    script_tags = soup.find_all("script", type="application/ld+json")
    for script in script_tags:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for event in data:
                    if event.get("@type") == "Event":
                        # --- DATUM: Extrahiere Startdatum ---
                        start_date = event.get("startDate", "")
                        if not start_date:
                            continue
                        try:
                            # Konvertiere ISO-Format (z. B. "2026-04-30T20:00:00+02:00") zu date
                            event_date = datetime.fromisoformat(start_date.replace("Z", "+00:00")).date()
                        except ValueError:
                            continue

                        if event_date != target:
                            continue

                        # --- UHRZEIT: Extrahiere Startzeit ---
                        start_time = event.get("startDate", "")
                        time_str = _find_time(start_time) if start_time else "?"

                        # --- TITEL: Extrahiere Titel ---
                        title = event.get("name", "?").strip()

                        # --- TICKET-LINK: Extrahiere URL ---
                        ticket_link = event.get("url")

                        # --- LABEL: Extrahiere Label (falls vorhanden) ---
                        extra = None

                        performances.append(
                            Performance(
                                theatre=theatre_name,
                                title=title,
                                time=time_str,
                                url=ticket_link,
                                extra=extra
                            )
                        )
        except (json.JSONDecodeError, AttributeError):
            continue

    # --- 2. Falls keine JSON-Daten gefunden wurden,Versuch mit dem statischen HTML ---
    if not performances:
        for event in soup.select("article.mec-event-article"):
            date_div = event.select_one("div.mec-event-date")
            if not date_div:
                continue

            date_text = date_div.get_text(" ", strip=True)
            date_parts = date_text.split()
            if len(date_parts) < 2:
                continue

            day = date_parts[0]
            month_abbr = date_parts[1].rstrip(".")

            month_num = None
            for m_abbr, m_num in DE_MONTH_ABBR.items():
                if month_abbr.lower() == m_abbr.lower():
                    month_num = m_num
                    break
            if not month_num:
                continue

            if int(day) != target.day or month_num != target.month:
                continue

            time_span = event.select_one("span.mec-start-time")
            time_str = _find_time(time_span.get_text(strip=True)) if time_span else "?"

            title_el = event.select_one("h4.mec-event-title a")
            title = title_el.get_text(strip=True) if title_el else "?"

            ticket_button = event.select_one("a.mec-detail-button[href]")
            ticket_link = ticket_button["href"] if ticket_button else None

            label_span = event.select_one("span.mec-event-label-captions")
            extra = label_span.get_text(strip=True) if label_span else None

            performances.append(
                Performance(
                    theatre=theatre_name,
                    title=title,
                    time=time_str,
                    url=ticket_link,
                    extra=extra
                )
            )

    return _dedupe(performances)

# ─────────────────────────────────────────────────────────────────────────────
# Parser: Die Schmiere
# ─────────────────────────────────────────────────────────────────────────────

def parse_die_schmiere(theatre_name: str, url: str, target: date) -> List[Performance]:
    try:
        soup = _get_soup(url)
    except Exception as e:
        logger.error("%s: %s", theatre_name, e)
        return []

    month_name = [
        k.capitalize() for k, v in DE_MONTHS.items()
        if v == target.month and len(k) >= 3
    ][0]

    # Matches: "Fr. 8. Mai: 20 Uhr:" or "So. 10. Mai: 19 Uhr:"
    date_pattern = re.compile(
        rf"(?:Mo|Di|Mi|Do|Fr|Sa|So)\.\s+{target.day}\.\s+{re.escape(month_name)}:\s+(\d{{1,2}})\s+Uhr",
        re.IGNORECASE,
    )

    # Extract all text lines from bold/strong elements — these carry dates AND titles
    # Plain text nodes carry subtitles/genres
    # Strategy: collect ALL leaf-level text blocks in document order, then
    # find the date line and harvest the next non-empty lines as subtitle + title.

    # Collect all text segments in document order, tagging each as bold or plain
    segments = []  # list of (is_bold: bool, text: str)
    for el in soup.find_all(string=True):
        text = el.strip()
        if not text:
            continue
        is_bold = el.parent.name in ("strong", "b") or (
            el.parent.parent and el.parent.parent.name in ("strong", "b")
        )
        segments.append((is_bold, text))

    performances = []

    for i, (is_bold, text) in enumerate(segments):
        if not is_bold:
            continue
        m = date_pattern.search(text)
        if not m:
            continue

        time_str = f"{int(m.group(1)):02d}:00"

        # Look ahead: collect up to 4 non-empty segments to find subtitle + title
        title = None
        extra_parts = []
        for j in range(i + 1, min(i + 8, len(segments))):
            _, seg_text = segments[j]
            seg_is_bold = segments[j][0]
            seg_text = seg_text.strip()
            if not seg_text:
                continue
            # Skip if it looks like the next date entry
            if date_pattern.search(seg_text) or re.match(
                r"(?:Mo|Di|Mi|Do|Fr|Sa|So)\.\s+\d+\.", seg_text
            ):
                break
            if seg_is_bold and title is None:
                title = seg_text
            elif title is None:
                # plain text before the bold title = genre/subtitle → extra
                extra_parts.append(seg_text.rstrip(":"))
            else:
                # plain text after title = cast / description
                extra_parts.append(seg_text)
                break  # one description line is enough

        if not title:
            continue

        extra = " | ".join(p for p in extra_parts if p) or None

        performances.append(Performance(
            theatre=theatre_name,
            title=title,
            time=time_str,
            url="https://die-schmiere.reservix.de/events",
            extra=extra,
        ))

    return _dedupe(performances)

# ─────────────────────────────────────────────────────────────────────────────
# Parser: Internationales Theater Frankfurt
# ─────────────────────────────────────────────────────────────────────────────

def parse_internationales_theater(theatre_name: str, url: str, target: date) -> List[Performance]:
    try:
        soup = _get_soup(url)
    except Exception as e:
        logger.error("%s: %s", theatre_name, e)
        return []

    # Date pattern as it appears: "So, 10. Mai. 2026 / 18:00 Uhr"
    date_pattern = re.compile(
        rf"(?:Mo|Di|Mi|Do|Fr|Sa|So),\s+{target.day}\.\s+(?:\w+\s+)?(\w+?)\.\s+{target.year}",
        re.IGNORECASE,
    )

    performances = []

    for h3 in soup.find_all("h3"):
        title_el = h3.find("a", href=True)
        if not title_el:
            continue

        # Walk up to find a container that holds the date text
        container = h3.parent
        found = False
        for _ in range(5):
            if date_pattern.search(container.get_text(" ", strip=True)):
                found = True
                break
            if container.parent:
                container = container.parent
        if not found:
            continue

        container_text = container.get_text(" ", strip=True)
        m = date_pattern.search(container_text)
        if not m:
            continue

        # Verify month matches target
        if DE_MONTH_ABBR.get(m.group(1).lower()[:3]) != target.month:
            continue

        # Skip cancelled events
        if re.search(r"Abgesagt", container_text, re.IGNORECASE):
            continue

        title = title_el.get_text(" ", strip=True)
        detail_url = urljoin("https://internationales-theater.de", title_el["href"])

        # Extract time directly from the date line to avoid _find_time
        # getting confused by the day number (e.g. "10." → "10:")
        time_str = "?"
        time_match = re.search(r"/\s*(\d{1,2}:\d{2})\s*Uhr", container_text)
        if time_match:
            time_str = time_match.group(1)

        # Subtitle from h4 (if present inside the container)
        subtitle = None
        h4 = container.find("h4")
        if h4:
            subtitle = h4.get_text(" ", strip=True)

        # Ticket link
        ticket_el = container.find("a", string=re.compile(r"Infos\s*&\s*Tickets", re.I))
        ticket_url = ticket_el["href"] if ticket_el else detail_url

        performances.append(Performance(
            theatre=theatre_name,
            title=title,
            time=time_str,
            url=ticket_url,
            extra=subtitle,
        ))

    return _dedupe(performances)

# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher – maps parser name → function
# ─────────────────────────────────────────────────────────────────────────────

_PARSERS = {
    "schauspiel_frankfurt": parse_schauspiel_frankfurt,
    "volksbuehne":          parse_volksbuehne,
    "kellertheater":        parse_kellertheater,
    "english_theatre":      parse_english_theatre,
    "dramatische_buehne":   parse_dramatische_buehne,
    "stalburg":             parse_stalburg,
    "oper_frankfurt":       parse_oper_frankfurt,
    "neues_theater_hoechst": parse_neues_theater_hoechst,
    "komoedie":             parse_komoedie,
    "die_schmiere":         parse_die_schmiere,
    "internationales_theater": parse_internationales_theater,
}


def fetch_theatre(entry: dict, target: date) -> List[Performance]:
    """
    Look up the parser for a theatre and run it.
    """
    parser_name = entry.get("parser")
    parser_func = _PARSERS.get(parser_name)

    if not parser_func:
        logger.error("No parser found for '%s'", parser_name)
        return []

    try:
        # Run the actual parser
        perfs = parser_func(entry["name"], entry["url"], target)
        
        # ────────── ADD THIS LINE BELOW ──────────
        logger.info("%s: %d performance(s) on %s", entry["name"], len(perfs), target)
        # ──────────────────────────────────────────
        
        return perfs
    except Exception as exc:
        logger.error("Parser '%s' crashed: %s", parser_name, exc)
        return []

def fetch_all(theatres: list, target: date, max_workers: int = 8) -> dict:
    """
    Run all theatre scrapers in parallel.
    Returns { theatre_name: [Performance, ...] }.
    """
    results = {t["name"]: [] for t in theatres}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {ex.submit(fetch_theatre, t, target): t["name"] for t in theatres}
        for future in concurrent.futures.as_completed(future_map):
            name = future_map[future]
            results[name] = future.result()
    return results

# ─────────────────────────────────────────────────────────────────────────────
# Message formatter
# ─────────────────────────────────────────────────────────────────────────────

def format_results(target: date, results: dict) -> str:
    date_str = target.strftime("%d.%m.%Y")
    lines = [f"🏛 *Frankfurter Theater – {date_str}*"]
    found_any = False

    for name, perfs in sorted(results.items()):
        if not perfs:
            continue
        found_any = True
        lines.append(f"\n*{name}*\n{'─' * 28}")
        for p in perfs:
            lines.append(p.format())
            lines.append("")

    if not found_any:
        lines.append(
            "\nFür diesen Tag wurden keine Vorstellungen gefunden.\n"
            "_Entweder gibt es wirklich keine, oder die Seiten konnten nicht gelesen werden._"
        )

    return "\n".join(lines)
