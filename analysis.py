# /// script
# dependencies = [
#   "pandas", "scikit-learn", "matplotlib", "joblib",
#   "spacy>=3.8,<3.9",
#   "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
# ]
# ///
"""
Phase 6: trend analysis - how Indian Express and Jansatta covered Jan-Aug 2024.

Run:   uv run analysis.py          (about a minute)

Steps
  1. Topics     headlines from topic sections keep their section label; "Mixed"-section
                headlines are classified with the Phase 5 models (models/best_*.joblib)
  2. Trends     each topic's monthly share of each paper's coverage
  3. Events     daily share of the relevant topic around key 2024 events
  4. Entities   who/what is mentioned: a shared English+Hindi list (same for both papers)
                + spaCy's open-ended English NER for Indian Express
  5. findings.md   one sentence per view, with the numbers, for Chapter 6

Writes: data/analysis/all_classified.csv  and  results/phase6/ (charts .png + tables .csv + findings.md)
"""

import re
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd

# ============================== SETTINGS ==============================
PRE_FILES = {                       # made by preprocess.py
    "ie_2024": "data/preprocessed/ie_2024_pre.csv",
    "jansatta_2024": "data/preprocessed/jansatta_2024_pre.csv",
}
MODEL_FILES = {"en": "models/best_en.joblib", "hi": "models/best_hi.joblib"}
OUT_DATA = "data/analysis"
OUT_RESULTS = "results/phase6"
SPACY_NER = True                    # open-ended English NER for Indian Express
MIN_ARTICLES_PER_DAY = 30           # days below this are left out of daily charts (e.g. Jansatta 4 Jun)

