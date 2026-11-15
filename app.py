# /// script
# dependencies = [
#   "flask", "pandas", "scikit-learn", "joblib",
#   "nltk", "simplemma", "indic-nlp-library", "matplotlib",
# ]
# ///
"""
Phase 7: two separate pages on one Flask app (templates/, static/).

Run:   uv run app.py
       then open http://localhost:5000            Dashboard (home page): explore the results
                 http://localhost:5000/pipeline   Pipeline: type a headline, watch it go through every step
       (Ctrl-C in the terminal to stop)

Needs:  data/analysis/all_classified.csv              (from analysis.py)
        models/best_en.joblib, models/best_hi.joblib  (from baseline.py)
        preprocess.py and analysis.py in the same folder: the Pipeline page calls their
        functions, so every step it shows is exactly what the real pipeline does.

The app only READS the pipeline's outputs; it never retrains or rewrites anything.
"""

import math
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from flask import Flask, jsonify, redirect, render_template, request

# ============================== SETTINGS ==============================
DATA = "data/analysis/all_classified.csv"
MODEL_FILES = {"en": "models/best_en.joblib", "hi": "models/best_hi.joblib"}
MIN_ARTICLES_PER_DAY = 30   # days with fewer headlines are left out of daily charts (as in analysis.py)
PORT = 5000
EVENTS = [  # (name, date, what to track, days before, days after) - keep in sync with analysis.py
    ("Ram temple consecration", "2024-01-22", "entity:Ayodhya", 7, 7),
    ("Kejriwal arrested by ED", "2024-03-21", "entity:Arvind Kejriwal", 7, 10),
    ("Lok Sabha results", "2024-06-04", "Politics", 10, 10),
    ("T20 World Cup final", "2024-06-29", "Sports", 7, 7),
    ("Wayanad landslides", "2024-07-30", "Weather/Environment", 7, 10),
    ("Paris Olympics opening", "2024-07-26", "Sports", 5, 20),
    ("Kolkata RG Kar case", "2024-08-09", "Crime/Law", 3, 20),
    ("Bangladesh unrest, Hasina resigns", "2024-08-05", "entity:Bangladesh", 7, 10),
]
# ======================================================================

ROOT = Path(__file__).resolve().parent
CATEGORIES = ["Politics", "Sports", "Business", "Weather/Environment", "Crime/Law",
              "Entertainment", "Tech/Science", "Health", "Other"]
PAPER_NAME = {"ie_2024": "Indian Express", "jansatta_2024": "Jansatta"}
PAPERS = list(PAPER_NAME.values())
sys.path.insert(0, str(ROOT))  # so the pipeline scripts (preprocess.py, analysis.py) can be imported

app = Flask(__name__)  # serves templates/ and static/


# =========================== data loading ============================
# Everything is loaded once and cached (lru_cache), so only the first request is slow.

@lru_cache(maxsize=1)
def load():
    """Every classified headline from analysis.py, with a few columns added for the API."""
    path = ROOT / DATA
    if not path.exists():
        sys.exit(f"Not found: {path}. Run analysis.py first, or fix DATA at the top of app.py.")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["date"] = pd.to_datetime(df["date"])
    df["Paper"] = df["paper"].map(PAPER_NAME)                     # display name
    df["entity_list"] = df["entities"].apply(lambda s: [e for e in s.split("; ") if e])
    df["shown"] = df["headline"].where(df["headline"] != "", df["text"])  # headline, else URL slug
    return df


@lru_cache(maxsize=2)
def model(lang):
    """The saved Phase 5 model for one language, split into its parts.

    vec         the fitted TF-IDF vectorizer (words + word pairs)
    clf         the fitted logistic regression
    tokenize    preprocess.py's tokenizer for this language (text -> tokens)
    to_version  turns tokens into the text version the model was trained on (tokens/stem/lemma)
    version     the name of that version
    features    column index -> word / word pair
    """
    import joblib
    import preprocess  # reuse exactly the preprocessing the model was trained with

    path = ROOT / MODEL_FILES[lang]
    if not path.exists():
        return None
    bundle = joblib.load(path)            # {"pipeline", "version", "lang"} saved by baseline.py
    tokenize, stem, lemma = preprocess.PIPE[lang]
    version = bundle["version"]
    pipe = bundle["pipeline"]
    return SimpleNamespace(
        vec=pipe.named_steps["vec"], clf=pipe.named_steps["clf"], tokenize=tokenize,
        to_version={"tokens": lambda t: t, "stem": stem, "lemma": lemma}[version], version=version,
        features=pipe.named_steps["vec"].get_feature_names_out(),
    )


