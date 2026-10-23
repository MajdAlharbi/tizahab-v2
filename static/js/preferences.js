(function () {
  "use strict";

  // ── State ──────────────────────────────────────────────────
  let currentStep   = 1;
  let _transitioning = false;
  let _isSubmitting  = false;

  const formData = {
    interests:  new Set(),
    startDate:  "",
    endDate:    "",
    budgetMin:  0,
    budgetMax:  4000,
    minRating:  null,
    language:   document.documentElement?.lang === "ar" ? "ar" : "en",
  };

  // ── Progress ───────────────────────────────────────────────
  function updateProgress() {
    const label = document.getElementById("stepLabel");
    const number=[1,2,4,5].indexOf(currentStep)+1;
    if (label) label.textContent = document.documentElement?.lang === "ar" ? `الخطوة ${number} من 4` : `Step ${number} of 4`;

    const dots = document.querySelectorAll("#progressDots span");
    dots.forEach((dot, i) => {
      dot.hidden = i === 2;
      const active = i === currentStep - 1;
      const done   = i < currentStep - 1;
      dot.style.background = (active || done) ? "var(--tz-violet)" : "#e5e7eb";
      dot.style.width      = active ? "24px" : "8px";
    });
  }

  // ── Step transitions ───────────────────────────────────────
  function goToStep(newStep, direction) {
    if (newStep === 3) newStep = direction === "forward" ? 4 : 2;
    if (_transitioning || newStep === currentStep || newStep < 1 || newStep > 5) return;
    _transitioning = true;

    const outEl = document.getElementById(`step-${currentStep}`);
    const inEl  = document.getElementById(`step-${newStep}`);
    if (!outEl || !inEl) { _transitioning = false; return; }

    const outX = direction === "forward" ? "-20px" : "20px";
    const inX  = direction === "forward" ? "20px"  : "-20px";

    outEl.style.transition = "opacity 0.2s ease, transform 0.2s ease";
    outEl.style.opacity    = "0";
    outEl.style.transform  = `translateX(${outX})`;

    setTimeout(() => {
      outEl.classList.add("hidden");
      outEl.style.cssText = "";

      inEl.style.opacity   = "0";
      inEl.style.transform = `translateX(${inX})`;
      inEl.classList.remove("hidden");

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          inEl.style.transition = "opacity 0.2s ease, transform 0.2s ease";
          inEl.style.opacity    = "1";
          inEl.style.transform  = "translateX(0)";
          setTimeout(() => {
            inEl.style.cssText = "";
            _transitioning = false;
          }, 200);
        });
      });

      currentStep = newStep;
      updateProgress();
      if (newStep === 5) renderSummary();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }, 200);
  }

  // ── Validation ─────────────────────────────────────────────
  function validateStep(step) {
    clearStepError(step);
    if (step === 1 && formData.interests.size === 0) {
      showStepError(1, "Please select at least one interest.");
      return false;
    }
    if (step === 2) {
      if (!formData.startDate || !formData.endDate) {
        showStepError(2, "Please select both start and end dates.");
        return false;
      }
      if (formData.endDate < formData.startDate) {
        showStepError(2, "End date must be on or after start date.");
        return false;
      }
    }
    return true;
  }

  function showStepError(step, msg) {
    const el = document.getElementById(`step${step}-error`);
    if (!el) return;
    el.textContent = msg;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 4000);
  }

  function clearStepError(step) {
    document.getElementById(`step${step}-error`)?.classList.add("hidden");
  }

  // ── Interest cards ─────────────────────────────────────────
  function setCardActive(card, active) {
    const check = card.querySelector(".interest-check");
    card.setAttribute("aria-pressed", String(active));
    card.style.borderColor = active ? "var(--tz-violet)" : "transparent";
    card.style.transform   = active ? "scale(1.03)" : "";
    if (check) check.style.display = active ? "flex" : "none";
  }

  function initInterestCards() {
    document.querySelectorAll(".interest-card").forEach(card => {
      card.addEventListener("click", () => {
        const cat      = card.dataset.cat;
        const selected = !formData.interests.has(cat);
        if (selected) formData.interests.add(cat);
        else          formData.interests.delete(cat);
        setCardActive(card, selected);
        clearStepError(1);
      });
    });
  }

  // ── Date pickers ────────────────────────────────────────────
  function calcDuration(start, end) {
    if (!start || !end || end < start) return null;
    return Math.round((new Date(`${end}T00:00:00`) - new Date(`${start}T00:00:00`)) / 86400000) + 1;
  }

  function refreshDurationBadge() {
    const badge = document.getElementById("durationBadge");
    if (!badge) return;
    const days = calcDuration(formData.startDate, formData.endDate);
    if (days) {
      badge.textContent = `${days} day${days !== 1 ? "s" : ""}`;
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }
  }

  function initDatePickers() {
    const startInput = document.getElementById("startDate");
    const endInput   = document.getElementById("endDate");

    startInput?.addEventListener("change", () => {
      formData.startDate = startInput.value;
      refreshDurationBadge();
      clearStepError(2);
    });
    endInput?.addEventListener("change", () => {
      formData.endDate = endInput.value;
      refreshDurationBadge();
      clearStepError(2);
    });

  }

  // ── Budget sliders ──────────────────────────────────────────
  function refreshBudgetLabels() {
    const rangeEl = document.getElementById("budgetRangeLabel");
    const minEl   = document.getElementById("budgetMinLabel");
    const maxEl   = document.getElementById("budgetMaxLabel");
    if (rangeEl) rangeEl.textContent = `${formData.budgetMin.toLocaleString()} – ${formData.budgetMax.toLocaleString()} SAR`;
    if (minEl)   minEl.textContent   = formData.budgetMin.toLocaleString();
    if (maxEl)   maxEl.textContent   = formData.budgetMax.toLocaleString();
  }

  function initBudget() {
    const minSlider = document.getElementById("budgetMin");
    const maxSlider = document.getElementById("budgetMax");

    minSlider?.addEventListener("input", () => {
      formData.budgetMin = parseInt(minSlider.value);
      if (formData.budgetMin > formData.budgetMax) {
        formData.budgetMax = formData.budgetMin;
        if (maxSlider) maxSlider.value = formData.budgetMax;
      }
      refreshBudgetLabels();
    });
    maxSlider?.addEventListener("input", () => {
      formData.budgetMax = parseInt(maxSlider.value);
      if (formData.budgetMax < formData.budgetMin) {
        formData.budgetMin = formData.budgetMax;
        if (minSlider) minSlider.value = formData.budgetMin;
      }
      refreshBudgetLabels();
    });
  }

  // ── Rating pills ────────────────────────────────────────────
  function setRatingActive(ratingVal) {
    document.querySelectorAll(".rating-pill").forEach(btn => {
      const active = btn.dataset.rating === (ratingVal || "");
      btn.setAttribute("aria-pressed", String(active));
      btn.style.borderColor     = active ? "var(--tz-violet)" : "#e5e7eb";
      btn.style.backgroundColor = active ? "var(--color-primary-bg)" : "white";
      btn.style.color           = active ? "var(--tz-violet)" : "#4b5563";
    });
  }

  function initRating() {
    document.querySelectorAll(".rating-pill").forEach(btn => {
      btn.addEventListener("click", () => {
        formData.minRating = btn.dataset.rating || null;
        setRatingActive(btn.dataset.rating);
      });
    });
  }

  // ── Language buttons ────────────────────────────────────────
  function setLangActive(lang) {
    document.querySelectorAll(".lang-btn").forEach(btn => {
      const active = btn.dataset.lang === lang;
      btn.setAttribute("aria-pressed", String(active));
      btn.style.borderColor     = active ? "var(--tz-violet)" : "#e5e7eb";
      btn.style.backgroundColor = active ? "var(--color-primary-bg)" : "white";
      btn.style.color           = active ? "var(--tz-violet)" : "#374151";
    });
  }

  function initLanguage() {
    document.querySelectorAll(".lang-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        formData.language = btn.dataset.lang;
        setLangActive(formData.language);
      });
    });
  }

  // ── Summary ─────────────────────────────────────────────────
  function renderSummary() {
    const translated = text => document.documentElement?.lang === "ar" && typeof window.tzTranslateText === "function" ? window.tzTranslateText(text) : text;
    const el = document.getElementById("summaryContent");
    if (!el) return;

    const fmt = iso => {
      try { return new Date(`${iso}T00:00:00`).toLocaleDateString(document.documentElement?.lang === "ar" ? "ar-SA-u-ca-gregory" : "en-GB", { day: "numeric", month: "short", year: "numeric" }); }
      catch (e) { return iso || "—"; }
    };

    const days     = calcDuration(formData.startDate, formData.endDate);
    const cats     = [...formData.interests].map(c => translated(c.charAt(0).toUpperCase() + c.slice(1))).join(", ") || "—";
    const durationText = days ? translated(`${days} ${days === 1 ? "day" : "days"}`) : "";
    const dateStr  = (formData.startDate && formData.endDate)
      ? `${fmt(formData.startDate)}${formData.startDate === formData.endDate ? "" : ` – ${fmt(formData.endDate)}`}${days ? ` (${durationText})` : ""}`
      : "—";

    const rows = [
      ["Interests",   cats],
      ["Dates",       dateStr],
      ["Price per place", `${formData.budgetMin.toLocaleString()} – ${formData.budgetMax.toLocaleString()} SAR`],
      ["Min rating",  formData.minRating ? `${formData.minRating}+ ★` : "Any"],
      ["Language",    formData.language === "ar" ? "العربية" : "English"],
    ];

    el.innerHTML = rows.map(([label, value]) => `
      <div class="flex items-start gap-2.5">
        <span class="text-[var(--tz-violet)] font-bold text-xs mt-0.5 shrink-0">✓</span>
        <span class="text-sm"><span class="font-medium text-gray-700">${translated(label)}:</span>
          <span class="text-gray-500 ml-1">${value}</span></span>
      </div>`
    ).join("");
  }

  // ── Submit ───────────────────────────────────────────────────
  async function handleSubmit() {
    if (_isSubmitting) return;
    if (typeof window.confirm === "function" && !window.confirm(document.documentElement?.lang === "ar" ? "إنشاء أو استبدال الخطط اليومية السابقة لهذه التواريخ؟ ستبقى الرحلات المسمّاة مستقلة دون تغيير." : "Create or replace classic daily plans for these dates? Named trips stay unchanged.")) return;
    _isSubmitting = true;

    const btn   = document.getElementById("submit-btn");
    const msgEl = document.getElementById("pref-message");

    if (btn) { btn.disabled = true; btn.textContent = "Saving…"; }
    if (msgEl) msgEl.classList.add("hidden");

    const days = calcDuration(formData.startDate, formData.endDate) || 1;

    const payload = {
      interests:          [...formData.interests],
      budget_min:         formData.budgetMin,
      budget_max:         formData.budgetMax,
      preferred_language: formData.language,
      min_rating:         formData.minRating ? parseFloat(formData.minRating) : null,
      trip_duration:      days,
      start_date:         formData.startDate || null,
      end_date:           formData.endDate   || null,
    };

    // Always persist to localStorage
    if (formData.startDate) {
      localStorage.setItem("tz_plan_start_date", formData.startDate);
      localStorage.setItem("tz_start_date",      formData.startDate);
    } else {
      localStorage.removeItem("tz_plan_start_date");
      localStorage.removeItem("tz_start_date");
    }
    if (formData.endDate) {
      localStorage.setItem("tz_plan_end_date", formData.endDate);
      localStorage.setItem("tz_end_date",      formData.endDate);
    } else {
      localStorage.removeItem("tz_plan_end_date");
      localStorage.removeItem("tz_end_date");
    }
    localStorage.setItem("tz_trip_duration", String(days));

    try {
      if (!isLoggedIn()) throw new Error("Please log in to save your preferences.");
      const saved = await apiPost("/api/auth/preferences/", payload);
      if (!saved) throw new Error("Could not save preferences. Please log in again.");
      if (msgEl) {
        msgEl.textContent = "Preferences saved! Building your plan…";
        msgEl.className = "text-sm text-center mt-4 rounded-xl py-2.5 px-4 bg-green-50 text-green-700";
      }
      const plan = await apiPost("/api/daily-plan/generate-multiday/", {
        start_date: formData.startDate,
        end_date: formData.endDate || undefined,
        trip_duration: days,
      });
      if (!plan?.plans?.length) throw new Error("Could not generate your plan. Please try again.");

      if (msgEl) {
        msgEl.textContent = "Your plan is ready!";
        msgEl.className   = "text-sm text-center mt-4 rounded-xl py-2.5 px-4 bg-green-50 text-green-700";
        msgEl.classList.remove("hidden");
      }
      setTimeout(() => { window.location.href = (document.documentElement?.lang === "ar" ? "/ar" : "") + "/daily-plan/"; }, 900);
    } catch (err) {
      const msg = (err?.message && !/^API error \d+$/i.test(String(err.message)))
        ? err.message
        : "Could not save preferences. Please try again.";
      if (msgEl) {
        msgEl.textContent = msg;
        msgEl.className   = "text-sm text-center mt-4 rounded-xl py-2.5 px-4 bg-red-50 text-red-600";
        msgEl.classList.remove("hidden");
      }
      if (btn) { btn.disabled = false; btn.textContent = "Generate My Plan →"; }
      _isSubmitting = false;
    }
  }

  // ── Load existing preferences from API ──────────────────────
  async function loadExistingPreferences() {
    if (typeof isLoggedIn === "function" && !isLoggedIn()) return;
    if (typeof apiGet !== "function") return;
    try {
      const data = await apiGet("/api/auth/preferences/");
      if (!data) return;

      if (Array.isArray(data.interests)) {
        data.interests.forEach(cat => {
          formData.interests.add(cat);
          const card = document.querySelector(`.interest-card[data-cat="${cat}"]`);
          if (card) setCardActive(card, true);
        });
      }

      if (data.start_date) {
        formData.startDate = data.start_date;
        const el = document.getElementById("startDate");
        if (el && !el.value) el.value = data.start_date;
      }
      if (data.end_date) {
        formData.endDate = data.end_date;
        const el = document.getElementById("endDate");
        if (el && !el.value) el.value = data.end_date;
      }
      if (formData.startDate || formData.endDate) refreshDurationBadge();

      if (data.budget_min != null) {
        formData.budgetMin = parseInt(data.budget_min);
        const sl = document.getElementById("budgetMin");
        if (sl) sl.value = formData.budgetMin;
      }
      if (data.budget_max != null) {
        formData.budgetMax = parseInt(data.budget_max);
        const sl = document.getElementById("budgetMax");
        if (sl) sl.value = formData.budgetMax;
      }
      refreshBudgetLabels();

      if (data.min_rating != null) {
        formData.minRating = String(data.min_rating);
        setRatingActive(formData.minRating);
      }
      if (data.preferred_language) {
        formData.language = data.preferred_language;
        setLangActive(formData.language);
      }
    } catch (e) { /* silent — existing prefs are a nice-to-have */ }
  }

  // ── Prefill from localStorage ───────────────────────────────
  function prefillFromStorage() {
    const storedStart = localStorage.getItem("tz_plan_start_date") || localStorage.getItem("tz_start_date");
    const storedEnd   = localStorage.getItem("tz_plan_end_date")   || localStorage.getItem("tz_end_date");
    if (storedStart) {
      formData.startDate = storedStart;
      const el = document.getElementById("startDate");
      if (el && !el.value) el.value = storedStart;
    }
    if (storedEnd) {
      formData.endDate = storedEnd;
      const el = document.getElementById("endDate");
      if (el && !el.value) el.value = storedEnd;
    }
    if (formData.startDate || formData.endDate) refreshDurationBadge();
  }

  // ── Keyboard navigation ─────────────────────────────────────
  function initKeyboard() {
    document.addEventListener("keydown", e => {
      if (e.target.tagName === "INPUT" && e.target.type !== "range") return;
      if (e.key === "Enter") {
        if (currentStep < 5) document.getElementById(`next-${currentStep}`)?.click();
        else document.getElementById("submit-btn")?.click();
      }
      if (e.key === "Escape" && currentStep > 1) {
        document.getElementById(`back-${currentStep}`)?.click();
      }
    });
  }

  // ── Wire buttons ────────────────────────────────────────────
  function initButtons() {
    for (let i = 1; i <= 4; i++) {
      document.getElementById(`next-${i}`)?.addEventListener("click", () => {
        if (validateStep(i)) goToStep(i + 1, "forward");
      });
    }
    for (let i = 2; i <= 5; i++) {
      document.getElementById(`back-${i}`)?.addEventListener("click", () => {
        goToStep(i - 1, "backward");
      });
    }
    document.getElementById("submit-btn")?.addEventListener("click", handleSubmit);
  }

  // ── Init ────────────────────────────────────────────────────
  function init() {
    initInterestCards();
    initDatePickers();
    initBudget();
    initRating();
    initLanguage();
    initKeyboard();
    initButtons();
    updateProgress();
    prefillFromStorage();
    loadExistingPreferences();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
