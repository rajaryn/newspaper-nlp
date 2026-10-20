# Phase 5: baseline results


## English (Indian Express)

Chosen model (best cross-validation macro-F1): **stem + tfidf + logistic_regression**

```
                     precision    recall  f1-score   support

           Politics       0.76      0.62      0.68        66
             Sports       0.79      0.83      0.81        23
           Business       0.29      0.73      0.41        11
Weather/Environment       1.00      0.80      0.89        15
          Crime/Law       0.82      0.64      0.72        42
      Entertainment       0.69      0.77      0.73        31
       Tech/Science       0.82      0.75      0.78        12
             Health       0.57      0.24      0.33        17
              Other       0.46      0.64      0.53        33

           accuracy                           0.66       250
          macro avg       0.69      0.67      0.65       250
       weighted avg       0.71      0.66      0.67       250

```

## Hindi (Jansatta)

Chosen model (best cross-validation macro-F1): **stem + tfidf + logistic_regression**

```
                     precision    recall  f1-score   support

           Politics       0.93      0.85      0.89        66
             Sports       0.93      0.95      0.94        40
           Business       0.75      0.75      0.75        12
Weather/Environment       0.75      0.60      0.67         5
          Crime/Law       0.81      0.65      0.72        34
      Entertainment       0.85      0.91      0.88        32
       Tech/Science       0.33      1.00      0.50         1
             Health       1.00      0.88      0.93        16
              Other       0.73      0.91      0.81        44

           accuracy                           0.85       250
          macro avg       0.79      0.83      0.79       250
       weighted avg       0.86      0.85      0.85       250

```

## All models

```
language version features               model  cv_macro_f1  test_accuracy  test_macro_f1
      en  tokens      bow         naive_bayes        0.793          0.640          0.625
      en  tokens      bow logistic_regression        0.801          0.620          0.610
      en  tokens    tfidf         naive_bayes        0.650          0.536          0.500
      en  tokens    tfidf logistic_regression        0.814          0.648          0.635
      en    stem      bow         naive_bayes        0.795          0.620          0.609
      en    stem      bow logistic_regression        0.807          0.620          0.609
      en    stem    tfidf         naive_bayes        0.653          0.540          0.500
      en    stem    tfidf logistic_regression        0.817          0.660          0.654
      en   lemma      bow         naive_bayes        0.797          0.628          0.615
      en   lemma      bow logistic_regression        0.802          0.624          0.618
      en   lemma    tfidf         naive_bayes        0.652          0.548          0.519
      en   lemma    tfidf logistic_regression        0.817          0.656          0.650
      hi  tokens      bow         naive_bayes        0.866          0.808          0.726
      hi  tokens      bow logistic_regression        0.877          0.840          0.850
      hi  tokens    tfidf         naive_bayes        0.827          0.784          0.776
      hi  tokens    tfidf logistic_regression        0.881          0.840          0.795
      hi    stem      bow         naive_bayes        0.859          0.816          0.728
      hi    stem      bow logistic_regression        0.877          0.836          0.806
      hi    stem    tfidf         naive_bayes        0.817          0.784          0.761
      hi    stem    tfidf logistic_regression        0.882          0.848          0.787
      hi   lemma      bow         naive_bayes        0.862          0.816          0.728
      hi   lemma      bow logistic_regression        0.877          0.836          0.789
      hi   lemma    tfidf         naive_bayes        0.820          0.776          0.765
      hi   lemma    tfidf logistic_regression        0.881          0.848          0.812
```

Stemming vs lemmatization (mean test macro-F1 over the 4 feature/model combinations):

```
version   lemma   stem  tokens
language                      
en        0.600  0.593   0.592
hi        0.774  0.770   0.787
```