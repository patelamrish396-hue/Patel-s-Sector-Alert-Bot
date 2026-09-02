"""
Sector News Alert — Telegram Bot
==================================
Polls Indian financial news every ~10-15 minutes. The moment a new article
matches keywords for a tracked sector (Auto, Banking, IT, Pharma, Energy,
Metals, FMCG, Realty, Defence), it sends an immediate Telegram alert tagged
with which sector(s) it likely affects.

This is event-driven, unlike the once-a-day market brief — it only speaks
up when something new and relevant shows up.

Runs every 10-15 min via GitHub Actions (see .github/workflows/).
Remembers which articles it has already seen using seen_articles.json,
which the workflow commits back to the repo.
"""

import os
import sys
import re
import json
import html
import requests
import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

_sentiment_analyzer = SentimentIntensityAnalyzer()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SEEN_FILE = "seen_articles.json"
MAX_SEEN_HISTORY = 800   # keep the state file from growing forever

NEWS_FEEDS = {
    "Economic Times Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Economic Times Industry": "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms",
    "Moneycontrol": "https://www.moneycontrol.com/rss/marketreports.xml",
    "Moneycontrol Business": "https://www.moneycontrol.com/rss/business.xml",
    "Livemint Markets": "https://www.livemint.com/rss/markets",
}

# Sector keyword mapping — case-insensitive substring match against each
# article's title + summary. Tune this list any time; no code changes needed
# elsewhere.
SECTOR_KEYWORDS = {
    "🚗 Auto": [
        "auto sector", "automobile", "car sales", "ev sales", "electric vehicle",
        "maruti", "tata motors", "mahindra", "bajaj auto", "hero motocorp",
        "two-wheeler", "vehicle sales", "eicher motors", "tvs motor",
    ],
    "🏦 Banking": [
        "rbi", "repo rate", "interest rate", "monetary policy", "banking sector",
        "npa", "credit growth", "sbi", "hdfc bank", "icici bank", "axis bank",
        "kotak", "bank of baroda", "psu bank",
    ],
    "💻 IT": [
        "it sector", "software services", "h-1b", "visa curbs", "tcs", "infosys",
        "wipro", "hcltech", "tech mahindra", "tech layoffs", "it services",
        "outsourcing", "ai spending",
    ],
    "💊 Pharma": [
        "pharma", "usfda", "fda approval", "generic drug", "sun pharma",
        "dr reddy", "cipla", "vaccine", "healthcare sector", "drug price",
        "clinical trial",
    ],
    "⚡ Energy": [
        "crude oil", "opec", "brent", "natural gas", "ongc", "reliance industries",
        "energy sector", "power sector", "renewable energy", "solar power",
        "coal india", "petroleum",
    ],
    "⛏️ Metals": [
        "steel", "metal sector", "aluminium", "copper prices", "tata steel",
        "jsw steel", "hindalco", "commodity prices", "mining sector", "vedanta",
    ],
    "🛒 FMCG": [
        "fmcg", "consumer goods", "hindustan unilever", "hul", "itc ltd",
        "nestle india", "rural demand", "consumer spending", "britannia",
    ],
    "🏗️ Realty": [
        "real estate", "realty sector", "housing sales", "property prices",
        "dlf", "godrej properties", "home loan rate", "construction sector",
    ],
    "🛡️ Defence": [
        "defence", "defense sector", "military", "hal ", "bharat electronics",
        "bharat dynamics", "border tension", "ceasefire", "missile test",
        "drone strike", "army", "navy", "air force", "defence deal",
    ],
}


# --------------------------------------------------------------------------
# State (which articles have we already alerted on)
# --------------------------------------------------------------------------

def load_seen() -> set:
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen: set):
    trimmed = list(seen)[-MAX_SEEN_HISTORY:]
    with open(SEEN_FILE, "w") as f:
        json.dump(trimmed, f)


# --------------------------------------------------------------------------
# Fetch & classify
# --------------------------------------------------------------------------

def fetch_all_articles():
    articles = []
    for source, url in NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                link = entry.get("link", "")
                if not link:
                    continue
                articles.append({
                    "source": source,
                    "title": entry.get("title", "").strip(),
                    "summary": entry.get("summary", "") or entry.get("description", ""),
                    "link": link,
                })
        except Exception as e:
            print(f"[warn] feed failed ({source}): {e}", file=sys.stderr)
    return articles


def classify_sectors(article) -> list:
    text = f"{article['title']} {article['summary']}".lower()
    matched = []
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(sector)
    return matched


def clean_snippet(raw_html: str, max_len: int = 320) -> str:
    """Strip HTML tags from an RSS summary and trim it to a short teaser.
    This is the feed's own short blurb, not a full-article paraphrase —
    kept brief on purpose, both for readability and to stay well clear of
    reproducing article text."""
    text = re.sub(r"<[^>]+>", " ", raw_html or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "…"
    return text


def classify_sentiment(article) -> tuple:
    """Rough automatic tone read using a general-purpose sentiment tool
    (not finance-tuned) — treat as a quick gut-check, not a trading signal.
    Returns (emoji, label)."""
    text = f"{article['title']}. {article['summary']}"
    score = _sentiment_analyzer.polarity_scores(text)["compound"]
    if score >= 0.25:
        return "🟢", "Positive"
    elif score <= -0.25:
        return "🔴", "Negative"
    return "⚪", "Neutral"


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------

def _chunk_message(text: str, max_len: int = 3800):
    """Split into Telegram-safe chunks, breaking only on line boundaries so
    an HTML tag is never cut in half across two messages."""
    lines = text.split("\n")
    chunks, current, current_len = [], [], 0
    for line in lines:
        if current and current_len + len(line) + 1 > max_len:
            chunks.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chunk in _chunk_message(text):
        resp = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=30)
        if not resp.ok:
            print(f"[error] Telegram API error: {resp.status_code} {resp.text}", file=sys.stderr)
            resp.raise_for_status()


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    seen = load_seen()
    is_first_run = len(seen) == 0
    articles = fetch_all_articles()

    new_alerts = []
    for article in articles:
        if article["link"] in seen:
            continue
        seen.add(article["link"])  # mark seen regardless of match, so we never re-check it

        if is_first_run:
            continue  # warm start: learn what's already out there, don't alert on it

        sectors = classify_sectors(article)
        if sectors:
            new_alerts.append((article, sectors))

    if is_first_run:
        print(f"First run: recorded {len(seen)} existing articles as a baseline, no alerts sent.")
    elif new_alerts:
        lines = ["<b>⚡ Sector Alert</b>", ""]
        for article, sectors in new_alerts:
            tag = " ".join(sectors)
            emoji, label = classify_sentiment(article)
            title = html.escape(article["title"])
            link = html.escape(article["link"])
            snippet = html.escape(clean_snippet(article["summary"]))

            lines.append(f"{tag}  {emoji} {label}")
            lines.append(f"<b>{title}</b>")
            if snippet:
                lines.append(snippet)
            lines.append(f'<a href="{link}">Read more</a> · <i>{article["source"]}</i>')
            lines.append("")
        send_telegram_message("\n".join(lines))
        print(f"Sent alert for {len(new_alerts)} article(s).")
    else:
        print("No new sector-relevant articles this run.")

    save_seen(seen)


if __name__ == "__main__":
    main()
