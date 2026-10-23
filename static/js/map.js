(function () {
  "use strict";

  const SELECTED_DATE_KEYS = [
    "tz_selected_plan_date",
    "tz_plan_start_date",
    "tz_start_date",
  ];

  const CATEGORIES = [
    ["", "All", "map"],
    ["culture", "Culture", "landmark"],
    ["heritage", "Heritage", "archway"],
    ["food", "Food", "utensils"],
    ["nature", "Nature", "trees"],
    ["shopping", "Shopping", "shopping-bag"],
    ["events", "Events", "ticket"],
    ["family", "Family", "users"],
    ["entertainment", "Entertainment", "clapperboard"],
  ];

  const CAT_GRADIENTS = {
    culture: "var(--color-primary-bg)",
    heritage: "var(--color-primary-bg)",
    food: "var(--color-primary-bg)",
    nature: "var(--color-primary-bg)",
    shopping: "var(--color-primary-bg)",
    events: "var(--color-primary-bg)",
    family: "var(--color-primary-bg)",
    entertainment: "var(--color-primary-bg)",
  };

  const AREAS = [
    "Central Riyadh",
    "Diriyah",
    "Boulevard Area",
    "KAFD",
    "Riyadh Front",
    "Diplomatic Quarter",
    "Tuwaiq / Edge Area",
    "Other Riyadh",
  ];

  const state = {
    events: [],
    plans: [],
    selectedCategory: "",
    search: "",
    selectedArea: "",
    selectedPlanIndex: 0,
    loadedExplore: false,
    loadedPlan: false,
  };

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function todayISO() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  function getSelectedPlanDate() {
    for (const key of SELECTED_DATE_KEYS) {
      const value = localStorage.getItem(key);
      if (value) return value;
    }
    return todayISO();
  }

  function unwrapList(data) {
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.results)) return data.results;
    if (Array.isArray(data?.plans)) return data.plans;
    if (Array.isArray(data?.days)) return data.days;
    if (Array.isArray(data?.events)) return data.events;
    return [];
  }

  async function fetchAllEvents() {
    const events = [];
    let nextUrl = "/api/events/?page_size=100";
    let pageCount = 0;

    while (nextUrl && pageCount < 10) {
      const data = await apiGet(nextUrl);
      events.push(...unwrapList(data));
      nextUrl = Array.isArray(data) ? null : data?.next || null;
      pageCount += 1;
    }

    return events.filter(Boolean);
  }

  function normalizeEvent(event) {
    return {
      ...event,
      id: event?.id,
      title: event?.title || event?.title_en || "Untitled",
      category: String(event?.category || "events").toLowerCase(),
      location: event?.location || event?.area || "",
      price: event?.price,
      price_range: event?.price_range,
      rating: event?.rating,
      latitude: event?.latitude,
      longitude: event?.longitude,
    };
  }

  function categoryLabel(category) {
    const found = CATEGORIES.find(([key]) => key === String(category || "").toLowerCase());
    return found ? found[1] : "Place";
  }

  function categoryIcon(category) {
    const found = CATEGORIES.find(([key]) => key === String(category || "").toLowerCase());
    return found ? found[2] : "map-pin";
  }

  function categoryGradient(category) {
    return CAT_GRADIENTS[String(category || "").toLowerCase()] || "var(--color-primary-bg)";
  }

  function formatPrice(event) {
    const price = formatEventPrice(event?.price);
    return event?.price_range ? `${price} · ${event.price_range}` : price;
  }

  function hasCoords(event) {
    return Number.isFinite(Number.parseFloat(event?.latitude)) && Number.isFinite(Number.parseFloat(event?.longitude));
  }

  function googleMapsSearchUrl(event) {
    if (hasCoords(event)) {
      return `https://www.google.com/maps/search/?api=1&query=${Number.parseFloat(event.latitude)},${Number.parseFloat(event.longitude)}`;
    }
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${event?.title || ""} Riyadh`)}`;
  }

  function googleMapsRouteUrl(events) {
    const stops = events.filter(hasCoords).slice(0, 10);
    if (!stops.length) return "";
    if (stops.length === 1) return googleMapsSearchUrl(stops[0]);

    const point = event => `${Number.parseFloat(event.latitude)},${Number.parseFloat(event.longitude)}`;
    const origin = point(stops[0]);
    const destination = point(stops[stops.length - 1]);
    const waypoints = stops.slice(1, -1).map(point).join("|");
    const params = new URLSearchParams({
      api: "1",
      origin,
      destination,
      travelmode: "driving",
    });
    if (waypoints) params.set("waypoints", waypoints);
    return `https://www.google.com/maps/dir/?${params.toString()}`;
  }

  function inferArea(event) {
    const text = `${event?.title || ""} ${event?.location || ""} ${event?.description || ""}`.toLowerCase();
    if (/diriyah|turaif|bujairi|salwa/.test(text)) return "Diriyah";
    if (/boulevard|winter wonderland|u walk/.test(text)) return "Boulevard Area";
    if (/kafd|financial district/.test(text)) return "KAFD";
    if (/riyadh front|front/.test(text)) return "Riyadh Front";
    if (/diplomatic quarter|dq/.test(text)) return "Diplomatic Quarter";
    if (/tuwaiq|edge of the world|hidden valley|red sand|desert|cliffs|heet cave|ammariyah/.test(text)) return "Tuwaiq / Edge Area";
    if (/masmak|murabba|national museum|king abdulaziz historical|deera|dirah|zal|thumairi|olaya|kingdom|faisaliah|malaz|central/.test(text)) {
      return "Central Riyadh";
    }
    return "Other Riyadh";
  }

  function filteredEvents() {
    const search = state.search.trim().toLowerCase();
    return state.events.filter(event => {
      if (state.selectedCategory && event.category !== state.selectedCategory) return false;
      if (state.selectedArea && inferArea(event) !== state.selectedArea) return false;
      if (!search) return true;
      const text = `${event.title} ${event.category} ${event.location} ${inferArea(event)}`.toLowerCase();
      return text.includes(search);
    });
  }

  function setMode(mode) {
    const explore = mode === "explore";
    document.getElementById("mapExploreMode")?.classList.toggle("hidden", !explore);
    document.getElementById("mapPlanMode")?.classList.toggle("hidden", explore);
    document.getElementById("mapExploreTab")?.classList.toggle("active", explore);
    document.getElementById("mapPlanTab")?.classList.toggle("active", !explore);
    if (explore) loadExplore().catch(renderExploreError);
    else loadPlan().catch(renderPlanError);
  }

  function renderCategoryPills() {
    const el = document.getElementById("mapCategoryPills");
    if (!el) return;
    el.innerHTML = CATEGORIES.map(([key, label, icon]) => `
      <button type="button" data-category="${escapeHtml(key)}"
        class="map-cat-pill ${key === state.selectedCategory ? "active" : ""} flex items-center gap-1.5 px-4 py-2 rounded-2xl border-2 border-transparent text-sm font-semibold whitespace-nowrap text-gray-700 transition"
        style="background:${key ? categoryGradient(key) : "var(--color-primary-bg)"}">
        <i data-lucide="${icon}" class="w-4 h-4"></i>
        ${escapeHtml(label)}
      </button>
    `).join("");

    el.querySelectorAll("[data-category]").forEach(btn => {
      btn.addEventListener("click", () => {
        state.selectedCategory = btn.dataset.category || "";
        renderExplore();
      });
    });
  }

  function renderAreas(events) {
    const grid = document.getElementById("mapAreasGrid");
    const countEl = document.getElementById("mapAreaCount");
    if (!grid) return;

    const byArea = new Map(AREAS.map(area => [area, []]));
    events.forEach(event => byArea.get(inferArea(event)).push(event));
    if (countEl) countEl.textContent = `${events.length} places`;

    grid.innerHTML = AREAS.map(area => {
      const places = byArea.get(area) || [];
      const preview = places.slice(0, 3).map(place => `<li class="truncate">${escapeHtml(place.title)}</li>`).join("");
      return `
        <article class="map-area-card ${state.selectedArea === area ? "active" : ""} bg-white rounded-2xl border border-gray-100 shadow-sm p-4 space-y-3">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h3 class="font-semibold text-gray-900">${escapeHtml(area)}</h3>
              <p class="text-xs text-gray-400 mt-0.5">${places.length} places</p>
            </div>
            <span class="w-9 h-9 rounded-xl bg-violet-50 text-violet-600 flex items-center justify-center shrink-0">
              <i data-lucide="map-pin" class="w-4 h-4"></i>
            </span>
          </div>
          <ul class="min-h-[3.75rem] space-y-1 text-xs text-gray-500">${preview || "<li>No matches yet</li>"}</ul>
          <button type="button" data-area="${escapeHtml(area)}"
            class="w-full h-9 rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-700 hover:bg-violet-50 hover:border-violet-200 hover:text-violet-700 transition">
            ${state.selectedArea === area ? "Showing Places" : "View Places"}
          </button>
        </article>
      `;
    }).join("");

    grid.querySelectorAll("[data-area]").forEach(btn => {
      btn.addEventListener("click", () => {
        state.selectedArea = state.selectedArea === btn.dataset.area ? "" : btn.dataset.area;
        renderExplore();
      });
    });
  }

  function renderPlaceCard(event) {
    const rating = event.rating ? `<span class="text-xs font-medium text-yellow-600">Star ${escapeHtml(event.rating)}</span>` : "";
    return `
      <article class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div class="h-2" style="background:${categoryGradient(event.category)}"></div>
        <div class="p-4 space-y-4">
          <div class="flex items-start gap-3">
            <span class="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style="background:${categoryGradient(event.category)}">
              <i data-lucide="${categoryIcon(event.category)}" class="w-5 h-5 text-gray-700"></i>
            </span>
            <div class="min-w-0 flex-1">
              <h3 class="font-semibold text-gray-900 leading-snug">${escapeHtml(event.title)}</h3>
              <div class="mt-1 flex flex-wrap items-center gap-2">
                <span class="text-xs px-2 py-0.5 rounded-full bg-gray-50 text-gray-600 border border-gray-100">${escapeHtml(categoryLabel(event.category))}</span>
                ${rating}
              </div>
            </div>
          </div>
          <div class="space-y-1.5 text-sm text-gray-500">
            <p class="flex items-center gap-2"><i data-lucide="wallet" class="w-4 h-4 shrink-0"></i>${escapeHtml(formatPrice(event))}</p>
            <p class="flex items-start gap-2"><i data-lucide="map-pin" class="w-4 h-4 shrink-0 mt-0.5"></i><span>${escapeHtml(event.location || inferArea(event))}</span></p>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <button type="button" data-add-plan="${escapeHtml(event.id)}"
              class="h-10 rounded-xl bg-violet-600 text-white text-sm font-semibold hover:bg-violet-700 transition">
              Add to Plan
            </button>
            <a href="${googleMapsSearchUrl(event)}" target="_blank" rel="noopener"
              class="h-10 rounded-xl border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50 transition flex items-center justify-center">
              Open in Maps
            </a>
          </div>
        </div>
      </article>
    `;
  }

  function renderPlaces(events) {
    const grid = document.getElementById("mapPlacesGrid");
    const title = document.getElementById("mapPlacesTitle");
    const count = document.getElementById("mapPlacesCount");
    if (!grid) return;

    if (title) title.textContent = state.selectedArea || "Places";
    if (count) count.textContent = `${events.length} shown`;

    if (!events.length) {
      grid.innerHTML = `
        <div class="md:col-span-2 xl:col-span-3 bg-white rounded-2xl border border-gray-100 shadow-sm p-10 text-center">
          <div class="w-12 h-12 rounded-2xl bg-violet-50 text-violet-600 flex items-center justify-center mx-auto mb-4">
            <i data-lucide="search-x" class="w-6 h-6"></i>
          </div>
          <h3 class="text-lg font-bold text-gray-900">No places found</h3>
          <p class="text-sm text-gray-500 mt-1">Try a different search, category, or area.</p>
        </div>`;
      refreshIcons();
      return;
    }

    grid.innerHTML = events.slice(0, 60).map(renderPlaceCard).join("");
    grid.querySelectorAll("[data-add-plan]").forEach(btn => {
      btn.addEventListener("click", () => addToPlan(Number(btn.dataset.addPlan), btn));
    });
  }

  function renderExplore() {
    renderCategoryPills();
    const events = filteredEvents();
    const areaBaseEvents = state.selectedArea ? state.events.filter(event => {
      if (state.selectedCategory && event.category !== state.selectedCategory) return false;
      if (!state.search.trim()) return true;
      const text = `${event.title} ${event.category} ${event.location} ${inferArea(event)}`.toLowerCase();
      return text.includes(state.search.trim().toLowerCase());
    }) : events;
    renderAreas(areaBaseEvents);
    renderPlaces(events);
    refreshIcons();
  }

  function renderExploreLoading() {
    const areas = document.getElementById("mapAreasGrid");
    const places = document.getElementById("mapPlacesGrid");
    if (areas) {
      areas.innerHTML = Array.from({ length: 4 }).map(() => `
        <div class="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 animate-pulse">
          <div class="h-4 bg-gray-100 rounded w-2/3 mb-3"></div>
          <div class="h-3 bg-gray-100 rounded w-1/3 mb-5"></div>
          <div class="space-y-2"><div class="h-3 bg-gray-100 rounded"></div><div class="h-3 bg-gray-100 rounded w-4/5"></div></div>
        </div>
      `).join("");
    }
    if (places) {
      places.innerHTML = Array.from({ length: 6 }).map(() => `
        <div class="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 animate-pulse">
          <div class="h-5 bg-gray-100 rounded w-4/5 mb-4"></div>
          <div class="h-3 bg-gray-100 rounded w-1/2 mb-6"></div>
          <div class="grid grid-cols-2 gap-2"><div class="h-10 bg-gray-100 rounded-xl"></div><div class="h-10 bg-gray-100 rounded-xl"></div></div>
        </div>
      `).join("");
    }
  }

  async function loadExplore() {
    if (state.loadedExplore) {
      renderExplore();
      return;
    }
    renderCategoryPills();
    renderExploreLoading();
    state.events = (await fetchAllEvents()).map(normalizeEvent);
    state.loadedExplore = true;
    renderExplore();
  }

  function renderExploreError(error) {
    console.error("Failed to load places", error);
    const places = document.getElementById("mapPlacesGrid");
    if (!places) return;
    places.innerHTML = `
      <div class="md:col-span-2 xl:col-span-3 bg-white rounded-2xl border border-red-100 shadow-sm p-10 text-center">
        <h3 class="text-lg font-bold text-gray-900">Could not load places</h3>
        <p class="text-sm text-gray-500 mt-1">Please try again.</p>
        <button id="mapRetryExplore" type="button" class="mt-5 h-10 px-5 rounded-xl bg-violet-600 text-white text-sm font-semibold">Retry</button>
      </div>`;
    document.getElementById("mapRetryExplore")?.addEventListener("click", () => {
      state.loadedExplore = false;
      loadExplore().catch(renderExploreError);
    });
  }

  function normalizePlan(plan) {
    const rawItems = Array.isArray(plan?.items) ? plan.items : [];
    const itemEvents = rawItems
      .map((item, index) => item?.event ? {
        ...normalizeEvent(item.event),
        slot_type: item.slot_type,
        item_order: Number.isFinite(Number(item.order)) ? Number(item.order) : index,
      } : null)
      .filter(Boolean)
      .sort((a, b) => (a.item_order || 0) - (b.item_order || 0));

    const events = itemEvents.length
      ? itemEvents
      : unwrapList(plan).map((event, index) => ({
        ...normalizeEvent(event),
        item_order: index,
      }));

    return {
      id: plan?.id,
      date: plan?.date || "",
      events,
    };
  }

  async function loadPlan() {
    if (!state.loadedPlan) {
      renderPlanLoading();
      const data = await apiGet("/api/daily-plan/");
      state.plans = unwrapList(data).map(normalizePlan).filter(plan => plan.events.length);
      state.plans.sort((a, b) => String(a.date).localeCompare(String(b.date)));
      const selectedDate = getSelectedPlanDate();
      const selectedIndex = state.plans.findIndex(plan => plan.date === selectedDate);
      state.selectedPlanIndex = selectedIndex >= 0 ? selectedIndex : 0;
      state.loadedPlan = true;
    }
    renderPlan();
  }

  function renderPlanLoading() {
    const route = document.getElementById("mapPlanRoute");
    if (!route) return;
    route.innerHTML = `
      <div class="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 animate-pulse">
        <div class="h-5 bg-gray-100 rounded w-2/3 mb-4"></div>
        <div class="space-y-3">
          <div class="h-14 bg-gray-100 rounded-xl"></div>
          <div class="h-14 bg-gray-100 rounded-xl"></div>
          <div class="h-14 bg-gray-100 rounded-xl"></div>
        </div>
      </div>`;
  }

  function renderPlanTabs() {
    const tabs = document.getElementById("mapPlanDayTabs");
    if (!tabs) return;
    tabs.innerHTML = state.plans.map((plan, index) => {
      const active = index === state.selectedPlanIndex;
      const dateText = formatDate(plan.date);
      return `
        <button type="button" data-plan-index="${index}"
          class="shrink-0 flex flex-col items-center px-5 py-2.5 rounded-xl text-sm font-semibold transition ${active ? "text-white" : "bg-white border border-gray-200 text-gray-600 hover:border-violet-300"}"
          style="${active ? "background-color:var(--tz-violet)" : ""}">
          <span>Day ${index + 1}</span>
          <span class="text-xs font-normal ${active ? "text-white/75" : "text-gray-400"}">${escapeHtml(dateText)}</span>
        </button>`;
    }).join("");
    tabs.querySelectorAll("[data-plan-index]").forEach(btn => {
      btn.addEventListener("click", () => {
        state.selectedPlanIndex = Number(btn.dataset.planIndex);
        renderPlan();
      });
    });
  }

  function formatDate(iso) {
    if (!iso) return "";
    try {
      return new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
    } catch {
      return iso;
    }
  }

  function formatSlot(event, index) {
    if (event.slot_type) return event.slot_type.charAt(0).toUpperCase() + event.slot_type.slice(1);
    return `Stop ${index + 1}`;
  }

  function renderPlan() {
    const route = document.getElementById("mapPlanRoute");
    const actions = document.getElementById("mapPlanActions");
    if (!route || !actions) return;

    if (!state.plans.length) {
      document.getElementById("mapPlanDayTabs").innerHTML = "";
      actions.classList.add("hidden");
      route.innerHTML = `
        <div class="bg-white rounded-2xl border border-gray-100 shadow-sm p-10 text-center">
          <div class="w-14 h-14 rounded-2xl bg-violet-50 text-violet-600 flex items-center justify-center mx-auto mb-5">
            <i data-lucide="calendar-plus" class="w-7 h-7"></i>
          </div>
          <h2 class="text-xl font-bold text-gray-900">No plan yet</h2>
          <p class="text-sm text-gray-500 mt-2">Generate your Riyadh journey first, then view it here.</p>
          <a href="/daily-plan/" class="mt-6 inline-flex items-center justify-center h-11 px-6 rounded-xl bg-violet-600 text-white text-sm font-semibold hover:bg-violet-700 transition">
            Generate Plan
          </a>
        </div>`;
      refreshIcons();
      return;
    }

    renderPlanTabs();
    const plan = state.plans[state.selectedPlanIndex] || state.plans[0];
    const events = plan.events || [];

    route.innerHTML = `
      <div class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100">
          <h2 class="text-lg font-bold text-gray-900">Route for ${escapeHtml(formatDate(plan.date) || "selected day")}</h2>
          <p class="text-sm text-gray-400">${events.length} ${events.length === 1 ? "stop" : "stops"}</p>
        </div>
        <div class="divide-y divide-gray-100">
          ${events.map((event, index) => `
            <article class="p-4 flex gap-4">
              <span class="w-8 h-8 rounded-full bg-violet-600 text-white text-sm font-bold flex items-center justify-center shrink-0">${index + 1}</span>
              <div class="min-w-0 flex-1 space-y-2">
                <div>
                  <p class="text-xs font-semibold text-violet-600 uppercase tracking-wide">${escapeHtml(formatSlot(event, index))}</p>
                  <h3 class="font-semibold text-gray-900 leading-snug">${escapeHtml(event.title)}</h3>
                </div>
                <div class="flex flex-wrap items-center gap-2 text-xs text-gray-500">
                  <span class="px-2 py-0.5 rounded-full bg-gray-50 border border-gray-100">${escapeHtml(categoryLabel(event.category))}</span>
                  ${event.rating ? `<span>Star ${escapeHtml(event.rating)}</span>` : ""}
                  <span>${escapeHtml(formatPrice(event))}</span>
                </div>
                <div class="flex flex-wrap gap-2 pt-1">
                  <a href="${googleMapsSearchUrl(event)}" target="_blank" rel="noopener"
                    class="h-9 px-4 rounded-xl bg-violet-600 text-white text-sm font-semibold hover:bg-violet-700 transition inline-flex items-center justify-center">
                    Navigate
                  </a>
                  ${event.id ? `<a href="/events/page/${event.id}/" class="h-9 px-4 rounded-xl border border-gray-200 text-sm font-medium text-gray-700 hover:bg-gray-50 transition inline-flex items-center justify-center">View Details</a>` : ""}
                </div>
              </div>
            </article>
          `).join("")}
        </div>
      </div>`;

    const routeUrl = googleMapsRouteUrl(events);
    actions.classList.remove("hidden");
    actions.innerHTML = `
      <div class="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
        <div>
          <p class="text-sm font-semibold text-gray-800">${events.filter(hasCoords).length >= 2 ? "Ready to navigate the route" : "Open first stop in Google Maps"}</p>
          <p class="text-xs text-gray-400">External Google Maps link. No embedded map required.</p>
        </div>
        ${routeUrl ? `<a href="${routeUrl}" target="_blank" rel="noopener" class="h-11 px-5 rounded-xl bg-violet-600 text-white text-sm font-semibold hover:bg-violet-700 transition inline-flex items-center justify-center">${events.filter(hasCoords).length >= 2 ? "Open Route in Google Maps" : "Open first stop in Google Maps"}</a>` : ""}
      </div>`;
    refreshIcons();
  }

  function renderPlanError(error) {
    console.error("Failed to load plan", error);
    const route = document.getElementById("mapPlanRoute");
    if (!route) return;
    route.innerHTML = `
      <div class="bg-white rounded-2xl border border-red-100 shadow-sm p-10 text-center">
        <h3 class="text-lg font-bold text-gray-900">Could not load your plan</h3>
        <p class="text-sm text-gray-500 mt-1">Please try again.</p>
        <button id="mapRetryPlan" type="button" class="mt-5 h-10 px-5 rounded-xl bg-violet-600 text-white text-sm font-semibold">Retry</button>
      </div>`;
    document.getElementById("mapRetryPlan")?.addEventListener("click", () => {
      state.loadedPlan = false;
      loadPlan().catch(renderPlanError);
    });
  }

  async function addToPlan(eventId, button) {
    if (!eventId || typeof apiPost !== "function") return;
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Adding...";
    try {
      await apiPost("/api/daily-plan/add/", {
        event_id: eventId,
        date: getSelectedPlanDate(),
      });
      button.textContent = "Added";
      state.loadedPlan = false;
      setTimeout(() => {
        button.disabled = false;
        button.textContent = original;
      }, 1400);
    } catch (error) {
      button.disabled = false;
      button.textContent = original;
      window.alert(error?.message || "Could not add this place to your plan.");
    }
  }

  function refreshIcons() {
    if (window.lucide) window.lucide.createIcons();
  }

  function initPage() {
    if (!document.getElementById("mapPageRoot")) return;

    document.getElementById("mapExploreTab")?.addEventListener("click", () => setMode("explore"));
    document.getElementById("mapPlanTab")?.addEventListener("click", () => setMode("plan"));
    document.getElementById("mapSearchInput")?.addEventListener("input", event => {
      state.search = event.target.value || "";
      document.getElementById("mapClearSearchBtn")?.classList.toggle("hidden", !state.search);
      renderExplore();
    });
    document.getElementById("mapClearSearchBtn")?.addEventListener("click", () => {
      state.search = "";
      const input = document.getElementById("mapSearchInput");
      if (input) input.value = "";
      document.getElementById("mapClearSearchBtn")?.classList.add("hidden");
      renderExplore();
    });

    setMode("explore");
    refreshIcons();
  }

  function renderMapFallback(containerId, message) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = `
      <div class="h-full w-full flex items-center justify-center p-6 bg-gray-50 text-center">
        <div class="max-w-sm space-y-2">
          <p class="text-sm font-semibold text-gray-700">Map preview unavailable</p>
          <p class="text-xs text-gray-500">${escapeHtml(message || "Use the external Google Maps links for directions.")}</p>
        </div>
      </div>`;
    return null;
  }

  function initMap(containerId) {
    return renderMapFallback(containerId, "This page uses external Google Maps links instead of an embedded map.");
  }

  window.TZMap = { initMap, renderMapFallback };
  document.addEventListener("DOMContentLoaded", initPage);
})();
