# /// script
# dependencies = ["requests"]
# ///
"""
Step 1 of 2: list the articles in each day's sitemap and save them to a CSV.
Headlines are filled in afterwards by headline_fetcher.py.

Run:   uv run sitemap_scraper.py
Edit the SETTINGS block below to change sites, year, months or sample size.

Output: one CSV per site, data/<site>/<site>_<year>.csv
        columns: date, headline, slug, url, section, source
        (headline stays empty unless the sitemap itself has one, or an earlier run
         of headline_fetcher.py already filled it in - those are kept)

Running it again for other months adds them to the same CSV; months not in
MONTHS are left as they are.
"""

import calendar
import csv
import faulthandler
import gzip
import os
import random
import re
import socket
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

# ============================== SETTINGS ==============================
SITES = {
    "ie": {
        "base": "https://indianexpress.com",
        "daily": "https://indianexpress.com/sitemap.xml?yyyy={y}&mm={m:02d}&dd={d:02d}",
    },
    "jansatta": {
        "base": "https://www.jansatta.com",
        "daily": "https://www.jansatta.com/sitemap.xml?yyyy={y}&mm={m:02d}&dd={d:02d}",
    },
}
RUN_SITES = ["jansatta"]  # which of SITES to scrape, in order
YEAR = 2024
DATA = Path(__file__).parent / "data"   # CSVs live in data/<site>/
MONTHS = "1-8"                  # "" = whole year; "9-12" for the rest; "1" for a quick test
PER_DAY = 100                   # 0 = keep all articles; otherwise a fixed random sample per day

DELAY = 1.0                     # seconds between requests
REQUEST_LIMIT = 30              # seconds: a request taking longer than this is abandoned
RETRIES = 3                     # tries per sitemap before giving up on that day
# ======================================================================

HEADERS = {"User-Agent": "Mozilla/5.0 (academic NLP project; headline research)"}
GENERIC_SEGMENTS = {"article", "articles", "news", "story", "amp", "hindi", "lite", "photos", "web"}
NON_ARTICLE = ("/web-stories/", "/videos/", "/photos/", "/podcast/")
FIELDS = ["date", "headline", "slug", "url", "section", "source"]

_session = requests.Session()
_session.headers.update(HEADERS)
robots = RobotFileParser()


class TooSlow(Exception):
    pass


# ----------------------------- network --------------------------------
def _cut(r, flag):
    """Called by the timer: shut the socket so a blocked read returns at once."""
    flag.set()
    for path in (("raw", "_connection", "sock"), ("raw", "_fp", "fp", "raw", "_sock")):
        obj = r
        try:
            for attr in path:
                obj = getattr(obj, attr)
            obj.shutdown(socket.SHUT_RDWR)
            return
        except Exception:
            continue
    try:
        r.close()
    except Exception:
        pass


def get(url):
    """One GET with a hard total time limit. Returns bytes. Raises on failure."""
    faulthandler.dump_traceback_later(180, repeat=False, file=sys.stderr)  # report if stuck 3 min
    with _session.get(url, timeout=(10, 15), stream=True) as r:
        # the normal timeout only measures gaps between bytes; a slow-dripping server
        # never trips it, so a timer cuts the connection after REQUEST_LIMIT seconds
        timed_out = threading.Event()
        timer = threading.Timer(REQUEST_LIMIT, _cut, (r, timed_out))
        timer.daemon = True
        timer.start()
        try:
            if r.status_code in (429, 503):
                wait = r.headers.get("Retry-After", "")
                raise requests.HTTPError(f"{r.status_code} retry-after {wait}" if wait.isdigit()
                                         else f"{r.status_code} (site asks to slow down)")
            r.raise_for_status()
            data = b"".join(r.iter_content(4096))
        except Exception:
            if timed_out.is_set():
                raise TooSlow(f"took over {REQUEST_LIMIT}s") from None
            raise
        finally:
            timer.cancel()
        if timed_out.is_set():
            raise TooSlow(f"took over {REQUEST_LIMIT}s")
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except OSError:
            pass
    return data


def fetch(url, check=None):
    """get() with retries and back-off; `check(data)` must accept the reply. Bytes or None."""
    if not robots.can_fetch(HEADERS["User-Agent"], url):
        print(f"  robots.txt disallows {url}, skipping")
        return None
    for attempt in range(1, RETRIES + 1):
        time.sleep(DELAY)
        try:
            data = get(url)
            if check is None or check(data):
                return data
            err = "reply was not a sitemap (block page?)"
        except (requests.RequestException, TooSlow) as e:
            err = str(e)
            m = re.search(r"retry-after (\d+)", err)
            if m:
                time.sleep(min(int(m.group(1)), 300))
        print(f"  try {attempt}/{RETRIES} failed: {url} ({err[:120]})")
        time.sleep(5 * 3 ** (attempt - 1))  # 5 s, 15 s, 45 s
    return None


def init_robots(base):
    global robots
    robots = RobotFileParser()
    try:
        r = _session.get(base.rstrip("/") + "/robots.txt", timeout=(10, 15))
        r.raise_for_status()
        robots.parse([ln for ln in r.text.splitlines() if ln.strip()])
        for entry in robots.entries + ([robots.default_entry] if robots.default_entry else []):
            entry.rulelines.sort(key=lambda rl: len(rl.path), reverse=True)
    except requests.RequestException:
        robots.allow_all = True


# ----------------------------- parsing --------------------------------
def local(tag):
    return tag.rsplit("}", 1)[-1]


