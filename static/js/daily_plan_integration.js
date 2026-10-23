/* ═══════════════════════════════════════════════════════════
   daily_plan_integration.js
   Timeline-based daily plan for tourists.
   Depends on api.js (apiGet, apiPost, apiPut, apiPatch, apiDelete)
═══════════════════════════════════════════════════════════ */

// ── Constants ─────────────────────────────────────────────
const SLOT_LABELS    = { breakfast: "Breakfast", activity: "Activity", lunch: "Lunch", evening: "Evening" };
const SLOT_LIMITS    = { breakfast: 1, activity: 3, lunch: 1, evening: 3 };
const SLOT_ORDER     = ["breakfast", "activity", "lunch", "evening"];

const SLOT_TIMES = {
  breakfast: ["08:00 AM"],
  activity:  ["10:00 AM", "12:00 PM", "02:00 PM"],
  lunch:     ["01:00 PM"],
  evening:   ["05:00 PM", "07:00 PM", "09:00 PM"],
};

const SLOT_GRADIENTS = {
  breakfast: "var(--color-primary-bg)",
  activity:  "var(--color-primary-bg)",
  lunch:     "var(--color-primary-bg)",
  evening:   "var(--color-primary-bg)",
};


const DARB_APP_URL = "https://play.google.com/store/apps/details?hl=ar&id=com.rcrc.riyadhjourneyplanner";

const PLAN_START_KEY   = "tz_plan_start_date";
const PLAN_END_KEY     = "tz_plan_end_date";
const SELECTED_DATE_KEY = "tz_selected_plan_date";

// ── Module State ──────────────────────────────────────────
let multiDayPlans           = [];
let currentDayIndex         = 0;
let _currentPlan            = null;
let _currentPreferences     = null;
let _viewedSavedDate        = null;
let _slotAssignmentsByDay   = {};
let _slotFeedbackByDay      = {};
let _slotBlockedIdsByDay    = {};
let _replacementCache       = new Map();
let _isPlanLoading          = false;
let _activityDebounce       = null;
let _userLocation           = null;
let _addActivityContext     = { dayIndex: 0, slotKey: "activity" };
// Tracks which day indices have ever had plan data — used to show
// placeholder slots (not full empty-state) after all activities are removed.
let _dayHasPlan             = {};

// ── Utilities ─────────────────────────────────────────────
function _localDateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function categoryEmoji(cat) {
  const c = String(cat || "").toLowerCase();
  if (c.includes("food") || c.includes("restaurant") || c.includes("cafe") || c.includes("beverage")) return "🍽️";
  if (c.includes("culture") || c.includes("heritage") || c.includes("histor")) return "🏛️";
  if (c.includes("nature") || c.includes("outdoor") || c.includes("park")) return "🌳";
  if (c.includes("entertainment")) return "🎭";
  if (c.includes("shopping")) return "🛍️";
  if (c.includes("event")) return "🎫";
  return "📍";
}

function formatCategory(cat) {
  return String(cat || "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) || "Place";
}

function formatPrice(price) {
  return formatEventPrice(price);
}

function getEventImageUrl(event) {
  return getPlaceImage(event,true);
}

// ── User geolocation (optional — for distance labels) ─────
function getUserLocation() {
  return new Promise(resolve => {
    if (_userLocation) { resolve(_userLocation); return; }
    if (!navigator.geolocation) { resolve(null); return; }
    navigator.geolocation.getCurrentPosition(
      pos => { _userLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude }; resolve(_userLocation); },
      () => resolve(null),
      { timeout: 5000, maximumAge: 60000 }
    );
  });
}

function haversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371, toRad = v => v * Math.PI / 180;
  const dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ── localStorage helpers ──────────────────────────────────
function getStoredPlanStartDate() {
  if (_viewedSavedDate) return _viewedSavedDate;
  return localStorage.getItem(PLAN_START_KEY) || _currentPreferences?.start_date || _localDateStr(new Date());
}

function getStoredPlanEndDate() {
  if (_viewedSavedDate) return _viewedSavedDate;
  return localStorage.getItem(PLAN_END_KEY) || _currentPreferences?.end_date || "";
}

function setSelectedPlanDate(dateStr) {
  localStorage.setItem(SELECTED_DATE_KEY, dateStr || _localDateStr(new Date()));
}

function getSelectedPlanDate() {
  return localStorage.getItem(SELECTED_DATE_KEY) || getStoredPlanStartDate() || null;
}

function getTripDuration() {
  const start = getStoredPlanStartDate(), end = getStoredPlanEndDate();
  if (start && end) {
    const d = Math.round((new Date(`${end}T00:00:00`) - new Date(`${start}T00:00:00`)) / 86400000) + 1;
    if (d > 0) return d;
  }
  const raw = parseInt(_currentPreferences?.trip_duration || localStorage.getItem("tz_trip_duration") || "1");
  return Math.max(1, Math.min(30, isFinite(raw) ? raw : 1));
}

function getPlanDateForIndex(index) {
  const day = new Date(`${getStoredPlanStartDate()}T00:00:00`);
  day.setDate(day.getDate() + index);
  return day;
}

// ── Plan normalisation (preserves original logic) ─────────
function normalizePlanEvent(event, index = 0) {
  if (!event || typeof event !== "object") return null;
  return {
    ...event,
    plan_id:          isFinite(Number(event.plan_id))         ? Number(event.plan_id)         : null,
    plan_date:        event.plan_date || null,
    slot_type:        event.slot_type || null,
    item_order:       isFinite(Number(event.item_order))       ? Number(event.item_order)       : index,
    plan_item_id:     isFinite(Number(event.plan_item_id))     ? Number(event.plan_item_id)     : null,
    locked:           Boolean(event.locked),
    plan_item_source: event.plan_item_source || null,
  };
}

function normalizePlanPayload(plan) {
  const rawItems = Array.isArray(plan?.items) ? plan.items.filter(Boolean) : [];
  const itemBacked = rawItems.map((item, i) => {
    if (!item?.event || typeof item.event !== "object") return null;
    return normalizePlanEvent({
      ...item.event,
      plan_id:          plan?.id || null,
      plan_date:        plan?.date || null,
      slot_type:        item.slot_type || null,
      item_order:       item.order,
      plan_item_id:     item.id,
      locked:           item.locked,
      plan_item_source: item.source,
    }, i);
  }).filter(Boolean).sort((a, b) => {
    const d = Number(a.item_order || 0) - Number(b.item_order || 0);
    return d !== 0 ? d : Number(a.id || 0) - Number(b.id || 0);
  });

  const fallback = Array.isArray(plan?.events)
    ? plan.events.map((e, i) => normalizePlanEvent({ ...e, plan_id: plan?.id || null, plan_date: plan?.date || null }, i)).filter(Boolean)
    : [];

  const events = itemBacked.length ? itemBacked : fallback;
  return { ...(plan || {}), items: rawItems, events, count: events.length };
}

