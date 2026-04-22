"""
scraper.py  ·  Frankfurt Theaterlust Telegram Bot – All scrapers in one place
════════════════════════════════════════════════════════════════

One file, one function per theatre.  No separate scraper modules.
To add a new parser, add a function here and reference it in theatres.py.
"""

import logging
import re
import concurrent.futures
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

    target_str = f"{target.day}.{target.month:02d}.{target.year}"
    performances = []

    for li in soup.select("li"):
        headings = li.select("h4")
        if not headings:
            continue
        date_text = headings[0].get_text(strip=True)
        if target_str not in date_text:
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

        # Ticket link
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
        k for k, v in DE_MONTHS.items() if v == target.month and len(k) > 3
    ][0].capitalize()

    for row in soup.select("div.zeile"):
        # --- DATE ---
        day_el = row.select_one(".news-day")
        if not day_el or day_el.get_text(strip=True) != target_day:
            continue

        month_text = row.get_text(" ", strip=True)
        if target_month.lower() not in month_text.lower():
            continue

        # --- TIME ---
        time_el = row.select_one(".news-content-left-colright b")
        time_str = _find_time(time_el.get_text(" ", strip=True)) if time_el else "?"

        # --- TITLE ---
        title_el = row.select_one(".beschreibung big")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        # --- LINK ---
        link_el = row.select_one(".beschreibung a[href]")
        ticket_url = urljoin(url, link_el["href"]) if link_el else url

        performances.append(Performance(theatre_name, title, time_str, ticket_url))

    result = _dedupe(performances)
    return result

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
        # logger.error("DramatischeBühne: %s", e)
        return []

    performances = []
    month_name = [k.capitalize() for k, v in DE_MONTHS.items() if v == target.month][0]
    date_query = f"{target.day}. {month_name} {target.year}"

    for element in soup.find_all(string=re.compile(re.escape(date_query))):
        parent = element.parent
        full_text = parent.get_text(" ", strip=True)

        title_el = None
        curr = parent
        while curr and not title_el:
            title_el = curr.find_previous(["h2", "h3", "h1"])
            curr = curr.parent
            if curr and curr.name == "body": break
            
        if not title_el:
            continue
            
        title = title_el.get_text(strip=True)

        time_match = re.search(r"(\d{1,2}[:.]\d{2})\s*Uhr", full_text)
        time_str = time_match.group(1).replace(".", ":") if time_match else "?"

        # EXTRA INFO: Capture the location (e.g., "Grüneburgpark")
        extra = None
        if "Frankfurt" in full_text:
            # Splits at comma to get "Grüneburgpark" from "Frankfurt am Main, Grüneburgpark"
            parts = full_text.split(",")
            if len(parts) > 1:
                extra = parts[-1].replace(".", "").strip()

        # LINK: Find the link inside the title header or the nearest 'Reservieren' link
        link_el = title_el.find("a", href=True) or parent.find("a", href=True)
        detail_url = urljoin(url, link_el["href"]) if link_el else url

        performances.append(Performance(theatre_name, title, time_str, detail_url, extra))

    return _dedupe(performances)


# ─────────────────────────────────────────────────────────────────────────────
# Parser: Stalburg Theater
# ─────────────────────────────────────────────────────────────────────────────

# to be added

# ─────────────────────────────────────────────────────────────────────────────
# Parser: Die Komödie
# ─────────────────────────────────────────────────────────────────────────────

# to be added

# ─────────────────────────────────────────────────────────────────────────────
# Parser: Oper Frankfurt
# ─────────────────────────────────────────────────────────────────────────────

# to be added

# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher – maps parser name → function
# ─────────────────────────────────────────────────────────────────────────────

_PARSERS = {
    "schauspiel_frankfurt": parse_schauspiel_frankfurt,
    "volksbuehne":          parse_volksbuehne,
    "kellertheater":        parse_kellertheater,
    "english_theatre":      parse_english_theatre,
    "dramatische_buehne":   parse_dramatische_buehne,
    # "komoedie":             parse_komoedie,
    # "stalburg":             parse_stalburg,
    # "oper_frankfurt":       parse_oper_frankfurt
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