def child_text(el, name):
    for c in el.iter():
        if local(c.tag) == name and c.text:
            return c.text.strip()
    return ""


def section_from_url(url):
    parts = [p for p in urlparse(url).path.split("/") if p]
    for p in parts[:-1]:
        if p.lower() not in GENERIC_SEGMENTS and not p.isdigit():
            return p
    return ""


def slug_from_url(url):
    parts = [p for p in urlparse(url).path.split("/") if p]
    best = max(parts, key=len) if parts else ""
    best = re.sub(r"\.(html?|cms|php)$", "", best)
    best = re.sub(r"[-_]?\d{5,}$", "", best)
    return best.replace("-", " ").replace("_", " ").strip()


def is_sitemap(data):
    """True only for a real sitemap (a block page can also be well-formed XML)."""
    try:
        return local(ET.fromstring(data).tag) in ("urlset", "sitemapindex")
    except ET.ParseError:
        return False


def read_day(url, day):
    """Articles listed in one day's sitemap, or None if it couldn't be read."""
    data = fetch(url, check=is_sitemap)
    if data is None:
        return None
    rows, seen = [], set()
    for u in ET.fromstring(data):
        if local(u.tag) != "url":
            continue
        loc = child_text(u, "loc")
        if not loc or loc in seen or any(p in loc for p in NON_ARTICLE):
            continue
        seen.add(loc)
        rows.append({
            "date": day,
            "headline": child_text(u, "title"),
            "slug": slug_from_url(loc),
            "url": loc,
            "section": section_from_url(loc),
            "source": urlparse(loc).netloc,
        })
    return rows


def sample_day(rows, day):
    """Fixed sample for a day: the same day always gives the same articles,
    whichever months a run covers (seeded by the date, not by run order)."""
    if not PER_DAY or len(rows) <= PER_DAY:
        return rows
    rows = sorted(rows, key=lambda r: r["url"])
    return random.Random(day).sample(rows, PER_DAY)


# ------------------------------- files --------------------------------
def months_list():
    if not MONTHS:
        return list(range(1, 13))
    a, _, b = MONTHS.partition("-")
    return list(range(int(a), int(b or a) + 1))


def save(rows, out):
    tmp = out + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["date"], r["url"])))
    for _ in range(30):  # on Windows the CSV may be open in Excel; wait instead of crashing
        try:
            os.replace(tmp, out)
            return
        except PermissionError:
            print(f"  can't write {out} (is it open in Excel?) - retrying in 10 s")
            time.sleep(10)
    raise SystemExit(f"Could not write {out}; close it and run again.")


def load(out):
    try:
        with open(out, newline="", encoding="utf-8") as f:
            return {r["url"]: r for r in csv.DictReader(f)}
    except FileNotFoundError:
        return {}


# ------------------------------- main ---------------------------------
def scrape_site(name, site):
    (DATA / name).mkdir(parents=True, exist_ok=True)
    out = str(DATA / name / f"{name}_{YEAR}.csv")
    print(f"\n=== {name} {YEAR} -> {out} ===")
    init_robots(site["base"])
    previous = load(out)
    run_months = months_list()

    # keep articles from months this run doesn't cover
    rows = {u: r for u, r in previous.items() if int(r["date"][5:7]) not in run_months}
    if rows:
        print(f"keeping {len(rows)} articles from other months already in {out}")

    failed_days, listed = [], {}
    try:
        for m in run_months:
            for d in range(1, calendar.monthrange(YEAR, m)[1] + 1):
                day = f"{YEAR}-{m:02d}-{d:02d}"
                got = read_day(site["daily"].format(y=YEAR, m=m, d=d), day)
                if got is None:
                    failed_days.append(day)
                    kept = [r for r in previous.values() if r["date"] == day]
                    for r in kept:  # keep that day's articles from an earlier run
                        rows[r["url"]] = r
                    print(f"{day}: FAILED" + (f" (kept {len(kept)} from earlier run)" if kept else ""))
                    continue
                listed[day] = len(got)
                picked = sample_day(got, day)
                for r in picked:
                    old = previous.get(r["url"])
                    if old and old.get("headline") and not r["headline"]:
                        r["headline"] = old["headline"]  # keep a headline fetched earlier
                    rows[r["url"]] = r
                note = f" (kept {len(picked)})" if len(picked) < len(got) else ""
                print(f"{day}: {len(got)} articles{note}")
            save(rows, out)  # keep what we have after every month
    except KeyboardInterrupt:
        save(rows, out)
        print(f"\nStopped. Saved what was collected to {out}; run again to redo these months.")
        raise SystemExit(1)
    finally:
        faulthandler.cancel_dump_traceback_later()

    save(rows, out)

    # health check
    if listed:
        median = sorted(listed.values())[len(listed) // 2]
        thin = [f"{d} ({n})" for d, n in sorted(listed.items()) if n < median * 0.25]
        if thin:
            print(f"WARNING thin days (under 25% of the usual {median}): {', '.join(thin)}")
    if failed_days:
        print(f"WARNING {len(failed_days)} days could not be read: {', '.join(failed_days)}")
        print("  Run again later with MONTHS set to those months.")
    with_title = sum(1 for r in rows.values() if r["headline"])
    print(f"saved {out}: {len(rows)} articles ({with_title} already have a headline)")


def main():
    for name in RUN_SITES:
        scrape_site(name, SITES[name])
    print("\nNext: uv run headline_fetcher.py")


if __name__ == "__main__":
    main()