// ── Slot assignment (preserves original logic) ────────────
function cloneSlotAssignments(a = {}) {
  return {
    breakfast: Array.isArray(a.breakfast) ? [...a.breakfast] : [],
    activity:  Array.isArray(a.activity)  ? [...a.activity]  : [],
    lunch:     Array.isArray(a.lunch)     ? [...a.lunch]     : [],
    evening:   Array.isArray(a.evening)   ? [...a.evening]   : [],
  };
}

function getSlotLimit(slotKey) { return SLOT_LIMITS[slotKey] || 1; }

function createSlotPlaceholder(slotKey, slotIndex = 0) {
  return { id: `placeholder-${slotKey}-${slotIndex}`, _placeholder: true, slotKey, slotIndex, title: "No activity selected" };
}

function isFoodEvent(event) {
  const category = String(event?.category || "").toLowerCase();
  return category === "food" || category === "restaurant" || category === "cafe";
}

function getDaySlotAssignments(events, dayIndex = currentDayIndex) {
  const existing = _slotAssignmentsByDay[dayIndex];
  if (existing) return cloneSlotAssignments(existing);

  const safe       = Array.isArray(events) ? events.filter(Boolean) : [];
  const hasExplicit = safe.some(e => typeof e?.slot_type === "string" && e.slot_type);
  const ids         = safe.map(e => Number(e?.id)).filter(id => isFinite(id));
  const assignments = { breakfast: [], activity: [], lunch: [], evening: [] };

  if (!ids.length) {
    _slotAssignmentsByDay[dayIndex] = cloneSlotAssignments(assignments);
    return cloneSlotAssignments(assignments);
  }

  if (hasExplicit) {
    [...safe].sort((a, b) => {
      const d = Number(a?.item_order ?? Number.MAX_SAFE_INTEGER) - Number(b?.item_order ?? Number.MAX_SAFE_INTEGER);
      return d !== 0 ? d : Number(a?.id || 0) - Number(b?.id || 0);
    }).forEach(e => {
      const key = String(e?.slot_type || "").toLowerCase();
      const id  = Number(e?.id);
      if (!SLOT_LIMITS[key] || !isFinite(id)) return;
      if (assignments[key].length < getSlotLimit(key)) assignments[key].push(id);
    });
    _slotAssignmentsByDay[dayIndex] = cloneSlotAssignments(assignments);
    return cloneSlotAssignments(assignments);
  }

  const foodIds = safe.filter(isFoodEvent).map(e => Number(e?.id)).filter(id => isFinite(id));
  const activityIds = safe.filter(e => !isFoodEvent(e)).map(e => Number(e?.id)).filter(id => isFinite(id));
  if (foodIds.length) assignments.breakfast = [foodIds[0]];
  if (foodIds.length > 1) assignments.lunch = [foodIds[1]];
  assignments.activity = activityIds.slice(0, getSlotLimit("activity"));
  // Legacy flat plans can include a third meal; keep it visible in the evening.
  assignments.evening = [...foodIds.slice(2), ...activityIds.slice(getSlotLimit("activity"))]
    .slice(0, getSlotLimit("evening"));

  if (!foodIds.length && !activityIds.length && ids.length) {
    assignments.activity = ids.slice(0, getSlotLimit("activity"));
  }

  _slotAssignmentsByDay[dayIndex] = cloneSlotAssignments(assignments);
  return cloneSlotAssignments(assignments);
}

function buildStructuredSlots(events, dayIndex = currentDayIndex) {
  const safe        = Array.isArray(events) ? events.filter(Boolean) : [];
  const hasExplicit = safe.some(e => typeof e?.slot_type === "string" && e.slot_type);

  if (hasExplicit) {
    return SLOT_ORDER.map(key => {
      const items = safe
        .filter(e => String(e?.slot_type || "").toLowerCase() === key)
        .sort((a, b) => {
          const d = Number(a?.item_order ?? Number.MAX_SAFE_INTEGER) - Number(b?.item_order ?? Number.MAX_SAFE_INTEGER);
          return d !== 0 ? d : Number(a?.id || 0) - Number(b?.id || 0);
        })
        .map((e, i) => ({ ...e, slotKey: key, slotIndex: i, itineraryLabel: SLOT_LABELS[key] }));
      return { key, label: SLOT_LABELS[key], items: items.length ? items : [createSlotPlaceholder(key)] };
    });
  }

  const assignments = getDaySlotAssignments(safe, dayIndex);
  const byId = new Map(safe.filter(e => isFinite(Number(e?.id))).map(e => [Number(e.id), e]));

  return SLOT_ORDER.map(key => {
    const items = (assignments[key] || [])
      .map((id, i) => {
        const e = isFinite(Number(id)) ? byId.get(Number(id)) : null;
        return e ? { ...e, slotKey: key, slotIndex: i, itineraryLabel: SLOT_LABELS[key] } : null;
      }).filter(Boolean);
    return { key, label: SLOT_LABELS[key], items: items.length ? items : [createSlotPlaceholder(key)] };
  });
}

function buildStructuredSlotEvents(...args) {
  return buildStructuredSlots(...args);
}
window.buildStructuredSlotEvents = buildStructuredSlotEvents;

// ── Plan state helpers ────────────────────────────────────
function getActiveDayEvents(dayIndex = currentDayIndex) {
  return Array.isArray(multiDayPlans[dayIndex]) ? multiDayPlans[dayIndex].filter(Boolean) : [];
}

function getStopTitle(event) {
  return event?.title || event?.title_en || event?.name || "";
}

function getStopCoordinates(event) {
  const lat = parseFloat(event?.latitude ?? event?.lat);
  const lng = parseFloat(event?.longitude ?? event?.lng);
  if (!isFinite(lat) || !isFinite(lng)) return null;
  return { lat, lng };
}

function coordinateQuery(point) {
  return `${point.lat},${point.lng}`;
}

