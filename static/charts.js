/* Thin layer over Chart.js for the dashboard: shared theme, paper colours, tooltips,
   and re-drawing every chart when the light/dark theme changes.
   Each chart lives in a <div id=...>; drawing into the same id replaces the old chart. */
const Charts = (() => {
  const live = new Map(); // element id -> { chart, draw }; draw(canvas, theme) is kept so redrawAll() can re-run it

  const css = (name) => getComputedStyle(document.querySelector(".viz-root")).getPropertyValue(name).trim();
  const paperColor = (p) => css(p === "Jansatta" ? "--ja" : "--ie");
  const fmt = (v) => (v == null ? "–" : (+v).toFixed(1));

  // Colours are read from the CSS variables each time, so they follow the current theme.
  function theme() {
    return {
      text: css("--text-secondary"), muted: css("--text-muted"), grid: css("--grid"),
      surface: css("--surface-1"), ink: css("--text-primary"), tipBg: css("--tip-bg"),
      font: getComputedStyle(document.body).fontFamily,
    };
  }

  /* ---------- plugins ---------- */
  // Vertical dashed line at the event day, with its name.
  const eventLine = {
    id: "eventLine",
    afterDatasetsDraw(chart, _a, opts) {
      if (!opts || !opts.label) return;
      const x = chart.scales.x.getPixelForValue(chart.data.labels.indexOf(opts.label));
      if (x == null || isNaN(x)) return;
      const { top, bottom } = chart.chartArea, ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = opts.color; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = opts.color; ctx.font = `600 11px ${opts.font}`;
      ctx.textAlign = "left"; ctx.fillText(opts.text || "event", x + 6, top + 12);
      ctx.restore();
    },
  };
  // Vertical line under the hovered point on line charts.
  const crosshair = {
    id: "crosshair",
    beforeDatasetsDraw(chart, _a, opts) {
      const act = chart.tooltip && chart.tooltip.getActiveElements();
      if (!opts || !opts.on || !act || !act.length) return;
      const x = act[0].element.x, { top, bottom } = chart.chartArea, ctx = chart.ctx;
      ctx.save(); ctx.strokeStyle = opts.color; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke(); ctx.restore();
    },
  };
  Chart.register(eventLine, crosshair);

  /* ---------- shared options ---------- */
  // Options every chart shares. `label` is the tooltip line, overridable per chart type.
  function base(t, unit, label) {
    Chart.defaults.font.family = t.font;
    Chart.defaults.color = t.text;
    return {
      responsive: true, maintainAspectRatio: false, animation: { duration: 350 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: t.tipBg, titleColor: t.ink, bodyColor: t.ink, borderColor: t.grid, borderWidth: 1,
          padding: 10, cornerRadius: 8, boxPadding: 4, usePointStyle: true,
          titleFont: { weight: "600" },
          callbacks: { label: label || ((c) => ` ${c.dataset.label}: ${fmt(c.parsed.x)}${unit}`) },
        },
      },
    };
  }

  // Replace whatever chart is in `id` with a fresh canvas drawn by draw(canvas, theme).
  function mount(id, draw) {
    if (live.has(id)) live.get(id).chart.destroy();
    const host = document.getElementById(id);
    host.innerHTML = "";
    const canvas = document.createElement("canvas");
    host.appendChild(canvas);
    const chart = draw(canvas, theme());
    live.set(id, { chart, draw });
    return chart;
  }

  /* ---------- chart types ---------- */
  /** Grouped horizontal bars, one colour per paper. data = { paper: [values aligned to labels] }.
      onPick(label) is called when a bar is clicked. */
  function bars(id, { labels, data, height, onPick }) {
    if (height) document.getElementById(id).style.height = height + "px";
    return mount(id, (cv, t) => new Chart(cv, {
      type: "bar",
      data: {
        labels,
        datasets: Object.entries(data).map(([p, vals]) => ({
          label: p, data: vals, backgroundColor: paperColor(p), hoverBackgroundColor: paperColor(p),
          borderRadius: 4, borderSkipped: "start", barPercentage: 0.86, categoryPercentage: 0.78,
        })),
      },
      options: {
        ...base(t, "%"), indexAxis: "y",
        interaction: { mode: "index", intersect: false, axis: "y" },
        ...(onPick && {
          onClick: (_e, els) => { if (els.length) onPick(labels[els[0].index]); },
          onHover: (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
        }),
        scales: {
          x: { beginAtZero: true, grid: { color: t.grid }, border: { display: false }, ticks: { callback: (v) => v + "%" } },
          y: { grid: { display: false }, border: { color: t.grid }, ticks: { color: t.ink, autoSkip: false } },
        },
      },
    }));
  }

  /** Diverging bars: positive = Jansatta covers it more, negative = Indian Express covers it more. */
  function diverging(id, { labels, values }) {
    const label = (c) => ` ${c.parsed.x >= 0 ? "Jansatta" : "Indian Express"} +${Math.abs(c.parsed.x).toFixed(1)} pts`;
    return mount(id, (cv, t) => new Chart(cv, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Gap", data: values, borderRadius: 4, borderSkipped: "start", barPercentage: 0.7,
          backgroundColor: values.map((v) => paperColor(v >= 0 ? "Jansatta" : "Indian Express")),
        }],
      },
      options: {
        ...base(t, " pts", label), indexAxis: "y",
        scales: {
          x: { grid: { color: (c) => (c.tick.value === 0 ? t.muted : t.grid) }, border: { display: false },
            ticks: { callback: (v) => (v > 0 ? "+" : "") + v } },
          y: { grid: { display: false }, border: { display: false }, ticks: { color: t.ink, autoSkip: false } },
        },
      },
    }));
  }

  /** Lines over time. series = { paper: [{x, y, n}] }. event = {date, text} draws a marker; xfmt formats dates. */
  function line(id, { series, event, xfmt = (s) => s }) {
    // x axis = every date that appears in any series (plus the event day, so its marker always has a spot)
    const labels = [...new Set([...Object.values(series).flat().map((d) => d.x), ...(event ? [event.date] : [])])].sort();
    const dense = labels.length > 40;
    const label = (c) => ` ${c.dataset.label}: ${fmt(c.parsed.y)}%  (${c.raw.n} headlines)`;
    return mount(id, (cv, t) => {
      const opts = base(t, "%", label);
      opts.plugins.tooltip.callbacks.title = (items) => xfmt(items[0].label, true);
      opts.plugins.crosshair = { on: true, color: t.muted };
      opts.plugins.eventLine = event ? { label: event.date, text: event.text, color: t.muted, font: t.font } : {};
      return new Chart(cv, {
        type: "line",
        data: {
          labels,
          datasets: Object.entries(series).map(([p, pts]) => ({
            label: p, data: pts, borderColor: paperColor(p), backgroundColor: paperColor(p),
            borderWidth: 2, cubicInterpolationMode: "monotone", spanGaps: false,
            pointRadius: dense ? 0 : 4, pointHoverRadius: 6,
            pointBorderColor: t.surface, pointBorderWidth: 2, pointHoverBorderColor: t.surface,
          })),
        },
        options: {
          ...opts,
          interaction: { mode: "index", intersect: false },
          scales: {
            y: { beginAtZero: true, grid: { color: t.grid }, border: { display: false },
              ticks: { callback: (v) => v + "%", maxTicksLimit: 6 } },
            x: { grid: { display: false }, border: { color: t.grid },
              ticks: { callback(v) { return xfmt(this.getLabelForValue(v)); }, maxRotation: 0, autoSkipPadding: 14 } },
          },
        },
      });
    });
  }

  // After a theme change: draw every chart again so it picks up the new colours.
  function redrawAll() {
    for (const [id, { draw }] of live) {
      if (document.getElementById(id)) mount(id, draw);
      else { live.get(id).chart.destroy(); live.delete(id); } // e.g. an unticked Trends topic
    }
  }

  return { bars, diverging, line, redrawAll };
})();
