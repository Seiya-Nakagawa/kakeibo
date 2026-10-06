// Chart.js をテーマ（CSS変数）とスマホ幅に合わせて生成する共通処理。

function kakeiboChartTheme() {
  const style = getComputedStyle(document.documentElement);
  const read = (name) => style.getPropertyValue(name).trim();
  const accent = read("--accent");
  const income = read("--income");
  const expense = read("--expense");
  return {
    accent,
    accentSoft: read("--accent-soft"),
    income,
    expense,
    surface: read("--surface"),
    ink: read("--ink"),
    muted: read("--muted"),
    line: read("--line"),
    // カテゴリ構成比用。隣り合う色が区別できる並びにする
    series: [accent, "#e0a42f", expense, income, "#8b6bd1", "#5aa86a", "#d46aa3", "#6f8a96"],
  };
}

function kakeiboChart(canvasId, type, data) {
  const theme = kakeiboChartTheme();
  const isCircular = type === "pie" || type === "doughnut";
  const yenFormat = (value) => `${Number(value).toLocaleString("ja-JP")}円`;

  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = theme.muted;

  return new Chart(document.getElementById(canvasId), {
    type,
    data,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      elements: { line: { tension: 0.3, borderWidth: 2 }, point: { radius: 2, hoverRadius: 5 } },
      plugins: {
        legend: {
          display: isCircular || data.datasets.length > 1,
          position: "bottom",
          labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true },
        },
        tooltip: {
          callbacks: {
            label: (context) => {
              const value = isCircular ? context.parsed : context.parsed.y;
              const prefix = context.dataset.label ? `${context.dataset.label}: ` : `${context.label}: `;
              return prefix + yenFormat(value);
            },
          },
        },
      },
      scales: isCircular
        ? {}
        : {
            x: { grid: { display: false }, ticks: {
                maxRotation: 0,
                autoSkip: true,
                maxTicksLimit: 5,
                // "2026-03" を "26/3" に短縮してスマホ幅でも重ならないようにする
                callback(value) {
                  const label = String(this.getLabelForValue(value));
                  const match = label.match(/^(\d{4})-(\d{2})$/);
                  return match ? `${match[1].slice(2)}/${Number(match[2])}` : label;
                },
              },
            },
            y: {
              grid: { color: theme.line },
              border: { display: false },
              ticks: {
                maxTicksLimit: 5,
                // 縦軸は「万」単位に省略して幅を節約する
                callback: (value) => (Math.abs(value) >= 10000 ? `${value / 10000}万` : value),
              },
            },
          },
    },
  });
}
