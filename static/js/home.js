// home.js - renders the logged-in tourism dashboard.
// Depends on api.js (apiGet, catLabel, catColor loaded by base template).

(function () {
  "use strict";


  function todayISO() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  function escHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatPlanDate(iso) {
    try {
      return new Date(iso).toLocaleDateString(document.documentElement?.lang === "ar" ? "ar-SA-u-ca-gregory" : "en-GB", {
        weekday: "long",
        day: "numeric",
        month: "short",
      });
    } catch (e) {
      return iso || "";
    }
  }

  function computeTripDay(startRaw) {
    if (!startRaw) return null;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const start = new Date(startRaw);
    start.setHours(0, 0, 0, 0);
    return Math.max(1, Math.floor((today - start) / 86400000) + 1);
  }

  function computeTripLength(startRaw, endRaw) {
    if (!startRaw || !endRaw) return null;
    const start = new Date(startRaw);
    start.setHours(0, 0, 0, 0);
    const end = new Date(endRaw);
    end.setHours(0, 0, 0, 0);
    return Math.max(1, Math.round((end - start) / 86400000) + 1);
  }

  function categoryLabel(category) {
    return typeof catLabel === "function" ? catLabel(category) : String(category || "Place");
  }

  function categoryClass(category) {
    return typeof catColor === "function" ? catColor(category) : "bg-violet-50 text-violet-700";
  }

  function imageFor(event) {
    return getPlaceImage(event,true);
  }

  function normalizeList(data) {
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.results)) return data.results;
    if (Array.isArray(data?.events)) return data.events;
    return [];
  }

  function renderPlanCard(plans) {
    const el = document.getElementById("planCard");
    if (!el) return;

    const today = todayISO();
    const sorted = [...(plans || [])].sort((a, b) =>
      String(a?.date || "").localeCompare(String(b?.date || ""))
    );
    const plan = sorted.find(p => String(p?.date || "") >= today) || sorted[0];

    if (plan && plan.events && plan.events.length) {
      const startRaw = localStorage.getItem("tz_plan_start_date") || localStorage.getItem("tz_start_date");
      const endRaw = localStorage.getItem("tz_plan_end_date") || localStorage.getItem("tz_end_date");
      const dayX = computeTripDay(startRaw);
      const dayY = computeTripLength(startRaw, endRaw);
      const dayLabel = (dayX && dayY) ? `Day ${dayX} of ${dayY}` : (dayX ? `Day ${dayX}` : null);

      const count = plan.events.length;
      const countText = `${count} ${count === 1 ? "activity" : "activities"}`;
      const dateText = plan.date ? formatPlanDate(plan.date) : "";
      const metaText = [dateText, countText].filter(Boolean).join(" - ");
      const lead = plan.events[0];
      const leadImage = imageFor(lead);

      const items = plan.events.slice(0, 4).map(ev => {
        const label = categoryLabel(ev.category);
        const color = categoryClass(ev.category);
        return `
          <div class="flex items-center gap-3 py-3 border-b border-violet-50 last:border-0">
            <img src="${escHtml(imageFor(ev))}" alt="${escHtml(ev.title)}" loading="lazy"
              class="w-11 h-11 rounded-xl object-cover shrink-0 bg-violet-50">
            <div class="min-w-0 flex-1">
              <p class="text-sm font-semibold text-gray-900 truncate">${escHtml(ev.title)}</p>
              <p class="text-xs text-gray-400 truncate">${escHtml(ev.area || ev.location || "Riyadh")}</p>
            </div>
            <span class="shrink-0 text-xs px-2 py-0.5 rounded-full ${color}">${escHtml(label)}</span>
          </div>`;
      }).join("");

      el.innerHTML = `
        <div class="h-full bg-white rounded-3xl border border-violet-100 shadow-sm overflow-hidden">
          <div class="relative h-44">
            ${leadImage ? `<img src="${escHtml(leadImage)}" alt="${escHtml(lead?.title || "Riyadh plan")}" class="absolute inset-0 h-full w-full object-cover">` : '<div class="absolute inset-0 bg-brand-dark"></div>'}
            <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent"></div>
            <div class="absolute bottom-0 left-0 right-0 p-6 text-white">
              ${dayLabel ? `<p class="text-xs font-semibold uppercase tracking-widest text-white/75">${escHtml(dayLabel)}</p>` : ""}
              <h2 class="mt-1 text-2xl font-bold">Your Plan is Ready</h2>
              ${metaText ? `<p class="mt-1 text-sm text-white/75">${escHtml(metaText)}</p>` : ""}
            </div>
          </div>
          <div class="px-6 py-2">${items}</div>
          <div class="px-6 pb-6 pt-3">
            <a href="${document.documentElement.lang === 'ar' ? '/ar' : ''}/daily-plan/?date=${encodeURIComponent(plan.date)}"
              class="block w-full text-center px-6 py-3 rounded-xl text-sm font-semibold text-white transition shadow-sm bg-violet-600 hover:bg-violet-700">
              View Plan
            </a>
          </div>
        </div>`;
    } else {
      el.innerHTML = `
        <div class="h-full bg-white rounded-3xl border border-violet-100 shadow-sm overflow-hidden">
          <div class="relative h-44">
            <img src="${escHtml(el.dataset?.heritageImage || '')}" alt="Riyadh heritage" class="absolute inset-0 h-full w-full object-cover">
            <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent"></div>
            <div class="absolute bottom-0 left-0 right-0 p-6 text-white">
              <h2 class="text-2xl font-bold">Create Your Personalized Journey</h2>
              <p class="mt-1 text-sm text-white/75">Tell us your interests and we will build your Riyadh itinerary.</p>
            </div>
          </div>
          <div class="p-6">
            <a href="/onboarding/"
              class="inline-flex w-full items-center justify-center px-6 py-3 rounded-xl text-sm font-semibold text-white transition shadow-sm bg-violet-600 hover:bg-violet-700">
              Generate My Plan
            </a>
          </div>
        </div>`;
    }
  }

  function renderRecommended(events) {
    if (typeof window.renderDiscoveryPlaces === "function") window.renderDiscoveryPlaces(events);
  }

  async function init() {
    try {
      const data = await apiGet("/api/daily-plan/");
      renderPlanCard(normalizeList(data));
    } catch (e) {
      renderPlanCard([]);
    }

    try {
      const events = await apiGet("/api/events/?page_size=6");
      renderRecommended(events);
    } catch (e) {
      renderRecommended([]);
    }

    if (typeof lucide !== "undefined") lucide.createIcons();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
