/* News Pulse dashboard front end.
   - one row of filter pills for every section: Period, Paper, Topic, Sort, sent with every API call
     (a section that does not use one ignores it, and its pill is greyed out there)
   - one render function per tab; a tab is only re-drawn when it is shown (see `dirty`)
   - all numbers come from app.py; this file only draws them */
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
// el("p", {class: "x"}, "text", child) -> a DOM element with attributes and children
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) k === "class" ? (n.className = v) : n.setAttribute(k, v);
  for (const k of kids) n.append(k);
  return n;
};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dayFmt = (s, long) => { const [y, m, d] = s.split("-"); return `${+d} ${MONTHS[m - 1]}${long ? " " + y : ""}`; };
const monthFmt = (s, long) => { const [y, m] = s.split("-"); return MONTHS[m - 1] + (long ? " " + y : ""); };
const weekFmt = (s, long) => (long ? "Week of " : "") + dayFmt(s, long);
const pkey = (p) => (p === "Jansatta" ? "ja" : "ie"); // short key used in CSS class names
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// dirty = tabs whose data changed while they were hidden; they re-render when next shown
// filters: start / end / papers / topics ([] = any topic) / sort ("newest" | "oldest")
const state = { meta: null, start: "", end: "", papers: [], topics: [], sort: "newest", tab: "overview", dirty: new Set(),
  trFreq: "M", event: null, hlPage: 0 };

// GET /api/<path> with the filters added to the query string (endpoints that don't use one ignore it).
async function api(path, params = {}) {
  const q = new URLSearchParams({ start: state.start, end: state.end, papers: state.papers.join(","),
    topics: state.topics.join(","), sort: state.sort, ...params });
  const r = await fetch(`/api/${path}?${q}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

// Fill every legend slot with the currently selected papers.
function legends() {
  document.querySelectorAll("[data-legend]").forEach((h) => {
    h.innerHTML = "";
    state.papers.forEach((p) => h.append(el("span", { class: "key" }, el("i", { class: `sw s-${pkey(p)}` }), p)));
  });
}

function empty(id, msg = "No headlines match these filters.") {
  $("#" + id).innerHTML = `<p class="empty">${msg}</p>`;
}

/* ---------------- Overview ---------------- */
async function renderOverview() {
  const d = await api("overview");
  // the count includes the Topic filter (sections that use topics show exactly these headlines)
  $("#fCount").textContent = `${d.in_topics.toLocaleString()} headlines selected`;
  const cards = $("#ovCards");
  cards.innerHTML = "";
  for (const c of d.cards) {
    cards.append(el("article", { class: `card stat stat-${pkey(c.paper)}` },
      el("p", { class: "stat-label" }, c.paper),
      el("p", { class: "stat-num" }, c.n.toLocaleString()),
      el("p", { class: "stat-sub" }, `headlines over ${c.days} days`)));
    if (c.top) cards.append(el("article", { class: `card stat stat-${pkey(c.paper)}` },
      el("p", { class: "stat-label" }, `${c.paper} · biggest topic`),
      el("p", { class: "stat-num word" }, c.top),
      el("p", { class: "stat-sub" }, `${c.top_share}% of headlines (excluding Other)`)));
  }
  if (!d.total) { empty("ovChart"); empty("ovGap"); $("#ovCallout").textContent = ""; return; }
  const cats = shownTopics(); // the Topic filter picks which topics the charts show
  Charts.bars("ovChart", { labels: cats, data: Object.fromEntries(Object.entries(d.share).map(([p, s]) => [p, cats.map((c) => s[c])])), height: 420 });
  if (d.gap) {
    const vals = cats.map((c) => +(d.share.Jansatta[c] - d.share["Indian Express"][c]).toFixed(2));
    const order = cats.map((c, i) => [c, vals[i]]).sort((a, b) => b[1] - a[1]);
    Charts.diverging("ovGap", { labels: order.map((o) => o[0]), values: order.map((o) => o[1]) });
    // the biggest gap each way, among the topics shown
    const [ja, ie] = [order[0], order[order.length - 1]];
    const parts = [ja[1] > 0 && `Jansatta gives <b>${ja[0]}</b> ${ja[1].toFixed(1)} points more`,
      ie[1] < 0 && `Indian Express gives <b>${ie[0]}</b> ${(-ie[1]).toFixed(1)} points more`].filter(Boolean);
    $("#ovCallout").innerHTML = parts.length ? parts.join("; ") + "." : "";
  } else {
    empty("ovGap", "Select both papers to compare them.");
    $("#ovCallout").textContent = "";
  }
}

/* ---------------- Trends ---------------- */
async function renderTrends() {
  const host = $("#trCharts"), topics = shownTopics();
  $("#trSub").textContent = state.topics.length ? `Showing the topics chosen in Filters.` : `Showing all nine topics. Pick some in Filters → Topic.`;
  const d = await api("trends", { topics: topics.join(","), freq: state.trFreq });
  host.innerHTML = "";
  const unit = state.trFreq === "M" ? "month" : "week";
  for (const t of topics) {
    const id = "tr-" + t.replace(/\W/g, "");
    host.append(el("article", { class: "card chart-card" }, el("h2", {}, t),
      el("p", { class: "sub" }, `Share of each paper's headlines, by ${unit}`),
      el("div", { class: "legend", "data-legend": "" }), el("div", { class: "chart", id })));
    Object.keys(d[t]).length ? Charts.line(id, { series: d[t], xfmt: state.trFreq === "M" ? monthFmt : weekFmt }) : empty(id);
  }
  legends();
}

