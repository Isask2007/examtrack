/* Chart.js data binding: every canvas declares its JSON endpoint via data-chart-url */
(function () {
  "use strict";

  const PALETTE = ["#4f46e5", "#0ea5a4", "#f59e0b", "#8b5cf6", "#f43f5e", "#14b8a6"];

  function baseOptions(type) {
    if (type === "doughnut" || type === "pie") {
      return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12, padding: 14, font: { size: 11 } } },
        },
        cutout: type === "doughnut" ? "62%" : null,
      };
    }

    const isLine = type === "line";
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "top", labels: { boxWidth: 12, padding: 14, font: { size: 11 } } },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { size: 10 }, maxRotation: 35, minRotation: 0 },
        },
        y: {
          beginAtZero: true,
          suggestedMax: 100,
          grid: { color: "#eef2f7" },
          ticks: { font: { size: 10 }, callback: function (value) { return value + "%"; } },
        },
      },
      elements: {
        line: { tension: isLine ? 0.35 : 0 },
        point: { radius: isLine ? 3 : 0, hoverRadius: 5 },
      },
    };
  }

  function renderChart(canvas, payload) {
    const type = canvas.dataset.chartType || "bar";
    const datasets = (payload.datasets || []).map(function (dataset, index) {
      return Object.assign(
        {
          backgroundColor: dataset.backgroundColor || PALETTE[index % PALETTE.length],
          borderColor: dataset.borderColor || PALETTE[index % PALETTE.length],
          borderWidth: dataset.borderWidth !== undefined ? dataset.borderWidth : 1,
        },
        dataset
      );
    });

    new window.Chart(canvas, {
      type: type,
      data: { labels: payload.labels || [], datasets: datasets },
      options: baseOptions(type),
    });
  }

  function showFallback(canvas, message) {
    const wrapper = document.createElement("div");
    wrapper.className = "text-muted small py-4 text-center";
    wrapper.textContent = message;
    canvas.replaceWith(wrapper);
  }

  document.addEventListener("DOMContentLoaded", function () {
    const canvases = document.querySelectorAll("canvas[data-chart-url]");
    if (!canvases.length) return;
    if (!window.Chart) {
      canvases.forEach(function (canvas) {
        showFallback(canvas, "Chart library unavailable. Check your internet connection for the Chart.js CDN.");
      });
      return;
    }

    canvases.forEach(function (canvas) {
      fetch(canvas.dataset.chartUrl, { credentials: "same-origin" })
        .then(function (response) {
          if (!response.ok) throw new Error("Chart request failed: " + response.status);
          return response.json();
        })
        .then(function (payload) { renderChart(canvas, payload); })
        .catch(function () { showFallback(canvas, "Could not load chart data."); });
    });
  });
})();
