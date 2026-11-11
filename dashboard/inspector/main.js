(function () {
  const configuredApi = localStorage.getItem("smartgrid_api_base") || "";
  const defaultApi = new URL(window.location.origin);
  if (window.location.pathname.startsWith("/dashboard/")) defaultApi.port = window.location.port;
  else if (defaultApi.port === "8081") defaultApi.port = "8001";
  else if (defaultApi.port === "8080") defaultApi.port = "8000";
  const apiBase = (configuredApi && configuredApi !== "http://127.0.0.1:8000" ? configuredApi : defaultApi.origin).replace(/\/$/, "");
  let currentSession = null;

  function badgeClass(level) {
    const value = String(level || "").toUpperCase();
    if (value === "HIGH") return "status-danger";
    if (value === "MEDIUM" || value === "ASSIGNED") return "status-warning";
    if (value === "COMPLETED") return "status-success";
    return "status-neutral";
  }

  async function fetchSession() {
    const response = await fetch(`${apiBase}/auth/session`, { credentials: "include" });
    if (!response.ok) {
      throw new Error("No session");
    }
    return response.json();
  }

  async function fetchDashboard() {
    const params = new URLSearchParams();
    const detectionClass = document.getElementById("classFilter").value;
    const risk = document.getElementById("riskFilter").value;
    const location = document.getElementById("locationFilter").value;
    const status = document.getElementById("statusFilter").value;
    const date = document.getElementById("dateFilter").value;
    if (detectionClass) params.set("detection_class", detectionClass);
    if (risk) params.set("risk_level", risk);
    if (location) params.set("location", location);
    if (status) params.set("status", status);
    if (date) params.set("date", date);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const response = await fetch(`${apiBase}/api/inspector/dashboard${suffix}`, { credentials: "include" });
    if (!response.ok) {
      throw new Error("Unable to load inspector dashboard");
    }
    return response.json();
  }

  function renderSummary(summary) {
    const cards = [
      ["Total Theft Cases", summary.total_theft_cases || 0, "Live suspicious records ready for review."],
      ["Total Anomaly Cases", summary.total_anomaly_cases || 0, "Anomaly detections available for inspection."],
      ["Total Pole Tamper", summary.total_pole_tamper || 0, "Pole tamper alerts in your assigned area."],
      ["Pending Inspections", summary.pending_inspections || 0, "Total theft and anomaly cases awaiting inspection."],
      ["Completed Inspections", summary.completed_inspections || 0, "Tasks closed with field remarks."],
      ["High Risk Cases", summary.high_risk_cases || 0, "Anomaly score greater than 0.9."],
    ];
    document.getElementById("summaryCards").innerHTML = cards
      .map(
        ([label, value, meta]) => `
          <article class="kpi-card glass-card">
            <span class="kpi-label">${label}</span>
            <strong class="kpi-value">${value}</strong>
            <p class="kpi-meta mb-0">${meta}</p>
          </article>
        `,
      )
      .join("");
  }

  function renderPoleTampers(records) {
    const body = document.getElementById("poleTamperTableBody");
    if (!records.length) {
      body.innerHTML = '<tr><td colspan="6"><div class="empty-inline">No pole tamper alerts in the assigned area.</div></td></tr>';
      return;
    }
    body.innerHTML = records
      .map(
        (item) => `
          <tr>
            <td>${item.pole_id || "-"}</td>
            <td>${item.area || "-"}</td>
            <td>${item.event_type || "-"}</td>
            <td>${Number(item.tamper_probability || 0).toFixed(4)}</td>
            <td>${Number(item.energy_gap || 0).toFixed(3)}</td>
            <td>${(item.timestamp || "").replace("T", " ").slice(0, 19) || "-"}</td>
          </tr>
        `,
      )
      .join("");
  }

  function populateFilterOptions(elementId, values, placeholder) {
    const select = document.getElementById(elementId);
    const currentValue = select.value;
    select.innerHTML = `<option value="">${placeholder}</option>${(values || [])
      .map((item) => `<option value="${item}">${item}</option>`)
      .join("")}`;
    if ((values || []).includes(currentValue)) {
      select.value = currentValue;
    }
  }

  function renderCases(cases) {
    const body = document.getElementById("caseTableBody");
    if (!cases.length) {
      body.innerHTML = '<tr><td colspan="11"><div class="empty-inline">No suspected cases match the selected filters.</div></td></tr>';
      return;
    }
    body.innerHTML = cases
      .map(
        (item) => `
          <tr data-meter-id="${item.meter_id}">
            <td>${item.meter_id}</td>
            <td>${item.location || "-"}</td>
            <td>${item.consumption_pattern || "-"}</td>
            <td><span class="status-badge ${badgeClass(item.detection_category === "Theft" ? "HIGH" : "MEDIUM")}">${item.detection_category || "-"}</span></td>
            <td>${Number(item.anomaly_score || 0).toFixed(4)}</td>
            <td>${Number(item.theft_probability || 0).toFixed(4)}</td>
            <td><span class="status-badge ${badgeClass(item.risk_level)}">${item.risk_level || "LOW"}</span></td>
            <td>${(item.detection_time || "").replace("T", " ").slice(0, 19) || "-"}</td>
            <td><span class="status-badge ${badgeClass(item.status)}">${item.status || "Pending"}</span></td>
            <td><button class="table-action-button assign-case" data-meter-id="${item.meter_id}">Assign</button></td>
          </tr>
        `,
      )
      .join("");
  }

  function renderTasks(tasks) {
    const body = document.getElementById("taskTableBody");
    if (!tasks.length) {
      body.innerHTML = '<tr><td colspan="6"><div class="empty-inline">No tasks assigned yet.</div></td></tr>';
      return;
    }
    body.innerHTML = tasks
      .map(
        (task) => `
          <tr>
            <td>${task.meter_id || "-"}</td>
            <td>${task.location || "-"}</td>
            <td>${task.inspection_date || "-"}</td>
            <td>${task.inspection_time || "-"}</td>
            <td><span class="status-badge ${badgeClass(task.status)}">${task.status || "Pending"}</span></td>
            <td><button class="table-action-button complete-task" data-task-id="${task.task_id}">Complete</button></td>
          </tr>
        `,
      )
      .join("");
  }

  async function assignCase(meterId) {
    const inspectionDate = window.prompt("Inspection date (YYYY-MM-DD):", new Date().toISOString().slice(0, 10));
    if (!inspectionDate) return;
    const inspectionTime = window.prompt("Inspection time (e.g. 10:00 AM):", "10:00 AM");
    if (!inspectionTime) return;
    const response = await fetch(`${apiBase}/api/inspector/tasks/assign`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        meter_id: meterId,
        inspection_date: inspectionDate,
        inspection_time: inspectionTime,
      }),
    });
    if (!response.ok) {
      window.alert("Unable to assign inspection.");
      return;
    }
    await refresh();
  }

  async function completeTask(taskId) {
    const remarks = window.prompt("Inspection remarks:", "Site inspection completed.");
    if (remarks === null) return;
    const response = await fetch(`${apiBase}/api/inspector/tasks/${encodeURIComponent(taskId)}/complete`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ remarks }),
    });
    if (!response.ok) {
      window.alert("Unable to complete task.");
      return;
    }
    await refresh();
  }

  async function refresh() {
    const payload = await fetchDashboard();
    renderSummary(payload.summary || {});
    populateFilterOptions("classFilter", payload.filters?.detection_classes, "All Classes");
    populateFilterOptions("riskFilter", payload.filters?.risk_levels, "All Risk Levels");
    populateFilterOptions("locationFilter", payload.filters?.locations, "All Locations");
    populateFilterOptions("statusFilter", payload.filters?.statuses, "All Statuses");
    renderPoleTampers(payload.pole_tampers || []);
    renderCases(payload.cases || []);
    renderTasks(payload.tasks || []);
  }

  async function logout() {
    await fetch(`${apiBase}/auth/logout`, { method: "POST", credentials: "include" });
    window.location.href = `${apiBase}/login`;
  }

  async function init() {
    try {
      currentSession = await fetchSession();
      if (currentSession.role !== "inspector") {
        window.location.href = `${apiBase}${currentSession.role === "admin" ? "/admin" : "/login"}`;
        return;
      }
      const baseName = currentSession.name || currentSession.username || "Inspector";
      const assignedArea = currentSession.assigned_area ? ` | ${currentSession.assigned_area}` : "";
      document.getElementById("inspectorIdentity").textContent = `${baseName}${assignedArea}`;
      await refresh();
    } catch (error) {
      window.location.href = `${apiBase}/login`;
      return;
    }

    ["classFilter", "riskFilter", "locationFilter", "statusFilter", "dateFilter"].forEach((id) => {
      document.getElementById(id).addEventListener("change", refresh);
    });

    document.getElementById("refreshInspectorButton").addEventListener("click", refresh);
    document.getElementById("logoutInspectorButton").addEventListener("click", logout);
    document.getElementById("caseTableBody").addEventListener("click", (event) => {
      const assignButton = event.target.closest(".assign-case");
      if (assignButton) {
        assignCase(assignButton.dataset.meterId);
      }
    });
    document.getElementById("taskTableBody").addEventListener("click", (event) => {
      const button = event.target.closest(".complete-task");
      if (button) {
        completeTask(button.dataset.taskId);
      }
    });
  }

  init();
})();
