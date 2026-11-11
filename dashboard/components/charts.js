(function () {
  const chartStore = {};

  function palette() {
    const styles = getComputedStyle(document.documentElement);
    const ink = styles.getPropertyValue("--ink").trim() || "#d8e2ef";
    const muted = styles.getPropertyValue("--muted").trim() || "#93a4bb";
    const border = styles.getPropertyValue("--border").trim() || "rgba(148, 163, 184, 0.16)";
    return { ink, muted, border };
  }

  function renderChart(containerId, type, labels, datasets, options) {
    if (typeof Chart === "undefined") {
      return null;
    }
    const canvas = document.getElementById(containerId);
    if (!canvas) {
      return null;
    }

    const colors = palette();
    const mergedOptions = Object.assign(
      {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 700 },
        plugins: { legend: { labels: { color: colors.ink } } },
        scales: {
          x: { ticks: { color: colors.muted }, grid: { color: colors.border } },
          y: { ticks: { color: colors.muted }, grid: { color: colors.border } },
        },
      },
      options || {}
    );

    if (chartStore[containerId]) {
      chartStore[containerId].data.labels = labels;
      chartStore[containerId].data.datasets = datasets;
      chartStore[containerId].options = mergedOptions;
      chartStore[containerId].update();
      return chartStore[containerId];
    }

    chartStore[containerId] = new Chart(canvas, {
      type,
      data: { labels, datasets },
      options: mergedOptions,
    });
    return chartStore[containerId];
  }

  function renderHistogram(containerId, values, label, color) {
    const numeric = (values || []).map((value) => Number(value || 0));
    if (!numeric.length) {
      return renderChart(containerId, "bar", ["No data"], [{ label: label || "Count", data: [0], backgroundColor: color || "#14b8a6" }]);
    }

    const minimum = Math.min(...numeric);
    const maximum = Math.max(...numeric);
    const bucketCount = Math.min(8, Math.max(4, Math.ceil(Math.sqrt(numeric.length))));
    const span = maximum === minimum ? 1 : (maximum - minimum) / bucketCount;
    const buckets = Array.from({ length: bucketCount }, (_, index) => ({
      label: `${(minimum + index * span).toFixed(2)} - ${(minimum + (index + 1) * span).toFixed(2)}`,
      count: 0,
    }));

    numeric.forEach((value) => {
      const index = maximum === minimum ? 0 : Math.min(bucketCount - 1, Math.floor((value - minimum) / span));
      buckets[index].count += 1;
    });

    return renderChart(
      containerId,
      "bar",
      buckets.map((bucket) => bucket.label),
      [{ label: label || "Distribution", data: buckets.map((bucket) => bucket.count), backgroundColor: color || "rgba(20, 184, 166, 0.75)", borderRadius: 12 }]
    );
  }

  function renderPlotly(containerId, traces, layout) {
    if (typeof Plotly === "undefined") {
      return;
    }
    const colors = palette();
    Plotly.react(
      containerId,
      traces,
      Object.assign(
        {
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          margin: { t: 20, r: 12, b: 42, l: 46 },
          font: { family: "Space Grotesk, sans-serif", color: colors.ink },
          xaxis: { gridcolor: colors.border, zerolinecolor: colors.border },
          yaxis: { gridcolor: colors.border, zerolinecolor: colors.border },
        },
        layout || {}
      ),
      { responsive: true }
    );
  }

  window.SmartGridCharts = {
    renderChart,
    renderHistogram,
    renderPlotly,
  };
})();
