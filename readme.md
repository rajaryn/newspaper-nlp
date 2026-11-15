# Newspaper NLP: Indian Express vs Jansatta (Jan–Aug 2024)

An NLP course project that compares what an English newspaper (**Indian Express**) and a Hindi newspaper from the same media group (**Jansatta**) covered from January to August 2024. Headlines are collected from the papers' sitemaps, classified into nine topics, and compared month by month, around key events, and by the people and places they mention. A web app (Flask + HTML/CSS/JS + Chart.js) presents the work: a **Pipeline** page that follows any typed headline through every step, and a separate data dashboard.

## Results at a glance

| | Indian Express | Jansatta |
|---|---|---|
| Headlines analysed (after cleaning) | 22,940 | 23,173 |
| Topic classifier (chosen by 5-fold CV) | stem + TF-IDF + Logistic Regression | stem + TF-IDF + Logistic Regression |
| Test accuracy / macro-F1 (250 headlines each) | 0.66 / 0.65 | 0.85 / 0.79 |
| Sports share of headlines | 7.1% | 19.3% |
| Business share of headlines | 9.3% | 4.8% |
| Politics share on Lok Sabha results day (4 Jun) | 60.9% (21.4% before) | not measurable (1 article that day) |
| Peak share mentioning Bangladesh (Aug unrest) | 10.9% | 21.9% |

Both papers react to the same events on the same days. Jansatta gives far more space to sport, the Hindi belt (Uttar Pradesh, Bihar) and Modi; Indian Express gives more to business, crime, Karnataka/Mumbai and international news.

## Topics

`Politics`, `Sports`, `Business`, `Weather/Environment`, `Crime/Law`, `Entertainment`, `Tech/Science`, `Health`, `Other`

## Project structure

```
newspaper-nlp/
├── sitemap_scraper.py        # 1. list articles from daily sitemaps (100 per day per paper)
├── headline_fetcher.py       # 1. fetch each article's real headline (og:title)
├── clean_and_profile.py      # 2. clean, count per day, list URL sections
├── build_training_data.py    # 2. section → category, test set, keyword candidates, training seed
├── preprocess.py             # 4. English + Hindi preprocessing (tokens / stem / lemma)
├── baseline.py               # 5. 24 classifiers, chosen by cross-validation, scored on the test set
├── analysis.py               # 6. topic trends, key events, named entities, findings.md
├── app.py                    # 7. web app: Flask API + pages (dashboard at /, Pipeline at /pipeline)
├── templates/                #    pipeline.html, dashboard.html
├── static/                   #    pipeline.css, pipeline.js, style.css, app.js, charts.js (Chart.js)
│
├── data/
│   ├── ie/, jansatta/  one folder per paper:
│   │                   <paper>_2024.csv            (scraped)
│   │                   <paper>_2024_clean.csv, _per_day.csv, _sections.csv
│   │                   <paper>_2024_sections_mapped.csv   (hand-made: section → category)
│   │                   <paper>_2024_phase2.csv     (every kept article + category)
│   ├── labels/         train_seed.csv, candidates_to_check.csv, gold_labelled.csv  (hand-labelled)
│   ├── preprocessed/   train_pre.csv, test_pre.csv, <paper>_pre.csv, preprocessing_examples.md
│   └── analysis/       all_classified.csv          (every headline + topic + entities)
├── models/           best_en.joblib, best_hi.joblib
└── results/
    ├── phase5/       all_models.csv, summary.md, reports, confusion matrices, errors_<lang>.csv
    └── phase6/       charts (.png), tables (.csv), findings.md
```

Every script has a **SETTINGS** block at the top with its input/output paths, so the folders can be changed there without touching the code.

## Setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/). Each script declares its own dependencies at the top (PEP 723), so `uv run <script>.py` installs what it needs on first run. No separate `pip install` is required.

Save any CSV you edit by hand as **CSV UTF-8**, or the Hindi text is corrupted.

## How to reproduce

Run the steps in order from the project folder.

### 1. Collect the data (hours)

```bash
uv run sitemap_scraper.py      # writes ie_2024.csv, jansatta_2024.csv (headline column empty)
uv run headline_fetcher.py     # fills in the headlines; ~1.7 h per paper for Jan–Aug at 100/day
```
- Settings: `MONTHS = "1-8"`, `PER_DAY = 100` (a fixed random sample per day, seeded by the date).
- Both scripts can be stopped and restarted. Progress is saved, and a rerun only fetches what is missing. Each request has a 30-second hard limit, retries and back-off, and a pause if the site starts blocking.
- Indian Express blocks cloud servers (HTTP 403), so run this step on your own machine. Keep the computer awake (`caffeinate -i` on macOS, power settings on Windows).
- Output: `data/ie/ie_2024.csv` and `data/jansatta/jansatta_2024.csv`.

### 2. Clean and build the labelled data

```bash
uv run clean_and_profile.py
```
- Removes duplicate URLs, videos, live blogs, web stories, horoscopes, very short headlines and same-day duplicates, and prints the row count after each step.
- Writes `_clean.csv`, `_per_day.csv` and `_sections.csv` next to each input file.
- **Manual step:** fill in the `category` column of each `_sections.csv` (one of the 9 topics, `Mixed` for general sections such as `cities`/`national`, or `Drop` for opinion, columns and sponsored content). Save the results as `data/<paper>/<paper>_2024_sections_mapped.csv`.

```bash
uv run build_training_data.py
```
Writes `data/<paper>/<paper>_2024_phase2.csv` (every kept article with its category) and, in `data/combined/`:
- `gold_to_label.csv`: the **test set**, 250 random headlines per paper, kept out of training.
- `candidates_to_check.csv`: Mixed-section headlines matching Weather or Crime keywords (English and Hindi), to be checked by hand.
- `train_seed.csv`: training rows labelled by their URL section.