def model_input(m, text):
    """Raw headline -> the space-separated string the model's vectorizer expects."""
    return " ".join(m.to_version(m.tokenize(text)))


def detect_lang(text):
    """Any Devanagari character means Hindi."""
    return "hi" if any("ऀ" <= ch <= "ॿ" for ch in text) else "en"


# ============================== helpers ==============================
def num(x, nd=2):
    """Round a number for JSON; NaN/None -> None (JSON has no NaN)."""
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


def filtered():
    """Apply the dashboard's global filters (?start=&end=&papers=a,b) shared by every view."""
    df = load()
    start = request.args.get("start") or df["date"].min()
    end = request.args.get("end") or df["date"].max()
    papers = [p for p in request.args.get("papers", ",".join(PAPERS)).split(",") if p in PAPERS]
    return df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
              & df["Paper"].isin(papers)], papers


def share_over_time(df, freq, what):
    """% of each paper's headlines per period (D/W/M) that match `what`:
    a topic, "entity:Name", or a True/False Series (one value per row of df)."""
    if isinstance(what, pd.Series):
        hit = what
    elif what.startswith("entity:"):
        hit = df["entity_list"].apply(lambda e: what[7:] in e)
    else:
        hit = df["topic"] == what
    g = df.assign(hit=hit, period=df["date"].dt.to_period(freq).dt.start_time)
    out = g.groupby(["Paper", "period"]).agg(share=("hit", "mean"), n=("hit", "size")).reset_index()
    out["share"] *= 100
    return out


def series_json(s):
    """share_over_time() output -> {paper: [{x: date, y: share, n: headlines}]} for Chart.js."""
    return {p: [{"x": r.period.strftime("%Y-%m-%d"), "y": num(r.share), "n": int(r.n)}
                for r in g.itertuples()] for p, g in s.groupby("Paper")}


# =============================== pages ===============================
@app.get("/")
def dashboard_page():
    """The home page: the dashboard."""
    return render_template("dashboard.html", page="dashboard")  # page = which link the top bar highlights


@app.get("/dashboard")
def dashboard_old_address():
    """The dashboard's earlier address, kept so old links and bookmarks still work."""
    return redirect("/")


@app.get("/pipeline")
def pipeline_page():
    return render_template("pipeline.html", page="pipeline")


# ============================ dashboard API ===========================
@app.get("/api/meta")
def meta():
    """Everything the dashboard needs once at start-up: date range, lists, events."""
    df = load()
    return jsonify(
        start=df["date"].min().strftime("%Y-%m-%d"), end=df["date"].max().strftime("%Y-%m-%d"),
        papers=PAPERS, categories=CATEGORIES, total=len(df),
        entities=sorted({e for lst in df["entity_list"] for e in lst}),
        events=[{"name": n, "date": d, "what": w, "before": b, "after": a} for n, d, w, b, a in EVENTS],
    )


@app.get("/api/overview")
def overview():
    """Headline counts, biggest topic per paper, topic shares, and the biggest gap between papers."""
    f, papers = filtered()
    cards = []
    for p in papers:
        sub = f[f["Paper"] == p]
        top = sub["topic"].value_counts(normalize=True).drop("Other", errors="ignore")
        cards.append({"paper": p, "n": len(sub), "days": int(sub["date"].nunique()),
                      "top": top.index[0] if len(top) else None,
                      "top_share": num(top.iloc[0] * 100, 1) if len(top) else None})
    share = {p: {t: num(f[f["Paper"] == p]["topic"].eq(t).mean() * 100) if (f["Paper"] == p).any() else 0
                 for t in CATEGORIES} for p in papers}
    gap = None
    if len(papers) == 2 and all(c["n"] for c in cards):
        d = pd.Series({t: share["Jansatta"][t] - share["Indian Express"][t] for t in CATEGORIES}).sort_values()
        gap = {"ja_topic": d.index[-1], "ja_pts": num(d.iloc[-1], 1),
               "ie_topic": d.index[0], "ie_pts": num(-d.iloc[0], 1)}
    topics = [t for t in request.args.get("topics", "").split(",") if t in CATEGORIES]
    in_topics = int(f["topic"].isin(topics).sum()) if topics else len(f)   # what the Topic filter leaves
    return jsonify(total=len(f), in_topics=in_topics, cards=cards, share=share, gap=gap)


