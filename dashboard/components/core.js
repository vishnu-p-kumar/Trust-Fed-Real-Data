(function () {
  const STORAGE_KEYS = {
    apiBase: "smartgrid_api_base",
    theme: "smartgrid_theme",
  };

  function readStorage(key, fallback) {
    try {
      return localStorage.getItem(key) || fallback;
    } catch (error) {
      return fallback;
    }
  }

  function getApiBase() {
    const configured = readStorage(STORAGE_KEYS.apiBase, "");
    const defaultBase = new URL(window.location.origin);
    if (window.location.pathname.startsWith("/dashboard/")) return window.location.origin;
    if (defaultBase.port === "8081") defaultBase.port = "8001";
    else if (defaultBase.port === "8080") defaultBase.port = "8000";
    const legacyDefault = configured === "http://127.0.0.1:8000";
    return (configured && !legacyDefault ? configured : defaultBase.origin).replace(/\/$/, "");
  }

  function getTheme() {
    return readStorage(STORAGE_KEYS.theme, "dark");
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document.body.setAttribute("data-theme", theme);
  }

  async function fetchJson(path) {
    const response = await fetch(`${getApiBase()}${path}`, { cache: "no-store", credentials: "include" });
    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      try {
        const payload = await response.json();
        if (typeof payload.detail === "string") detail = payload.detail;
      } catch (error) {
        // Preserve the HTTP status for non-JSON error responses.
      }
      throw new Error(`${path}: ${detail}`);
    }
    return response.json();
  }

  function formatNumber(value, digits) {
    const numeric = Number(value || 0);
    return numeric.toLocaleString(undefined, {
      minimumFractionDigits: digits || 0,
      maximumFractionDigits: digits || 0,
    });
  }

  function formatDecimal(value, digits) {
    return Number(value || 0).toFixed(digits || 2);
  }

  function formatKwh(value, digits) {
    return `${formatDecimal(value, digits || 2)} kWh`;
  }

  function renderList(containerId, items, formatter, emptyMessage) {
    const container = document.getElementById(containerId);
    if (!container) {
      return;
    }
    if (!items || !items.length) {
      container.innerHTML = `<div class="empty-state">${emptyMessage || "No records available."}</div>`;
      return;
    }
    container.innerHTML = items.map(formatter).join("");
  }

  function statusBadge(status) {
    if (status === "Electricity Theft") {
      return "status-danger";
    }
    if (status === "Anomaly") {
      return "status-warning";
    }
    if (status === "Power Wastage") {
      return "status-success";
    }
    return "status-neutral";
  }

  function sendParentMessage(payload) {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage(payload, "*");
    }
  }

  function connectWebSocket(onPayload) {
    let socket;
    let reconnectHandle;

    function open() {
      socket = new WebSocket(`${getApiBase().replace(/^http/, "ws")}/ws/live`);
      socket.onmessage = (event) => {
        try {
          onPayload(JSON.parse(event.data));
        } catch (error) {
          return;
        }
      };
      socket.onclose = () => {
        reconnectHandle = window.setTimeout(open, 4000);
      };
    }

    open();
    return {
      close() {
        window.clearTimeout(reconnectHandle);
        if (socket) {
          socket.close();
        }
      },
    };
  }

  function setupSection(options) {
    const refresh = typeof options.refresh === "function" ? options.refresh : null;
    const socketHandle = typeof options.socket === "function" ? connectWebSocket(options.socket) : null;
    let refreshing = false;

    function notifyVisible() {
      window.setTimeout(() => {
        window.dispatchEvent(new Event("resize"));
      }, 50);
    }

    async function runRefresh() {
      if (!refresh || refreshing) {
        return;
      }
      refreshing = true;
      try {
        await refresh();
        sendParentMessage({ type: "section-status", text: `Updated ${new Date().toLocaleTimeString()}` });
      } catch (error) {
        console.error(error);
        sendParentMessage({ type: "section-status", text: `Refresh failed at ${new Date().toLocaleTimeString()}` });
      } finally {
        refreshing = false;
      }
    }

    applyTheme(getTheme());

    window.addEventListener("message", (event) => {
      const message = event.data || {};
      if (message.type === "dashboard-config") {
        if (message.theme) {
          applyTheme(message.theme);
        }
        if (message.apiBase) {
          runRefresh();
        }
      }
      if (message.type === "theme-change" && message.theme) {
        applyTheme(message.theme);
      }
      if (message.type === "dashboard-refresh") {
        runRefresh();
      }
      if (message.type === "dashboard-activated") {
        runRefresh();
        notifyVisible();
      }
    });

    if (refresh) {
      runRefresh();
      window.setInterval(runRefresh, options.interval || 3000);
    }

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        notifyVisible();
      }
    });

    window.addEventListener("beforeunload", () => {
      if (socketHandle) {
        socketHandle.close();
      }
    });

    sendParentMessage({ type: "section-ready", section: options.name || document.title });
  }

  window.SmartGridDashboard = {
    applyTheme,
    connectWebSocket,
    fetchJson,
    formatDecimal,
    formatKwh,
    formatNumber,
    getApiBase,
    getTheme,
    renderList,
    sendParentMessage,
    setupSection,
    statusBadge,
  };
})();