function buildDailyRouteUrl(stops) {
  const realStops = (Array.isArray(stops) ? stops : []).filter(e => e && !e._placeholder);
  const coordinateStops = realStops
    .map(event => ({ event, point: getStopCoordinates(event) }))
    .filter(row => row.point);

  if (coordinateStops.length >= 2) {
    const origin = coordinateQuery(coordinateStops[0].point);
    const destination = coordinateQuery(coordinateStops[coordinateStops.length - 1].point);
    const waypoints = coordinateStops.slice(1, -1).map(row => coordinateQuery(row.point));
    const params = new URLSearchParams({
      api: "1",
      origin,
      destination,
      travelmode: "driving",
    });
    if (waypoints.length) params.set("waypoints", waypoints.join("|"));
    return `https://www.google.com/maps/dir/?${params.toString()}`;
  }

  if (coordinateStops.length === 1) {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(coordinateQuery(coordinateStops[0].point))}`;
  }

  const firstTitle = realStops.map(getStopTitle).find(Boolean);
  if (firstTitle) {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${firstTitle} Riyadh`)}`;
  }

  return "";
}

function buildEventMapUrl(event) {
  const point = getStopCoordinates(event);
  if (point) {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(coordinateQuery(point))}`;
  }
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((event?.title || "") + " Riyadh")}`;
}

function buildUberUrl(event) {
  const point = getStopCoordinates(event);
  if (point) {
    return `https://m.uber.com/ul/?action=setPickup&dropoff[latitude]=${point.lat}&dropoff[longitude]=${point.lng}&dropoff[nickname]=${encodeURIComponent(event?.title || "")}`;
  }
  return `https://m.uber.com/ul/?action=setPickup&dropoff[nickname]=${encodeURIComponent((event?.title || "") + " Riyadh")}`;
}

function updateRouteNavigationCard(stops) {
  const card = document.getElementById("routeNavigationCard");
  const btn = document.getElementById("openRouteBtn");
  if (!card || !btn) return;

  const url = buildDailyRouteUrl(stops);
  if (!url) {
    card.classList.add("hidden");
    btn.disabled = true;
    btn.dataset.routeUrl = "";
    return;
  }

  btn.disabled = false;
  btn.dataset.routeUrl = url;
  card.classList.remove("hidden");
  if (window.lucide) window.lucide.createIcons();
}

// ── Preferences ───────────────────────────────────────────
async function refreshPreferences() {
  try {
    const data = await apiGet("/api/auth/me/");
    if (!data) return _currentPreferences;
    _currentPreferences = data;
    if (data.trip_duration) localStorage.setItem("tz_trip_duration", String(data.trip_duration));
    if (!localStorage.getItem(PLAN_START_KEY) && data.start_date) {
      localStorage.setItem(PLAN_START_KEY, data.start_date);
      if (data.end_date) localStorage.setItem(PLAN_END_KEY, data.end_date);
    }
  } catch (e) { console.error("Preferences fetch failed:", e); }
  return _currentPreferences;
}

// ── UI helpers ────────────────────────────────────────────
function showPlanMessage(text, tone = "info") {
  const el = document.getElementById("plan-message");
  if (!el) return;
  if (!text) { el.classList.add("hidden"); el.textContent = ""; return; }
  el.textContent = text;
  el.className = `text-sm text-center rounded-xl py-2 ${
    tone === "error"   ? "text-red-600 bg-red-50" :
    tone === "success" ? "text-green-700 bg-green-50" :
                         "text-gray-500 bg-gray-50"
  }`;
  el.classList.remove("hidden");
}

function setLoading(on) {
  _isPlanLoading = on;
  document.getElementById("skeleton")?.classList.toggle("hidden", !on);
  if (on) {
    document.getElementById("timeline")?.classList.add("hidden");
    document.getElementById("emptyState")?.classList.add("hidden");
    document.getElementById("routeNavigationCard")?.classList.add("hidden");
  }
}

// ── Hero update ───────────────────────────────────────────
function updateHero(dayIndex = currentDayIndex) {
  try {
    const date = getPlanDateForIndex(dayIndex);

    const dateEl = document.getElementById("heroDate");
    if (dateEl) {
      dateEl.textContent = date.toLocaleDateString(document.documentElement?.lang === "ar" ? "ar-SA-u-ca-gregory" : "en-GB", { weekday: "long", day: "numeric", month: "long" });
    }

    const dayY = getTripDuration();
    const badge = document.getElementById("dayBadge");
    if (badge) {
      badge.textContent = `Day ${dayIndex + 1} of ${dayY}`;
      badge.classList.remove("hidden");
      badge.classList.add("inline-flex");
    }

    // Activity count
    const count  = getActiveDayEvents(dayIndex).filter(e => !e._placeholder).length;
    const countEl = document.getElementById("activityCount");
    if (countEl) countEl.textContent = count > 0 ? `${count} ${count === 1 ? "activity" : "activities"} planned` : "";
  } catch (e) { /* fail silently */ }
}

// ── Day Tabs ──────────────────────────────────────────────
function renderDayTabs() {
  const container = document.getElementById("dayTabs");
  if (!container) return;

  const duration = getTripDuration();
  container.innerHTML = "";

  for (let i = 0; i < duration; i++) {
    const isActive = i === currentDayIndex;
    const hasPlan  = Array.isArray(multiDayPlans[i]) && multiDayPlans[i].length > 0;
    const date     = getPlanDateForIndex(i);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "relative shrink-0 flex flex-col items-center px-5 py-2.5 rounded-xl text-sm font-semibold transition-all";

    if (isActive) {
      btn.style.cssText = "background-color:var(--tz-violet);color:white;";
    } else {
      btn.className += " bg-white border border-gray-200 text-gray-600 hover:border-violet-300";
    }

    btn.setAttribute("aria-pressed", String(isActive));
    const label = document.createElement("span");
    label.textContent = `Day ${i + 1}`;
    btn.appendChild(label);

    const sub = document.createElement("span");
    sub.className = `text-xs font-normal ${isActive ? "text-white/70" : "text-gray-400"}`;
    sub.textContent = date.toLocaleDateString(document.documentElement?.lang === "ar" ? "ar-SA-u-ca-gregory" : "en-GB", { weekday: "short", day: "numeric", month: "short" });
    btn.appendChild(sub);

    if (hasPlan && !isActive) {
      const dot = document.createElement("span");
      dot.className = "absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-violet-400";
      btn.appendChild(dot);
    }

    btn.addEventListener("click", () => {
      currentDayIndex = i;
      setSelectedPlanDate(_localDateStr(date));
      renderDayTabs();
      renderTimeline(i);
    });

    container.appendChild(btn);
  }
  if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => {
    const active = container.querySelector('[aria-pressed="true"]');
    if (!active) return;
    const rect = active.getBoundingClientRect(), bounds = container.getBoundingClientRect();
    container.scrollLeft += rect.left - bounds.left - (bounds.width - rect.width) / 2;
  });

}

// Preserve each slot's original action index while displaying suggested times chronologically.
function getTimelineEntries(slots) {
  return slots.flatMap(slot => slot.items.map((event, slotIndex) => {
    const times = SLOT_TIMES[slot.key];
    const time = times[Math.min(slotIndex, times.length - 1)];
    const [clock, period] = time.split(" ");
    const [hour, minute] = clock.split(":").map(Number);
    return {slotKey: slot.key, event, slotIndex,
      minutes: (hour % 12 + (period === "PM" ? 12 : 0)) * 60 + minute};
  })).sort((a, b) => a.minutes - b.minutes);
}

