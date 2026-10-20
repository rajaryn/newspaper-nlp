# /// script
# dependencies = ["pandas"]
# ///
"""
Phase 2 -> 3: attach categories, set aside a test set, and prepare files for hand-labelling.

Run:   uv run build_training_data.py
Edit the SETTINGS block below to change file names or sample sizes.

Reads (for each paper):  data/<site>/<name>_clean.csv  and  data/<site>/<name>_sections_mapped.csv
Writes:
  data/<site>/<name>_phase2.csv
                                every kept article with its category
                           (8 categories, Other, or Mixed = the model will classify it)
  data/combined/gold_to_label.csv
                           TEST SET: random articles from both papers, label column empty.
                           Label these by hand (Phase 3). They are kept OUT of training.
  data/combined/candidates_to_check.csv
                           Mixed-section headlines that match Weather or Crime keywords.
                           Put the right category in 'label' (or leave empty to skip).
  data/combined/train_seed.csv
                           training data so far: articles labelled by their URL section,
                           minus the test set. Add the checked candidates to it later.

Categories: Politics, Sports, Business, Weather/Environment, Crime/Law,
            Entertainment, Tech/Science, Health, Other
"""

import re
from pathlib import Path

import pandas as pd

# ============================== SETTINGS ==============================
PAPERS = {                 # name -> language
    "ie_2024": "en",
    "jansatta_2024": "hi",
}
GOLD_PER_PAPER = 250       # test-set articles per paper (hand-label these)
CANDIDATES_PER_CLASS = 200 # keyword candidates per category per paper to hand-check
SEED = 42
DATA = Path(__file__).parent / "data"   # data/<site>/ per paper, data/combined/ for both
# ======================================================================

CATEGORIES = ["Politics", "Sports", "Business", "Weather/Environment", "Crime/Law",
              "Entertainment", "Tech/Science", "Health", "Other"]

# English: whole words (IE text is the lowercase URL slug). Hindi: substrings, because
# word boundaries don't work reliably with Devanagari vowel signs.
KEYWORDS = {
    "Weather/Environment": {
        "en": r"\b(?:rain|rains|rainfall|monsoon|heatwave|heat wave|heatstroke|imd|flood|floods|cyclone|"
              r"weather|temperature|cold wave|fog|aqi|air pollution|pollution|climate|landslide|"
              r"cloudburst|snowfall|drought|thunderstorm|lightning)\b",
        "hi": r"(?:बारिश|वर्षा|मौसम|मानसून|गर्मी|लू |हीटवेव|बाढ़|चक्रवात|तूफान|तापमान|ठंड|शीतलहर|कोहरा|"
              r"प्रदूषण|एक्यूआई|AQI|जलवायु|भूस्खलन|बादल फटा|बर्फबारी|सूखा|आईएमडी|IMD|आकाशीय बिजली)",
    },
    "Crime/Law": {
        "en": r"\b(?:arrested|arrest|murder|murdered|killed|rape|raped|bail|fir|accused|gang|robbery|"
              r"fraud|scam|chargesheet|kidnap|kidnapped|abducted|stabbed|shot dead|lynching|"
              r"high court|supreme court|hc|sc|convicted|sentenced|police)\b",
        "hi": r"(?:गिरफ्तार|हत्या|मर्डर|दुष्कर्म|बलात्कार|रेप|जमानत|आरोपी|गैंग|लूट|ठगी|धोखाधड़ी|घोटाला|"
              r"चार्जशीट|अपहरण|एफआईआर|FIR|हाईकोर्ट|हाई कोर्ट|सुप्रीम कोर्ट|अदालत|सजा|पुलिस|गोली मार)",
    },
}


def paper_dir(name):
    return DATA / name.rsplit("_", 1)[0]   # "ie_2024" -> data/ie


def load_paper(name, lang):
    d = paper_dir(name)
    df = pd.read_csv(d / f"{name}_clean.csv", dtype=str, keep_default_na=False)
    m = pd.read_csv(d / f"{name}_sections_mapped.csv", dtype=str, keep_default_na=False)
    lookup = dict(zip(m["section"], m["category"]))
    sec = df["section"].replace("", "(none)")
    unknown = sorted(set(sec) - set(lookup))
    if unknown:
        print(f"  WARNING {name}: sections not in mapping, treated as Mixed: {unknown}")
    df["category"] = sec.map(lookup).fillna("Mixed")
    df["paper"], df["lang"] = name, lang
    n0 = len(df)
    df = df[df["category"] != "Drop"].copy()
    print(f"{name}: {n0} articles, {n0 - len(df)} dropped (opinion/columns/brand/etc.), {len(df)} kept")
    df.to_csv(d / f"{name}_phase2.csv", index=False)
    return df


def main():
    out = DATA / "combined"
    out.mkdir(parents=True, exist_ok=True)
    papers = [load_paper(n, lang) for n, lang in PAPERS.items()]
    allr = pd.concat(papers, ignore_index=True)
    cols = ["paper", "lang", "date", "text", "url", "section"]

    # ---- test set: random over ALL kept articles (incl. Mixed), so it reflects real data ----
    gold = pd.concat([g.sample(min(GOLD_PER_PAPER, len(g)), random_state=SEED)
                      for _, g in allr.groupby("paper")])
    gold_out = gold[cols + ["category"]].rename(columns={"category": "section_category"})
    gold_out["label"] = ""
    gold_out.sort_values(["paper", "date"]).to_csv(out / "gold_to_label.csv", index=False)
    gold_urls = set(gold["url"])

    rest = allr[~allr["url"].isin(gold_urls)]

    # ---- keyword candidates for the two categories with no section labels ----
    cand = []
    mixed = rest[rest["category"] == "Mixed"]
    for cat, pats in KEYWORDS.items():
        for paper, g in mixed.groupby("paper"):
            lang = g["lang"].iat[0]
            hit = g[g["text"].str.contains(pats[lang], case=False, regex=True)]
            take = hit.sample(min(CANDIDATES_PER_CLASS, len(hit)), random_state=SEED)
            c = take[cols].copy()
            c["suggested"], c["label"] = cat, ""
            cand.append(c)
            print(f"  {paper}: {len(hit)} Mixed headlines match {cat} keywords; {len(take)} sampled to check")
    cand = pd.concat(cand).drop_duplicates("url")
    cand.sort_values(["suggested", "paper", "date"]).to_csv(out / "candidates_to_check.csv", index=False)

    # ---- training seed: section-labelled articles, test set excluded ----
    seed = rest[rest["category"].isin(CATEGORIES)][cols + ["category"]].rename(columns={"category": "label"})
    seed["source_of_label"] = "url_section"
    seed.to_csv(out / "train_seed.csv", index=False)

    # ---- summary ----
    print("\ntrain_seed.csv (labelled by URL section, test set removed):")
    table = seed.pivot_table(index="label", columns="paper", values="url", aggfunc="count", fill_value=0)
    print(table.reindex(CATEGORIES, fill_value=0).to_string())
    print(f"\ngold_to_label.csv:       {len(gold_out)} articles to hand-label (test set)")
    print(f"candidates_to_check.csv: {len(cand)} keyword matches to confirm or reject")
    print(f"<paper>_phase2.csv:      all kept articles with category; Mixed = "
          f"{(allr['category'] == 'Mixed').sum()} to be classified by the model")


if __name__ == "__main__":
    main()
