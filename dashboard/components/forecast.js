(function () {
  function renderForecastSummary(prefix, forecast) {
    const targets = {
      hour: document.getElementById(`${prefix}ForecastHour`),
      day: document.getElementById(`${prefix}ForecastDay`),
      week: document.getElementById(`${prefix}ForecastWeek`),
    };
    if (targets.hour) {
      targets.hour.textContent = SmartGridDashboard.formatKwh(forecast.ensemble?.next_hour || forecast.next_hour || 0, 2);
    }
    if (targets.day) {
      targets.day.textContent = SmartGridDashboard.formatKwh(forecast.ensemble?.next_day || forecast.next_day || 0, 2);
    }
    if (targets.week) {
      targets.week.textContent = SmartGridDashboard.formatKwh(forecast.ensemble?.next_week || forecast.next_week || 0, 2);
    }
  }

  function renderForecastComparison(containerId, forecast) {
    const areaForecasts = forecast.area_forecasts || [];
    if (areaForecasts.length && window.Plotly) {
      Plotly.react(
        containerId,
        [{
          x: areaForecasts.map((item) => item.area),
          y: areaForecasts.map((item) => Number(item.predicted_consumption_kwh || 0)),
          type: "bar",
          marker: { color: "#14b8a6" },
          name: "Next-day CEEW forecast",
        }],
        {
          margin: { l: 55, r: 20, t: 20, b: 75 },
          xaxis: { title: "Bengaluru zone", gridcolor: "rgba(147, 164, 187, 0.12)" },
          yaxis: { title: "Forecast kWh", gridcolor: "rgba(147, 164, 187, 0.12)" },
          showlegend: false,
        },
        { responsive: true, displayModeBar: false }
      );
      return;
    }
    const lstmSeries = forecast.comparison_series?.lstm || forecast.lstm?.series || [];
    const transformerSeries = forecast.comparison_series?.transformer || forecast.transformer?.series || [];
    SmartGridCharts.renderPlotly(
      containerId,
      [
        { x: lstmSeries.map((item) => item.step), y: lstmSeries.map((item) => item.forecast_kwh), type: "scatter", mode: "lines", name: "LSTM", line: { color: "#14b8a6", width: 3 } },
        { x: transformerSeries.map((item) => item.step), y: transformerSeries.map((item) => item.forecast_kwh), type: "scatter", mode: "lines", name: "Transformer", line: { color: "#f97316", width: 3, dash: "dash" } },
      ],
      {
        xaxis: { title: "Forecast Step", gridcolor: "rgba(147, 164, 187, 0.12)" },
        yaxis: { title: "Forecast kWh", gridcolor: "rgba(147, 164, 187, 0.12)" },
        legend: { orientation: "h" },
      }
    );
  }

  window.SmartGridForecast = {
    renderForecastComparison,
    renderForecastSummary,
  };
})();