// ── Timeline card builder ─────────────────────────────────
function buildTimelineCard(slotKey, event, slotIndex) {
  const gradient  = SLOT_GRADIENTS[slotKey] || SLOT_GRADIENTS.activity;
  const times     = SLOT_TIMES[slotKey] || ["09:00 AM"];
  const time      = times[Math.min(slotIndex, times.length - 1)];
  const slotLabel = SLOT_LABELS[slotKey] || slotKey;

  if (event._placeholder) {
    return `
      <div class="space-y-2">
        <div class="flex items-center gap-2 px-1 text-sm text-gray-400">
          <span class="font-semibold text-gray-500">${escapeHtml(time)}</span>
          <span class="text-gray-300">•</span>
          <span>${escapeHtml(slotLabel)}</span>
        </div>
        <div class="rounded-2xl border-2 border-dashed border-violet-100 bg-white/75 py-7 text-center text-gray-400 text-sm">
          <p>No ${escapeHtml(slotLabel.toLowerCase())} planned yet</p>
          <button type="button"
            data-slot-key="${escapeHtml(slotKey)}"
            data-day-index="${currentDayIndex}"
            class="placeholder-add-btn mt-3 inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold text-violet-700 bg-violet-50 hover:bg-violet-100 transition">
            <i data-lucide="plus" class="w-4 h-4"></i>
            Add to ${escapeHtml(slotLabel)}
          </button>
        </div>
      </div>`;
  }

  const emoji     = categoryEmoji(event.category);
  const price     = formatPrice(event.price);
  const catLabel  = formatCategory(event.category);
  const rating    = event.rating ? `★ ${parseFloat(event.rating).toFixed(1)}` : "";
  const imageUrl  = getEventImageUrl(event);
  const googleMapsUrl = buildEventMapUrl(event);
  const uberUrl = buildUberUrl(event);

  const navigateBtn = `<button type="button"
      class="navigate-btn inline-flex items-center justify-center gap-1.5 px-5 py-2.5 rounded-xl text-sm font-semibold text-white shadow-sm hover:opacity-90 transition"
      style="background-color:var(--tz-violet)"
      data-navigate-url="${escapeHtml(googleMapsUrl)}">
      <i data-lucide="map-pinned" class="w-4 h-4"></i>
      Navigate
    </button>`;

  return `
    <div class="space-y-2">
      <div class="flex items-center gap-2 px-1 text-sm text-gray-500">
        <span class="font-semibold text-gray-700">${escapeHtml(time)}</span>
        <span class="text-gray-300">•</span>
        <span>${escapeHtml(slotLabel)}</span>
      </div>
      <div class="rounded-2xl p-5 shadow-sm" style="background:${gradient}">
        <div class="flex ${imageUrl ? 'flex-col sm:flex-row' : 'flex-row'} items-start gap-4 mb-4">
          ${imageUrl ? `
            <div class="timeline-media w-full sm:w-32 h-40 sm:h-32 rounded-2xl overflow-hidden shrink-0">
              <img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(event.title || "")}" loading="lazy"
                class="h-full w-full object-cover relative z-10"
                onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">
              <span class="absolute inset-0 flex items-center justify-center" aria-hidden="true"><i data-lucide="${catIcon(event.category)}"></i></span>
            </div>
          ` : `<span class="slot-category-icon" aria-hidden="true"><i data-lucide="${catIcon(event.category)}"></i></span>`}
          <div class="flex-1 min-w-0 pt-1">
            <h3 data-user-content class="text-xl font-bold text-gray-900 leading-snug">${escapeHtml(event.title || "")}</h3>
            <div class="flex items-center flex-wrap gap-2 mt-1.5">
              <span class="inline-flex text-xs px-2.5 py-0.5 rounded-full bg-white/70 text-gray-600 font-medium">
                ${escapeHtml(catLabel)}
              </span>
              ${rating ? `<span class="text-xs text-amber-600 font-semibold">${escapeHtml(rating)}</span>` : ""}
              <span class="text-xs text-gray-500">${escapeHtml(price)}</span>
            </div>
            <p class="distance-label text-xs text-gray-400 mt-1"
               data-lat="${event.latitude || ""}" data-lng="${event.longitude || ""}"></p>
          </div>
        </div>
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-t border-white/40 pt-4">
          <div class="flex items-center gap-2 flex-wrap">
            ${navigateBtn}
            <button type="button"
              class="try-another-btn inline-flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-xl text-sm font-semibold text-gray-700 bg-white/75 hover:bg-white border border-white/50 hover:border-gray-200 transition"
              data-event-id="${event.id}"
              data-slot-key="${escapeHtml(slotKey)}"
              data-slot-index="${slotIndex}"
              data-plan-item-id="${event.plan_item_id || ""}">
              <i data-lucide="shuffle" class="w-4 h-4"></i>
              Replace
            </button>
          </div>
          <div class="flex items-center gap-2 sm:justify-end">
            <details class="plan-action-menu relative">
              <summary class="cursor-pointer inline-flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-xl text-sm font-semibold text-gray-700 bg-white/75 hover:bg-white border border-white/50 hover:border-gray-200 transition">
                <i data-lucide="car" class="w-4 h-4"></i>
                Ride
              </summary>
              <div class="mt-2 sm:absolute sm:right-0 sm:bottom-full sm:mb-2 z-20 grid grid-cols-2 gap-2 rounded-2xl border border-gray-100 bg-white p-2 shadow-lg min-w-[180px]">
                <button type="button"
                  class="navigate-btn px-3 py-2 rounded-xl text-sm font-semibold text-gray-700 bg-gray-50 hover:bg-gray-100 transition"
                  data-navigate-url="${escapeHtml(uberUrl)}">
                  Uber
                </button>
                <button type="button"
                  class="navigate-btn px-3 py-2 rounded-xl text-sm font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 transition"
                  data-navigate-url="${escapeHtml(DARB_APP_URL)}">
                  Metro
                </button>
              </div>
            </details>
            <button type="button"
              class="remove-btn inline-flex items-center justify-center w-11 h-11 rounded-xl text-red-500 bg-white/70 hover:bg-white border border-white/50 hover:border-red-200 transition"
              data-event-id="${event.id}"
              data-slot-key="${escapeHtml(slotKey)}"
              data-plan-item-id="${event.plan_item_id || ""}"
              title="Remove activity"
              aria-label="Remove activity">
              <i data-lucide="trash-2" class="w-4 h-4"></i>
            </button>
          </div>
        </div>
      </div>
    </div>`;
}

