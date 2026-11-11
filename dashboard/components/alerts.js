(function () {
  function buildAlerts(payload) {
    const alerts = [];
    (payload.theft?.records || []).forEach((record) => {
      alerts.push({
        severity: "Critical",
        category: "Suspected theft candidate",
        meter_id: record.meter_id,
        area: record.area,
        summary: `Investigation aid only · risk ${Number(record.risk_score || 0).toFixed(1)} | model probability ${Number(record.theft_probability || 0).toFixed(2)}`,
        timestamp: record.timestamp || "",
      });
    });
    (payload.anomalies?.records || []).forEach((record) => {
      alerts.push({
        severity: "High",
        category: "Anomaly Detected",
        meter_id: record.meter_id,
        area: record.area,
        summary: `Anomaly ${Number(record.anomaly_score || 0).toFixed(3)} | Status ${record.status}`,
        timestamp: record.timestamp || "",
      });
    });
    (payload.efficiency?.records || []).forEach((record) => {
      if (Number(record.wastage_flag || 0) !== 1) {
        return;
      }
      alerts.push({
        severity: "Medium",
        category: "Energy Wastage",
        meter_id: record.meter_id,
        area: record.area,
        summary: `Efficiency ${Number(record.efficiency_score || 0).toFixed(1)}% | Losses ${Number(record.estimated_losses_kwh || 0).toFixed(2)} kWh`,
        timestamp: record.timestamp || "",
      });
    });
    if (payload.drift?.drift_detected) {
      alerts.push({
        severity: "High",
        category: "Data Drift Detected",
        meter_id: "-",
        area: "System-wide",
        summary: `Concept shift ${Number(payload.drift.concept_drift?.prediction_rate_shift || 0).toFixed(3)}`,
        timestamp: payload.drift.generated_at || "",
      });
    }
    (payload.pole?.records || []).forEach((record) => {
      if (Number(record.tamper_flag || 0) !== 1) {
        return;
      }
      alerts.push({
        severity: "Critical",
        category: "Pole Tamper Alert",
        meter_id: record.pole_id,
        area: record.area,
        summary: `Gap ${Number(record.energy_gap || 0).toFixed(2)} kWh | Probability ${Number(record.tamper_probability || 0).toFixed(2)}`,
        timestamp: record.timestamp || "",
      });
    });
    return alerts.sort((left, right) => String(right.timestamp).localeCompare(String(left.timestamp)));
  }

  function renderAlerts(containerId, alerts) {
    SmartGridDashboard.renderList(
      containerId,
      alerts,
      (alert) => `
        <article class="alert-item ${alert.severity.toLowerCase()}">
          <div class="alert-meta">
            <span class="severity-pill ${alert.severity.toLowerCase()}">${alert.severity}</span>
            <span>${alert.category}</span>
          </div>
          <strong>${alert.meter_id} | ${alert.area}</strong>
          <p>${alert.summary}</p>
          <small>${alert.timestamp ? alert.timestamp.replace("T", " ").slice(0, 19) : "Live alert"}</small>
        </article>
      `,
      "No active alerts."
    );
  }

  window.SmartGridAlerts = {
    buildAlerts,
    renderAlerts,
  };
})();
