# /// script
# dependencies = ["pandas", "nltk", "simplemma", "indic-nlp-library"]
# ///
"""
Phase 4: preprocess headlines in English and Hindi, three ways, for the models.

Run:   uv run preprocess.py
Edit the SETTINGS block below if your files are somewhere else.

For every headline it makes three versions (the report compares them):
  tokens   lowercase, punctuation removed, stopwords removed
  stem     tokens cut to a crude root      (English: Porter stemmer, Hindi: light suffix stripper)
  lemma    tokens turned into dictionary form (simplemma, both languages)

Writes:
  (all in ds/preprocessed/)
  train_pre.csv      training rows  = train_seed + your reviewed candidates (test set excluded)
  test_pre.csv       the reviewed test set (gold)
  <paper>_pre.csv    every article of each paper, for classifying later (Phase 7)
  preprocessing_examples.md   before/after examples + vocabulary sizes, ready for the report
"""

import re
import unicodedata
from pathlib import Path

import pandas as pd
import simplemma
from indicnlp.normalize.indic_normalize import IndicNormalizerFactory
from indicnlp.tokenize import indic_tokenize
from nltk.stem import PorterStemmer

# ============================== SETTINGS ==============================
TRAIN_SEED = "data/labels/train_seed.csv"
CANDIDATES = "data/labels/candidates_to_check.csv"
GOLD = "data/labels/gold_labelled.csv"               
PHASE2 = {                                                 # every kept article per paper
    "ie_2024": "data/ie/ie_2024_phase2.csv",
    "jansatta_2024": "data/jansatta/jansatta_2024_phase2.csv",
}
OUT_DIR = "data/preprocessed"        # all outputs go here
USE_DRAFT_IF_LABEL_EMPTY = False   # True = take draft_label when you left 'label' empty
# ======================================================================

ROOT = Path(__file__).resolve().parent
CATEGORIES = ["Politics", "Sports", "Business", "Weather/Environment", "Crime/Law",
              "Entertainment", "Tech/Science", "Health", "Other"]

# ----------------------------- English --------------------------------
EN_STOP = set("""
a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have
having he her here hers herself him himself his how i if in into is it its itself just me more most my
myself no nor not now of off on once only or other our ours ourselves out over own same she should so
some such than that the their theirs them themselves then there these they this those through to too
under until up very was we were what when where which while who whom why will with would you your
yours yourself yourselves s t don amid via vs per
says said say tells told watch live updates update highlights news today know here's heres
""".split())
_porter = PorterStemmer()


def en_tokens(text):
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"'s\b", " ", text)
    toks = re.findall(r"[a-z]+(?:-[a-z]+)*|\d+", text)
    return [t for t in toks if t not in EN_STOP and not t.isdigit() and len(t) > 1]


def en_stem(toks):
    return [_porter.stem(t) for t in toks]


def en_lemma(toks):
    return [simplemma.lemmatize(t, lang="en") for t in toks]


# ------------------------------ Hindi ---------------------------------
HI_STOP = set("""
के का की को में से है हैं था थे थी थीं और या पर ने भी तो ही यह वह ये वो इस उस इन उन इसे उसे इसका उसका
एक लिए लिये किया किए किये कर करें करने करना करते करती करता गया गई गए गये हो होगा होगी होंगे होने
रहा रही रहे जा जाता जाती जाते जाएगा जाएगी जाएंगे तक साथ बाद पहले अब जब तब कि क्या कैसे कैसा क्यों कौन
कहां कहाँ सबसे बहुत कुछ सभी अपने अपनी अपना हुआ हुई हुए दिया दी दिए लिया ली बोले बोली बोला कहा कहीं
नहीं न ना वाले वाली वाला जो जिस जिन तरह द्वारा बीच अगर फिर पास दौरान
जानें जानिए जानिये देखें देखिए पढ़ें आज अपडेट लाइव वीडियो
""".split())
# light stemmer suffixes (after Ramanathan & Rao, 2003); longest are tried first
HI_SUFFIXES = sorted(set("""
ों ें ां ाँ ा ि ी ु ू े ो ं
ाओं ाएं ाएँ ियों ियां ियाँ िया ाने ाना ाते ाती ाता ने ना ते ती ता कर ाकर ाई ाए ाओ ाया ायी ाये
ेगा ेगी ेंगे ेंगी ूंगा ूंगी ाएगा ाएगी ाएंगे ाएंगी ाइए ाइये ाइयाँ ाइयां ाइयों ाहट पन त्व
""".split()), key=len, reverse=True)
_hi_norm = IndicNormalizerFactory().get_normalizer("hi")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"^[a-z]+$")


def hi_tokens(text):
    text = _hi_norm.normalize(unicodedata.normalize("NFC", text))
    out = []
    for t in indic_tokenize.trivial_tokenize(text, "hi"):
        t = t.lower().strip("।॥")
        if _DEVANAGARI.search(t):
            t = re.sub(r"[^ऀ-ॿ]", "", t)          # keep Devanagari letters only
            if len(t) > 1 and t not in HI_STOP:
                out.append(t)
        elif _LATIN.match(t) and len(t) > 1 and t not in EN_STOP:  # English words in Hindi headlines
            out.append(t)
    return out