function bindTimelineActions(container, dayIndex) {
  container.querySelectorAll(".placeholder-add-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      openAddActivityModal({
        dayIndex: Number(btn.dataset.dayIndex || dayIndex),
        slotKey: btn.dataset.slotKey || "activity",
      });
    });
  });

  container.querySelectorAll(".navigate-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const url = btn.dataset.navigateUrl;
      if (url) window.open(url, "_blank", "noopener,noreferrer");
    });
  });

  container.querySelectorAll(".try-another-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const eventId   = Number(btn.dataset.eventId);
      const slotKey   = btn.dataset.slotKey;
      const slotIndex = Number(btn.dataset.slotIndex);
      btn.disabled = true; btn.textContent = "Loading…";
      try {
        await replaceActivityForSlot(slotKey, isFinite(eventId) ? eventId : null, { dayIndex, itemIndex: slotIndex });
      } catch (e) {
        console.error("Replace failed:", e);
        showPlanMessage("No alternative found for this slot.", "error");
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="shuffle" class="w-4 h-4"></i> Replace';
        if (window.lucide) window.lucide.createIcons();
      }
    });
  });

  container.querySelectorAll(".remove-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const eventId = Number(btn.dataset.eventId);
      const slotKey = btn.dataset.slotKey;
      const itemId  = btn.dataset.planItemId ? Number(btn.dataset.planItemId) : null;
      btn.disabled = true; btn.textContent = "Removing…";
      try {
        await removeEventFromPlan(eventId, slotKey, { dayIndex, itemId });
      } catch (e) {
        console.error("Remove failed:", e);
        showPlanMessage("Could not remove this activity.", "error");
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="trash-2" class="w-4 h-4"></i>';
        if (window.lucide) window.lucide.createIcons();
      }
    });
  });
}

async function populateDistanceLabels(container) {
  const userLoc = await getUserLocation();
  if (!userLoc) return;
  container.querySelectorAll(".distance-label[data-lat]").forEach(el => {
    const lat = parseFloat(el.dataset.lat), lng = parseFloat(el.dataset.lng);
    if (!isFinite(lat) || !isFinite(lng)) return;
    const km = haversineKm(userLoc.lat, userLoc.lng, lat, lng);
    el.textContent = km < 1 ? `${(km * 1000).toFixed(0)} m from you` : `${km.toFixed(1)} km from you`;
  });
}

function renderTimeline(dayIndex = currentDayIndex) {
  const container  = document.getElementById("timeline");
  const emptyEl    = document.getElementById("emptyState");
  const skeletonEl = document.getElementById("skeleton");
  const mapSection = document.getElementById("mapSection");
  if (!container) return;

  const events = getActiveDayEvents(dayIndex);
  skeletonEl?.classList.add("hidden");

  if (!events.length) {
    if (_dayHasPlan[dayIndex]) {
      emptyEl?.classList.add("hidden");
      mapSection?.classList.add("hidden");
      updateRouteNavigationCard([]);
      const slots = buildStructuredSlots([], dayIndex);
      container.innerHTML = getTimelineEntries(slots)
        .map(entry => buildTimelineCard(entry.slotKey, entry.event, entry.slotIndex))
        .join("");
      container.classList.remove("hidden");
      bindTimelineActions(container, dayIndex);
      if (window.lucide) window.lucide.createIcons();
      updateHero(dayIndex);
      return;
    }
    container.classList.add("hidden");
    container.innerHTML = "";
    emptyEl?.classList.remove("hidden");
    mapSection?.classList.add("hidden");
    updateRouteNavigationCard([]);
    updateHero(dayIndex);
    return;
  }

  emptyEl?.classList.add("hidden");

  const slots   = buildStructuredSlots(events, dayIndex);
  const allReal = getTimelineEntries(slots).map(entry => entry.event).filter(e => e && !e._placeholder);

  container.innerHTML = getTimelineEntries(slots)
    .map(entry => buildTimelineCard(entry.slotKey, entry.event, entry.slotIndex))
    .join("");
  container.classList.remove("hidden");

  bindTimelineActions(container, dayIndex);
  if (window.lucide) window.lucide.createIcons();
  populateDistanceLabels(container).catch(() => {});

  if (allReal.length) {
    mapSection?.classList.add("hidden");
    updateRouteNavigationCard(allReal);
  } else {
    updateRouteNavigationCard([]);
  }

  updateHero(dayIndex);
}

function renderDailyPlan(planOrDayIndex = currentDayIndex) {
  if (planOrDayIndex && typeof planOrDayIndex === "object" && !Array.isArray(planOrDayIndex)) {
    const normalized = normalizePlanPayload(planOrDayIndex);
    multiDayPlans[currentDayIndex] = Array.isArray(normalized.events) ? normalized.events : [];
    if (Array.isArray(planOrDayIndex.events) || Array.isArray(planOrDayIndex.items) || normalized.id) {
      _dayHasPlan[currentDayIndex] = true;
    }
    if (normalized.date) {
      _currentPlan = normalized;
      setSelectedPlanDate(normalized.date);
    }
    return renderTimeline(currentDayIndex);
  }
  return renderTimeline(planOrDayIndex);
}

window.renderDailyPlan = renderDailyPlan;

// ── Plan loading ──────────────────────────────────────────
async function loadCurrentPlan(options = {}) {
  setLoading(true);
  try {
    const requestedDate = new URLSearchParams(window.location.search || "").get("date");
    _viewedSavedDate = null;
    await refreshPreferences();
    multiDayPlans       = [];
    _slotAssignmentsByDay = {};
    _slotFeedbackByDay    = {};
    _slotBlockedIdsByDay  = {};

    const data  = await apiGet("/api/daily-plan/");
    const plans = (Array.isArray(data) ? data : (data?.results || [])).map(p => normalizePlanPayload(p));
    if (plans.some(plan => plan.date === requestedDate) &&
        (requestedDate < getStoredPlanStartDate() || requestedDate > (getStoredPlanEndDate() || getStoredPlanStartDate()))) {
      _viewedSavedDate = requestedDate;
    }
    const duration = getTripDuration();
    const start = new Date(`${getStoredPlanStartDate()}T00:00:00`);
    const selectedIndex = Math.round((new Date(`${requestedDate}T00:00:00`) - start) / 86400000);
    const requestedDayIndex = options.dayIndex !== undefined && isFinite(Number(options.dayIndex))
      ? Number(options.dayIndex) : (isFinite(selectedIndex) ? selectedIndex : currentDayIndex);

    for (let i = 0; i < duration; i++) {
      const day   = new Date(start); day.setDate(start.getDate() + i);
      const match = plans.find(p => p.date === _localDateStr(day));
      multiDayPlans[i] = match?.events?.length ? match.events.filter(Boolean) : [];
      if (match?.events?.length) _dayHasPlan[i] = true;
    }

    currentDayIndex = Math.min(Math.max(requestedDayIndex, 0), Math.max(duration - 1, 0));
    const selectedDate = new Date(start);
    selectedDate.setDate(start.getDate() + currentDayIndex);
    setSelectedPlanDate(_localDateStr(selectedDate));
    _currentPlan = plans.find(plan => plan.date === _localDateStr(selectedDate)) || null;
    renderDayTabs();
    renderTimeline(currentDayIndex);
  } catch (e) {
    console.error("Failed to load plan:", e);
    renderDayTabs();
    renderTimeline(currentDayIndex);
    document.getElementById("emptyState")?.classList.add("hidden");
    showPlanMessage("Unable to load your itinerary. Please reload to try again.", "error");
  } finally {
    setLoading(false);
  }
}

