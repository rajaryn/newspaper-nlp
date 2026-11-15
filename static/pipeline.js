/* Pipeline page: "Try it" + one headline followed through every pipeline step.
   One call (POST /api/trace) returns every intermediate result; each STEPS entry turns its part
   of that reply into a visual. Nothing is computed here except layout. */
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const isHindi = (s) => /[ऀ-ॿ]/.test(s);
const hiCls = (s) => (isHindi(s) ? " hi" : "");
const signed = (v, d = 2) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d);
// a chip that pops in after the ones before it (--i staggers the animation)
const chip = (text, cls = "", i = 0, title = "") =>
  `<span class="tok ${cls}${hiCls(text)}" style="--i:${i}"${title ? ` title="${esc(title)}"` : ""}>${esc(text)}</span>`;

const EXAMPLES = [
  "Rohit Sharma leads India to T20 World Cup win",
  "Sensex jumps 800 points as banking stocks rally",
  "Police arrest two men for cheating investors in Delhi",
  "बिहार में भारी बारिश, कई जिलों में बाढ़ का अलर्ट",
  "चुनाव आयोग ने मतदान की तारीखों का ऐलान किया",
];

let trace = null;   // the last /api/trace reply
let step = 0;       // index into STEPS
let timer = null;   // autoplay interval

