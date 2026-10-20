# /// script
# dependencies = ["pandas", "scikit-learn", "matplotlib", "joblib"]
# ///
"""
Phase 5: baseline classifiers for English and Hindi headlines.

Run:   uv run baselines.py          (a few minutes on a laptop)
Edit the SETTINGS block below to change folders or what gets compared.

For each language it trains every combination of
    text version : tokens / stem / lemma            (from preprocess.py)
    features     : bag of words (counts) / TF-IDF   (words + word pairs)
    model        : Naive Bayes / Logistic Regression
= 12 models per language, 24 in total.

How the final model is chosen (no peeking at the test set):
    each model gets a 5-fold cross-validation score (macro-F1) on the TRAINING rows;
    the best one per language is picked by that score, then retrained on all training rows.
The test set is only used to report scores.

Writes to RESULTS_DIR:
    all_models.csv              every model: CV macro-F1, test accuracy, test macro-F1
    best_<lang>_report.txt      per-category precision / recall / F1 for the chosen model
    best_<lang>_confusion.png   confusion matrix for the chosen model
    errors_<lang>.csv           test headlines the chosen model got wrong (for error analysis)
    summary.md                  the tables above in report-ready form
and saves the chosen models to MODEL_DIR (best_en.joblib, best_hi.joblib) for Phase 6.
"""

import time
from itertools import product
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score, classification_report,
                             confusion_matrix, f1_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

# ============================== SETTINGS ==============================
PRE_DIR = "data/preprocessed"       # where preprocess.py wrote train_pre.csv / test_pre.csv
RESULTS_DIR = "results/phase5"
MODEL_DIR = "models"
VERSIONS = ["tokens", "stem", "lemma"]
FEATURES = ["bow", "tfidf"]
MODELS = ["naive_bayes", "logistic_regression"]
CV_FOLDS = 5
SEED = 42
# ======================================================================

ROOT = Path(__file__).resolve().parent
CATEGORIES = ["Politics", "Sports", "Business", "Weather/Environment", "Crime/Law",
              "Entertainment", "Tech/Science", "Health", "Other"]
LANG_NAME = {"en": "English (Indian Express)", "hi": "Hindi (Jansatta)"}


def make_pipeline(features, model):
    vec_args = dict(ngram_range=(1, 2), min_df=2, token_pattern=r"\S+", lowercase=False)
    vec = CountVectorizer(**vec_args) if features == "bow" else TfidfVectorizer(sublinear_tf=True, **vec_args)
    if model == "naive_bayes":
        clf = MultinomialNB(alpha=0.3)
    else:
        clf = LogisticRegression(max_iter=2000, C=5, class_weight="balanced")
    return Pipeline([("vec", vec), ("clf", clf)])


def save_confusion(y_true, y_pred, title, path):
    labels = [c for c in CATEGORIES if c in set(y_true) | set(y_pred)]
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(8, 7))
    ConfusionMatrixDisplay(cm, display_labels=[l.replace("/", "/\n") for l in labels]).plot(
        ax=ax, cmap="Blues", colorbar=False, xticks_rotation=45)
    ax.set_title(title)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True (test label)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    pre, res, mod = ROOT / PRE_DIR, ROOT / RESULTS_DIR, ROOT / MODEL_DIR
    for p in ("train_pre.csv", "test_pre.csv"):
        if not (pre / p).exists():
            raise SystemExit(f"Not found: {pre / p}\nRun preprocess.py first, or fix PRE_DIR in SETTINGS.")
    res.mkdir(parents=True, exist_ok=True)
    mod.mkdir(parents=True, exist_ok=True)

    train = pd.read_csv(pre / "train_pre.csv", dtype=str, keep_default_na=False)
    test = pd.read_csv(pre / "test_pre.csv", dtype=str, keep_default_na=False)

    rows, summary = [], ["# Phase 5: baseline results\n"]
    for lang in ["en", "hi"]:
        tr, te = train[train["lang"] == lang], test[test["lang"] == lang]
        print(f"\n=== {LANG_NAME[lang]}: {len(tr)} training, {len(te)} test headlines ===")
        cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=SEED)
        results = []
        for version, features, model in product(VERSIONS, FEATURES, MODELS):
            t0 = time.time()
            pipe = make_pipeline(features, model)
            cv_f1 = cross_val_score(pipe, tr[version], tr["label"], cv=cv, scoring="f1_macro", n_jobs=-1).mean()
            pipe.fit(tr[version], tr["label"])
            pred = pipe.predict(te[version])
            r = {"language": lang, "version": version, "features": features, "model": model,
                 "cv_macro_f1": round(cv_f1, 3),
                 "test_accuracy": round(accuracy_score(te["label"], pred), 3),
                 "test_macro_f1": round(f1_score(te["label"], pred, average="macro", zero_division=0), 3)}
            results.append((r, pipe, pred))
            print(f"  {version:6} {features:5} {model:19}  CV F1 {r['cv_macro_f1']:.3f}   "
                  f"test acc {r['test_accuracy']:.3f}  test F1 {r['test_macro_f1']:.3f}   ({time.time() - t0:.0f}s)")
        rows += [r for r, _, _ in results]

        # ---- choose by cross-validation, not by test score ----
        best_r, best_pipe, best_pred = max(results, key=lambda x: x[0]["cv_macro_f1"])
        name = f"{best_r['version']} + {best_r['features']} + {best_r['model']}"
        print(f"  -> chosen by CV: {name}  (test accuracy {best_r['test_accuracy']:.3f}, "
              f"macro-F1 {best_r['test_macro_f1']:.3f})")
        joblib.dump({"pipeline": best_pipe, "version": best_r["version"], "lang": lang},
                    mod / f"best_{lang}.joblib")

        report = classification_report(te["label"], best_pred, labels=CATEGORIES, zero_division=0)
        (res / f"best_{lang}_report.txt").write_text(f"{LANG_NAME[lang]}: {name}\n\n{report}", encoding="utf-8")
        save_confusion(te["label"], best_pred, f"{LANG_NAME[lang]}: {name}", res / f"best_{lang}_confusion.png")

        err = te.assign(predicted=best_pred)
        err = err[err["predicted"] != err["label"]][["paper", "date", "text", "label", "predicted"]]
        err.to_csv(res / f"errors_{lang}.csv", index=False, encoding="utf-8-sig")
        print(f"  {len(err)} of {len(te)} test headlines wrong -> errors_{lang}.csv")

        summary += [f"\n## {LANG_NAME[lang]}\n", f"Chosen model (best cross-validation macro-F1): **{name}**\n",
                    "```", report, "```"]

    df = pd.DataFrame(rows)
    df.to_csv(res / "all_models.csv", index=False)
    try:
        table = df.to_markdown(index=False)
    except ImportError:
        table = "```\n" + df.to_string(index=False) + "\n```"
    summary += ["\n## All models\n", table,
                "\nStemming vs lemmatization (mean test macro-F1 over the 4 feature/model combinations):\n"]
    comp = df.groupby(["language", "version"])["test_macro_f1"].mean().unstack().round(3)
    summary.append("```\n" + comp.to_string() + "\n```")
    (res / "summary.md").write_text("\n".join(summary), encoding="utf-8")

    print("\nMean test macro-F1 by text version (does stemming or lemmatization help?):")
    print(comp.to_string())
    print(f"\nwrote {RESULTS_DIR}/ (all_models.csv, summary.md, reports, confusion matrices, errors) "
          f"and {MODEL_DIR}/best_en.joblib, best_hi.joblib")


if __name__ == "__main__":
    main()