@app.get("/api/trends")
def trends():
    """Monthly (or weekly) share of each chosen topic, per paper."""
    f, _ = filtered()
    freq = "W" if request.args.get("freq") == "W" else "M"
    topics = [t for t in request.args.get("topics", "Politics,Sports").split(",") if t in CATEGORIES]
    return jsonify({t: series_json(share_over_time(f, freq, t)) for t in topics})


@app.get("/api/event")
def event():
    """Daily share of a topic or a name around one date, plus before-vs-peak numbers.
    what = a topic, "entity:<listed name>", or "name:<any name>" (matched like the name search).
    Uses the paper filter but not the date filter: the event defines its own window."""
    _, papers = filtered()
    df = load()
    day = pd.Timestamp(request.args.get("date", "2024-06-04"))
    what = request.args.get("what", "Politics")
    before, after = int(request.args.get("before", 7)), int(request.args.get("after", 10))
    win = df[(df["date"] >= day - pd.Timedelta(days=before)) & (df["date"] <= day + pd.Timedelta(days=after))
             & df["Paper"].isin(papers)]
    matched = None
    if what.startswith("name:"):            # a typed name: listed names in both languages, else text
        hit, listed, terms = name_mask(win, what[5:].strip()[:200])
        matched = {"listed": listed, "terms": terms, "hindi_hint": needs_hindi(listed, terms, papers)}
        what = hit
    s = share_over_time(win, "D", what)
    s = s[s["n"] >= MIN_ARTICLES_PER_DAY]   # e.g. Jansatta on 4 June has only 1 headline
    rows = []
    for p, g in s.groupby("Paper"):
        pk = g.loc[g["share"].idxmax()]
        rows.append({"paper": p, "before": num(g[g["period"] < day]["share"].mean(), 1),
                     "peak": num(pk["share"], 1), "peak_date": pk["period"].strftime("%Y-%m-%d"),
                     "offset": int((pk["period"] - day).days)})
    return jsonify(series=series_json(s), table=rows, min_n=MIN_ARTICLES_PER_DAY, matched=matched)


@app.get("/api/entities")
def entities():
    """The N most-mentioned names (optionally within some topics): % of each paper's headlines."""
    f, _ = filtered()
    topics = [t for t in request.args.get("topics", "").split(",") if t in CATEGORIES]
    n_top = max(1, min(40, int(request.args.get("n", 15))))
    sub = f[f["topic"].isin(topics)] if topics else f
    if sub.empty:
        return jsonify(names=[], share={})
    ex = sub[["Paper", "entity_list"]].explode("entity_list").dropna()   # one row per (headline, name)
    totals = sub.groupby("Paper").size()
    ent = (ex.groupby(["Paper", "entity_list"]).size().div(totals, level="Paper").mul(100)
             .rename("share").reset_index())
    keep = list(ent.groupby("entity_list")["share"].max().nlargest(n_top).index)
    share = {p: {r.entity_list: num(r.share) for r in g.itertuples() if r.entity_list in keep}
             for p, g in ent.groupby("Paper")}
    return jsonify(names=keep, share=share)


def listed_name(q):
    """The entry of analysis.py's shared English-Hindi name list that a query refers to
    (its canonical name, or one of its spellings, e.g. "modi" -> "Narendra Modi"), or None."""
    import analysis
    q = q.strip()
    for name, (en, hi) in analysis.ENTITIES.items():
        if q.lower() == name.lower() or q.lower() in en or q in hi:
            return name
    return None


def text_match(df, terms):
    """Headlines containing any of the terms as a whole word (English: any case; Hindi: not inside
    a longer Devanagari word, the same rule analysis.py uses)."""
    import re
    parts = []
    for t in terms:
        t = re.escape(t)
        parts.append(rf"(?<![\u0900-\u097f]){t}(?![\u0900-\u097f])" if re.search("[\u0900-\u097f]", t) else rf"\b{t}\b")
    return df["shown"].str.contains("|".join(parts), case=False, regex=True)


def name_mask(df, q):
    """Which rows of df mention the name q -> (True/False Series, listed name or None, terms).
    A name on the shared list counts exactly as the rest of the dashboard counts it (both languages);
    anything else is a text search, several spellings separated by commas."""
    terms = [t.strip() for t in q.split(",") if t.strip()]
    listed = listed_name(q) if len(terms) == 1 else None
    hit = df["entity_list"].apply(lambda e: listed in e) if listed else text_match(df, terms)
    return hit, listed, terms