/* ---------------- Events ---------------- */
function eventList() {
  const host = $("#evList");
  host.innerHTML = "";
  for (const e of state.meta.events) {
    const b = el("button", { type: "button", class: `event ${state.event === e ? "on" : ""}` },
      el("span", { class: "event-date" }, dayFmt(e.date)), el("span", { class: "event-name" }, e.name));
    b.onclick = () => { state.event = e; $("#evCustom").open = false; eventList(); renderEvents(); };
    host.append(b);
  }
}
// Your own event: what = a topic, or "name:<typed name>" (matched like the name search).
function customEvent() {
  const kind = $("#evKind .on").dataset.v;
  const what = kind === "topic" ? $("#evWhatTopic").value : "name:" + $("#evWhatName").value.trim();
  const date = $("#evDate").value;
  const tracked = kind === "topic" ? what : $("#evWhatName").value.trim();
  return { name: $("#evName").value.trim() || `${tracked} around ${dayFmt(date)}`, date, what, custom: true,
    before: Math.min(30, Math.max(1, +$("#evBefore").value || 7)), after: Math.min(30, Math.max(1, +$("#evAfter").value || 10)) };
}
async function renderEvents() {
  const e = state.event;
  const tracked = e.what.startsWith("entity:") ? e.what.slice(7) : e.what.startsWith("name:") ? e.what.slice(5) : null;
  const label = tracked ? `headlines mentioning ${tracked}` : `${e.what} headlines`;
  $("#evTitle").textContent = e.name;
  $("#evSub").textContent = `Share of ${label}, ${e.before} days before to ${e.after} days after ${dayFmt(e.date, true)}`;
  const d = await api("event", { date: e.date, what: e.what, before: e.before, after: e.after });
  if (!Object.keys(d.series).length) empty("evChart", "No days with enough headlines in this window.");
  else Charts.line("evChart", { series: d.series, xfmt: dayFmt, event: { date: e.date, text: e.name } });
  $("#evTable").innerHTML = d.table.length ? `<thead><tr><th>Paper</th><th>Average before</th><th>Peak</th><th>Peak date</th><th>Days from event</th></tr></thead><tbody>` +
    d.table.map((r) => `<tr><td><i class="sw s-${pkey(r.paper)}"></i>${r.paper}</td><td>${r.before ?? "–"}%</td><td><b>${r.peak}%</b></td><td>${dayFmt(r.peak_date)}</td><td>${r.offset > 0 ? "+" : ""}${r.offset}</td></tr>`).join("") + "</tbody>" : "";
  // for a typed name: say how it was matched, and when Jansatta needs the Hindi spelling
  const m = d.matched;
  $("#evMatch").innerHTML = !m ? "" : (m.listed
    ? `Tracking <b>${esc(m.listed)}</b> from the name list, in English and Hindi headlines.`
    : `Tracking headlines that contain ${m.terms.map((t) => `"<b>${esc(t)}</b>"`).join(" or ")}.`) +
    (m && m.hindi_hint ? ` <span class="ns-hint">Jansatta's headlines are in Hindi: add the Hindi spelling after a comma to track this name there.</span>` : "");
  $("#evNote").textContent = `Days with fewer than ${d.min_n} headlines are hidden (e.g. Jansatta on 4 June, which has 1).`;
}