/* ============================ the steps ============================ */
// Each step: name, the script that does it in the real pipeline, one sentence on what happens,
// and draw(t) -> HTML for this headline.
const STEPS = [
  {
    name: "Collect", file: "sitemap_scraper.py · headline_fetcher.py",
    what: "The real pipeline finds each article in the paper's daily sitemap, opens the page, and reads its headline from the og:title tag. Your typed headline stands in for one.",
    draw: (t) => `
      <div class="flow">
        <div class="box"><p class="label">Sitemap entry</p><code>&lt;loc&gt;https://${t.lang === "hi" ? "www.jansatta.com/national" : "indianexpress.com/article/india"}/…&lt;/loc&gt;</code></div>
        <span class="arrow">→</span>
        <div class="box"><p class="label">Article page</p><code>&lt;meta property="og:title" content="<b class="${hiCls(t.raw)}">${esc(t.raw)}</b>"&gt;</code></div>
        <span class="arrow">→</span>
        <div class="box"><p class="label">Language</p><p class="big">${t.lang === "hi" ? "Hindi" : "English"}</p>
          <p class="small">${t.lang === "hi" ? "Devanagari letters found" : "No Devanagari letters"} → the <b>${t.paper}</b> model</p></div>
      </div>`,
  },
  {
    name: "Clean", file: "clean_and_profile.py",
    what: "Cleaning removes things that are not real news headlines. Two of its rules apply to a single typed headline.",
    draw: (t) => `
      <ul class="checks">
        <li class="ok">Extra spaces collapsed <span class="mono${hiCls(t.cleaned)}">${esc(t.cleaned)}</span></li>
        <li class="${t.kept_by_cleaning ? "ok" : "bad"}">At least 3 words: <b>${t.n_words}</b> ${t.kept_by_cleaning ? "" : "→ this headline would be <b>dropped</b>"}</li>
        <li class="na">Not a video, photo gallery, live blog or horoscope page (checked on the URL, so not applicable here)</li>
        <li class="na">Not the same headline twice on one day (checked across the whole day)</li>
      </ul>
      <p class="result ${t.kept_by_cleaning ? "ok" : "bad"}">${t.kept_by_cleaning ? "Kept ✓" : "Dropped ✗ (the rest still runs, so you can see it)"}</p>`,
  },
  {
    name: "Normalise", file: "preprocess.py",
    what: (t) => t.lang === "hi"
      ? "Unicode is normalised and the Indic NLP normaliser makes different spellings of the same Devanagari letters identical."
      : "Unicode is normalised, everything is lowercased, curly quotes become straight, and the possessive 's is removed.",
    draw: (t) => `
      <div class="before-after">
        <p class="label">Before</p><p class="line${hiCls(t.cleaned)}">${esc(t.cleaned)}</p>
        <p class="label">After</p><p class="line${hiCls(t.normalised)}">${esc(t.normalised)}</p>
      </div>`,
  },
  {
    name: "Tokenize", file: "preprocess.py",
    what: (t) => t.lang === "hi"
      ? "The Indic NLP tokenizer splits the text into words and punctuation marks."
      : "The text is split into words (hyphenated words stay together) and numbers; punctuation disappears.",
    draw: (t) => `<div class="chips">${t.tokens.map((x, i) => chip(x.raw, "", i)).join("")}</div>
      <p class="small">${t.tokens.length} tokens</p>`,
  },
  {
    name: "Stopwords", file: "preprocess.py",
    what: "Words that carry no topic (the, of, के, में…), numbers, punctuation and single letters are removed.",
    draw: (t) => {
      const kept = t.tokens.filter((x) => !x.reason).length;
      return `<div class="chips">${t.tokens.map((x, i) =>
        x.reason ? `<span class="gone" style="--i:${i}">${chip(x.raw, "off", 0)}<small>${x.reason}</small></span>` : chip(x.token, "", i)).join("")}</div>
        <p class="small"><b>${kept}</b> kept · ${t.tokens.length - kept} removed</p>`;
    },
  },
  {
    name: "Stem", file: "preprocess.py",
    what: (t) => `Each word is cut to a common root, so different forms count as one word. The model uses the <b>${t.version}</b> version, the one that scored best in cross-validation.`,
    draw: (t) => {
      if (!t.forms.length) return `<p class="empty">No words left.</p>`;
      const head = (v, label) => `<th class="${t.version === v ? "used" : ""}">${label}${t.version === v ? " ✓ used" : ""}</th>`;
      return `<table class="forms"><tr><th>Token</th><th></th>${head("stem", t.lang === "hi" ? "Stem (suffix stripper)" : "Stem (Porter)")}${head("lemma", "Lemma (simplemma)")}</tr>
        ${t.forms.map((f, i) => `<tr style="--i:${i}"><td class="${hiCls(f.token)}">${esc(f.token)}</td><td class="arrow">→</td>
          <td class="${t.version === "stem" ? "used" : ""}${hiCls(f.stem)}">${esc(f.stem)}</td>
          <td class="${t.version === "lemma" ? "used" : ""}${hiCls(f.lemma)}">${esc(f.lemma)}</td></tr>`).join("")}</table>`;
    },
  },
  {
    name: "Features", file: "baseline.py (TF-IDF)",
    what: "The model reads single words and word pairs. Each one it saw in training gets a TF-IDF value: higher for rarer, more telling words. Anything it never saw is ignored.",
    draw: (t) => {
      const known = t.features.filter((f) => f.known).sort((a, b) => b.tfidf - a.tfidf);
      const unknown = t.features.filter((f) => !f.known);
      const max = Math.max(1e-9, ...known.map((f) => f.tfidf));
      return `<p class="label">Model input</p><p class="line mono${hiCls(t.model_input)}">${esc(t.model_input) || "∅"}</p>
        <div class="feat-grid">${known.map((f, i) => `
          <div class="feat" style="--i:${i}"><span class="tok ${f.term.includes(" ") ? "pair" : ""}${hiCls(f.term)}">${esc(f.term)}</span>
            <span class="bar"><i style="width:${(f.tfidf / max) * 100}%"></i></span><b>${f.tfidf.toFixed(2)}</b></div>`).join("")}</div>
        ${unknown.length ? `<p class="small">Never seen in training, ignored: ${unknown.map((f) => chip(f.term, "off")).join(" ")}</p>` : ""}
        <p class="small">${known.filter((f) => !f.term.includes(" ")).length} words + ${known.filter((f) => f.term.includes(" ")).length} word pairs.
          <span class="pair-key">Outlined</span> = a word pair.</p>`;
    },
  },
  {
    name: "Score", file: "baseline.py (logistic regression)",
    what: "Every topic gets a score: a starting bias, plus each feature's TF-IDF value times the weight the model learned for that topic. This breakdown is exact.",
    draw: (t) => {
      const score = t.classes.map((_, k) => t.intercept[k] + t.words[k]);
      const order = t.classes.map((c, k) => k).sort((a, b) => score[b] - score[a]);
      const lo = Math.min(0, ...score), hi = Math.max(0, ...score), span = hi - lo || 1;
      const w = t.classes.indexOf(t.topic);
      const contrib = t.features.filter((f) => f.known).map((f) => [f.term, f.contrib[w]])
        .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 8);
      const cmax = Math.max(1e-9, ...contrib.map((c) => Math.abs(c[1])));
      return `<div class="score-grid">
        <div><p class="label">Score per topic = bias + words</p>
          <div class="scores">${order.map((k, i) => `
            <div class="srow ${k === w ? "win" : ""}" style="--i:${i}">
              <span>${t.classes[k]}</span>
              <span class="sbar"><i class="${score[k] >= 0 ? "pos" : "neg"}" style="left:${((Math.min(0, score[k]) - lo) / span) * 100}%;width:${(Math.abs(score[k]) / span) * 100}%"></i>
                <em style="left:${((0 - lo) / span) * 100}%"></em></span>
              <b title="bias ${signed(t.intercept[k])} + words ${signed(t.words[k])}">${signed(score[k])}</b></div>`).join("")}</div></div>
        <div><p class="label">What made <b>${t.topic}</b> win</p>
          <p class="sum"><span>bias</span><b>${signed(t.intercept[w])}</b></p>
          ${contrib.map(([term, v], i) => `<p class="sum" style="--i:${i}"><span class="${hiCls(term)}">${esc(term)}</span>
            <i class="cbar ${v >= 0 ? "pos" : "neg"}" style="width:${(Math.abs(v) / cmax) * 60}%"></i><b>${signed(v)}</b></p>`).join("")}
          <p class="sum total"><span>score</span><b>${signed(score[w])}</b></p></div></div>`;
    },
  },
  {
    name: "Predict", file: "baseline.py (softmax)",
    what: "The scores are turned into probabilities that add up to 100% (softmax). The highest one is the answer.",
    draw: (t) => {
      const order = t.classes.map((c, k) => k).sort((a, b) => t.probs[b] - t.probs[a]);
      return `<div class="predict">
        <div class="probs big">${order.map((k, i) => probRow(t.classes[k], t.probs[k], k === t.classes.indexOf(t.topic), i)).join("")}</div>
        <div class="verdict-box"><p class="label">Answer</p><p class="answer">${t.topic}</p><p class="conf">${t.probs[t.classes.indexOf(t.topic)]}% probability</p></div></div>`;
    },
  },
  {
    name: "Analyse", file: "analysis.py",
    what: "In the analysis, every headline counts toward its topic's share of its paper's coverage, and is checked against a shared English–Hindi list of about 75 people, parties and places.",
    draw: (t) => `
      <div class="flow">
        <div class="box"><p class="label">Counts toward</p><p class="big">${t.topic}</p><p class="small">in ${t.paper}'s topic share for its day and month</p></div>
        <div class="box wide"><p class="label">Names found</p>
          <div class="chips">${t.entities.length ? t.entities.map((e, i) => chip(e, "name", i)).join("") : `<span class="small">None from the list</span>`}</div>
          <p class="small">Each one counts toward that name's share of mentions.</p></div>
      </div>
      <p class="small">See these totals across all 46,113 headlines in the <a href="/#people">dashboard →</a></p>`,
  },
];