def needs_hindi(listed, terms, papers):
    """True when a text search could miss Jansatta: not a listed name, and no Devanagari spelling given."""
    return (not listed and "Jansatta" in papers
            and not any(any("\u0900" <= ch <= "\u097f" for ch in t) for t in terms))


@app.get("/api/name_search")
def name_search():
    """Everything about one name, within the global filters: how often each paper mentions it,
    its weekly trend, which topics those headlines are in, and the latest headlines.

    q = a name on the shared list (matched in both languages, exactly as the rest of the dashboard
    counts it), or any text; several spellings can be given separated by commas
    ("Nitin Gadkari, नितिन गडकरी"). topics = only these topics (optional); sort = newest (default) | oldest."""
    f, papers = filtered()
    q = request.args.get("q", "").strip()[:200]
    terms = [t.strip() for t in q.split(",") if t.strip()]
    if not terms:
        return jsonify(error="Type a name."), 400
    # search-only filters: limit to some topics (shares are then within those topics), and sort order
    only_topics = [t for t in request.args.get("topics", "").split(",") if t in CATEGORIES]
    if only_topics:
        f = f[f["topic"].isin(only_topics)]
    oldest_first = request.args.get("sort") == "oldest"
    hit, listed, terms = name_mask(f, q)
    found = f[hit]

    cards = []
    for p in papers:
        n_all, n_hit = int((f["Paper"] == p).sum()), int((found["Paper"] == p).sum())
        cards.append({"paper": p, "n": n_hit, "share": num(n_hit / n_all * 100, 2) if n_all else 0})
    topics = {p: [num((g["topic"] == t).mean() * 100, 1) for t in CATEGORIES] for p, g in found.groupby("Paper")}
    rows = found.sort_values("date", ascending=oldest_first).head(30)
    return jsonify(
        query=q, listed=listed, terms=terms, only_topics=only_topics, cards=cards, total=len(found),
        trend=series_json(share_over_time(f, "W", hit)), topics=topics, categories=CATEGORIES,
        hindi_hint=needs_hindi(listed, terms, papers),
        rows=[{"date": r.date.strftime("%Y-%m-%d"), "paper": r.Paper, "topic": r.topic, "headline": r.shown,
               "url": r.url} for r in rows.itertuples()],
    )


@app.get("/api/headlines")
def headlines():
    """Search / filter the headlines, 50 per page; sort = newest (default) | oldest."""
    h, _ = filtered()
    topics = [t for t in request.args.get("topics", "").split(",") if t]
    q = request.args.get("q", "").strip()
    src = request.args.get("src", "")
    page, size = max(0, int(request.args.get("page", 0))), 50
    if topics:
        h = h[h["topic"].isin(topics)]
    if q:
        h = h[h["shown"].str.contains(q, case=False, regex=False)]
    if src in ("url_section", "model"):
        h = h[h["topic_source"] == src]
    h = h.sort_values("date", ascending=request.args.get("sort") == "oldest")
    rows = h.iloc[page * size:(page + 1) * size]
    return jsonify(total=len(h), page=page, size=size, rows=[
        {"date": r.date.strftime("%Y-%m-%d"), "paper": r.Paper, "topic": r.topic, "source": r.topic_source,
         "headline": r.shown, "entities": r.entity_list, "url": r.url} for r in rows.itertuples()])


# ============================ Pipeline API ============================
def trace_tokens(text, lang):
    """preprocess.py's tokenizer, unrolled so each intermediate stage can be shown.
    Returns (normalised text, [{"raw", "token", "reason"}]) where reason is None for kept tokens.
    Mirrors en_tokens() / hi_tokens() line by line; /api/trace checks the result against them."""
    import re
    import unicodedata

    import preprocess as pp
    from indicnlp.tokenize import indic_tokenize

    out = []
    if lang == "en":
        norm = unicodedata.normalize("NFKC", text).lower().replace("\u2019", "'").replace("\u2018", "'")
        norm = re.sub(r"'s\b", " ", norm)
        for t in re.findall(r"[a-z]+(?:-[a-z]+)*|\d+", norm):
            reason = ("stopword" if t in pp.EN_STOP else "number" if t.isdigit()
                      else "too short" if len(t) <= 1 else None)
            out.append({"raw": t, "token": t, "reason": reason})
        return norm, out

    norm = pp._hi_norm.normalize(unicodedata.normalize("NFC", text))
    for raw in indic_tokenize.trivial_tokenize(norm, "hi"):
        t = raw.lower().strip("\u0964\u0965")
        if pp._DEVANAGARI.search(t):
            t = re.sub(r"[^\u0900-\u097f]", "", t)
            reason = "too short" if len(t) <= 1 else "stopword" if t in pp.HI_STOP else None
        elif pp._LATIN.match(t):
            reason = "too short" if len(t) <= 1 else "stopword" if t in pp.EN_STOP else None
        else:
            reason = "number" if t.isdigit() else "punctuation"
        out.append({"raw": raw, "token": t, "reason": reason})
    return norm, out