// ── Plan generation ───────────────────────────────────────
async function ensurePlanGenerationReady() {
  await refreshPreferences();
  const interests = Array.isArray(_currentPreferences?.interests)
    ? _currentPreferences.interests.filter(Boolean) : [];
  if (!interests.length) {
    showPlanMessage(
      "Set your preferences before generating a plan.",
      "info"
    );
    return false;
  }
  return true;
}

function _setBtnGenerating(btn, on) {
  if (!btn) return;
  btn.disabled = on;
  const label = document.getElementById("generate-plan-btn-label");
  if (label) label.textContent = on ? "Generating..." : "Regenerate Day";
}

async function generateAllDays(btn) {
  _setBtnGenerating(btn, true);
  setLoading(true);
  const snapshotPlans = [...multiDayPlans];
  const snapshotPlan  = _currentPlan;
  _currentPlan = null; multiDayPlans = [];
  _slotAssignmentsByDay = {}; _slotFeedbackByDay = {}; _slotBlockedIdsByDay = {};
  try {
    if (!await ensurePlanGenerationReady()) {
      multiDayPlans = snapshotPlans;
      _currentPlan = snapshotPlan;
      renderDayTabs();
      renderTimeline(currentDayIndex);
      return;
    }
    const payload = { start_date: getStoredPlanStartDate() };
    const end = getStoredPlanEndDate();
    if (end) payload.end_date = end;

    const resp  = await apiPost("/api/daily-plan/generate-multiday/", payload);
    const plans = Array.isArray(resp?.plans) ? resp.plans : [];
    plans.sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
    plans.forEach((plan, i) => {
      const events = normalizePlanPayload(plan).events;
      multiDayPlans[i] = events;
      if (events?.length) _dayHasPlan[i] = true;
    });
    const duration = getTripDuration();
    for (let i = 0; i < duration; i++) { if (!Array.isArray(multiDayPlans[i])) multiDayPlans[i] = []; }

    _currentPlan    = plans[0] ? normalizePlanPayload(plans[0]) : null;
    currentDayIndex = 0;
    setSelectedPlanDate(getStoredPlanStartDate());
    renderDayTabs(); renderTimeline(0);
    showPlanMessage("Plan generated!", "success");
    setTimeout(() => showPlanMessage(""), 3000);
  } catch (e) {
    multiDayPlans = snapshotPlans;
    _currentPlan  = snapshotPlan;
    renderDayTabs();
    renderTimeline(currentDayIndex);
    handleGenerateError(e);
  } finally { setLoading(false); _setBtnGenerating(btn, false); }
}

async function requestPlanForDay(btn) {
  _setBtnGenerating(btn, true);
  setLoading(true);
  const snapshotEvents = multiDayPlans[currentDayIndex] ? [...multiDayPlans[currentDayIndex]] : [];
  const snapshotPlan   = _currentPlan;
  try {
    if (!await ensurePlanGenerationReady()) return;
    const targetDate = _localDateStr(getPlanDateForIndex(currentDayIndex));
    const selectedStart = getStoredPlanStartDate();
    const selectedEnd = getStoredPlanEndDate();
    const payload = { date: targetDate, start_date: selectedStart, seed: Date.now(), exclude_plan_dates: Array.from({length: getTripDuration()}, (_, index) => _localDateStr(getPlanDateForIndex(index))).filter(value => value !== targetDate) };
    if (selectedEnd) payload.end_date = selectedEnd;

    const resp   = normalizePlanPayload(await apiPost("/api/daily-plan/generate/", payload));
    const events = Array.isArray(resp?.events) ? resp.events.filter(Boolean) : [];
    delete _slotAssignmentsByDay[currentDayIndex];
    delete _slotFeedbackByDay[currentDayIndex];
    delete _slotBlockedIdsByDay[currentDayIndex];
    multiDayPlans[currentDayIndex] = events;
    if (events.length) _dayHasPlan[currentDayIndex] = true;
    _currentPlan = resp || _currentPlan;
    setSelectedPlanDate(targetDate);
    renderDayTabs(); renderTimeline(currentDayIndex);
    showPlanMessage("Plan updated!", "success");
    setTimeout(() => showPlanMessage(""), 3000);
  } catch (e) {
    multiDayPlans[currentDayIndex] = snapshotEvents;
    _currentPlan = snapshotPlan;
    renderDayTabs();
    renderTimeline(currentDayIndex);
    handleGenerateError(e);
  } finally { setLoading(false); _setBtnGenerating(btn, false); }
}

function requestPlanForSelectedDate(...args) {
  return requestPlanForDay(...args);
}
window.requestPlanForSelectedDate = requestPlanForSelectedDate;

function handleGenerateError(error) {
  const msg = error?.status === 404
    ? "No places match your current preferences. <a href='/onboarding/' class='underline text-violet-600'>Adjust preferences →</a>"
    : "Could not generate plan. Please try again.";
  const el = document.getElementById("plan-message");
  if (el) {
    el.innerHTML = msg;
    el.className = "text-sm text-center rounded-xl py-2 text-red-600 bg-red-50";
    el.classList.remove("hidden");
  }
}

// ── Remove & Replace ──────────────────────────────────────
async function findPlanForDate(targetDate) {
  if (_currentPlan?.date === targetDate && _currentPlan?.id) return _currentPlan;
  const data  = await apiGet("/api/daily-plan/");
  const plans = (Array.isArray(data) ? data : (data?.results || [])).map(p => normalizePlanPayload(p));
  return plans.find(p => p.date === targetDate) || null;
}