### 3. Label the test set and the candidates (manual)

Fill in the `label` column of both files with one of the 9 topics, using the headline only. Save them as `gold_labelled.csv` and `candidates_to_check.csv` in `data/labels/`, and copy `train_seed.csv` there too. (`data/combined/` stays separate so a re-run of step 2 can't overwrite your labels.)

### 4. Preprocess

```bash
uv run preprocess.py      # ~10 s
```
| Version | English | Hindi |
|---|---|---|
| tokens | lowercase, punctuation and stopwords removed | Indic NLP normaliser + tokenizer, Hindi stopwords removed |
| stem | Porter stemmer | light suffix stripper (Ramanathan & Rao, 2003) |
| lemma | simplemma | simplemma |

Set `USE_DRAFT_IF_LABEL_EMPTY = True` if the candidates' corrected labels are in the `draft_label` column. Outputs go to `data/preprocessed/`, where the later steps read from.

### 5. Train and evaluate the classifiers

```bash
uv run baseline.py        # ~2 min
```
For each language this tries 3 text versions × 2 feature types (bag of words, TF-IDF; words and word pairs) × 2 models (Multinomial Naive Bayes, Logistic Regression). The final model is chosen by 5-fold cross-validation macro-F1 on the training data, never by the test score. It writes `results/phase5/` and `models/best_en.joblib`, `models/best_hi.joblib`.

### 6. Trend analysis

```bash
uv run analysis.py        # ~1 min
```
- **Topics:** headlines from topic sections keep their section label; general-section ("Mixed") headlines are classified by the Phase 5 model.
- **Trends:** each topic's monthly share of each paper's headlines.
- **Events:** daily share of a topic, or of mentions of a name, around 8 events: Ram temple consecration, Kejriwal's arrest, Lok Sabha results, T20 World Cup final, Wayanad landslides, Paris Olympics, Kolkata RG Kar case, Bangladesh unrest. Days with fewer than 30 headlines are excluded.
- **Entities:** a shared English–Hindi list of ~75 people, parties, institutions and places, matched the same way in both papers. spaCy's English NER is also run for Indian Express.
- Writes charts, tables and an auto-generated `findings.md` to `results/phase6/`, and `data/analysis/all_classified.csv`.

### 7. Pipeline page and dashboard

```bash
uv run app.py             # then open http://localhost:5000
```

Two separate pages, sharing one top bar (Dashboard | Pipeline):

**Pipeline** (`/pipeline`) - type any English or Hindi headline.
- **Try it:** the predicted topic, its probability, the words that pushed it there, and every topic's probability.
- **Follow it through the pipeline:** the same headline through all 10 steps, one at a time (Back / Next / Play, the arrow keys, or *Show all steps*):
  1. Collect, 2. Clean, 3. Normalise, 4. Tokenize, 5. Stopwords, 6. Stem, 7. Features (TF-IDF), 8. Score (bias + words per topic), 9. Predict (softmax), 10. Analyse (topic share + names found).

  Every step is computed live with the project's own code (`preprocess.py`, the saved model, `analysis.py`).
- `/pipeline?q=<headline>` opens the page with that headline loaded.

**Dashboard** (`/`, the home page) - Overview, Trends, Events, People & places, Headlines, with three tiers of navigation: the top bar (Dashboard | Pipeline), the section tabs (with the headline count), and a row of **filter pills**, the same in every section: Period (All, Q1, Election, Jul–Aug or custom dates), Paper, Topic and Sort. Each pill shows its current value (highlighted when set) and opens a small menu under it; menus close on scroll, a click elsewhere or Esc. A pill the current section does not use is greyed out (e.g. Topic and Sort in Events). **Reset filters** appears when anything is set. In Events, **Define your own event** lets you name an event, pick its date and window, and track a topic or any name (typed names match like the name search). In People & places, **Search a name** finds any person, party or place: names on the shared list match both languages; for others, add the Hindi spelling after a comma (e.g. `Nitin Gadkari, नितिन गडकरी`). Chart.js loads from a CDN, so the app needs internet the first time.

## Limitations

- **Period and sample:** January–August 2024 only, 100 random articles per paper per day. Results are shares of coverage, not publishing volumes.
- **Missing day:** Jansatta's sitemap lists only one article for 4 June 2024 (Lok Sabha results), so that day is excluded from daily charts.
- **One media group:** both papers belong to the Express Group, so findings are about language and audience within that group, not English vs Hindi media in general.
- **Training labels:** these come from URL sections, which don't cover general sections such as `cities`. This is the main reason English test accuracy (0.66) is well below cross-validation (0.82). Indian Express also files health tips under `lifestyle` (mapped to Other).
- **Test set:** test labels were drafted with an AI assistant at the author's request; there was no second annotator, so there is no inter-annotator agreement score. Tech/Science has only 13 test headlines (1 Jansatta), so its per-class scores are unreliable.
- **Weather and Crime training examples:** these come from keyword-matched headlines, AI-drafted and reviewed.
- **Entities:** a fixed list of ~75 names, so people and places not on it are not counted. spaCy's small English model mislabels some entities (e.g. "Lok Sabha" as a person).
- **Sentiment:** sentiment analysis was left out of scope.

## Tools

Python, pandas, scikit-learn, NLTK (Porter stemmer), simplemma, Indic NLP Library, spaCy (`en_core_web_sm`), matplotlib, Plotly, Flask, Chart.js, requests, uv.