@app.post("/api/trace")
def trace():
    """One headline through every step of the pipeline, with each step's intermediate result.

    clean      -> clean_and_profile.py rules that apply to a typed headline (spaces, 3+ words)
    normalise, tokenize, stopwords -> preprocess.py (en_tokens / hi_tokens)
    stem       -> preprocess.py (the version the saved model was trained on, plus the others)
    features   -> the saved TF-IDF vectorizer (words + word pairs it saw in training)
    scores     -> the saved logistic regression: score = intercept + sum(tfidf x weight)
    predict    -> softmax of the scores
    entities   -> analysis.py find_entities (the shared English-Hindi name list)
    """
    import re

    import analysis

    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if not text:
        return jsonify(error="Type a headline first."), 400
    lang = detect_lang(text)
    m = model(lang)
    if m is None:
        return jsonify(error=f"Model not found: {MODEL_FILES[lang]}. Run baseline.py first."), 500

    # 2. cleaning: the rules from clean_and_profile.py that apply to a single typed headline
    cleaned = re.sub(r"\s+", " ", text).strip()
    n_words = len(cleaned.split())

    # 3-5. normalise, tokenize, remove stopwords
    norm, toks = trace_tokens(cleaned, lang)
    kept = [t["token"] for t in toks if t["reason"] is None]
    consistent = kept == m.tokenize(cleaned)   # sanity check against preprocess.py itself

    # 6. stem / lemma (the model uses one of them: m.version)
    import preprocess
    _, stem, lemma = preprocess.PIPE[lang]
    forms = [{"token": t, "stem": s_, "lemma": l_} for t, s_, l_ in zip(kept, stem(kept), lemma(kept))]

    # 7. features: every word / word pair the vectorizer builds, and whether the model knows it
    x = " ".join(m.to_version(kept))
    X = m.vec.transform([x])
    value = dict(zip(X.indices, X.data))
    counts = {}
    for g in m.vec.build_analyzer()(x):
        counts[g] = counts.get(g, 0) + 1
    classes = list(m.clf.classes_)
    features = []
    for g, n in counts.items():
        col = m.vec.vocabulary_.get(g)
        f = {"term": g, "count": n, "known": col is not None}
        if col is not None:
            f.update(idf=num(m.vec.idf_[col], 2), tfidf=num(value.get(col, 0), 3),
                     contrib=[num(value.get(col, 0) * m.clf.coef_[k, col], 3) for k in range(len(classes))])
        features.append(f)

    # 8-9. scores and probabilities
    words = [sum(f["contrib"][k] for f in features if f["known"]) for k in range(len(classes))]
    probs = m.clf.predict_proba(X)[0]
    return jsonify(
        lang=lang, paper=PAPER_NAME["jansatta_2024" if lang == "hi" else "ie_2024"],
        raw=text, cleaned=cleaned, n_words=n_words, kept_by_cleaning=n_words >= 3,
        normalised=norm, tokens=toks, consistent=consistent,
        version=m.version, forms=forms, model_input=x,
        features=features, classes=classes,
        intercept=[num(v, 3) for v in m.clf.intercept_], words=[num(v, 3) for v in words],
        probs=[num(p * 100, 1) for p in probs], topic=classes[probs.argmax()],
        entities=analysis.find_entities(cleaned, lang),
    )


if __name__ == "__main__":
    load()                          # fail fast if the data is missing
    model("en"), model("hi")        # load both models now, not on the first click
    print(f"Dashboard: http://localhost:{PORT}   Pipeline: http://localhost:{PORT}/pipeline")
    app.run(port=PORT, debug=False)
