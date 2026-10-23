if (document.getElementById("login-form")) {
  function getLoginPageErrorMessage(err) {
    const fromResponse =
      typeof extractApiErrorMessage === "function"
        ? extractApiErrorMessage(err?.responseData, "")
        : "";
    const fromError = typeof err?.message === "string" ? err.message.trim() : "";

    if (fromResponse) return fromResponse;
    if (fromError && !/^API error \d+$/i.test(fromError)) return fromError;
    return "Something went wrong. Please try again.";
  }

  document.getElementById("login-form").addEventListener("submit", async function(e) {
    e.preventDefault();

    const email = e.target.email.value;
    const password = e.target.password.value;

    try {
      const data = await apiPost("/api/auth/login/", { email, password });
      alert("Login successful!");
      localStorage.setItem("access", data.access);
      localStorage.setItem("refresh", data.refresh);
      window.location.href = "/daily-plan/";
    } catch (err) {
      document.getElementById("login-error").innerText =
        getLoginPageErrorMessage(err);
    }
  });
}
