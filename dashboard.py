# /// script
# dependencies = [
#   "streamlit", "pandas", "plotly", "scikit-learn", "joblib",
#   "nltk", "simplemma", "indic-nlp-library",
# ]
# ///
"""
Phase 7: interactive dashboard - Indian Express vs Jansatta, Jan-Aug 2024.

Run:   uv run dashboard.py
       (opens in your browser at http://localhost:8501; Ctrl-C in the terminal to stop)

Needs:  data/analysis/all_classified.csv   (from analysis.py)
        models/best_en.joblib, models/best_hi.joblib   (from baselines.py)
        preprocess.py in the same folder   (for the live headline classifier)

Tabs: Overview | Trends | Events | People & places | Headlines | Classify a headline
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# ============================== SETTINGS ==============================
DATA = "data/analysis/all_classified.csv"
MODEL_FILES = {"en": "models/best_en.joblib", "hi": "models/best_hi.joblib"}
MIN_ARTICLES_PER_DAY = 30
EVENTS = [  # (name, date, what to track, days before, days after) - same as analysis.py
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
COLORS = {"Indian Express": "#1f6feb", "Jansatta": "#e8590c"}


@st.cache_data
def load():
    path = ROOT / DATA
    if not path.exists():
        st.error(f"Not found: {path}. Run analysis.py first, or fix DATA at the top of dashboard.py.")
        st.stop()
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["date"] = pd.to_datetime(df["date"])
    df["Paper"] = df["paper"].map(PAPER_NAME)
    df["entity_list"] = df["entities"].apply(lambda s: [e for e in s.split("; ") if e])
    df["shown"] = df["headline"].where(df["headline"] != "", df["text"])
    return df


@st.cache_resource
def load_models():
    import joblib
    sys.path.insert(0, str(ROOT))
    import preprocess  # reuse exactly the preprocessing the models were trained on
    models = {}
    for lang, f in MODEL_FILES.items():
        if (ROOT / f).exists():
            models[lang] = joblib.load(ROOT / f)
    return models, preprocess


def share_over_time(df, freq, what):
    """Share of each paper's headlines per period that match `what` (topic or entity:Name)."""
    hit = df["entity_list"].apply(lambda e: what[7:] in e) if what.startswith("entity:") else df["topic"] == what
    g = df.assign(hit=hit, period=df["date"].dt.to_period(freq).dt.start_time)
    out = g.groupby(["Paper", "period"]).agg(share=("hit", "mean"), n=("hit", "size")).reset_index()
    out["share"] *= 100
    return out