/* ---------------- People & places ---------------- */
async function renderPeopleTop() {
  const n = $("#peN").value;
  $("#peSub").textContent = `% of headlines mentioning each name${state.topics.length ? ` · within ${state.topics.join(", ")}` : ""} · click a bar to search it`;
  const d = await api("entities", { n });
  if (!d.names.length) return empty("peChart");
  const data = Object.fromEntries(state.papers.map((p) => [p, d.names.map((x) => (d.share[p] || {})[x] ?? 0)]));
  Charts.bars("peChart", { labels: d.names, data, height: Math.max(360, d.names.length * 34),
    onPick: (name) => { $("#nsQ").value = name; renderNameSearch(); $("#nsQ").scrollIntoView({ behavior: "smooth", block: "center" }); } });
}
/* ---- search one name ---- */
async function renderNameSearch() {
  const q = $("#nsQ").value.trim(), out = $("#nsOut");
  if (!q) { out.innerHTML = ""; return; }
  const d = await api("name_search", { q });
  if (d.error) { out.innerHTML = `<p class="empty">${d.error}</p>`; return; }
  const how = (d.listed
    ? `Matched <b>${d.listed}</b> from the name list, in English and Hindi headlines`
    : `Searched headlines for ${d.terms.map((t) => `"<b>${esc(t)}</b>"`).join(" or ")}`) +
    (d.only_topics.length ? `, within ${d.only_topics.join(", ")} only.` : ".");
  out.innerHTML = `
    <p class="ns-how">${how}${d.hindi_hint ? ` <span class="ns-hint">Jansatta's headlines are in Hindi: add the Hindi spelling after a comma to find this name there.</span>` : ""}</p>
    <div class="cards ns-cards">${d.cards.map((c) => `
      <article class="card stat stat-${pkey(c.paper)}"><p class="stat-label">${c.paper}</p>
        <p class="stat-num">${c.n.toLocaleString()}</p><p class="stat-sub">headlines · ${c.share}% of the paper's headlines</p></article>`).join("")}</div>
    ${d.total ? `<div class="grid-2">
      <div><h3>Week by week</h3><p class="sub">% of each paper's headlines that mention it</p><div class="legend" data-legend></div><div class="chart" id="nsTrend"></div></div>
      <div><h3>In which topics</h3><p class="sub">% of the matching headlines in each topic</p><div class="legend" data-legend></div><div class="chart" id="nsTopics"></div></div>
    </div>
    <h3 class="ns-list-head">${state.sort === "oldest" ? "Earliest" : "Latest"} headlines <span>${Math.min(30, d.total)} of ${d.total.toLocaleString()}</span></h3>
    <ol class="feed ns-feed">${d.rows.map((r) => `<li><a class="hl ${pkey(r.paper) === "ja" ? "hi" : ""}" href="${r.url}" target="_blank" rel="noopener">${esc(r.headline)}</a>
      <div class="hl-meta"><span class="tag tag-${pkey(r.paper)}">${r.paper}</span><span>${dayFmt(r.date, true)}</span><span class="topic">${r.topic}</span></div></li>`).join("")}</ol>`
    : `<p class="empty">No headlines mention it in the selected dates and papers.</p>`}`;
  legends();
  if (!d.total) return;
  Charts.line("nsTrend", { series: d.trend, xfmt: weekFmt });
  Charts.bars("nsTopics", { labels: d.categories, data: d.topics, height: 340 });
}
const renderPeople = () => Promise.all([renderPeopleTop(), renderNameSearch()]);

/* ---------------- Headlines ---------------- */
async function renderHeadlines() {
  const d = await api("headlines", { q: $("#hlQ").value, src: $("#hlSrc").value, page: state.hlPage });
  const pages = Math.max(1, Math.ceil(d.total / d.size));
  $("#hlCount").textContent = `${d.total.toLocaleString()} headlines`;
  $("#hlPage").textContent = `Page ${d.page + 1} of ${pages}`;
  $("#hlPrev").disabled = d.page === 0;
  $("#hlNext").disabled = d.page + 1 >= pages;
  const feed = $("#hlFeed");
  feed.innerHTML = "";
  for (const r of d.rows) {
    const a = el("a", { href: r.url, target: "_blank", rel: "noopener", class: `hl ${pkey(r.paper) === "ja" ? "hi" : ""}` }, r.headline);
    const meta = el("div", { class: "hl-meta" },
      el("span", { class: `tag tag-${pkey(r.paper)}` }, r.paper), el("span", {}, dayFmt(r.date, true)),
      el("span", { class: "topic" }, r.topic), el("span", { class: "src", title: "Where the topic came from" }, r.source === "model" ? "model" : "URL"));
    r.entities.forEach((x) => meta.append(el("span", { class: "ent" }, x)));
    feed.append(el("li", {}, a, meta));
  }
  if (!d.rows.length) feed.innerHTML = `<li class="empty">Nothing matches.</li>`;
}

/* ---------------- filters ---------------- */
// One row of pills for every section: Period, Paper, Topic, Sort. Each pill shows its current value and
// opens a small menu under it. Any change re-renders the visible section and marks the others to
// re-render when shown. APPLIES (below) says which sections use which filter.
function initFilters(m) {
  const PRESETS = [["All", m.start, m.end], ["Q1", "2024-01-01", "2024-03-31"],
    ["Election", "2024-04-19", "2024-06-10"], ["Jul–Aug", "2024-07-01", m.end]];

  // ---- menus: one open at a time; close on scroll, a click elsewhere, or Esc ----
  const close = () => $$(".pill-wrap").forEach((w) => {
    w.querySelector(".pop").hidden = true;
    w.querySelector(".pill").setAttribute("aria-expanded", "false");
  });
  $$(".pill-wrap").forEach((w) => (w.querySelector(".pill").onclick = () => {
    const wasOpen = !w.querySelector(".pop").hidden;
    close();
    if (wasOpen) return;
    w.querySelector(".pop").hidden = false;
    w.querySelector(".pill").setAttribute("aria-expanded", "true");
  }));
  // composedPath() = the path at the moment of the click (an option redraws its menu as it is clicked)
  document.addEventListener("click", (e) => { if (!e.composedPath().some((n) => n.classList && n.classList.contains("pill-wrap"))) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  window.addEventListener("scroll", () => { if (!document.activeElement.matches("input[type=date]")) close(); }, { passive: true });

  // ---- changing a filter ----
  const changed = () => { drawFilters(); filtersChanged(); };
  for (const id of ["#fStart", "#fEnd"]) Object.assign($(id), { min: m.start, max: m.end });
  const setDates = (s, e) => {
    $("#fStart").value = s; $("#fEnd").value = e;
    state.start = s; state.end = e;
    changed();
  };
  const onDate = () => {
    const s = $("#fStart").value, e = $("#fEnd").value;
    if (s && e && s <= e) setDates(s, e);
  };
  $("#fStart").onchange = onDate; $("#fEnd").onchange = onDate;
  const toggle = (list, item, order) => {
    const i = list.indexOf(item);
    i >= 0 ? list.splice(i, 1) : list.push(item);
    list.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  };
  // one option button inside a menu
  const option = (label, on, onclick, extra = "") =>
    Object.assign(el("button", { type: "button", class: `opt ${on ? "on" : ""}`, "aria-pressed": on }), { onclick, innerHTML: extra + esc(label) });

  // ---- draw the menus and the pills' values ----
  function drawFilters() {
    const preset = PRESETS.find(([, s, e]) => s === state.start && e === state.end);
    $("#fPresets").replaceChildren(...PRESETS.map(([label, s, e]) => option(label, preset && preset[0] === label, () => { setDates(s, e); close(); })),
      option("Custom dates", !preset, () => $("#fStart").focus()));
    $("#fPapers").replaceChildren(...m.papers.map((p) => option(p, state.papers.includes(p),
      () => { toggle(state.papers, p, m.papers); changed(); }, `<i class="sw s-${pkey(p)}"></i>`)));
    $("#fTopics").replaceChildren(option("Any topic", !state.topics.length, () => { state.topics = []; changed(); }),
      ...m.categories.map((t) => option(t, state.topics.includes(t), () => { toggle(state.topics, t, m.categories); changed(); })));
    $("#fSort").replaceChildren(...[["newest", "Newest first"], ["oldest", "Oldest first"]].map(([v, label]) =>
      option(label, state.sort === v, () => { state.sort = v; changed(); close(); })));

    // each pill: its current value, highlighted when not the default
    const allDates = state.start === m.start && state.end === m.end;
    const values = {
      period: [preset ? preset[0] : `${dayFmt(state.start)} – ${dayFmt(state.end)}`, !allDates],
      paper: [state.papers.length === m.papers.length ? "Both" : state.papers[0] || "None", state.papers.length !== m.papers.length],
      topic: [!state.topics.length ? "Any" : state.topics.length === 1 ? state.topics[0] : `${state.topics[0]} +${state.topics.length - 1}`, state.topics.length > 0],
      sort: [state.sort === "oldest" ? "Oldest" : "Newest", state.sort !== "newest"],
    };
    for (const [key, [text, set]] of Object.entries(values)) {
      const w = $(`.pill-wrap[data-filter="${key}"]`);
      w.querySelector(".pill-v").textContent = text;
      w.querySelector(".pill").classList.toggle("set", set);
    }
    $("#fReset").hidden = !Object.values(values).some(([, set]) => set);
  }
  $("#fReset").onclick = () => {
    state.topics = []; state.sort = "newest";
    state.papers.splice(0, Infinity, ...m.papers);
    setDates(m.start, m.end);
  };
  $("#fStart").value = m.start; $("#fEnd").value = m.end;
  drawFilters();
}

// Which filters each section uses; the others' pills are greyed out there, with a tooltip.
const APPLIES = {
  period: ["overview", "trends", "events", "people", "headlines"],
  paper: ["overview", "trends", "events", "people", "headlines"],
  topic: ["overview", "trends", "people", "headlines"],   // Events track their own topic or name
  sort: ["people", "headlines"],                          // only the headline lists have an order
};
function markFilters(tab) {
  for (const [key, tabs] of Object.entries(APPLIES)) {
    const pill = $(`.pill-wrap[data-filter="${key}"] .pill`), used = tabs.includes(tab);
    pill.disabled = !used;
    pill.title = used ? "" : `Not used in ${SECTIONS[tab]}`;
  }
}
// The topics a chart should show: the Topic filter's choice, or all nine.
const shownTopics = () => (state.topics.length ? state.topics : state.meta.categories);

/* ---------------- wiring ---------------- */
// the dashboard's sections: id (= #tab-<id> in the page, #<id> in the address) -> name
const SECTIONS = { overview: "Overview", trends: "Trends", events: "Events", people: "People & places", headlines: "Headlines" };
const RENDER = { overview: renderOverview, trends: renderTrends, events: renderEvents, people: renderPeople, headlines: renderHeadlines };

// Switch tab; render it now if its data changed while it was hidden.
function show(tab) {
  state.tab = tab;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  markFilters(tab);
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + tab));
  if (state.dirty.has(tab)) { state.dirty.delete(tab); RENDER[tab]().catch(console.error); }
  history.replaceState(null, "", "#" + tab);
}
// Filters changed: re-render the visible tab, mark the rest dirty. Overview is also refreshed
// because it updates the headline count in the section bar.
function filtersChanged() {
  legends();
  state.hlPage = 0;
  Object.keys(RENDER).forEach((t) => state.dirty.add(t));
  state.dirty.delete(state.tab);
  RENDER[state.tab]().catch(console.error);
  if (state.tab !== "overview") renderOverview().then(() => state.dirty.delete("overview")).catch(console.error);
}
async function init() {
  const m = state.meta = await (await fetch("/api/meta")).json();
  state.start = m.start; state.end = m.end; state.papers = [...m.papers];
  state.event = m.events[2];

  initFilters(m);

  // section bar: switching section starts the new one at the top of the page
  document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => { show(b.dataset.tab); window.scrollTo({ top: 0 }); }));
  // a link or typed address with another #section (e.g. /#people) switches section too
  window.addEventListener("hashchange", () => { const t = location.hash.slice(1); if (RENDER[t] && t !== state.tab) show(t); });

  // trends
  $("#trFreq").querySelectorAll("button").forEach((b) => (b.onclick = () => { // Month / Week switch
    state.trFreq = b.dataset.v;
    $("#trFreq").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    renderTrends();
  }));

  // events
  eventList();
  $("#evWhatTopic").innerHTML = m.categories.map((x) => `<option>${x}</option>`).join("");
  $$("#evKind button").forEach((b) => (b.onclick = () => {    // Track: a name (typed) or a topic (picked)
    $$("#evKind button").forEach((x) => x.classList.toggle("on", x === b));
    $("#evWhatName").hidden = b.dataset.v !== "name";
    $("#evWhatTopic").hidden = b.dataset.v !== "topic";
    $("#evHelp").hidden = b.dataset.v !== "name";
  }));
  $("#evForm").onsubmit = (ev) => {
    ev.preventDefault();
    if ($("#evKind .on").dataset.v === "name" && !$("#evWhatName").value.trim()) { $("#evWhatName").focus(); return; }
    state.event = customEvent();
    eventList(); renderEvents();
  };

  // people
  $("#peNames").innerHTML = m.entities.map((x) => `<option value="${x}">`).join("");
  $("#peN").oninput = () => { $("#peNv").textContent = $("#peN").value; };
  $("#peN").onchange = renderPeopleTop;
  $("#nsForm").onsubmit = (e) => { e.preventDefault(); renderNameSearch(); };
  // quick picks: listed names (both languages), and an unlisted one with its Hindi spelling
  for (const x of ["Rahul Gandhi", "Narendra Modi", "Virat Kohli", "Vinesh Phogat", "Bangladesh", "Nitin Gadkari, नितिन गडकरी"]) {
    const b = el("button", { type: "button", class: "chip small" }, x);
    b.onclick = () => { $("#nsQ").value = x; renderNameSearch(); };
    $("#nsPicks").append(b);
  }

  // headlines
  const firstPage = () => { state.hlPage = 0; renderHeadlines(); };
  const turnPage = (step) => { state.hlPage += step; renderHeadlines(); window.scrollTo({ top: 0, behavior: "smooth" }); };
  $("#hlQ").oninput = debounce(firstPage);
  $("#hlSrc").onchange = firstPage;
  $("#hlPrev").onclick = () => turnPage(-1);
  $("#hlNext").onclick = () => turnPage(1);

  // theme: charts read their colours from CSS variables, so redraw them after a switch
  $("#themeBtn").onclick = () => {
    const dark = getComputedStyle(document.querySelector(".viz-root")).colorScheme === "dark";
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    localStorage.setItem("theme", document.documentElement.dataset.theme);
    Charts.redrawAll();
  };
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => Charts.redrawAll());

  // first render: every tab starts dirty; open the tab named in the URL (#trends etc.)
  legends();
  Object.keys(RENDER).forEach((t) => state.dirty.add(t));
  const start = location.hash.slice(1);
  show(RENDER[start] ? start : "overview");
  if (state.tab !== "overview") renderOverview().then(() => state.dirty.delete("overview"));
}

init().catch((e) => { document.querySelector("main").innerHTML = `<p class="error">Could not load data: ${e.message}. Is app.py running?</p>`; });