def hi_stem_word(t):
    if not _DEVANAGARI.search(t):
        return _porter.stem(t)
    for s in HI_SUFFIXES:
        if t.endswith(s) and len(t) - len(s) >= 2:
            return t[: -len(s)]
    return t


def hi_stem(toks):
    return [hi_stem_word(t) for t in toks]


def hi_lemma(toks):
    return [simplemma.lemmatize(t, lang="hi" if _DEVANAGARI.search(t) else "en") for t in toks]


PIPE = {"en": (en_tokens, en_stem, en_lemma), "hi": (hi_tokens, hi_stem, hi_lemma)}


def add_versions(df):
    toks, stem, lem = [], [], []
    for text, lang in zip(df["text"], df["lang"]):
        tok_f, stem_f, lem_f = PIPE[lang]
        t = tok_f(text)
        toks.append(" ".join(t))
        stem.append(" ".join(stem_f(t)))
        lem.append(" ".join(lem_f(t)))
    df = df.copy()
    df["tokens"], df["stem"], df["lemma"] = toks, stem, lem
    return df


# ------------------------------- data ---------------------------------
def read(path):
    p = ROOT / path
    if not p.exists():
        raise SystemExit(f"Not found: {p}\nFix the path in SETTINGS at the top of preprocess.py.")
    return pd.read_csv(p, dtype=str, keep_default_na=False)


def check_labels(df, name):
    df = df.copy()
    df["label"] = df["label"].str.strip()
    if USE_DRAFT_IF_LABEL_EMPTY and "draft_label" in df:
        df.loc[df["label"] == "", "label"] = df["draft_label"]
    empty = (df["label"] == "").sum()
    bad = df[(df["label"] != "") & ~df["label"].isin(CATEGORIES)]
    if len(bad):
        print(f"  WARNING {name}: {len(bad)} rows have a label that isn't one of the 9 categories "
              f"(typo?): {sorted(bad['label'].unique())} - these rows are skipped")
    if empty:
        print(f"  {name}: {empty} rows with empty label skipped")
    return df[df["label"].isin(CATEGORIES)]


def main():
    print("Reading files...")
    seed = read(TRAIN_SEED)
    cand = check_labels(read(CANDIDATES), "candidates")
    gold = check_labels(read(GOLD), "test set")
    gold_urls = set(gold["url"])

    cols = ["paper", "lang", "date", "text", "url", "label"]
    seed["source_of_label"] = seed.get("source_of_label", "url_section")
    cand = cand.assign(source_of_label="keyword_candidate_reviewed")
    train = pd.concat([seed[cols + ["source_of_label"]], cand[cols + ["source_of_label"]]])
    train = train[~train["url"].isin(gold_urls)].drop_duplicates("url", keep="last")

    print("Preprocessing train / test...")
    train, gold = add_versions(train), add_versions(gold[cols])
    out = ROOT / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    train.to_csv(out / "train_pre.csv", index=False)
    gold.to_csv(out / "test_pre.csv", index=False)

    for paper, path in PHASE2.items():
        print(f"Preprocessing all of {paper}...")
        df = add_versions(read(path))
        df.to_csv(out / f"{paper}_pre.csv", index=False)

    # ---- summary for the report ----
    print("\nTraining rows per label:")
    print(train.pivot_table(index="label", columns="paper", values="url", aggfunc="count",
                            fill_value=0).reindex(CATEGORIES, fill_value=0).to_string())
    print(f"\ntrain_pre.csv: {len(train)} rows   test_pre.csv: {len(gold)} rows")

    lines = ["# Preprocessing: before and after\n"]
    stats = []
    for lang, name in [("en", "English (Indian Express)"), ("hi", "Hindi (Jansatta)")]:
        tr = train[train["lang"] == lang]
        lines.append(f"\n## {name}\n")
        for _, r in tr.sample(3, random_state=1).iterrows():
            lines += [f"- **Original:** {r['text']}",
                      f"  - tokens: `{r['tokens']}`",
                      f"  - stem: `{r['stem']}`",
                      f"  - lemma: `{r['lemma']}`\n"]
        for v in ["tokens", "stem", "lemma"]:
            vocab = set(" ".join(tr[v]).split())
            avg = tr[v].str.split().str.len().mean()
            stats.append({"language": lang, "version": v, "vocabulary": len(vocab), "avg tokens per headline": round(avg, 1)})
    st = pd.DataFrame(stats)
    try:
        table = st.to_markdown(index=False)          # needs the 'tabulate' package
    except ImportError:
        table = "```\n" + st.to_string(index=False) + "\n```"
    lines += ["\n## Vocabulary size (training rows)\n", table]
    (out / "preprocessing_examples.md").write_text("\n".join(lines), encoding="utf-8")
    print("\nVocabulary size by version (smaller = more words merged together):")
    print(st.to_string(index=False))
    print(f"\nwrote {OUT_DIR}/train_pre.csv, test_pre.csv, preprocessing_examples.md and <paper>_pre.csv")


if __name__ == "__main__":
    main()