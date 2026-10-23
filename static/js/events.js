// Auth helpers (getToken, apiGet, apiPost, apiDelete, catLabel, catEmoji, catColor) come from api.js
const SELECTED_PLAN_DATE_STORAGE_KEYS = [
  "tz_selected_plan_date",
  "tz_plan_start_date",
  "tz_start_date",
];

const PLAN_START_STORAGE_KEYS = ["tz_plan_start_date", "tz_start_date"];
const PLAN_END_STORAGE_KEYS = ["tz_plan_end_date", "tz_end_date"];

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


const RIYADH_AREAS = [
  "Central Riyadh",
  "North Riyadh",
  "East Riyadh",
  "South Riyadh",
  "West Riyadh",
];


function catGradient(cat) {
  return CAT_GRADIENTS[cat] || "var(--color-primary-bg)";
}

function escapeHtml(str) {
  return String(str || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getSelectedPlanDate() {
  for (const key of SELECTED_PLAN_DATE_STORAGE_KEYS) {
    const selectedDate = localStorage.getItem(key);
    if (selectedDate) return selectedDate;
  }
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
}

function showToast(msg, type = "success") {
  const bg = type === "error" ? "#ef4444" : type === "info" ? "var(--tz-violet)" : "#10b981";
  const toast = document.createElement("div");
  toast.style.cssText = [
    "position:fixed", "bottom:24px", "left:50%",
    "transform:translateX(-50%) translateY(80px)",
    `background:${bg}`, "color:#fff",
    "padding:10px 20px", "border-radius:12px",
    "font-size:13px", "font-weight:600",
    "box-shadow:0 4px 16px rgba(0,0,0,0.18)",
    "z-index:9999",
    "transition:transform 0.3s ease,opacity 0.3s ease",
    "opacity:0", "white-space:nowrap",
  ].join(";");
  toast.textContent = msg;
  document.body.appendChild(toast);
  requestAnimationFrame(() => {
    toast.style.transform = "translateX(-50%) translateY(0)";
    toast.style.opacity = "1";
  });
  setTimeout(() => {
    toast.style.transform = "translateX(-50%) translateY(80px)";
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 350);
  }, 2500);
}

function updatePillActiveState(activeCat) {
  document.querySelectorAll(".cat-pill").forEach(btn => {
    const isActive = btn.dataset.cat === activeCat;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-pressed", String(isActive));
    if (isActive) {
      btn.style.background = "";
      btn.style.borderColor = "";
      btn.style.color = "";
    } else {
      btn.style.background = "#ffffff";
      btn.style.borderColor = "#ede9fe";
      btn.style.color = "var(--tz-deep)";
    }
  });
}

function getStoredValue(keys) {
  for (const key of keys) {
    const value = localStorage.getItem(key);
    if (value) return value;
  }
  return "";
}

function localDateStr(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function parseLocalDate(value) {
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function getPlanStartDate() {
  return getStoredValue(PLAN_START_STORAGE_KEYS) || getSelectedPlanDate();
}

function getTripDurationDays() {
  const start = parseLocalDate(getPlanStartDate());
  const end = parseLocalDate(getStoredValue(PLAN_END_STORAGE_KEYS));
  if (start && end && end >= start) {
    return Math.max(1, Math.min(30, Math.round((end - start) / 86400000) + 1));
  }
  const raw = Number.parseInt(localStorage.getItem("tz_trip_duration") || "3", 10);
  return Math.max(1, Math.min(30, Number.isFinite(raw) ? raw : 3));
}

function getPlanDayChoices() {
  const start = parseLocalDate(getPlanStartDate()) || new Date();
  const duration = getTripDurationDays();
  return Array.from({ length: duration }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    return {
      index,
      date: localDateStr(date),
      label: `Day ${index + 1}`,
      sublabel: date.toLocaleDateString(document.documentElement?.lang === "ar" ? "ar-SA-u-ca-gregory" : "en-GB", { weekday: "short", day: "numeric", month: "short" }),
    };
  });
}

function updateActiveFilterBar() {
  const bar = document.getElementById("activeFilterBar");
  const text = document.getElementById("activeFilterText");
  if (!bar || !text) return;

  const parts = [];
  const ar = document.documentElement.lang === "ar";
  if (_currentCategory) parts.push(catLabel(_currentCategory));
  if (_currentArea) parts.push(_currentArea);
  if (_currentSearch) parts.push(`${ar?"البحث":"Search"}: "${_currentSearch}"`);

  bar.classList.toggle("hidden", !parts.length);
  bar.classList.toggle("flex", Boolean(parts.length));
  text.textContent = parts.length ? `${ar?"الفلاتر النشطة":"Active filters"}: ${parts.join(" + ")}` : "";
}

function clearFilter() {
  _currentCategory = "";
  _currentSearch = "";
  _currentArea = "";
  _nextPageUrl = null;
  const searchEl = document.getElementById("searchInput");
  if (searchEl) searchEl.value = "";
  const clearBtn = document.getElementById("clearSearchBtn");
  if (clearBtn) clearBtn.classList.add("hidden");
  updatePillActiveState("");
  updateActiveFilterBar();
  loadEvents().catch(console.error);
}

const FAV_KEY = "tizahab_favorites";
let _favoriteIds = new Set();
let _favoriteEvents = new Map();

const getFavs = () => _favoriteIds;

function promptLoginForFavorites() {
  const prefix=document.documentElement.lang === "ar" ? "/ar" : "";
  window.location.href = prefix + "/login/?next=" + encodeURIComponent(location.pathname + location.search);
}

async function migrateLegacyFavorites() {
  const token = getToken();
  if (!isLoggedIn()) return;
  let saved = [];
  try { saved = JSON.parse(localStorage.getItem(FAV_KEY) || "[]"); } catch { saved = []; }
  if (!Array.isArray(saved) || !saved.length) return;
  const eventIds = [...new Set(saved.map(v => Number.parseInt(v, 10)).filter(Number.isInteger))];
  if (!eventIds.length) { localStorage.removeItem(FAV_KEY); return; }
  try {
    await apiPost("/api/events/favorites/bulk/", { event_ids: eventIds });
    localStorage.removeItem(FAV_KEY);
  } catch { /* keep for retry on next login */ }
}

async function loadFavoriteIds() {
  const token = getToken();
  if (!isLoggedIn()) { _favoriteIds = new Set(); _favoriteEvents = new Map(); return; }
  try {
    const data = await apiGet("/api/events/favorites/");
    const rows = Array.isArray(data) ? data : [];
    _favoriteEvents = new Map(rows.filter(row=>row?.event).map(row=>[String(row.event.id),row.event]));
    _favoriteIds = new Set(
      rows.map(row => row?.event?.id).filter(id => Number.isInteger(id)).map(id => String(id))
    );
  } catch { _favoriteIds = new Set(); }
}

async function removeFavorite(eventId) {
  const token = getToken();
  if (!isLoggedIn()) { promptLoginForFavorites(); return false; }
  try {
    await apiDelete(`/api/events/favorites/${eventId}/`);
  } catch (error) {
    if (error.status === 401) { promptLoginForFavorites(); return false; }
    if (error.status !== 404) throw new Error("Could not remove favorite.");
  }
  return true;
}

function getEventsErrorMessage(err) {
  const fromResponse = typeof extractApiErrorMessage === "function"
    ? extractApiErrorMessage(err?.responseData, "") : "";
  const fromError = typeof err?.message === "string" ? err.message.trim() : "";
  if (fromResponse) return fromResponse;
  if (fromError && !/^API error \d+$/i.test(fromError)) return fromError;
  return "Something went wrong. Please try again.";
}

async function toggleFav(id) {
  const token = getToken();
  if (!isLoggedIn()) { promptLoginForFavorites(); return null; }
  const key = String(id);
  const isFav = _favoriteIds.has(key);
  if (isFav) {
    await removeFavorite(id);
    _favoriteIds.delete(key);
    _favoriteEvents.delete(key);
    return false;
  }
  try {
    const saved = await apiPost("/api/events/favorites/", { event_id: Number(id) });
    if (saved?.event) _favoriteEvents.set(key,saved.event);
    _favoriteIds.add(key);
    return true;
  } catch (err) {
    if (String(err?.message || "").toLowerCase().includes("already")) {
      _favoriteIds.add(key);
      return true;
    }
    throw err;
  }
}

async function updateFavoriteButton(eventId, root) {
  const button=root.querySelector(".fav-btn");button.disabled=true;
  try {
    const nowFav=await toggleFav(eventId);
    if(nowFav===null)return;
    button.setAttribute("aria-pressed",String(nowFav));
    root.querySelector(".fav-icon").textContent=nowFav ? "\u2665" : "\u2661";
    if(_favsOnly)renderFavoritesSection();
  } catch(error) {showToast(getEventsErrorMessage(error),"error");}
  finally {button.disabled=false;}
}

function notifyPlanUpdated(detail) {
  window.dispatchEvent(new CustomEvent("tizahab:plan-updated", { detail: detail || {} }));
}

let _pendingPlanAdd = null;

function setPlanDayMessage(message = "", type = "info") {
  const el = document.getElementById("planDayMessage");
  if (!el) return;
  if (!message) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  el.textContent = message;
  el.className = `text-sm rounded-xl px-4 py-3 ${
    type === "error" ? "bg-red-50 text-red-600" :
    type === "success" ? "bg-green-50 text-green-700" :
    "bg-violet-50 text-violet-700"
  }`;
}

function closePlanDayModal() {
  document.getElementById("planDayModal")?.classList.add("hidden");
  setPlanDayMessage("");
  _pendingPlanAdd = null;
}

function goToTrip(eventId) {
  let activeId = null;
  try { activeId = isLoggedIn() ? sessionStorage.getItem("tz_active_trip") : null; } catch {}
  const query = activeId && /^\d+$/.test(activeId) ? `trip=${activeId}&place=${encodeURIComponent(eventId)}` : `place=${encodeURIComponent(eventId)}`;
  window.location.href = (document.documentElement.lang === "ar" ? "/ar" : "") + "/trips/?" + query;
}

function openAddToPlanDayModal(event, button) {
  goToTrip(event.id);
}

async function addEventToPlan(eventId, button, targetDate = getSelectedPlanDate(), dayLabel = "") {
  const token = getToken();
  if (!isLoggedIn()) { promptLoginForFavorites(); return; }

  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Adding...";
  document.querySelectorAll(".plan-day-choice").forEach(btn => { btn.disabled = true; btn.classList.add("opacity-60"); });
  setPlanDayMessage("Adding to your plan...");

  try {
    await apiPost("/api/daily-plan/add/", {
      event_id: Number(eventId),
      date: targetDate,
    });
    notifyPlanUpdated({ eventId: Number(eventId), date: targetDate });
    localStorage.setItem("tz_selected_plan_date", targetDate);
    button.textContent = dayLabel ? `Added ${dayLabel}` : "Added";
    setPlanDayMessage(`Added to ${dayLabel || targetDate}.`, "success");
    showToast(`Added to ${dayLabel || "your plan"}!`);
    setTimeout(closePlanDayModal, 650);
    setTimeout(() => {
      button.textContent = original;
      button.disabled = false;
    }, 1500);
  } catch (error) {
    button.disabled = false;
    button.textContent = original;
    document.querySelectorAll(".plan-day-choice").forEach(btn => { btn.disabled = false; btn.classList.remove("opacity-60"); });
    setPlanDayMessage(getEventsErrorMessage(error), "error");
    showToast(getEventsErrorMessage(error), "error");
  }
}

function getTitle(ev) {
  return ev.title || ev.title_en || ev.name || "Untitled";
}

function unwrapList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  if (Array.isArray(data?.events)) return data.events;
  return [];
}

function normalizeEvent(ev) {
  return {
    ...ev,
    title: getTitle(ev),
    category: String(ev?.category || "events").toLowerCase(),
    area: ev?.area || "",
    image_url: ev?.image_url || ev?.image || ev?.photo_url || "",
    location: ev?.location || ev?.area || ev?.address || "",
  };
}

function getImageUrl(ev) {
  return getPlaceImage(ev,true);
}

function getLocationText(ev) {
  return ev.location || ev.address || ev.area || "";
}

function getPriceText(ev) {
  const price = formatEventPrice(ev.price);
  return ev.price_range ? `${price} · ${ev.price_range}` : price;
}

function getGoogleMapsUrl(ev) {
  const lat = Number.parseFloat(ev.latitude);
  const lng = Number.parseFloat(ev.longitude);
  if (Number.isFinite(lat) && Number.isFinite(lng)) {
    return `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
  }
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${getTitle(ev)} Riyadh`)}`;
}

function formatDateWindow(ev) {
  if (ev.start_date && ev.end_date) return `${ev.start_date} to ${ev.end_date}`;
  if (ev.start_date) return ev.start_date;
  return "Check dates before visiting";
}

function inferArea(ev) {
  const explicitArea = String(ev?.area || "").trim();
  if (RIYADH_AREAS.includes(explicitArea)) return explicitArea;

  const text = `${getTitle(ev)} ${getLocationText(ev)} ${ev.description || ""}`.toLowerCase();
  if (/masmak|murabba|national museum|king abdulaziz historical|deera|dirah|zal|thumairi|muaiq|malaz|central/.test(text)) {
    return "Central Riyadh";
  }
  if (/riyadh park|nakheel|granada|roshn|riyadh front|kafd|u walk|boulevard|wonder garden|winter wonderland|king salman|olaya|kingdom/.test(text)) {
    return "North Riyadh";
  }
  if (/rawdat khuraim|king fahd stadium|aviation museum|al nahda/.test(text)) {
    return "East Riyadh";
  }
  if (/wadi namar|red sand|heet cave|manakh/.test(text)) {
    return "South Riyadh";
  }
  if (/diriyah|turaif|bujairi|salwa|tuwaiq|edge of the world|qiddiya|hidden valley/.test(text)) {
    return "West Riyadh";
  }

  const lat = Number.parseFloat(ev.latitude);
  const lng = Number.parseFloat(ev.longitude);
  if (Number.isFinite(lat) && Number.isFinite(lng)) {
    const centerLat = 24.7136;
    const centerLng = 46.6753;
    if (Math.abs(lat - centerLat) < 0.035 && Math.abs(lng - centerLng) < 0.035) {
      return "Central Riyadh";
    }
    const dLat = (lat - centerLat) * 111;
    const dLng = (lng - centerLng) * 102;
    if (Math.abs(dLat) >= Math.abs(dLng)) {
      return dLat > 0 ? "North Riyadh" : "South Riyadh";
    }
    return dLng > 0 ? "East Riyadh" : "West Riyadh";
  }

  return "Central Riyadh";
}

function eventMatchesExploreFilters(ev, includeArea = true) {
  const search = _currentSearch.trim().toLowerCase();
  if (_currentCategory && String(ev.category || "").toLowerCase() !== _currentCategory) return false;
  if (includeArea && _currentArea && inferArea(ev) !== _currentArea) return false;
  if (!search) return true;
  const text = `${getTitle(ev)} ${ev.category || ""} ${getLocationText(ev)} ${inferArea(ev)}`.toLowerCase();
  return text.includes(search);
}

function getVisibleEvents() {
  if (!_currentArea) return _allEvents;
  const source = _areaEvents.length ? _areaEvents : _allEvents;
  return source.filter(ev => eventMatchesExploreFilters(ev));
}

function buildEventCard(ev) {
  const fav = getFavs().has(String(ev.id));
  const label = catLabel(ev.category);
  const emoji = catEmoji(ev.category);
  const grad = catGradient(ev.category);
  const title = getTitle(ev);
  const imageUrl = getImageUrl(ev);
  const verifiedPhoto = window.TizahabPhotos?.photo(ev);
  const location = getLocationText(ev);
  const price = getPriceText(ev);
  const rating = ev.rating
    ? `<span class="text-xs text-yellow-600 font-medium">Rating ${escapeHtml(ev.rating)}</span>` : "";

  const card = document.createElement("article");
  card.dataset.id = String(ev.id);
  card.className = "event-card rounded-2xl border border-gray-100 overflow-hidden bg-white hover:shadow-lg transition cursor-pointer";

  card.innerHTML = `
    <div class="h-32 relative overflow-hidden flex items-center justify-center" style="background:${grad}">
      ${imageUrl ? `
        <img src="${escapeHtml(imageUrl)}" ${verifiedPhoto ? `srcset="${escapeHtml(verifiedPhoto.srcset)}" sizes="(min-width:1024px) 32vw, (min-width:640px) 48vw, 100vw"` : ""} alt="${escapeHtml(title)}" width="960" height="640" loading="lazy" decoding="async"
          class="absolute inset-0 h-full w-full object-cover"
          onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">
        <div class="h-full w-full items-center justify-center" style="background:${grad};display:none">
          <i data-lucide="${catIcon(ev.category)}" class="destination-fallback-icon" aria-hidden="true"></i>
        </div>
        <div class="absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-black/25 to-transparent pointer-events-none"></div>
      ` : `<i data-lucide="${catIcon(ev.category)}" class="destination-fallback-icon" aria-hidden="true"></i><span class="photo-unavailable">${document.documentElement.lang==="ar"?"الصورة غير متوفرة بعد":"Photo not yet available"}</span>`}
      <button type="button" class="fav-btn absolute top-2 right-2 w-8 h-8 rounded-full bg-white/80 grid place-items-center border border-white/60 hover:bg-white transition z-10"
        data-id="${escapeHtml(ev.id)}" aria-label="Toggle favorite" aria-pressed="${fav}">
        <span class="fav-icon text-base leading-none">${fav ? "&hearts;" : "&#9825;"}</span>
      </button>
    </div>
    <div class="p-4 space-y-3">
      <div class="space-y-1">
        <h3 data-user-content class="font-semibold text-gray-900 text-sm leading-snug line-clamp-2"><a href="${document.documentElement?.lang === 'ar' ? '/ar' : ''}/events/page/${encodeURIComponent(ev.id)}/">${escapeHtml(title)}</a></h3>
        <div class="flex items-center gap-1.5 flex-wrap">
          <span class="text-xs px-2 py-0.5 rounded-full font-medium text-gray-600" style="background:${grad}">${escapeHtml(label)}</span>
          ${rating}
        </div>
      </div>
      <div class="space-y-1 min-h-[40px]">
        ${location ? `<p class="text-xs text-gray-500 line-clamp-1">${escapeHtml(location)}</p>` : ""}
        ${price ? `<p class="text-xs text-gray-500 capitalize">${escapeHtml(price)}</p>` : ""}
      </div>
      <div class="grid grid-cols-[1fr_auto] gap-2">
        <button type="button" class="add-to-plan-btn h-10 rounded-xl bg-purple-600 hover:bg-purple-700 text-xs font-semibold text-white transition px-3">
          Add to Plan
        </button>
        <a class="maps-link h-10 rounded-xl border border-gray-200 bg-gray-50 hover:bg-gray-100 text-xs font-semibold text-gray-700 transition inline-flex items-center justify-center px-3"
          href="${getGoogleMapsUrl(ev)}" target="_blank" rel="noopener">
          Maps
        </a>
      </div>
    </div>
  `;

  if (ev.is_active === false) {
    const notice=document.createElement("p");
    notice.textContent=document.documentElement.lang === "ar" ? "المكان غير منشور حاليًا" : "No longer published";
    notice.className="text-xs text-gray-500";
    card.querySelector("h3").after(notice);
    card.querySelector("h3 a")?.removeAttribute("href");
    const add=card.querySelector(".add-to-plan-btn");
    add.disabled=true;add.textContent=document.documentElement.lang === "ar" ? "غير متاح" : "Unavailable";
  }
  card.addEventListener("click", e => {
    if (ev.is_active === false) return;
    if (e.target.closest(".fav-btn") || e.target.closest(".add-to-plan-btn") || e.target.closest(".maps-link")) return;
    window.location.href = `${document.documentElement?.lang === 'ar' ? '/ar' : ''}/events/page/${ev.id}/`;
  });

  card.querySelector(".fav-btn").addEventListener("click", async e => {
    e.stopPropagation();
    await updateFavoriteButton(ev.id, card);
  });

  card.querySelector(".add-to-plan-btn").addEventListener("click", e => {
    e.stopPropagation();
    openAddToPlanDayModal(ev, e.currentTarget);
  });

  card.querySelector(".maps-link").addEventListener("click", e => e.stopPropagation());

  return card;
}

function buildTrendingCard(ev) {
  const fav = getFavs().has(String(ev.id));
  const label = catLabel(ev.category);
  const emoji = catEmoji(ev.category);
  const grad = catGradient(ev.category);
  const title = getTitle(ev);
  const imageUrl = getImageUrl(ev);
  const verifiedPhoto = window.TizahabPhotos?.photo(ev);
  const rating = ev.rating
    ? `<span class="text-xs text-gray-600 font-medium">${escapeHtml(ev.rating)}</span>` : "";

  const article = document.createElement("article");
  article.dataset.id = String(ev.id);
  article.className = "relative min-w-[280px] w-72 h-72 rounded-3xl overflow-hidden flex-shrink-0 cursor-pointer shadow-sm";
  article.style.background = grad;

  article.innerHTML = `
    ${imageUrl ? `
      <img src="${escapeHtml(imageUrl)}" ${verifiedPhoto?`srcset="${escapeHtml(verifiedPhoto.srcset)}" sizes="280px"`:""} width="960" height="640" decoding="async" alt="${escapeHtml(title)}" loading="lazy"
        class="absolute inset-0 h-full w-full object-cover"
        onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">
      <div class="absolute inset-0 items-center justify-center" style="background:${grad};display:none">
        <i data-lucide="${catIcon(ev.category)}" class="destination-fallback-icon" aria-hidden="true"></i>
      </div>
      <div class="featured-photo-shade"></div>
    ` : ""}
    <div class="absolute inset-0 flex flex-col p-4">
      <div class="flex items-start justify-between">
        ${imageUrl ? `<span></span>` : `<i data-lucide="${catIcon(ev.category)}" class="destination-fallback-icon" aria-hidden="true"></i>`}
        <button type="button" class="fav-btn w-8 h-8 rounded-full bg-white/80 grid place-items-center border border-white/60 hover:bg-white transition z-10 shrink-0"
          data-id="${escapeHtml(ev.id)}" aria-label="Toggle favorite" aria-pressed="${fav}">
          <span class="fav-icon text-base leading-none">${fav ? "&hearts;" : "&#9825;"}</span>
        </button>
      </div>
      <div class="mt-auto space-y-3">
        <a href="${document.documentElement?.lang === 'ar' ? '/ar' : ''}/events/page/${encodeURIComponent(ev.id)}/" class="font-bold ${imageUrl ? "text-white" : "text-gray-800"} text-base leading-snug line-clamp-2">${escapeHtml(title)}</a>
        <div class="flex items-center gap-2">
          <span class="text-xs px-2 py-0.5 rounded-full bg-white/60 text-gray-600 font-medium">${escapeHtml(label)}</span>
          ${rating}
        </div>
        <div class="grid grid-cols-[1fr_auto] gap-2">
          <button type="button" class="add-to-plan-btn h-10 rounded-xl bg-white/90 hover:bg-white text-xs font-semibold text-gray-800 transition px-3">
            Add to Plan
          </button>
          <a class="maps-link h-10 rounded-xl bg-white/70 hover:bg-white text-xs font-semibold text-gray-800 transition inline-flex items-center justify-center px-3"
            href="${getGoogleMapsUrl(ev)}" target="_blank" rel="noopener">
            Maps
          </a>
        </div>
      </div>
    </div>
  `;

  article.addEventListener("click", e => {
    if (e.target.closest(".fav-btn") || e.target.closest(".add-to-plan-btn") || e.target.closest(".maps-link")) return;
    window.location.href = `${document.documentElement?.lang === 'ar' ? '/ar' : ''}/events/page/${ev.id}/`;
  });

  article.querySelector(".fav-btn").addEventListener("click", async e => {
    e.stopPropagation();
    await updateFavoriteButton(ev.id, article);
  });

  article.querySelector(".add-to-plan-btn").addEventListener("click", e => {
    e.stopPropagation();
    openAddToPlanDayModal(ev, e.currentTarget);
  });

  article.querySelector(".maps-link").addEventListener("click", e => e.stopPropagation());

  return article;
}

function buildAreaCard(area, events) {
  const card = document.createElement("article");
  const active = _currentArea === area;
  const names = events.slice(0, 3).map(ev => getTitle(ev));
  const imageUrl = "";
  card.className = `area-card group relative h-52 overflow-hidden rounded-3xl border shadow-sm cursor-pointer ${active ? "border-purple-300 ring-2 ring-purple-100" : "border-gray-100"}`;
  card.innerHTML = `
    <img hidden src="${escapeHtml(imageUrl)}" alt="" loading="lazy"
      class="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-105"
      onerror="this.style.display='none';">
    <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-black/25 to-black/5"></div>
    <div class="relative z-10 flex h-full flex-col justify-between p-4 text-white">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="font-bold text-white">${escapeHtml(area)}</h3>
          <p class="text-xs text-white/80">${events.length} places</p>
        </div>
        <span class="w-9 h-9 rounded-xl bg-white/20 text-white flex items-center justify-center backdrop-blur">
        <i data-lucide="map-pin" class="w-4 h-4"></i>
        </span>
      </div>
      <div class="space-y-3">
        <div class="space-y-1">
          ${names.length
            ? names.map(name => `<p class="text-xs text-white/85 line-clamp-1">${escapeHtml(name)}</p>`).join("")
            : `<p class="text-xs text-white/70">No places in this filter yet.</p>`}
        </div>
        <button type="button" class="view-area-btn w-full h-10 rounded-xl ${active ? "bg-purple-600 text-white" : "bg-white/90 text-gray-900"} text-xs font-bold hover:opacity-90 transition">
          ${active ? "Viewing Area" : "View Places"}
        </button>
      </div>
    </div>
  `;
  card.querySelector(".view-area-btn").addEventListener("click", () => {
    _currentArea = active ? "" : area;
    renderAreaCards();
    renderEventsGrid(getVisibleEvents());
    updateAreaControls();
    document.getElementById("allEventsSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  return card;
}

function buildSkeletonCard(extraClasses = "") {
  const el = document.createElement("div");
  el.className = `rounded-2xl border border-gray-100 overflow-hidden skeleton-pulse${extraClasses ? " " + extraClasses : ""}`;
  el.innerHTML = `
    <div class="h-24" style="background:var(--color-primary-bg)"></div>
    <div class="p-3.5 space-y-2">
      <div class="h-3 bg-gray-100 rounded-full w-4/5"></div>
      <div class="h-3 bg-gray-100 rounded-full w-1/2"></div>
      <div class="h-7 bg-gray-100 rounded-xl mt-1"></div>
    </div>
  `;
  return el;
}

function showGridSkeletons(count = 3) {
  const grid = document.getElementById("eventsGrid");
  if (!grid) return;
  grid.innerHTML = "";
  const extraClasses = ["", "hidden sm:block", "hidden lg:block"];
  for (let i = 0; i < count; i++) {
    grid.appendChild(buildSkeletonCard(extraClasses[i] || ""));
  }
}

let _allEvents = [];
let _areaEvents = [];
let _totalCount = 0;
let _nextPageUrl = null;
let _isLoadingMore = false;
let _currentCategory = "";
let _currentSearch = "";
let _currentArea = "";
let _debounceTimer = null;
let _favsOnly = false;

async function fetchAreaEvents() {
  const events = [];
  let nextUrl = "/api/events/?page_size=100";
  let pageCount = 0;

  while (nextUrl && pageCount < 10) {
    const data = await apiGet(nextUrl);
    events.push(...unwrapList(data));
    nextUrl = Array.isArray(data) ? null : data?.next || null;
    pageCount += 1;
  }

  return events.filter(Boolean).map(normalizeEvent);
}

function updateLoadMoreState() {
  const wrap = document.getElementById("loadMoreWrap");
  const btn = document.getElementById("loadMoreBtn");
  if (!wrap || !btn) return;
  const shouldShow = Boolean(_nextPageUrl) && !_favsOnly && !_currentArea;
  wrap.classList.toggle("hidden", !shouldShow);
  btn.disabled = !shouldShow || _isLoadingMore;
  if (_isLoadingMore) {
    btn.textContent = "Loading...";
  } else {
    const remaining = _totalCount - _allEvents.length;
    btn.textContent = remaining > 0 ? `Load More (${remaining} remaining)` : "Load More";
  }
}

function updateAreaControls() {
  const clearBtn = document.getElementById("clearAreaBtn");
  const heading = document.getElementById("placesHeading");
  clearBtn?.classList.toggle("hidden", !_currentArea);
  if (heading) heading.textContent = _currentArea || "Places";
  updateActiveFilterBar();
  updateLoadMoreState();
}

function renderEventsGrid(events) {
  const highlights=document.getElementById("discoveryHighlights");if(highlights)highlights.hidden=Boolean(_currentCategory||_currentSearch||_currentArea||_favsOnly);
  const grid = document.getElementById("eventsGrid");
  const countText = document.getElementById("countText");
  if (!grid) return;

  grid.innerHTML = "";

  if (!events.length) {
    const hasFilter = _currentCategory || _currentSearch || _currentArea;
    grid.innerHTML = `
      <div class="col-span-full py-16 text-center space-y-3 bg-white rounded-2xl border border-gray-100">
        <p class="text-gray-500 font-medium">No places found</p>
        <p class="text-sm text-gray-400">Try a different search, category, or area.</p>
        ${hasFilter ? `<button onclick="clearFilter()" class="mt-2 px-5 py-2 rounded-xl border border-purple-200 text-sm font-medium text-purple-700 hover:bg-purple-50 transition">Clear Filters</button>` : ""}
      </div>`;
    if (countText) countText.textContent = "";
    return;
  }

  events.forEach(ev => grid.appendChild(buildEventCard(ev)));
  if (countText) {
    if (_currentArea) {
      countText.textContent = `${events.length} places in ${_currentArea}`;
    } else {
      countText.textContent = _totalCount > _allEvents.length
        ? `Showing ${_allEvents.length} of ${_totalCount} places`
        : `${_allEvents.length} places found`;
    }
  }
  if (window.lucide) window.lucide.createIcons();
}

function renderTrendingRow(events) {
  const row = document.getElementById("trendingRow");
  if (!row) return;
  row.innerHTML = "";
  const source=_areaEvents.length?_areaEvents:events;
  const uniquePhotos=new Map();source.forEach(event=>{const photo=window.TizahabPhotos?.photo(event);if(photo&&!uniquePhotos.has(photo.slug))uniquePhotos.set(photo.slug,event);});
  const photographed=[...uniquePhotos.values()];
  const highlights=document.getElementById("discoveryHighlights");
  if(highlights)highlights.hidden=Boolean(_currentCategory||_currentSearch||_currentArea||_favsOnly||!photographed.length);
  photographed
    .map((ev, index) => ({ ev, index }))
    .sort((a, b) => {
      const ratingDiff = (Number.parseFloat(b.ev?.rating) || 0) - (Number.parseFloat(a.ev?.rating) || 0);
      if (ratingDiff) return ratingDiff;
      const priorityDiff = (Number.parseFloat(b.ev?.tourism_priority) || 0) - (Number.parseFloat(a.ev?.tourism_priority) || 0);
      if (priorityDiff) return priorityDiff;
      return a.index - b.index;
    })
    .slice(0, 6)
    .forEach(({ ev }) => row.appendChild(buildTrendingCard(ev)));
}

function renderAreaCards() {
  const grid = document.getElementById("eventsAreasGrid");
  if (!grid) return;
  const source = _areaEvents.length ? _areaEvents : _allEvents;
  const baseEvents = source.filter(ev => eventMatchesExploreFilters(ev, false));
  const grouped = new Map(RIYADH_AREAS.map(area => [area, []]));
  baseEvents.forEach(ev => grouped.get(inferArea(ev))?.push(ev));

  const orderedAreas = RIYADH_AREAS
    .map(area => ({ area, events: grouped.get(area) || [] }))
    .filter(row => row.events.length);

  grid.innerHTML = "";
  if (!orderedAreas.length) {
    grid.innerHTML = `
      <div class="sm:col-span-2 lg:col-span-4 bg-white rounded-2xl border border-gray-100 shadow-sm p-6 text-center">
        <p class="text-sm font-medium text-gray-600">No Riyadh areas match this filter.</p>
        <p class="text-xs text-gray-400 mt-1">Try another category or search term.</p>
      </div>`;
    return;
  }
  orderedAreas.forEach(row => grid.appendChild(buildAreaCard(row.area, row.events)));
  if (window.lucide) window.lucide.createIcons();
}

let _eventsRequestVersion=0;
async function loadEvents({append=false}={}) {
  const requestVersion=++_eventsRequestVersion;
  const countText = document.getElementById("countText");

  if (!append) {
    showGridSkeletons(3);
    if (countText) countText.textContent = "";
    _totalCount = 0;
  }

  let requestUrl = append ? _nextPageUrl : null;
  if (!append || !requestUrl) {
    const params = new URLSearchParams();
    if (_currentCategory) params.set("category", _currentCategory);
    if (_currentSearch) params.set("search", _currentSearch);
    params.set("page_size", "25");
    const qs = params.toString();
    requestUrl = `/api/events/${qs ? "?" + qs : ""}`;
  }

  let data;
  try {data=await apiGet(requestUrl);} catch(error) {
    if(requestVersion!==_eventsRequestVersion)return;
    if(append){showToast(getEventsErrorMessage(error),"error");return;}
    const ar=document.documentElement.lang==="ar";
    const grid=document.getElementById("eventsGrid");
    if(grid){grid.innerHTML=`<div role="alert" class="discovery-error"><h3>${ar?"تعذر تحميل الأماكن":"We couldn't load places"}</h3><p>${ar?"حاول مجددًا عندما يعود الاتصال.":"Please try again when the connection is available."}</p><button type="button" class="btn-outline" data-retry-events>${ar?"إعادة المحاولة":"Try again"}</button></div>`;grid.querySelector("[data-retry-events]")?.addEventListener("click",()=>loadEvents());}
    if(countText)countText.textContent=ar?"تعذر تحميل النتائج":"Results unavailable";
    const highlights=document.getElementById("discoveryHighlights");if(highlights)highlights.hidden=true;
    return;
  }
  if(requestVersion!==_eventsRequestVersion||!data)return;

  const events = unwrapList(data).map(normalizeEvent);
  _nextPageUrl = Array.isArray(data) ? null : data.next || null;
  if (!Array.isArray(data) && data.count != null) {
    _totalCount = data.count;
  } else if (!append) {
    _totalCount = events.length;
  }

  if (append) {
    const merged = new Map(_allEvents.map(ev => [String(ev.id), ev]));
    events.forEach(ev => merged.set(String(ev.id), ev));
    _allEvents = [...merged.values()];
  } else {
    _allEvents = events;
  }

  renderAreaCards();
  renderEventsGrid(getVisibleEvents());
  renderTrendingRow(getVisibleEvents());
  updateAreaControls();
  updateLoadMoreState();
}

async function loadMoreEvents() {
  if (!_nextPageUrl || _isLoadingMore) return;
  _isLoadingMore = true;
  updateLoadMoreState();
  try {
    await loadEvents({append:true});
  } finally {
    _isLoadingMore = false;
    updateLoadMoreState();
  }
}

function onSearchChange(value) {
  _currentSearch = value.trim();
  _isLoadingMore=false;
  _currentArea = "";
  _nextPageUrl = null;
  updateActiveFilterBar();
  clearTimeout(_debounceTimer);
  _debounceTimer = setTimeout(() => loadEvents().catch(console.error), 350);
}

function onCategorySelect(cat) {
  _currentCategory = cat;
  _isLoadingMore=false;
  _currentArea = "";
  _nextPageUrl = null;
  updatePillActiveState(_currentCategory);
  updateActiveFilterBar();
  loadEvents().catch(console.error);
}

function renderFavoritesSection() {
  const grid = document.getElementById("favoritesGrid");
  const countEl = document.getElementById("favoritesCount");
  if (!grid) return;
  const favIds = getFavs();
  const favEvents = [..._favoriteEvents.values()].filter(ev=>favIds.has(String(ev.id)) && eventMatchesExploreFilters(ev));
  grid.innerHTML = "";
  favEvents.forEach(ev => grid.appendChild(buildEventCard(ev)));
  if (!favEvents.length) grid.innerHTML = '<div class="card col-span-full p-8 text-center text-sm text-gray-500">No favorites match these filters. Save a place or clear your filters.</div>';
  if (countEl) countEl.textContent = _favoriteIds.size ? `${_favoriteIds.size} favorites` : "";
}

function initFavoritesToggle() {
  const prefBtn = document.getElementById("prefBtn");
  const favSection = document.getElementById("favoritesSection");
  const eventsGrid = document.getElementById("eventsGrid");
  const loadMoreWrap = document.getElementById("loadMoreWrap");

  prefBtn?.addEventListener("click", () => {
    _favsOnly = !_favsOnly;
    prefBtn.setAttribute("aria-pressed", String(_favsOnly));
    if (_favsOnly) {
      prefBtn.style.background = "#ede9fe";
      prefBtn.style.color = "var(--tz-violet)";
      prefBtn.style.borderColor = "#c4b5fd";
      renderFavoritesSection();
      favSection?.classList.remove("hidden");
      eventsGrid?.classList.add("hidden");
      loadMoreWrap?.classList.add("hidden");
    } else {
      prefBtn.style.background = "";
      prefBtn.style.color = "";
      prefBtn.style.borderColor = "";
      favSection?.classList.add("hidden");
      eventsGrid?.classList.remove("hidden");
      updateLoadMoreState();
    }
  });
}

function initTrendingNav() {
  const row = document.getElementById("trendingRow");
  document.getElementById("trendPrev")?.addEventListener("click", () =>
    row?.scrollBy({ left: document.documentElement.dir === "rtl" ? 260 : -260, behavior: "smooth" })
  );
  document.getElementById("trendNext")?.addEventListener("click", () =>
    row?.scrollBy({ left: document.documentElement.dir === "rtl" ? -260 : 260, behavior: "smooth" })
  );
}

function renderEventDetails(ev) {
  const container=document.getElementById("eventDetails");if(!container)return;
  const ar=document.documentElement.lang==="ar";const t=(en,arabic)=>ar?arabic:en;
  const price=getPriceText(ev),label=catLabel(ev.category),imageUrl=getImageUrl(ev),photo=window.TizahabPhotos?.photo(ev);
  const source=ev.source_url||ev.website||"";const safeSource=/^https?:\/\//i.test(source)?source:"";
  const hours=ev.opening_hours_text||(ev.start_time&&ev.end_time?`${ev.start_time.slice(0,5)}–${ev.end_time.slice(0,5)}`:t("Hours unknown — check before visiting","ساعات العمل غير معروفة — تحقّق قبل الزيارة"));
  container.innerHTML=`
    <header class="detail-hero card overflow-hidden">
      <div class="detail-photo-wrap">${imageUrl?`<img src="${escapeHtml(imageUrl)}" ${photo?`srcset="${escapeHtml(photo.srcset)}" sizes="(min-width:1280px) 1200px, 100vw"`:""} alt="${escapeHtml(getTitle(ev))}" width="1280" height="853" class="detail-photo" fetchpriority="high" onerror="this.hidden=true;this.nextElementSibling.hidden=false">`:""}<div ${imageUrl?"hidden":""} class="destination-image-fallback"><i data-lucide="${catIcon(ev.category)}" aria-hidden="true"></i><span class="photo-unavailable">${t("Photo not yet available","الصورة غير متوفرة بعد")}</span></div></div>
      <div class="p-6 sm:p-8"><span class="eyebrow">${escapeHtml(label)}</span><h1 data-user-content dir="auto">${escapeHtml(getTitle(ev))}</h1><p class="trip-note mt-3">${escapeHtml(getLocationText(ev)||t("Riyadh","الرياض"))}</p></div>
    </header>
    <div class="detail-columns"><div class="detail-body">
      <section class="card detail-information"><h2>${t("About this place","عن المكان")}</h2><p data-user-content>${escapeHtml(ev.description||"")}</p>${!ev.description?`<p>${t("No description available. Check the official source before visiting.","لا يتوفر وصف للمكان. راجع المصدر الرسمي قبل الزيارة.")}</p>`:""}</section>
      <section class="card detail-information"><h2>${t("Good to know before you go","قبل أن تنطلق")}</h2><dl class="detail-facts"><div><dt>${t("Available dates","تواريخ التوافر")}</dt><dd>${escapeHtml(formatDateWindow(ev))}</dd></div><div><dt>${t("Opening hours","ساعات العمل")}</dt><dd data-user-content>${escapeHtml(hours)}</dd></div><div><dt>${t("Category","التصنيف")}</dt><dd>${escapeHtml(label)}</dd></div>${ev.rating!=null?`<div><dt>${t("Catalogue rating","تقييم الدليل")}</dt><dd>★ ${escapeHtml(ev.rating)}</dd></div>`:""}</dl><p class="detail-source-note">${t("Confirm opening times and entry requirements with the venue. A catalogue listing does not guarantee availability.","تحقّق من أوقات العمل ومتطلبات الدخول لدى المكان. إدراجه في الدليل لا يضمن توافره.")}</p></section>
      ${ev.source||ev.last_verified_at?`<section class="card detail-information"><h2>${t("Source information","معلومات المصدر")}</h2>${ev.source?`<p data-user-content>${escapeHtml(ev.source)}</p>`:""}${ev.last_verified_at?`<p>${t("Last content verification","آخر مراجعة للمحتوى")}: ${escapeHtml(ev.last_verified_at.slice(0,10))}</p>`:`<p>${t("Verification date unknown. Check the source for current information.","تاريخ المراجعة غير معروف. راجع المصدر للحصول على معلومات محدثة.")}</p>`}</section>`:""}
    </div><aside class="detail-bookmark"><div><p class="trip-note">${t("Entry price","سعر الدخول")}</p><p class="entry-price">${escapeHtml(price)}</p></div><button type="button" id="detailAddToPlanBtn" class="btn-primary">${t("Add to my trip","أضف إلى رحلتي")}</button><p class="trip-note">${t("Plan as a guest. Sign in only when saving your trip.","خطّط كضيف. سجّل الدخول عند حفظ الرحلة فقط.")}</p><div id="ticketMsg" role="status"></div><a href="${getGoogleMapsUrl(ev)}" target="_blank" rel="noopener noreferrer" class="btn-outline">${t("Open in Google Maps ↗","افتح في خرائط Google ↗")}</a>${safeSource?`<a href="${escapeHtml(safeSource)}" target="_blank" rel="noopener noreferrer" class="text-link">${t("Visit source ↗","زيارة المصدر ↗")}</a>`:""}<p class="trip-note">${t("Prices may change. Unknown prices do not mean free entry.","قد تتغير الأسعار. السعر غير المعروف لا يعني أن الدخول مجاني.")}</p></aside></div>`;
  if(window.lucide)lucide.createIcons();
}

function wireDetailTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  const panels = {
    overview: document.getElementById("tab-overview"),
    schedule: document.getElementById("tab-schedule"),
    reviews: document.getElementById("tab-reviews"),
  };
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(t => {
        const active = t === btn;
        t.style.background = active ? "#fff" : "";
        t.style.boxShadow = active ? "0 1px 3px rgba(0,0,0,0.1)" : "";
        t.style.color = active ? "var(--tz-violet)" : "";
      });
      Object.entries(panels).forEach(([key, el]) => {
        if (el) el.classList.toggle("hidden", key !== btn.dataset.tab);
      });
    });
  });
}

function wireGetTickets(eventId) {
  document.getElementById("detailAddToPlanBtn")?.addEventListener("click", () => {
    goToTrip(eventId);
  });
}

async function loadEventDetails(eventId) {
  const data = await apiGet(`/api/events/${eventId}/`);
  if (data) {
    renderEventDetails(data);
    wireDetailTabs();
    wireGetTickets(data.id);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("eventsGrid")) {
    const params = new URLSearchParams(window.location.search);
    const initialSearch = params.get("search") || "";
    const initialCategory = params.get("category") || "";
    _currentCategory = Object.hasOwn(CATEGORY_MAP, initialCategory) ? initialCategory : "";
    updatePillActiveState(_currentCategory);
    _currentSearch = initialSearch;
    const initialSearchInput = document.getElementById("searchInput");
    if (initialSearchInput) initialSearchInput.value = initialSearch;
    (async () => {
      await migrateLegacyFavorites();
      await loadFavoriteIds();
      // Fire area-grouping fetch in the background so the main grid renders
      // immediately instead of waiting for up to 10 paginated requests first.
      fetchAreaEvents()
        .then(events => {
          _areaEvents = events;
          renderAreaCards();
          renderTrendingRow(events);
          if (window.lucide) window.lucide.createIcons();
        })
        .catch(err => console.warn("Area grouping dataset failed to load:", err));
      await loadEvents();
    })().catch(console.error);

    initTrendingNav();
    initFavoritesToggle();
    updateLoadMoreState();

    document.getElementById("loadMoreBtn")?.addEventListener("click", () =>
      loadMoreEvents().catch(console.error)
    );

    document.getElementById("clearAreaBtn")?.addEventListener("click", () => {
      _currentArea = "";
      renderAreaCards();
      renderEventsGrid(getVisibleEvents());
      updateAreaControls();
    });

    const searchInput = document.getElementById("searchInput");
    const clearBtn = document.getElementById("clearSearchBtn");
    clearBtn?.classList.toggle("hidden", !initialSearch);

    searchInput?.addEventListener("input", e => {
      onSearchChange(e.target.value);
      if (clearBtn) clearBtn.classList.toggle("hidden", !e.target.value);
    });

    clearBtn?.addEventListener("click", () => {
      if (searchInput) searchInput.value = "";
      clearBtn.classList.add("hidden");
      onSearchChange("");
    });

    document.querySelectorAll(".cat-pill").forEach(btn =>
      btn.addEventListener("click", () => onCategorySelect(btn.dataset.cat))
    );

    document.getElementById("closePlanDayModal")?.addEventListener("click", closePlanDayModal);
    document.getElementById("planDayOverlay")?.addEventListener("click", closePlanDayModal);
  }

  if (window.EVENT_ID) {
    loadEventDetails(window.EVENT_ID).catch(error => {
      document.getElementById("eventLoading")?.classList.add("hidden");
      const panel = document.getElementById("eventDetails");
      const message = document.createElement("p");
      message.setAttribute("role", "alert");
      message.textContent = document.documentElement.lang === "ar" ? "المكان غير متاح أو تعذر تحميله. عُد إلى الاستكشاف وحاول مجددًا." : "This place is unavailable or could not be loaded. Return to Discover and try again.";
      panel?.replaceChildren(message);
    });
  }
});
