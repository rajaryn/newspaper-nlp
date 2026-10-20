# Preprocessing: before and after


## English (Indian Express)

- **Original:** Paytm shares fall for second consecutive session, tanks nearly 9%
  - tokens: `paytm shares fall second consecutive session tanks nearly`
  - stem: `paytm share fall second consecut session tank nearli`
  - lemma: `paytm share fall second consecutive session tank nearly`

- **Original:** Kiran Rao says parents asked her, Aamir Khan to rethink divorce since they remained friends: ‘Don’t need a paper to say we’re married’
  - tokens: `kiran rao parents asked aamir khan rethink divorce since remained friends need paper re married`
  - stem: `kiran rao parent ask aamir khan rethink divorc sinc remain friend need paper re marri`
  - lemma: `kiran Rao parent ask aamir khan rethink divorce since remain friend need paper re marry`

- **Original:** Boiled guava chaat: Is it advisable against cold, cough?
  - tokens: `boiled guava chaat advisable cold cough`
  - stem: `boil guava chaat advis cold cough`
  - lemma: `boil guava chaat advisable cold cough`


## Hindi (Jansatta)

- **Original:** Happy Hug Day 2024 Wishes: हग डे पर पार्टनर को फील कराएं स्पेशल, भेजें ये प्यार भरे मैसेज और Photos
  - tokens: `happy hug day wishes हग डे पार्टनर फील कराएं स्पेशल भेजें प्यार भरे मैसेज photos`
  - stem: `happi hug day wish हग डे पार्टनर फील कर स्पेशल भेज प्यार भर मैसेज photo`
  - lemma: `happy hug day wish हगना डे पार्टनर फील कराएं स्पेशल भेजना प्यार भरना मैसेज photo`

- **Original:** इस 1 कारण की वजह से आंतों में सूजन और पेट में मचती है तबाही,दवाई से भी गट हेल्थ में नहीं हो रहा सुधार, इस तरह करें बीमारी का उपचार
  - tokens: `कारण वजह आंतों सूजन पेट मचती तबाही दवाई गट हेल्थ सुधार बीमारी उपचार`
  - stem: `कारण वजह आंत सूजन पेट मच तबाह दव गट हेल्थ सुधार बीमार उपचार`
  - lemma: `कारण वजह आंतों सूजन पेट मचना तबाही दवाई गट हेल्थ सुधार बीमारी उपचार`

- **Original:** Ind vs Eng: रहाणे और पुजारा का टेस्ट करियर अब हो चुका है खत्म, पूर्व भारतीय खिलाड़ी ने दिया बड़ा बयान
  - tokens: `ind eng रहाणे पुजारा टेस्ट करियर चुका खत्म पूर्व भारतीय खिलाड़ी बड़ा बयान`
  - stem: `ind eng रहाण पुजार टेस्ट करियर चुक खत्म पूर्व भारतीय खिलाड़ बड़ बयान`
  - lemma: `ind eng रहाणे पुजारा टेस्ट करियर चुकना खत्म पूर्व भारतीय खिलाड़ी बड़ा बयान`


## Vocabulary size (training rows)

```
language version  vocabulary  avg tokens per headline
      en  tokens       19688                     10.4
      en    stem       15147                     10.4
      en   lemma       16095                     10.4
      hi  tokens       18557                     12.2
      hi    stem       14609                     12.2
      hi   lemma       15936                     12.2
```