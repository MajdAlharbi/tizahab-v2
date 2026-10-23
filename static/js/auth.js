const signupForm = document.getElementById("signup-form");

if (signupForm) {
  const errorBox = document.getElementById("signup-error");

  function getSignupPageErrorMessage(err) {
    const fromResponse =
      typeof extractApiErrorMessage === "function"
        ? extractApiErrorMessage(err?.responseData, "")
        : "";
    const fromError = typeof err?.message === "string" ? err.message.trim() : "";

    if (fromResponse) return fromResponse;
    if (fromError && !/^API error \d+$/i.test(fromError)) return fromError;
    return "Something went wrong. Please try again.";
  }

  function setSignupLoading(loading) {
    const btn      = document.getElementById("signup-btn");
    const btnText  = document.getElementById("signup-btn-text");
    const btnSpinner = document.getElementById("signup-btn-spinner");
    if (btn) btn.disabled = loading;
    if (btnText)    btnText.classList.toggle("hidden", loading);
    if (btnSpinner) btnSpinner.classList.toggle("hidden", !loading);
  }

  function showSignupError(message) {
    if (!errorBox) return;
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
  }

  signupForm.addEventListener("submit", async function (e) {
    e.preventDefault();

    errorBox?.classList.add("hidden");
    if (errorBox) errorBox.textContent = "";

    if (!signupForm.reportValidity()) return;

    if (typeof window.apiPost !== "function") {
      showSignupError("Signup is temporarily unavailable. Please reload the page.");
      return;
    }

    const fullName = (
      document.getElementById("signup-name") ??
      signupForm.querySelector("input[name='full_name']")
    )?.value ?? "";

    const email = (
      document.getElementById("signup-email") ??
      signupForm.querySelector("input[name='email']")
    )?.value ?? "";

    const password = (
      document.getElementById("signup-password") ??
      signupForm.querySelector("input[name='password']")
    )?.value ?? "";

    const password2 = (
      document.getElementById("signup-confirm") ??
      signupForm.querySelector("input[name='password2']")
    )?.value ?? "";

    if (password.length < 8) {
      showSignupError(window.authT?.("passwordHelp", "Password must be at least 8 characters.") || "Password must be at least 8 characters.");
      return;
    }

    if (password !== password2) {
      showSignupError(window.authT?.("passwordMismatch", "Passwords do not match.") || "Passwords do not match.");
      return;
    }

    setSignupLoading(true);

    try {
      const data = await window.apiPost("/api/auth/signup/", {
        full_name: fullName,
        email,
        password,
        password2,
      });

      localStorage.setItem("access", data.access);
      localStorage.setItem("refresh", data.refresh);
      const next = window.safeInternalRedirect(new URLSearchParams(location.search).get("next"));
      window.location.href = next || (document.documentElement.lang === "ar" ? "/ar" : "") + "/trips/";
    } catch (err) {
      showSignupError(getSignupPageErrorMessage(err));
      setSignupLoading(false);
    }
  });
}
