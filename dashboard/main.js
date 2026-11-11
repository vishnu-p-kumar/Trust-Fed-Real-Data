(function () {
  const DASHBOARD_ASSET_VERSION = "2026-11-02-map-tiles-no-notice-v1";
  const SECTIONS = {
    overview: { path: "./sections/overview.html", title: "Overview", subtitle: "System-wide KPIs, live demand, and smart-grid operational health." },
    live_monitoring: { path: "./sections/live_monitoring.html", title: "Live Monitoring", subtitle: "Realtime electricity usage, peak load shifts, and area demand trends." },
    theft_detection: { path: "./sections/theft_detection.html", title: "Electricity Theft Detection", subtitle: "High-risk meters, theft probabilities, and investigation priorities." },
    anomaly_detection: { path: "./sections/anomaly_detection.html", title: "Anomaly Detection", subtitle: "Isolation Forest anomaly surfaces, suspicious outliers, and score distributions." },
    demand_forecast: { path: "./sections/demand_forecast.html", title: "Demand Forecasting", subtitle: "LSTM and Transformer demand projections for the next hour, day, and week." },
    energy_efficiency: { path: "./sections/energy_efficiency.html", title: "Energy Efficiency Analytics", subtitle: "Efficiency scores, wastage exposure, and power-factor performance by area." },
    pole_monitoring: { path: "./sections/pole_monitoring.html", title: "Pole Monitoring", subtitle: "Pole energy balance, tamper probabilities, illegal connections, and transformer-to-pole mismatch tracking." },
    heatmap: { path: "./sections/heatmap.html", title: "Bengaluru Heatmap", subtitle: "Interactive theft and anomaly hotspots on a live geospatial control map." },
    weather_impact: { path: "./sections/weather_impact.html", title: "Weather Impact Analytics", subtitle: "Demand correlations against temperature, humidity, rainfall, and live weather shifts." },
    alerts: { path: "./sections/alerts.html", title: "Alert Center", subtitle: "Realtime alert streams for theft, anomalies, voltage irregularities, and drift events." },
    reports: { path: "./sections/reports.html", title: "Reports & Insights", subtitle: "Operational summaries, downloadable reports, and daily analytics intelligence." },
    federated_research: { path: "./sections/federated_research.html", title: "Federated Research", subtitle: "Run bounded local simulations and inspect measured client and model results." },
  };

  const STORAGE_KEYS = {
    apiBase: "smartgrid_api_base",
    theme: "smartgrid_theme",
    section: "smartgrid_current_section",
  };
  const frameRegistry = new Map();
  let activeSectionKey = null;

  function readStorage(key, fallback) {
    try {
      return localStorage.getItem(key) || fallback;
    } catch (error) {
      return fallback;
    }
  }

  function writeStorage(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (error) {
      return;
    }
  }

  function currentApiBase() {
    const configured = readStorage(STORAGE_KEYS.apiBase, "");
    const defaultBase = new URL(window.location.origin);
    if (window.location.pathname.startsWith("/dashboard/")) {
      return window.location.origin;
    }
    if (defaultBase.port === "8081") defaultBase.port = "8001";
    else if (defaultBase.port === "8080") defaultBase.port = "8000";
    const legacyDefault = configured === "http://127.0.0.1:8000";
    return (configured && !legacyDefault ? configured : defaultBase.origin).replace(/\/$/, "");
  }

  function currentTheme() {
    return readStorage(STORAGE_KEYS.theme, "dark");
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document.body.setAttribute("data-theme", theme);
    const toggle = document.getElementById("themeToggle");
    if (toggle) {
      toggle.innerHTML =
        theme === "dark"
          ? '<i class="bi bi-sun-fill"></i><span>Light Mode</span>'
          : '<i class="bi bi-moon-stars-fill"></i><span>Dark Mode</span>';
    }
  }

  function frameId(sectionKey) {
    return `sectionFrame-${sectionKey}`;
  }

  function frameShell() {
    return document.querySelector(".frame-shell");
  }

  function versionedPath(path) {
    const separator = path.includes("?") ? "&" : "?";
    return `${path}${separator}v=${encodeURIComponent(DASHBOARD_ASSET_VERSION)}`;
  }

  function activeFrame() {
    return activeSectionKey ? frameRegistry.get(activeSectionKey) || null : null;
  }

  function postToFrame(frame, message) {
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage(message, "*");
    }
  }

  function broadcastToFrame(message) {
    postToFrame(activeFrame(), message);
  }

  function broadcastToLoadedFrames(message) {
    frameRegistry.forEach((frame) => {
      postToFrame(frame, message);
    });
  }

  function ensureFrame(sectionKey) {
    const section = SECTIONS[sectionKey] || SECTIONS.overview;
    const resolvedPath = versionedPath(section.path);

    if (frameRegistry.has(sectionKey)) {
      const existingFrame = frameRegistry.get(sectionKey);
      if (existingFrame && existingFrame.dataset.sectionSrc !== resolvedPath) {
        existingFrame.dataset.sectionSrc = resolvedPath;
        existingFrame.src = resolvedPath;
      }
      return existingFrame;
    }

    const frame = document.createElement("iframe");
    frame.id = frameId(sectionKey);
    frame.className = "section-frame";
    frame.title = `${section.title} Section`;
    frame.src = resolvedPath;
    frame.dataset.sectionSrc = resolvedPath;
    frame.style.display = "none";
    frame.addEventListener("load", () => {
      sendConfigToFrame(frame);
    });
    frameShell().appendChild(frame);
    frameRegistry.set(sectionKey, frame);
    return frame;
  }

  function sendConfigToFrame(frame) {
    postToFrame(frame || activeFrame(), {
      type: "dashboard-config",
      apiBase: currentApiBase(),
      theme: currentTheme(),
    });
  }

  function setActiveNav(sectionKey) {
    document.querySelectorAll(".nav-pill").forEach((button) => {
      button.classList.toggle("active", button.dataset.section === sectionKey);
    });
  }

  function loadSection(sectionKey) {
    const section = SECTIONS[sectionKey] || SECTIONS.overview;
    document.getElementById("sectionTitle").textContent = section.title;
    document.getElementById("sectionSubtitle").textContent = section.subtitle;
    activeSectionKey = sectionKey;
    const frame = ensureFrame(sectionKey);
    const resolvedPath = versionedPath(section.path);
    if (frame.dataset.sectionSrc !== resolvedPath) {
      frame.dataset.sectionSrc = resolvedPath;
      frame.src = resolvedPath;
    }
    frameRegistry.forEach((frame, key) => {
      frame.style.display = key === sectionKey ? "block" : "none";
    });
    setActiveNav(sectionKey);
    writeStorage(STORAGE_KEYS.section, sectionKey);
    sendConfigToFrame();
    window.requestAnimationFrame(() => {
      postToFrame(frame, { type: "dashboard-activated", section: sectionKey });
    });
  }

  async function updateApiStatus() {
    const dot = document.getElementById("apiStatusDot");
    const text = document.getElementById("apiStatusText");
    const meta = document.getElementById("apiStatusMeta");
    try {
      const response = await fetch(`${currentApiBase()}/health`);
      if (!response.ok) {
        throw new Error("Health request failed.");
      }
      const payload = await response.json();
      dot.className = `status-dot ${payload.status === "ok" ? "online" : "degraded"}`;
      text.textContent = payload.status === "ok" ? "API online" : "API degraded";
      meta.textContent = payload.current_tick ? `Current tick ${payload.current_tick.replace("T", " ").slice(0, 19)}` : "Backend responding";
    } catch (error) {
      dot.className = "status-dot offline";
      text.textContent = "API unavailable";
      meta.textContent = "Check the FastAPI server and API base URL.";
    }
  }

  function init() {
    const apiBase = currentApiBase();
    document.getElementById("apiBase").value = apiBase;
    writeStorage(STORAGE_KEYS.apiBase, apiBase);
    applyTheme(currentTheme());

    document.querySelectorAll(".nav-pill").forEach((button) => {
      button.addEventListener("click", () => {
        if (!button.dataset.section) return;
        loadSection(button.dataset.section);
        if (window.innerWidth < 992) {
          document.getElementById("sidebar").classList.remove("open");
        }
      });
    });

    document.getElementById("apiBase").addEventListener("change", (event) => {
      writeStorage(STORAGE_KEYS.apiBase, event.target.value.trim());
      broadcastToLoadedFrames({
        type: "dashboard-config",
        apiBase: currentApiBase(),
        theme: currentTheme(),
      });
      updateApiStatus();
    });

    document.getElementById("refreshButton").addEventListener("click", () => {
      broadcastToFrame({ type: "dashboard-refresh" });
      updateApiStatus();
    });

    document.getElementById("themeToggle").addEventListener("click", () => {
      const nextTheme = currentTheme() === "dark" ? "light" : "dark";
      writeStorage(STORAGE_KEYS.theme, nextTheme);
      applyTheme(nextTheme);
      broadcastToLoadedFrames({ type: "theme-change", theme: nextTheme });
    });

    document.getElementById("sidebarToggle").addEventListener("click", () => {
      document.getElementById("sidebar").classList.toggle("open");
    });

    window.addEventListener("message", (event) => {
      const message = event.data || {};
      if (message.type === "section-ready") {
        sendConfigToFrame();
      }
      if (message.type === "section-status" && message.text) {
        document.getElementById("apiStatusMeta").textContent = message.text;
      }
    });

    const initialFrame = document.getElementById("sectionFrame");
    if (initialFrame) {
      initialFrame.remove();
    }

    loadSection(readStorage(STORAGE_KEYS.section, "overview"));
    updateApiStatus();
    setInterval(updateApiStatus, 10000);
  }

  init();
})();