async function persistCurrentDayEvents(rawEvents, dayIndex = currentDayIndex) {
  const targetDate = _localDateStr(getPlanDateForIndex(dayIndex));
  const ids        = rawEvents.filter(e => e && !e._placeholder).map(e => Number(e.id)).filter(id => isFinite(id));
  const plan       = await findPlanForDate(targetDate);
  if (plan?.id) {
    return normalizePlanPayload(await apiPut(`/api/daily-plan/${plan.id}/`, { date: targetDate, events: ids }));
  }
  if (!ids.length) return null;
  return normalizePlanPayload(await apiPost("/api/daily-plan/", { date: targetDate, events: ids }));
}

async function getReplacementCandidates(dayIndex = currentDayIndex) {
  const targetDate = _localDateStr(getPlanDateForIndex(dayIndex));
  if (_replacementCache.has(targetDate)) return _replacementCache.get(targetDate);
  const data = await apiGet(`/api/events/filtered/?date_from=${encodeURIComponent(targetDate)}&date_to=${encodeURIComponent(targetDate)}`);
  let candidates = Array.isArray(data) ? data : (data?.results || []);
  _replacementCache.set(targetDate, candidates);
  return candidates;
}

function pickReplacement(slotKey, candidates, excludedIds) {
  const excl = new Set([...excludedIds].map(Number).filter(isFinite));
  const pool = candidates.filter(c => { const id = Number(c?.id); return isFinite(id) && !excl.has(id); });
  if (slotKey === "breakfast" || slotKey === "lunch") {
    return pool.find(c => String(c.category || "").toLowerCase() === "food") || null;
  }
  return pool.find(c => String(c.category || "").toLowerCase() !== "food") || pool[0] || null;
}

function updateCurrentDayEvents(events, planData = null, options = {}) {
  const dayIndex = isFinite(options.dayIndex) ? options.dayIndex : currentDayIndex;
  const plan     = planData ? normalizePlanPayload(planData) : null;
  const source   = plan?.events || events;
  const safe     = (Array.isArray(source) ? source : []).map((e, i) => normalizePlanEvent(e, i)).filter(Boolean);
  multiDayPlans[dayIndex] = safe;
  const targetDate = _localDateStr(getPlanDateForIndex(dayIndex));
  if (plan) {
    _currentPlan = { ...plan, date: targetDate, events: safe, count: safe.length };
  } else if (_currentPlan?.date === targetDate) {
    _currentPlan = { ..._currentPlan, date: targetDate, events: safe, count: safe.length };
  }
  if (dayIndex === currentDayIndex) { renderDayTabs(); renderTimeline(dayIndex); }
}

async function replaceActivityForSlot(slotKey, currentEventId = null, options = {}) {
  const dayIndex  = isFinite(options.dayIndex)  ? options.dayIndex  : currentDayIndex;
  const itemIndex = isFinite(options.itemIndex) ? options.itemIndex : 0;
  const current   = getActiveDayEvents(dayIndex).filter(e => !e._placeholder);
  const excl      = new Set(current.map(e => Number(e?.id)).filter(isFinite));
  const blocked   = _slotBlockedIdsByDay[dayIndex]?.[slotKey] || [];
  blocked.forEach(id => excl.add(Number(id)));
  if (currentEventId !== null) excl.add(Number(currentEventId));

  const candidates  = await getReplacementCandidates(dayIndex);
  const replacement = pickReplacement(slotKey, candidates, excl);
  if (!replacement) { alert("No more alternatives available for this slot."); return; }

  const targetDate    = _localDateStr(getPlanDateForIndex(dayIndex));
  const plan          = await findPlanForDate(targetDate);
  const currentEvent  = current.find(e => Number(e?.id) === Number(currentEventId));

  if (currentEvent?.plan_item_id && plan?.id) {
    const updated = normalizePlanPayload(
      await apiPatch(`/api/daily-plan/${plan.id}/items/${currentEvent.plan_item_id}/`, { event_id: Number(replacement.id) })
    );
    await loadCurrentPlan();
    return;
  }

  const next = [...current];
  const idx  = next.findIndex(e => Number(e?.id) === Number(currentEventId));
  if (idx >= 0) next[idx] = replacement; else next.push(replacement);

  const prevAssign    = cloneSlotAssignments(getDaySlotAssignments(current, dayIndex));
  const nextAssign    = cloneSlotAssignments(prevAssign);
  const nextSlotIds   = [...(nextAssign[slotKey] || [])];
  if (idx >= 0 && itemIndex < nextSlotIds.length) nextSlotIds[itemIndex] = Number(replacement.id);
  else if (nextSlotIds.length < getSlotLimit(slotKey)) nextSlotIds.push(Number(replacement.id));
  nextAssign[slotKey] = nextSlotIds.slice(0, getSlotLimit(slotKey));
  _slotAssignmentsByDay[dayIndex] = cloneSlotAssignments(nextAssign);

  if (!_slotBlockedIdsByDay[dayIndex]) _slotBlockedIdsByDay[dayIndex] = {};
  _slotBlockedIdsByDay[dayIndex][slotKey] = [
    ...new Set([...(blocked || []), Number(currentEventId) || null, Number(replacement.id)].filter(id => isFinite(id)))
  ];

  await persistCurrentDayEvents(next, dayIndex);
  await loadCurrentPlan();
}

async function removeEventFromPlan(eventId, slotKey = "evening", options = {}) {
  const dayIndex     = isFinite(options.dayIndex) ? options.dayIndex : currentDayIndex;
  const normalizedId = Number(eventId);
  const itemId       = isFinite(Number(options.itemId)) ? Number(options.itemId) : null;
  if (!isFinite(normalizedId) || normalizedId <= 0) throw new Error("Invalid event ID");

  const current = getActiveDayEvents(dayIndex);
  const next    = current.filter(e => Number(e?.id) !== normalizedId);
  if (next.length === current.length) return;

  const prevAssign  = cloneSlotAssignments(getDaySlotAssignments(current, dayIndex));
  const nextAssign  = cloneSlotAssignments(prevAssign);
  nextAssign[slotKey] = (nextAssign[slotKey] || []).filter(id => Number(id) !== normalizedId);
  _slotAssignmentsByDay[dayIndex] = cloneSlotAssignments(nextAssign);
  if (!_slotBlockedIdsByDay[dayIndex]) _slotBlockedIdsByDay[dayIndex] = {};
  _slotBlockedIdsByDay[dayIndex][slotKey] = [...new Set([...(_slotBlockedIdsByDay[dayIndex][slotKey] || []), normalizedId])];

  const prev = [...current];
  updateCurrentDayEvents(next, null, { dayIndex });

  const targetDate = _localDateStr(getPlanDateForIndex(dayIndex));
  try {
    const plan = await findPlanForDate(targetDate);
    if (!plan?.id) return;
    const updated = normalizePlanPayload(
      itemId
        ? await apiDelete(`/api/daily-plan/${plan.id}/items/${itemId}/`)
        : await apiDelete(`/api/daily-plan/${plan.id}/events/${normalizedId}/`)
    );
    _dayHasPlan[dayIndex] = true;
    await loadCurrentPlan();
  } catch (e) {
    _slotAssignmentsByDay[dayIndex] = cloneSlotAssignments(prevAssign);
    updateCurrentDayEvents(prev, null, { dayIndex });
    throw e;
  }
}