EVENTS = [  # (name, date, what to track, days before, days after)
    # what to track = a topic, or "entity:<name from the ENTITIES list>"
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
COLORS = {"ie_2024": "#1f6feb", "jansatta_2024": "#e8590c"}

# canonical name: (English patterns, Hindi patterns). English = whole words, Hindi = substrings.
ENTITIES = {
    # people
    "Narendra Modi": (["modi"], ["मोदी"]),
    "Rahul Gandhi": (["rahul gandhi"], ["राहुल गांधी"]),
    "Arvind Kejriwal": (["kejriwal"], ["केजरीवाल"]),
    "Amit Shah": (["amit shah"], ["अमित शाह"]),
    "Yogi Adityanath": (["adityanath", "yogi"], ["योगी"]),
    "Mamata Banerjee": (["mamata"], ["ममता"]),
    "Nitish Kumar": (["nitish"], ["नीतीश"]),
    "Akhilesh Yadav": (["akhilesh"], ["अखिलेश"]),
    "Lalu Prasad Yadav": (["lalu"], ["लालू"]),
    "Tejashwi Yadav": (["tejashwi"], ["तेजस्वी"]),
    "Hemant Soren": (["hemant soren"], ["हेमंत सोरेन"]),
    "Uddhav Thackeray": (["uddhav"], ["उद्धव"]),
    "Eknath Shinde": (["eknath shinde", "shinde"], ["शिंदे"]),
    "Sharad Pawar": (["sharad pawar"], ["शरद पवार"]),
    "Ajit Pawar": (["ajit pawar"], ["अजित पवार"]),
    "Siddaramaiah": (["siddaramaiah"], ["सिद्धारमैया"]),
    "Chandrababu Naidu": (["naidu"], ["नायडू"]),
    "Priyanka Gandhi": (["priyanka gandhi"], ["प्रियंका गांधी"]),
    "Mallikarjun Kharge": (["kharge"], ["खड़गे", "खरगे"]),
    "Prajwal Revanna": (["revanna"], ["रेवन्ना"]),
    "Virat Kohli": (["kohli"], ["कोहली"]),
    "Rohit Sharma": (["rohit sharma"], ["रोहित शर्मा"]),
    "Vinesh Phogat": (["vinesh"], ["विनेश"]),
    "Neeraj Chopra": (["neeraj chopra"], ["नीरज चोपड़ा"]),
    "Shah Rukh Khan": (["shah rukh"], ["शाहरुख"]),
    "Salman Khan": (["salman khan"], ["सलमान खान"]),
    "Donald Trump": (["trump"], ["ट्रंप", "ट्रम्प"]),
    "Joe Biden": (["biden"], ["बाइडेन", "बाइडन"]),
    "Vladimir Putin": (["putin"], ["पुतिन"]),
    "Benjamin Netanyahu": (["netanyahu"], ["नेतन्याहू"]),
    # parties, alliances, institutions
    "BJP": (["bjp"], ["बीजेपी", "भाजपा"]),
    "Congress": (["congress"], ["कांग्रेस"]),
    "AAP": (["aap", "aam aadmi party"], ["आम आदमी पार्टी", "आप पार्टी"]),
    "TMC": (["tmc", "trinamool"], ["टीएमसी", "तृणमूल"]),
    "Samajwadi Party": (["samajwadi"], ["सपा", "समाजवादी"]),
    "INDIA bloc": (["india bloc", "indi alliance"], ["इंडिया गठबंधन", "इंडिया ब्लॉक"]),
    "NDA": (["nda"], ["एनडीए"]),
    "Enforcement Directorate": (["enforcement directorate"], ["ईडी", "प्रवर्तन निदेशालय"]),
    "CBI": (["cbi"], ["सीबीआई"]),
    "Supreme Court": (["supreme court"], ["सुप्रीम कोर्ट", "उच्चतम न्यायालय", "एससी"]),
    "Election Commission": (["election commission"], ["चुनाव आयोग", "निर्वाचन आयोग"]),
    "RBI": (["rbi"], ["आरबीआई"]),
    "ISRO": (["isro"], ["इसरो"]),
    "IMD": (["imd"], ["आईएमडी", "मौसम विभाग"]),
    "IPL": (["ipl"], ["आईपीएल"]),
    "NEET": (["neet"], ["नीट"]),
    # places
    "Delhi": (["delhi"], ["दिल्ली"]),
    "Mumbai": (["mumbai"], ["मुंबई"]),
    "Uttar Pradesh": (["uttar pradesh"], ["उत्तर प्रदेश", "यूपी"]),
    "Bihar": (["bihar"], ["बिहार"]),
    "West Bengal": (["bengal", "kolkata"], ["बंगाल", "कोलकाता"]),
    "Maharashtra": (["maharashtra"], ["महाराष्ट्र"]),
    "Karnataka": (["karnataka", "bengaluru", "bangalore"], ["कर्नाटक", "बेंगलुरु"]),
    "Kerala": (["kerala", "wayanad"], ["केरल", "वायनाड"]),
    "Gujarat": (["gujarat", "ahmedabad"], ["गुजरात", "अहमदाबाद"]),
    "Punjab": (["punjab"], ["पंजाब"]),
    "Haryana": (["haryana"], ["हरियाणा"]),
    "Rajasthan": (["rajasthan"], ["राजस्थान"]),
    "Madhya Pradesh": (["madhya pradesh"], ["मध्य प्रदेश"]),
    "Jharkhand": (["jharkhand"], ["झारखंड"]),
    "Tamil Nadu": (["tamil nadu", "chennai"], ["तमिलनाडु", "चेन्नई"]),
    "Manipur": (["manipur"], ["मणिपुर"]),
    "Jammu and Kashmir": (["kashmir", "jammu"], ["कश्मीर", "जम्मू"]),
    "Ayodhya": (["ayodhya", "ram temple", "ram mandir"], ["अयोध्या", "राम मंदिर"]),
    "Pakistan": (["pakistan"], ["पाकिस्तान"]),
    "China": (["china", "chinese"], ["चीन"]),
    "United States": (["america", "united states", "american"], ["अमेरिका", "अमेरिकी"]),
    "Israel / Gaza": (["israel", "gaza", "hamas"], ["इजरायल", "इसराइल", "गाजा", "हमास"]),
    "Russia / Ukraine": (["russia", "ukraine"], ["रूस", "यूक्रेन"]),
    "Bangladesh": (["bangladesh"], ["बांग्लादेश"]),
}


# English abbreviations that are only safe to match in CAPITALS ("UP" vs the word "up")
EN_CASE_SENSITIVE = {
    "Uttar Pradesh": ["UP"],
    "Enforcement Directorate": ["ED"],
    "Supreme Court": ["SC"],
    "United States": ["US", "USA"],
}
_HI_LETTER = r"[\u0900-\u097F]"
_PATTERNS = {}
for _name, (_en, _hi) in ENTITIES.items():
    _PATTERNS[_name] = (
        re.compile(r"\b(?:" + "|".join(map(re.escape, _en)) + r")\b") if _en else None,
        re.compile(r"\b(?:" + "|".join(map(re.escape, EN_CASE_SENSITIVE.get(_name, []))) + r")\b")
        if _name in EN_CASE_SENSITIVE else None,
        # Hindi: whole word only (not inside a longer word, e.g. यूपी inside यूपीएससी)
        re.compile(rf"(?<!{_HI_LETTER})(?:" + "|".join(map(re.escape, _hi)) + rf")(?!{_HI_LETTER})") if _hi else None,
    )


# ------------------------------- helpers ------------------------------
def p(path):
    return ROOT / path


def need(path):
    if not p(path).exists():
        raise SystemExit(f"Not found: {p(path)}\nFix the path in SETTINGS at the top of analysis.py.")
    return p(path)


def save_fig(fig, name):
    fig.tight_layout()
    fig.savefig(p(OUT_RESULTS) / name, dpi=150)
    plt.close(fig)


def pct(x):
    return f"{100 * x:.1f}%"


# ------------------------------ 1. topics -----------------------------
def classify():
    frames = []
    for paper, path in PRE_FILES.items():
        df = pd.read_csv(need(path), dtype=str, keep_default_na=False)
        lang = df["lang"].iat[0]
        bundle = joblib.load(need(MODEL_FILES[lang]))
        df["topic"] = df["category"]
        df["topic_source"] = "url_section"
        mixed = df["category"] == "Mixed"
        if mixed.any():
            df.loc[mixed, "topic"] = bundle["pipeline"].predict(df.loc[mixed, bundle["version"]])
            df.loc[mixed, "topic_source"] = "model"
        print(f"  {PAPER_NAME[paper]}: {len(df)} headlines, {mixed.sum()} classified by the model")
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").astype(str)
    return df


# ------------------------------ 2. trends -----------------------------
def trends(df, findings):
    overall = (df.groupby("paper")["topic"].value_counts(normalize=True)
                 .unstack(0).reindex(CATEGORIES).fillna(0))
    overall.to_csv(p(OUT_RESULTS) / "topic_share_overall.csv")

    fig, ax = plt.subplots(figsize=(9, 5))
    y = range(len(CATEGORIES))
    h = 0.4
    for i, paper in enumerate(PRE_FILES):
        ax.barh([v + (i - 0.5) * h for v in y], overall[paper] * 100, height=h,
                color=COLORS[paper], label=PAPER_NAME[paper])
    ax.set_yticks(list(y), CATEGORIES)
    ax.invert_yaxis()
    ax.set_xlabel("Share of the paper's headlines, Jan-Aug 2024 (%)")
    ax.set_title("What each paper covered")
    ax.legend()
    save_fig(fig, "01_topic_share_overall.png")

    diff = (overall["jansatta_2024"] - overall["ie_2024"]).sort_values()
    findings.append("## Topic share (Jan–Aug 2024)\n")
    findings.append(f"- Jansatta gives the most extra space to **{diff.index[-1]}** "
                    f"({pct(overall.loc[diff.index[-1], 'jansatta_2024'])} vs "
                    f"{pct(overall.loc[diff.index[-1], 'ie_2024'])} in Indian Express); "
                    f"Indian Express gives the most extra space to **{diff.index[0]}** "
                    f"({pct(overall.loc[diff.index[0], 'ie_2024'])} vs "
                    f"{pct(overall.loc[diff.index[0], 'jansatta_2024'])}).")

    monthly = (df.groupby(["paper", "month"])["topic"].value_counts(normalize=True)
                 .rename("share").reset_index())
    monthly.to_csv(p(OUT_RESULTS) / "topic_share_monthly.csv", index=False)

    fig, axes = plt.subplots(3, 3, figsize=(13, 10), sharex=True)
    for ax, cat in zip(axes.flat, CATEGORIES):
        for paper in PRE_FILES:
            m = monthly[(monthly["paper"] == paper) & (monthly["topic"] == cat)].sort_values("month")
            ax.plot(m["month"].str[5:], m["share"] * 100, marker="o", ms=3,
                    color=COLORS[paper], label=PAPER_NAME[paper])
        ax.set_title(cat, fontsize=11)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.3)
    axes[0, 0].legend(fontsize=8)
    for ax in axes[-1]:
        ax.set_xlabel("Month (2024)")
    fig.suptitle("Monthly share of coverage by topic (%)", fontsize=13)
    save_fig(fig, "02_topic_share_monthly.png")

    findings.append("\n## Monthly trends\n")
    for cat in CATEGORIES:
        for paper in PRE_FILES:
            m = monthly[(monthly["paper"] == paper) & (monthly["topic"] == cat)].set_index("month")["share"]
            if len(m):
                findings.append(f"- {cat}, {PAPER_NAME[paper]}: peak in **{m.idxmax()}** "
                                f"({pct(m.max())}), lowest in {m.idxmin()} ({pct(m.min())}).")


