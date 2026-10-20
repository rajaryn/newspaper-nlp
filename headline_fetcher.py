# /// script
# dependencies = ["requests"]
# ///
"""
Step 2 of 2: fill in the headline column of the CSVs made by sitemap_scraper.py.

Run:   uv run headline_fetcher.py
Edit the SETTINGS block below to change which files and how fast.

For every row with an empty headline it opens the article page, reads og:title
(falling back to <title>) and writes it into the same CSV.

Safe to stop and restart: progress is saved every SAVE_EVERY articles and on Ctrl-C;
running it again only fetches rows that still have no headline.
"""

import csv
import faulthandler
import gzip
import html
import os
import re
import socket
import sys
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

# ============================== SETTINGS ==============================
RUN_SITES = ["ie", "jansatta"]  # reads data/<site>/<site>_<YEAR>.csv for each of these
YEAR = 2024
DATA = Path(__file__).parent / "data"   # CSVs live in data/<site>/
MONTHS = ""                     # "" = every row in the file; "1-8" = only those months

WORKERS = 4                     # articles fetched at the same time
DELAY = 1.0                     # seconds each worker waits between its requests (~4 pages/s total)
REQUEST_LIMIT = 30              # seconds: a request taking longer than this is abandoned
RETRIES = 3                     # tries per article before giving up on it
SAVE_EVERY = 500                # articles between progress saves
# ======================================================================

HEADERS = {"User-Agent": "Mozilla/5.0 (academic NLP project; headline research)"}
FIELDS = ["date", "headline", "slug", "url", "section", "source"]

_local = threading.local()      # one requests.Session per thread (Sessions aren't thread-safe)
robots = RobotFileParser()
fail_streak = 0
fail_lock = threading.Lock()


class TooSlow(Exception):
    pass


# ----------------------------- network --------------------------------
def session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.headers.update(HEADERS)
    return _local.s


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


def get_head(url):
    """Download a page up to </head> (the headline is in <head>), with a hard time limit."""
    faulthandler.dump_traceback_later(180, repeat=False, file=sys.stderr)  # report if stuck 3 min
    stop = b"</head>"
    with session().get(url, timeout=(10, 15), stream=True) as r:
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
            data = b""
            for chunk in r.iter_content(4096):
                data += chunk
                if stop in data[-len(chunk) - len(stop):] or len(data) > 2_000_000:
                    break
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


def fetch_head(url):
    """get_head() with retries and back-off. Bytes or None."""
    global fail_streak
    if not robots.can_fetch(HEADERS["User-Agent"], url):
        return None
    for attempt in range(1, RETRIES + 1):
        time.sleep(DELAY)
        try:
            data = get_head(url)
            with fail_lock:
                fail_streak = 0
            return data
        except (requests.RequestException, TooSlow) as e:
            err = str(e)
            m = re.search(r"retry-after (\d+)", err)
            if m:
                time.sleep(min(int(m.group(1)), 300))
            if isinstance(e, requests.HTTPError) and " 404 " in f" {err} ":
                return None  # page is gone; retrying won't help
        print(f"  try {attempt}/{RETRIES} failed: {url} ({err[:120]})")
        time.sleep(5 * 3 ** (attempt - 1))  # 5 s, 15 s, 45 s
    with fail_lock:
        fail_streak += 1
        if fail_streak >= 20:
            print("  20 articles in a row failed: the site may be blocking us. Pausing 10 minutes...")
            time.sleep(600)
            fail_streak = 0
    return None


def init_robots(base):
    global robots
    robots = RobotFileParser()
    try:
        r = session().get(base.rstrip("/") + "/robots.txt", timeout=(10, 15))
        r.raise_for_status()
        robots.parse([ln for ln in r.text.splitlines() if ln.strip()])
        for entry in robots.entries + ([robots.default_entry] if robots.default_entry else []):
            entry.rulelines.sort(key=lambda rl: len(rl.path), reverse=True)
    except requests.RequestException:
        robots.allow_all = True


def fetch_title(url):
    data = fetch_head(url)
    if data is None:
        return ""
    page = data.decode("utf-8", "ignore")  # Indian news sites are UTF-8; keeps Hindi intact
    m = re.search(r'<meta[^>]+(?:property|name)=["\']og:title["\'][^>]+content=(["\'])(.*?)\1', page) \
        or re.search(r'<meta[^>]+content=(["\'])(.*?)\1[^>]+(?:property|name)=["\']og:title', page) \
        or re.search(r"<title[^>]*>()(.*?)</title>", page, re.S)
    if not m:
        return ""
    title = html.unescape(re.sub(r"\s+", " ", m.group(2))).strip()
    return re.sub(r"\s+\|\s+[^|]{1,30}$", "", title)  # drop " | Site Name"


# ------------------------------- files --------------------------------
def months_list():
    if not MONTHS:
        return set(range(1, 13))
    a, _, b = MONTHS.partition("-")
    return set(range(int(a), int(b or a) + 1))


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        return {r["url"]: r for r in csv.DictReader(f)}


def save(rows, path):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["date"], r["url"])))
    for _ in range(30):  # on Windows the CSV may be open in Excel; wait instead of crashing
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            print(f"  can't write {path} (is it open in Excel?) - retrying in 10 s")
            time.sleep(10)
    raise SystemExit(f"Could not write {path}; close it and run again.")


# ------------------------------- main ---------------------------------
def fill_site(name):
    path = str(DATA / name / f"{name}_{YEAR}.csv")
    print(f"\n=== {path} ===")
    if not os.path.exists(path):
        print(f"  {path} not found - run sitemap_scraper.py first")
        return
    rows = load(path)
    months = months_list()
    missing = [u for u, r in rows.items() if not r["headline"] and int(r["date"][5:7]) in months]
    if not missing:
        print(f"  all {len(rows)} articles already have a headline")
        return
    p = urlparse(missing[0])
    init_robots(f"{p.scheme}://{p.netloc}")

    hours = len(missing) * DELAY / WORKERS / 3600
    print(f"  {len(rows) - len(missing)} headlines already known; fetching {len(missing)} (~{hours:.1f} h)")
    start, done, empty = time.monotonic(), 0, 0
    pool = ThreadPoolExecutor(max_workers=WORKERS)
    try:
        futures = {pool.submit(fetch_title, u): u for u in missing}
        for f in as_completed(futures):
            title = f.result()
            rows[futures[f]]["headline"] = title
            done += 1
            empty += not title
            if done % 50 == 0 or done == len(missing):
                rate = done / (time.monotonic() - start)
                left = (len(missing) - done) / rate / 3600 if rate else 0
                print(f"  {done}/{len(missing)}  ({rate:.1f}/s, ~{left:.1f} h left, {empty} without headline)")
            if done % SAVE_EVERY == 0:
                save(rows, path)
    except KeyboardInterrupt:
        pool.shutdown(wait=False, cancel_futures=True)
        save(rows, path)
        print(f"\nStopped. Progress saved to {path}; run again to continue.")
        raise SystemExit(1)
    finally:
        faulthandler.cancel_dump_traceback_later()
    pool.shutdown()
    save(rows, path)
    still = sum(1 for r in rows.values() if not r["headline"])
    print(f"  saved {path}: {len(rows)} articles, {still} still without a headline"
          + (" (run again to retry them)" if still else ""))


def main():
    for name in RUN_SITES:
        fill_site(name)


if __name__ == "__main__":
    main()