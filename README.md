# Sector News Alert — Telegram Bot

Watches Indian financial news continuously. The moment an article matches
one of your tracked sectors — Auto, Banking, IT, Pharma, Energy, Metals,
FMCG, Realty, Defence — it sends an immediate Telegram alert, so you find
out as it happens rather than waiting for the next morning brief.

## How it works

- Checks 5 news feeds every ~15 minutes
- Matches each new article's headline/summary against keyword lists per sector
- Sends one alert message per run, listing every new relevant article found,
  tagged with which sector(s) it likely affects
- Remembers what it's already seen, so nothing gets alerted twice

## Setup

You can reuse the **same Telegram bot** you already made for the market
brief — no need for a new one. Just point this at the same chat.

1. Push this folder to a new GitHub repo (or a new folder inside your
   existing one, if you'd rather keep everything together).
2. Add these repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | same token as your other bots |
| `TELEGRAM_CHAT_ID` | same chat ID, or a different one if you want alerts separate from the daily brief |

3. Go to **Actions** → **Sector News Alert** → **Run workflow** to test.

## Important: the first run is silent on purpose

The very first time this runs, it has no memory of what's "old" news yet —
so instead of flooding you with every recent article at once, it quietly
records everything currently out there as a starting baseline and sends
**no alerts** for that run. From the second run onward, it only alerts on
genuinely new articles. This is normal — check the Actions log and you'll
see "First run: recorded N existing articles as a baseline."

## Customizing sectors/keywords

Open `sector_news_bot.py` and edit the `SECTOR_KEYWORDS` dictionary near the
top — add, remove, or retune keywords per sector any time, no other code
changes needed. Keywords are matched as simple lowercase substrings against
each article's title + summary.

## Honest caveats

- **Keyword matching isn't perfect.** It'll occasionally flag something
  loosely related (a keyword like "bank" can appear in unrelated contexts),
  and it can miss events that are genuinely important but phrased in a way
  that doesn't hit any keyword. Tune the list as you notice gaps.
- **~15 minute delay, not instant** — fine for most sector-moving news,
  which usually keeps mattering for hours/days, not seconds.
- If a feed goes down or changes format, that one source is skipped
  (logged as a `[warn]`) rather than breaking the whole run.