# ------------------------------ 3. events -----------------------------
def events(df, findings):
    daily_n = df.groupby(["paper", "date"]).size()
    rows = []
    findings.append("\n## Coverage around key events (daily share of the topic)\n")
    fig, axes = plt.subplots(len(EVENTS), 1, figsize=(10, 2.6 * len(EVENTS)))
    for ax, (name, day, topic, before, after) in zip(axes, EVENTS):
        d0 = pd.Timestamp(day)
        win = df[(df["date"] >= d0 - pd.Timedelta(days=before)) & (df["date"] <= d0 + pd.Timedelta(days=after))]
        for paper in PRE_FILES:
            w = win[win["paper"] == paper]
            if topic.startswith("entity:"):
                hit = w["entities"].apply(lambda e: topic[7:] in e)
            else:
                hit = w["topic"] == topic
            share = w.assign(hit=hit).groupby("date")["hit"].mean()
            n = daily_n.loc[paper].reindex(share.index)
            share = share[n >= MIN_ARTICLES_PER_DAY]
            if share.empty:
                continue
            base = share[share.index < d0].mean()
            rows.append({"event": name, "date": day, "topic": topic, "paper": PAPER_NAME[paper],
                         "baseline_share_before": round(base, 3), "peak_share": round(share.max(), 3),
                         "peak_date": share.idxmax().date().isoformat(),
                         "days_from_event_to_peak": (share.idxmax() - d0).days})
            ax.plot((share.index - d0).days, share * 100, marker="o", ms=3,
                    color=COLORS[paper], label=PAPER_NAME[paper])
        ax.axvline(0, color="grey", ls="--", lw=1)
        what = f"headlines mentioning {topic[7:]}" if topic.startswith("entity:") else f"{topic} headlines"
        ax.set_title(f"{name} ({day}) - share of {what}", fontsize=10)
        ax.set_ylabel("%")
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    for ax in axes:
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    axes[-1].set_xlabel("Days from the event")
    save_fig(fig, "03_events.png")
    ev = pd.DataFrame(rows)
    ev.to_csv(p(OUT_RESULTS) / "events.csv", index=False)
    for name, g in ev.groupby("event", sort=False):
        parts = [f"{r.paper}: {pct(r.baseline_share_before)} before → peak {pct(r.peak_share)} on "
                 f"{r.peak_date} ({r.days_from_event_to_peak:+d} days)" for r in g.itertuples()]
        t = g["topic"].iat[0]
        label = f"mentions of {t[7:]}" if t.startswith("entity:") else t
        findings.append(f"- **{name}** ({label}): " + "; ".join(parts) + ".")