/* ============================ drawing ============================ */
function probRow(topic, p, win, i) {
  return `<div class="prow ${win ? "win" : ""}" style="--i:${i}"><span>${topic}</span>
    <span class="pbar"><i style="width:${p}%"></i></span><b>${p.toFixed(1)}%</b></div>`;
}

// The "Try it" box: answer, confidence, evidence words, probability bars.
function drawTry(t) {
  const w = t.classes.indexOf(t.topic);
  $("#answer").textContent = t.topic;
  $("#conf").textContent = `${t.probs[w]}% probability · ${t.paper} model`;
  const pushes = t.features.filter((f) => f.known && f.contrib[w] > 0).sort((a, b) => b.contrib[w] - a.contrib[w]).slice(0, 8);
  $("#evidence").innerHTML = pushes.map((f, i) => chip(f.term, "ev", i, `+${f.contrib[w]}`)).join("") ||
    `<span class="small">No known words: the model falls back on its starting bias.</span>`;
  const order = t.classes.map((c, k) => k).sort((a, b) => t.probs[b] - t.probs[a]);
  $("#probs").innerHTML = order.map((k, i) => probRow(t.classes[k], t.probs[k], k === w, i)).join("");
}

// One step's card. `n` is its position, shown as the step number.
function stepCard(n) {
  const s = STEPS[n], what = typeof s.what === "function" ? s.what(trace) : s.what;
  return `<article class="step-card" data-n="${n}">
    <header><span class="num">${n + 1}</span><div><h3>${s.name}</h3><code class="file">${s.file}</code></div></header>
    <p class="what">${what}</p>
    <div class="visual">${s.draw(trace)}</div></article>`;
}

