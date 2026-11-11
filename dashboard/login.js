(function () {
  const configuredApi = localStorage.getItem("smartgrid_api_base") || "";
  const defaultApi = new URL(window.location.origin);
  if (window.location.pathname.startsWith("/dashboard/")) defaultApi.port = window.location.port;
  else if (defaultApi.port === "8081") defaultApi.port = "8001";
  else if (defaultApi.port === "8080") defaultApi.port = "8000";
  const apiBase = (configuredApi && configuredApi !== "http://127.0.0.1:8000" ? configuredApi : defaultApi.origin).replace(/\/$/, "");

  async function checkExistingSession() {
    const response = await fetch(`${apiBase}/auth/session`, { credentials: "include" });
    if (!response.ok) {
      return null;
    }
    return response.json();
  }

  function showError(message) {
    const errorBox = document.getElementById("loginError");
    errorBox.textContent = message;
    errorBox.classList.add("visible");
  }

  function setSubmittingState(isSubmitting) {
    const submitButton = document.querySelector('#loginForm button[type="submit"]');
    if (!submitButton) {
      return;
    }
    submitButton.disabled = isSubmitting;
    submitButton.textContent = isSubmitting ? "Signing In..." : "Login";
  }

  async function init() {
    try {
      const session = await checkExistingSession();
      if (session?.authenticated) {
        const destinations = { admin: "/admin", inspector: "/inspector", client: "/client" };
        window.location.href = `${apiBase}${destinations[session.role] || "/login"}`;
        return;
      }
    } catch (error) {
      return;
    }

    document.getElementById("loginForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const formData = new FormData(form);
      const identifier = String(formData.get("identifier") || "").trim();
      const errorBox = document.getElementById("loginError");
      errorBox.classList.remove("visible");
      setSubmittingState(true);
      try {
        const response = await fetch(`${apiBase}/auth/login`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            identifier,
            password: formData.get("password"),
          }),
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({ detail: "Invalid login." }));
          showError(payload.detail || "Invalid login.");
          setSubmittingState(false);
          return;
        }
        const fallbackRedirect = identifier.includes("@") ? "/admin" : "/inspector";
        const payload = await response.clone().json().catch(() => ({}));
        window.location.replace(`${apiBase}${payload.redirect_to || fallbackRedirect}`);
      } catch (error) {
        showError("Unable to sign in right now.");
        setSubmittingState(false);
      }
    });
  }

  init();
})();