# ----------------------------- 4. entities ----------------------------
def find_entities(text, lang):
    """Names from the shared list found in one headline (English rules also apply to English
    words inside Hindi headlines, e.g. 'BJP', 'IPL')."""
    low = text.lower()
    found = []
    for name, (en_lower, en_caps, hi) in _PATTERNS.items():
        if (en_lower and en_lower.search(low)) or (en_caps and en_caps.search(text)) \
                or (lang == "hi" and hi and hi.search(text)):
            found.append(name)
    return found


def entities(df, findings):
    df["entities"] = [find_entities(t, l) for t, l in zip(df["text"], df["lang"])]
    ex = df[["paper", "topic", "month", "entities"]].explode("entities").dropna(subset=["entities"])
    total = df.groupby("paper").size()
    top = (ex.groupby(["paper", "entities"]).size().div(total, level="paper")
             .rename("share_of_headlines").reset_index())
    top.to_csv(p(OUT_RESULTS) / "entities_overall.csv", index=False)
    by_topic = (ex.groupby(["paper", "topic", "entities"]).size().rename("headlines").reset_index()
                  .sort_values(["paper", "topic", "headlines"], ascending=[True, True, False])
                  .groupby(["paper", "topic"]).head(10))
    by_topic.to_csv(p(OUT_RESULTS) / "entities_by_topic.csv", index=False)

    piv = top.pivot(index="entities", columns="paper", values="share_of_headlines").fillna(0)
    piv = piv.loc[piv.max(axis=1).sort_values(ascending=False).index[:20]]
    fig, ax = plt.subplots(figsize=(9, 7))
    y = range(len(piv))
    h = 0.4
    for i, paper in enumerate(PRE_FILES):
        ax.barh([v + (i - 0.5) * h for v in y], piv[paper] * 100, height=h, color=COLORS[paper],
                label=PAPER_NAME[paper])
    ax.set_yticks(list(y), piv.index)
    ax.invert_yaxis()
    ax.set_xlabel("% of the paper's headlines that mention it")
    ax.set_title("Most-mentioned people, parties and places (shared English-Hindi list)")
    ax.legend()
    save_fig(fig, "04_entities.png")

    findings.append("\n## Named entities (shared English–Hindi list)\n")
    for paper in PRE_FILES:
        t5 = piv[paper].sort_values(ascending=False).head(5)
        findings.append(f"- {PAPER_NAME[paper]} top 5: " + ", ".join(f"{k} ({pct(v)})" for k, v in t5.items()) + ".")
    gap = (piv["jansatta_2024"] - piv["ie_2024"]).sort_values()
    findings.append(f"- Mentioned relatively more in Jansatta: {', '.join(gap.index[-3:][::-1])}; "
                    f"relatively more in Indian Express: {', '.join(gap.index[:3])}.")

    if SPACY_NER:
        import spacy
        nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
        ie = df[df["paper"] == "ie_2024"]
        ents = []
        for doc in nlp.pipe(ie["headline"].where(ie["headline"] != "", ie["text"]), batch_size=256):
            ents += [(e.label_, e.text) for e in doc.ents if e.label_ in ("PERSON", "ORG", "GPE")]
        sp = (pd.DataFrame(ents, columns=["type", "entity"]).value_counts().rename("headlines")
                .reset_index().groupby("type").head(20))
        sp.to_csv(p(OUT_RESULTS) / "entities_spacy_ie.csv", index=False)
        findings.append("- spaCy (Indian Express, open-ended) most frequent PERSON tags: " +
                        ", ".join(sp[sp["type"] == "PERSON"]["entity"].head(8)) +
                        " (check these: spaCy's small model mislabels some, e.g. 'Lok Sabha' as a person).")


# -------------------------------- main --------------------------------
def main():
    p(OUT_DATA).mkdir(parents=True, exist_ok=True)
    p(OUT_RESULTS).mkdir(parents=True, exist_ok=True)
    findings = ["# Phase 6 findings (auto-generated - check each one before using it)\n"]

    print("1. Topics: classifying Mixed-section headlines...")
    df = classify()
    print("2. Monthly trends...")
    trends(df, findings)
    print("3. Entities...")
    entities(df, findings)
    print("4. Events...")
    events(df, findings)

    keep = ["paper", "lang", "date", "month", "headline", "text", "url", "section", "category",
            "topic", "topic_source", "entities"]
    out = df[keep].copy()
    out["entities"] = out["entities"].str.join("; ")
    out.to_csv(p(OUT_DATA) / "all_classified.csv", index=False, date_format="%Y-%m-%d")
    (p(OUT_RESULTS) / "findings.md").write_text("\n".join(findings), encoding="utf-8")
    print("\n".join(findings))
    print(f"\nwrote {OUT_DATA}/all_classified.csv and {OUT_RESULTS}/ (charts, tables, findings.md)")


if __name__ == "__main__":
    main()