function drawRail() {
  $("#rail").innerHTML = STEPS.map((s, i) =>
    `<li class="${i === step ? "on" : i < step ? "done" : ""}" data-i="${i}"><b>${i + 1}</b><span>${s.name}</span></li>`).join("");
  $$("#rail li").forEach((li) => (li.onclick = () => go(+li.dataset.i)));
}

function drawStage() {
  if (!trace) return;
  const all = $("#showAll").checked;
  $("#stage").innerHTML = all ? STEPS.map((_, i) => stepCard(i)).join("") : stepCard(step);
  $("#stage").classList.toggle("all", all);
  drawRail();
  $("#prev").disabled = all || step === 0;
  $("#next").disabled = all || step === STEPS.length - 1;
}

function go(i) {
  step = Math.max(0, Math.min(STEPS.length - 1, i));
  if ($("#showAll").checked) {
    $(`.step-card[data-n="${step}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    drawRail();
  } else drawStage();
}

/* ============================ data + wiring ============================ */
async function run() {
  const text = $("#text").value.trim();
  if (!text) return;
  const r = await fetch("/api/trace", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  const d = await r.json();
  if (!r.ok) { $("#answer").textContent = d.error; return; }
  if (!d.consistent) console.warn("trace tokens differ from preprocess.py tokens", d);
  trace = d;
  drawTry(d);
  drawStage();
}

function setPlaying(on) {
  clearInterval(timer);
  timer = null;
  $("#play").textContent = on ? "❚❚ Pause" : "▶ Play";
  if (!on) return;
  if (step === STEPS.length - 1) go(0);
  timer = setInterval(() => (step === STEPS.length - 1 ? setPlaying(false) : go(step + 1)), 3500);
}

function autosize() { const t = $("#text"); t.style.height = "auto"; t.style.height = t.scrollHeight + "px"; }

function init() {
  const box = $("#text");
  box.oninput = debounce(() => { autosize(); run(); }, 250);
  for (const x of EXAMPLES) {
    const b = Object.assign(document.createElement("button"), { type: "button", className: `chip small${hiCls(x)}`, textContent: x });
    b.onclick = () => { box.value = x; autosize(); run(); };
    $("#examples").append(b);
  }
  $("#prev").onclick = () => { setPlaying(false); go(step - 1); };
  $("#next").onclick = () => { setPlaying(false); go(step + 1); };
  $("#play").onclick = () => setPlaying(!timer);
  $("#showAll").onchange = () => { setPlaying(false); drawStage(); };
  document.addEventListener("keydown", (e) => {
    if (["TEXTAREA", "INPUT"].includes(document.activeElement.tagName)) return; // typing, not navigating
    if (e.key === "ArrowRight") { setPlaying(false); go(step + 1); }
    if (e.key === "ArrowLeft") { setPlaying(false); go(step - 1); }
  });
  $("#themeBtn").onclick = () => {
    const dark = getComputedStyle($(".viz-root")).colorScheme === "dark";
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    localStorage.setItem("theme", document.documentElement.dataset.theme);
  };
  const q = new URLSearchParams(location.search).get("q"); // /?q=<headline> opens with that headline
  if (q) box.value = q;
  // section bar: highlight the section in view (the lower one wins once its top passes the bars)
  const links = $$("#sections a");
  const spy = () => {
    const y = $("#steps").getBoundingClientRect().top;
    const current = y < window.innerHeight * 0.45 ? "#steps" : "#try";
    links.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === current));
  };
  window.addEventListener("scroll", spy, { passive: true });
  spy();

  // the box's height depends on its width and font, so measure again once fonts load and on resize
  autosize();
  document.fonts.ready.then(autosize);
  window.addEventListener("resize", debounce(autosize, 100));
  run();
}

init();