def app():
    st.set_page_config(page_title="News Pulse: IE vs Jansatta", layout="wide")
    df = load()

    # ---------------- sidebar filters ----------------
    st.sidebar.header("Filters")
    dmin, dmax = df["date"].min().date(), df["date"].max().date()
    picked = st.sidebar.date_input("Date range", (dmin, dmax), min_value=dmin, max_value=dmax)
    start, end = picked if len(picked) == 2 else (dmin, dmax)  # mid-selection only one date is set
    papers = st.sidebar.multiselect("Papers", list(COLORS), default=list(COLORS))
    f = df[(df["date"].dt.date >= start) & (df["date"].dt.date <= end) & df["Paper"].isin(papers)]
    st.sidebar.caption(f"{len(f):,} headlines selected")
    st.sidebar.markdown("---")
    st.sidebar.caption("Topics: URL section where it names one, otherwise the Phase 5 model "
                       "(test accuracy: English 0.66, Hindi 0.85). 100 random articles per paper per day.")

    st.title("News Pulse: Indian Express vs Jansatta")
    st.caption("What an English and a Hindi newspaper from the same group covered, January–August 2024")
    if f.empty:
        st.warning("No headlines match these filters.")
        return

    tabs = st.tabs(["Overview", "Trends", "Events", "People & places", "Headlines", "Classify a headline"])

    # ---------------- Overview ----------------
    with tabs[0]:
        cols = st.columns(len(papers) * 2)
        for i, p in enumerate(papers):
            sub = f[f["Paper"] == p]
            top = sub["topic"].value_counts(normalize=True).drop("Other", errors="ignore")
            cols[2 * i].metric(f"{p}: headlines", f"{len(sub):,}")
            cols[2 * i + 1].metric(f"{p}: biggest topic (excl. Other)", top.index[0],
                                   f"{top.iloc[0] * 100:.1f}% of headlines", delta_color="off")
        share = (f.groupby("Paper")["topic"].value_counts(normalize=True).mul(100).rename("share")
                   .reset_index())
        fig = px.bar(share, x="share", y="topic", color="Paper", barmode="group", orientation="h",
                     color_discrete_map=COLORS, category_orders={"topic": CATEGORIES},
                     labels={"share": "% of the paper's headlines", "topic": ""},
                     title="What each paper covered")
        st.plotly_chart(fig, width="stretch")
        if len(papers) == 2:
            w = share.pivot(index="topic", columns="Paper", values="share").fillna(0)
            gap = (w["Jansatta"] - w["Indian Express"]).sort_values()
            st.info(f"Biggest gaps in this selection: Jansatta gives **{gap.index[-1]}** "
                    f"{gap.iloc[-1]:+.1f} points more; Indian Express gives **{gap.index[0]}** "
                    f"{-gap.iloc[0]:+.1f} points more.")

    # ---------------- Trends ----------------
    with tabs[1]:
        c1, c2 = st.columns([3, 1])
        topics = c1.multiselect("Topics", CATEGORIES, default=["Politics", "Sports"])
        freq = c2.radio("Group by", ["Month", "Week"], horizontal=True)
        fq = {"Month": "M", "Week": "W"}[freq]
        for t in topics:
            s = share_over_time(f, fq, t)
            fig = px.line(s, x="period", y="share", color="Paper", markers=True, color_discrete_map=COLORS,
                          hover_data={"n": True}, labels={"share": "% of headlines", "period": ""},
                          title=f"{t}: share of each paper's headlines by {freq.lower()}")
            fig.update_yaxes(rangemode="tozero")
            st.plotly_chart(fig, width="stretch")

    # ---------------- Events ----------------
    with tabs[2]:
        names = [e[0] for e in EVENTS] + ["Custom…"]
        choice = st.selectbox("Event", names)
        if choice == "Custom…":
            c1, c2, c3, c4 = st.columns(4)
            day = c1.date_input("Date", pd.Timestamp("2024-06-04"))
            kind = c2.radio("Track", ["Topic", "Name"], horizontal=True)
            all_ents = sorted({e for lst in df["entity_list"] for e in lst})
            what = c3.selectbox("Topic" if kind == "Topic" else "Person / party / place",
                                CATEGORIES if kind == "Topic" else all_ents)
            what = what if kind == "Topic" else f"entity:{what}"
            before, after = c4.slider("Days before / after", 1, 30, (7, 10))
            day = pd.Timestamp(day)
        else:
            _, d, what, before, after = next(e for e in EVENTS if e[0] == choice)
            day = pd.Timestamp(d)
        win = df[(df["date"] >= day - pd.Timedelta(days=before)) & (df["date"] <= day + pd.Timedelta(days=after))
                 & df["Paper"].isin(papers)]
        s = share_over_time(win, "D", what)
        s = s[s["n"] >= MIN_ARTICLES_PER_DAY]
        s["days from event"] = (s["period"] - day).dt.days
        label = f"headlines mentioning {what[7:]}" if what.startswith("entity:") else f"{what} headlines"
        fig = px.line(s, x="period", y="share", color="Paper", markers=True, color_discrete_map=COLORS,
                      hover_data={"days from event": True, "n": True},
                      labels={"share": "% of the day's headlines", "period": ""},
                      title=f"{choice if choice != 'Custom…' else 'Custom event'}: share of {label}")
        fig.add_vline(x=day, line_dash="dash", line_color="grey")
        st.plotly_chart(fig, width="stretch")
        rows = []
        for p, g in s.groupby("Paper"):
            base = g[g["period"] < day]["share"].mean()
            pk = g.loc[g["share"].idxmax()]
            rows.append({"Paper": p, "Average before (%)": round(base, 1), "Peak (%)": round(pk["share"], 1),
                         "Peak date": pk["period"].date(), "Days from event": int(pk["days from event"])})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption(f"Days with fewer than {MIN_ARTICLES_PER_DAY} headlines are hidden "
                   "(e.g. Jansatta on 4 June, which has 1).")

    # ---------------- People & places ----------------
    with tabs[3]:
        c1, c2 = st.columns([1, 3])
        topic = c1.selectbox("Within topic", ["All topics"] + CATEGORIES)
        n_top = c1.slider("How many", 5, 30, 15)
        sub = f if topic == "All topics" else f[f["topic"] == topic]
        ex = sub[["Paper", "entity_list"]].explode("entity_list").dropna()
        totals = sub.groupby("Paper").size()
        ent = ex.groupby(["Paper", "entity_list"]).size().div(totals, level="Paper").mul(100).rename("share").reset_index()
        keep = ent.groupby("entity_list")["share"].max().nlargest(n_top).index
        ent = ent[ent["entity_list"].isin(keep)]
        fig = px.bar(ent, x="share", y="entity_list", color="Paper", barmode="group", orientation="h",
                     color_discrete_map=COLORS, category_orders={"entity_list": list(keep)},
                     labels={"share": "% of headlines mentioning it", "entity_list": ""},
                     title=f"Most-mentioned names ({topic.lower()})")
        fig.update_layout(height=max(400, 32 * len(keep)))
        c2.plotly_chart(fig, width="stretch")

        all_ents = sorted({e for lst in df["entity_list"] for e in lst})
        pick = st.selectbox("Follow one name over time", all_ents,
                            index=all_ents.index("Narendra Modi") if "Narendra Modi" in all_ents else 0)
        s = share_over_time(f, "W", f"entity:{pick}")
        fig = px.line(s, x="period", y="share", color="Paper", markers=True, color_discrete_map=COLORS,
                      labels={"share": "% of headlines", "period": ""}, title=f"Weekly mentions of {pick}")
        st.plotly_chart(fig, width="stretch")
        st.caption("Names come from a fixed English-Hindi list of ~75 people, parties, institutions and places.")

    # ---------------- Headlines ----------------
    with tabs[4]:
        c1, c2, c3 = st.columns(3)
        t = c1.multiselect("Topic", CATEGORIES)
        q = c2.text_input("Search text (English or Hindi)")
        src = c3.radio("Topic from", ["Any", "URL section", "Model"], horizontal=True)
        h = f
        if t:
            h = h[h["topic"].isin(t)]
        if q:
            h = h[h["shown"].str.contains(q, case=False, regex=False)]
        if src != "Any":
            h = h[h["topic_source"] == ("url_section" if src == "URL section" else "model")]
        st.caption(f"{len(h):,} headlines")
        st.dataframe(h.sort_values("date", ascending=False)[["date", "Paper", "topic", "topic_source", "shown",
                                                             "entities", "url"]]
                     .rename(columns={"shown": "headline"}).head(1000),
                     hide_index=True, width="stretch",
                     column_config={"url": st.column_config.LinkColumn("link", display_text="open"),
                                    "date": st.column_config.DateColumn(format="D MMM YYYY")})

    # ---------------- Classify ----------------
    with tabs[5]:
        st.write("Type any English or Hindi headline; the Phase 5 model for that language predicts its topic.")
        text = st.text_input("Headline", "बिहार में भारी बारिश, कई जिलों में बाढ़ का अलर्ट")
        if text.strip():
            models, pre = load_models()
            lang = "hi" if any("ऀ" <= ch <= "ॿ" for ch in text) else "en"
            if lang not in models:
                st.error(f"Model not found: {MODEL_FILES[lang]}. Run baselines.py first.")
            else:
                b = models[lang]
                tok_f, stem_f, lem_f = pre.PIPE[lang]
                toks = tok_f(text)
                version = {"tokens": toks, "stem": stem_f(toks), "lemma": lem_f(toks)}[b["version"]]
                x = " ".join(version)
                pipe = b["pipeline"]
                st.markdown(f"**Language:** {'Hindi' if lang == 'hi' else 'English'} · "
                            f"**model input ({b['version']}):** `{x}`")
                if hasattr(pipe, "predict_proba"):
                    pr = pd.Series(pipe.predict_proba([x])[0], index=pipe.classes_).sort_values(ascending=False)
                    st.success(f"Predicted topic: **{pr.index[0]}** ({pr.iloc[0] * 100:.0f}%)")
                    fig = px.bar(pd.DataFrame({"topic": pr.index, "probability": pr.values * 100}),
                                 x="probability", y="topic", orientation="h",
                                 labels={"probability": "%", "topic": ""}, title="Model confidence")
                    fig.update_yaxes(autorange="reversed")
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.success(f"Predicted topic: **{pipe.predict([x])[0]}**")


if __name__ == "__main__":
    from streamlit import runtime
    if runtime.exists():
        app()
    else:  # started with "uv run dashboard.py" / "python dashboard.py": relaunch under streamlit
        from streamlit.web import cli
        sys.argv = ["streamlit", "run", str(Path(__file__).resolve())]
        sys.exit(cli.main())