// ── Add Activity Modal ────────────────────────────────────
function openAddActivityModal(options = {}) {
  const dayIndex = isFinite(Number(options.dayIndex)) ? Number(options.dayIndex) : currentDayIndex;
  _addActivityContext = {
    dayIndex,
    slotKey: options.slotKey || "activity",
  };
  setSelectedPlanDate(_localDateStr(getPlanDateForIndex(dayIndex)));
  const contextLabel = document.getElementById("addActivityContextLabel");
  if (contextLabel) {
    const slotLabel = SLOT_LABELS[_addActivityContext.slotKey] || "Activity";
    contextLabel.textContent = `Day ${dayIndex + 1} - ${slotLabel}`;
  }
  document.getElementById("addActivityModal")?.classList.remove("hidden");
  const input = document.getElementById("activitySearchInput");
  if (input) input.value = "";
  const results = document.getElementById("activitySearchResults");
  if (results) results.innerHTML = '<p class="text-sm text-gray-400 text-center py-8">Type to search for places</p>';
  setTimeout(() => input?.focus(), 50);
}

function closeAddActivityModal() {
  document.getElementById("addActivityModal")?.classList.add("hidden");
  _addActivityContext = { dayIndex: currentDayIndex, slotKey: "activity" };
}

function renderActivityResults(events) {
  const container = document.getElementById("activitySearchResults");
  if (!container) return;
  if (!events.length) {
    container.innerHTML = '<p class="text-sm text-gray-400 text-center py-8">No results found</p>';
    return;
  }
  container.innerHTML = events.map(e => `
    <div class="flex items-center gap-3 p-3 rounded-xl border border-gray-100 cursor-pointer hover:bg-gray-50 transition"
         data-event-id="${e.id}">
      ${getEventImageUrl(e) ? `
        <div class="w-11 h-11 rounded-xl overflow-hidden bg-gray-100 shrink-0">
          <img src="${escapeHtml(getEventImageUrl(e))}" alt="${escapeHtml(e.title || "")}" loading="lazy"
            class="h-full w-full object-cover relative z-10"
            onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">
          <span class="h-full w-full items-center justify-center text-xl" style="display:none">${categoryEmoji(e.category)}</span>
        </div>
      ` : `<span class="text-2xl shrink-0">${categoryEmoji(e.category)}</span>`}
      <div class="min-w-0 flex-1">
        <div class="text-sm font-medium text-gray-800 truncate">${escapeHtml(e.title || "")}</div>
        <div class="text-xs text-gray-500">${escapeHtml(formatCategory(e.category))}</div>
      </div>
    </div>`).join("");

  container.querySelectorAll("[data-event-id]").forEach(card => {
    card.addEventListener("click", async () => {
      const id       = Number(card.dataset.eventId);
      const dayIndex = isFinite(Number(_addActivityContext.dayIndex)) ? Number(_addActivityContext.dayIndex) : currentDayIndex;
      const slotKey  = _addActivityContext.slotKey || "activity";
      const date     = _localDateStr(getPlanDateForIndex(dayIndex));
      if (!isFinite(id) || !date) return;
      card.classList.add("opacity-50");
      try {
        await apiPost("/api/daily-plan/add/", { date, event_id: id, slot_type: slotKey });
        closeAddActivityModal();
        await loadCurrentPlan({ dayIndex });
        showPlanMessage("Activity added to your plan.", "success");
      } catch (e) {
        console.error("Add activity failed:", e);
        showPlanMessage("Could not add this activity. It may already be in your plan.", "error");
        card.classList.remove("opacity-50");
      }
    });
  });
}

async function searchActivities(query) {
  const container = document.getElementById("activitySearchResults");
  if (!container) return;
  if (!query.trim()) {
    container.innerHTML = '<p class="text-sm text-gray-400 text-center py-8">Type to search for places</p>';
    return;
  }
  container.innerHTML = '<p class="text-sm text-gray-400 text-center py-8">Searching…</p>';
  try {
    const data   = await apiGet(`/api/events/?search=${encodeURIComponent(query)}`);
    const events = Array.isArray(data) ? data : (data?.results || []);
    renderActivityResults(events);
  } catch (e) {
    container.innerHTML = '<p class="text-sm text-red-400 text-center py-8">Search failed. Please try again.</p>';
  }
}

// ── Map ───────────────────────────────────────────────────
function initDailyPlanMap() {
  const el = document.getElementById("dailyPlanMap");
  if (el) {
    el.innerHTML = '<div class="h-full flex items-center justify-center text-sm text-gray-400">Use the route navigation card below.</div>';
  }
}

function updateMapMarkers(allEvents) {
  window.__TZ_DP_PENDING_POINTS = Array.isArray(allEvents) ? allEvents : [];
}

// ── Page init ─────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Show skeleton immediately while API loads
  document.getElementById("skeleton")?.classList.remove("hidden");

  loadCurrentPlan();

  // Generate / Regenerate button
  document.getElementById("generate-plan-btn")?.addEventListener("click", async () => {
    const btn = document.getElementById("generate-plan-btn");
    try {
      const hasPlan    = multiDayPlans.some(day => Array.isArray(day) && day.length > 0);
      const hasCurrent = Array.isArray(multiDayPlans[currentDayIndex]) && multiDayPlans[currentDayIndex].length > 0;
      if (currentDayIndex > 0 || hasCurrent || hasPlan) {
        await requestPlanForDay(btn);
      } else {
        await generateAllDays(btn);
      }
    } catch (e) {
      handleGenerateError(e);
      _setBtnGenerating(document.getElementById("generate-plan-btn"), false);
    }
  });

  // Add Activity modal
  document.getElementById("add-activity-btn")?.addEventListener("click", () => {
    openAddActivityModal({ dayIndex: currentDayIndex, slotKey: "activity" });
  });
  document.getElementById("closeAddActivity")?.addEventListener("click", closeAddActivityModal);
  document.getElementById("addActivityOverlay")?.addEventListener("click", closeAddActivityModal);
  document.getElementById("activitySearchInput")?.addEventListener("input", e => {
    clearTimeout(_activityDebounce);
    _activityDebounce = setTimeout(() => searchActivities(e.target.value), 350);
  });
  document.getElementById("openRouteBtn")?.addEventListener("click", e => {
    const url = e.currentTarget.dataset.routeUrl;
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  });
});
