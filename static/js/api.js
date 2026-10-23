// Tizahab  shared API layer
// All pages import this file for auth + fetch

const CATEGORY_MAP = {
  culture:       { label: "Culture",       emoji: "🏛️", color: "bg-violet-50 text-violet-700" },
  heritage:      { label: "Heritage",      emoji: "🕌", color: "bg-violet-50 text-violet-700" },
  entertainment: { label: "Entertainment", emoji: "🎡", color: "bg-violet-50 text-violet-700" },
  food:          { label: "Food",          emoji: "🍽️", color: "bg-violet-50 text-violet-700" },
  shopping:      { label: "Shopping",      emoji: "🛍️", color: "bg-violet-50 text-violet-700" },
  nature:        { label: "Nature",        emoji: "🌿", color: "bg-violet-50 text-violet-700" },
  family:        { label: "Family",        emoji: "👨‍👩‍👧", color: "bg-violet-50 text-violet-700" },
  events:        { label: "Events",        emoji: "🎫", color: "bg-violet-50 text-violet-700" },
};

function getToken() {
  return localStorage.getItem("access") || "";
}

function storeAuthTokens(data) {
  if (!data) return false;
  if (data.access) localStorage.setItem("access", data.access);
  if (data.refresh) localStorage.setItem("refresh", data.refresh);
  return Boolean(data.access);
}

function isLoggedIn() {
  return localStorage.getItem("access") !== null || window.TZ_SESSION_AUTHENTICATED === true;
}

function redirectToLogin() {
  const next = window.location.pathname;
  window.location.href = (next.startsWith("/ar/") ? "/ar" : "") + "/login/?next=" + encodeURIComponent(next);
}

function safeInternalRedirect(value) {
  if (typeof value !== "string" || !value.startsWith("/") ||
      value.startsWith("//") || /[\\\s\u0000-\u001f\u007f]/.test(value)) return null;
  try {
    const target = new URL(value, window.location.origin);
    if (target.origin !== window.location.origin) return null;
    return target.pathname + target.search + target.hash;
  } catch {
    return null;
  }
}

function getCookie(name) {
  const prefix = `${name}=`;
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length) || "";
}

function formatEventPrice(price) {
  const ar = document.documentElement?.lang === "ar";
  if (price === null || price === undefined || String(price).trim() === "") {
    return ar ? "السعر غير معروف" : "Price unknown";
  }
  const amount = Number(price);
  if (!Number.isFinite(amount) || amount < 0) return ar ? "السعر غير معروف" : "Price unknown";
  if (amount === 0) return ar ? "مجاني" : "Free";
  return `${amount.toLocaleString(ar ? "ar-SA" : "en", {maximumFractionDigits: 2})} ${ar ? "ر.س" : "SAR"}`;
}

function logError(...args) {
  if (window.DEBUG) console.error(...args);
}

function authHeaders(url = "") {
  const headers = {
    "Content-Type": "application/json",
  };

  const token = localStorage.getItem("access");

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const csrfToken = getCookie("csrftoken");
  if (csrfToken) headers["X-CSRFToken"] = csrfToken;
  return headers;
}

function toISODate(dateStr) {
  if (!dateStr) return null;

  const parts = dateStr.split("/");
  if (parts.length === 3) {
    return `${parts[2]}-${parts[0].padStart(2, "0")}-${parts[1].padStart(2, "0")}`;
  }

  return dateStr;
}

async function parseResponseBody(res) {
  const text = await res.text();
  const trimmed = text.trim();

  if (trimmed.startsWith("<!DOCTYPE") || trimmed.startsWith("<html")) {
    console.warn("Unexpected HTML response");
    const err = new Error("Invalid response");
    err.type = "server";
    err.status = res.status;
    throw err;
  }

  if (!trimmed) return null;

  try {
    return JSON.parse(text);
  } catch (error) {
    console.error("Failed to parse API response body", error);
    return null;
  }
}

function _flattenApiErrorParts(value) {
  if (value == null) return [];
  if (typeof value === "string" || typeof value === "number") {
    const text = String(value).trim();
    return text ? [text] : [];
  }
  if (Array.isArray(value)) return value.flatMap(_flattenApiErrorParts);
  if (typeof value === "object") {
    return Object.values(value).flatMap(_flattenApiErrorParts);
  }
  return [];
}

function extractApiErrorMessage(responseData, fallback = "Request failed. Please try again.") {
  if (!responseData) return fallback;

  for (const key of ["detail", "error", "message"]) {
    const parts = _flattenApiErrorParts(responseData[key]);
    if (parts.length) return parts.join(" ");
  }

  const nonFieldParts = _flattenApiErrorParts(responseData.non_field_errors);
  if (nonFieldParts.length) return nonFieldParts.join(" ");

  if (typeof responseData === "object" && !Array.isArray(responseData)) {
    const fieldMessages = [];
    for (const [field, rawValue] of Object.entries(responseData)) {
      if (["detail", "error", "message", "non_field_errors"].includes(field)) continue;
      const parts = _flattenApiErrorParts(rawValue);
      if (parts.length) fieldMessages.push(`${field}: ${parts.join(" ")}`);
    }
    if (fieldMessages.length) return fieldMessages.join(" ");
  }

  const genericParts = _flattenApiErrorParts(responseData);
  if (genericParts.length) return genericParts.join(" ");

  return fallback;
}

async function _raiseApiError(res, fallbackPrefix = "Request failed") {
  const body = await parseResponseBody(res);
  const err = new Error(
    extractApiErrorMessage(body, `${fallbackPrefix}. Please try again.`),
  );
  err.status = res.status;
  err.responseData = body;
  if (res.status >= 500) {
    console.error("API failure:", err);
  } else {
    console.warn("Handled API response:", err.message);
  }
  throw err;
}

/**
 * Attempt a silent token refresh using the stored refresh token.
 * Returns true if a new access token was obtained and stored, false otherwise.
 */
async function _tryRefresh() {
  const refresh = localStorage.getItem("refresh");
  if (!refresh) return false;

  try {
    const res = await fetch("/api/auth/token/refresh/", {
      method: "POST",
      headers: authHeaders("/api/auth/token/refresh/"),
      credentials: "include",
      body: JSON.stringify({ refresh }),
    });
    if (!res.ok) return false;
    const data = await parseResponseBody(res);
    return storeAuthTokens(data);
  } catch (error) {
    logError("API ERROR", error);
  }
  return false;
}

async function _trySessionToken() {
  try {
    const res = await fetch("/api/auth/session-token/", {
      method: "GET",
      headers: authHeaders("/api/auth/session-token/"),
      credentials: "include",
    });
    if (!res.ok) return false;
    const data = await parseResponseBody(res);
    return storeAuthTokens(data);
  } catch (error) {
    logError("API ERROR", error);
  }
  return false;
}

/** Clear browser state only after the server session has been closed. */
async function logout(options = {}) {
  const redirect = options.redirect !== false;

  try {
    const response = await fetch("/logout/", {
      method: "POST",
      headers: authHeaders("/logout/"),
      credentials: "include",
    });
    if (!response.ok) await _raiseApiError(response, "Unable to log out");
  } catch (error) {
    logError("API ERROR", error);
    if (window.alert) window.alert("Unable to log out. Please try again.");
    return false;
  }

  window.TZ_SESSION_AUTHENTICATED = false;
  try {sessionStorage.removeItem("tz_active_trip");sessionStorage.removeItem("tizahab_pending_trips_v1");} catch {}
  localStorage.removeItem("access");
  localStorage.removeItem("refresh");
  localStorage.removeItem("tz_trip_duration");
  localStorage.removeItem("tz_plan_start_date");
  localStorage.removeItem("tz_plan_end_date");
  localStorage.removeItem("tz_selected_plan_date");
  localStorage.removeItem("selectedStartDate");
  localStorage.removeItem("selectedEndDate");
  localStorage.removeItem("tripDuration");
  localStorage.removeItem("currentDayIndex");
  if (redirect) {
    window.location.href = (window.location.pathname?.startsWith("/ar/") ? "/ar" : "") + "/login/";
  }
  return true;
}

function _logout() {
  return logout();
}

async function apiGet(url, retry = true) {
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: authHeaders(url),
      credentials: "include",
    });

    if (res.status === 401) {
      if (retry && await _tryRefresh()) return apiGet(url, false);
      if (retry && await _trySessionToken()) return apiGet(url, false);
      redirectToLogin();
      return;
    }

    if (!res.ok) await _raiseApiError(res, "Unable to load data");
    return parseResponseBody(res);
  } catch (error) {
    logError("API ERROR", error);
    throw error;
  }
}

async function apiPost(url, data, retry = true) {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: authHeaders(url),
      credentials: "include",
      body: JSON.stringify(data),
    });

    if (res.status === 401) {
      if (retry && await _tryRefresh()) return apiPost(url, data, false);
      if (retry && await _trySessionToken()) return apiPost(url, data, false);
      redirectToLogin();
      return;
    }

    if (!res.ok) await _raiseApiError(res, "Unable to complete request");
    return parseResponseBody(res);
  } catch (error) {
    logError("API ERROR", error);
    throw error;
  }
}

async function apiPut(url, data, retry = true) {
  try {
    const res = await fetch(url, {
      method: "PUT",
      headers: authHeaders(url),
      credentials: "include",
      body: JSON.stringify(data),
    });

    if (res.status === 401) {
      if (retry && await _tryRefresh()) return apiPut(url, data, false);
      if (retry && await _trySessionToken()) return apiPut(url, data, false);
      redirectToLogin();
      return;
    }

    if (!res.ok) await _raiseApiError(res, "Unable to save changes");
    return parseResponseBody(res);
  } catch (error) {
    logError("API ERROR", error);
    throw error;
  }
}

async function apiPatch(url, data, retry = true) {
  try {
    const res = await fetch(url, {
      method: "PATCH",
      headers: authHeaders(url),
      credentials: "include",
      body: JSON.stringify(data),
    });

    if (res.status === 401) {
      if (retry && await _tryRefresh()) return apiPatch(url, data, false);
      if (retry && await _trySessionToken()) return apiPatch(url, data, false);
      redirectToLogin();
      return;
    }

    if (!res.ok) await _raiseApiError(res, "Unable to update data");
    return parseResponseBody(res);
  } catch (error) {
    logError("API ERROR", error);
    throw error;
  }
}

async function apiDelete(url, retry = true) {
  try {
    const res = await fetch(url, {
      method: "DELETE",
      headers: authHeaders(url),
      credentials: "include",
    });

    if (res.status === 401) {
      if (retry && await _tryRefresh()) return apiDelete(url, false);
      if (retry && await _trySessionToken()) return apiDelete(url, false);
      redirectToLogin();
      throw new Error("Your session has expired. Please log in again.");
    }

    if (!res.ok) await _raiseApiError(res, "Unable to delete data");
    return parseResponseBody(res);
  } catch (error) {
    logError("API ERROR", error);
    throw error;
  }
}

function catLabel(cat) { return CATEGORY_MAP[cat]?.label || cat; }
function catEmoji(cat) { return CATEGORY_MAP[cat]?.emoji || ""; }
function catColor(cat) { return CATEGORY_MAP[cat]?.color || "bg-gray-100 text-gray-700"; }

document.addEventListener("click", function (e) {
  const target = e.target.closest("[data-requires-auth]");

  if (!target) return;

  if (!isLoggedIn()) {
    e.preventDefault();
    e.stopImmediatePropagation();
    redirectToLogin();
  }
}, true);

// expose globally for all scripts
window.apiGet = apiGet;
window.apiPost = apiPost;
window.apiPut = apiPut;
window.apiPatch = apiPatch;
window.apiDelete = apiDelete;
window.extractApiErrorMessage = extractApiErrorMessage;
window.catLabel = catLabel;
window.catEmoji = catEmoji;
window.toISODate = toISODate;
window.catColor = catColor;
window.getToken = getToken;
window.isLoggedIn = isLoggedIn;
window.redirectToLogin = redirectToLogin;
window.safeInternalRedirect = safeInternalRedirect;
window.formatEventPrice = formatEventPrice;
window.logout = logout;
window.storeAuthTokens = storeAuthTokens;

// Legacy category illustrations are not photographs of individual destinations.
function getPlaceImage(event, verifiedOnly=false) {
  const verifiedPhoto = window.TizahabPhotos?.photo(event);
  if (verifiedPhoto) return verifiedPhoto.src;
  if (verifiedOnly) return "";
  const value = event?.image_url || event?.image || event?.photo_url || "";
  if (!value) return "";
  try {
    const url = new URL(value, window.location.origin);
    if (!["https:", "http:"].includes(url.protocol) || /(^|\.)example\.(com|org|net)$/.test(url.hostname)) return "";
    const path = decodeURIComponent(url.pathname);
    const legacyIllustrations = [
      "National_Museum_Riyadh_(6781666263).jpg", "Masmak_Fort_(12753717253).jpg",
      "1944213.jpg", "descriptionimage_1727952417.jpg", "malls-in-riyadh.jpg",
      "LG-1.webp", "bwlyfard_syty_balryad_25321bd3b8.jpg", "Boulevard_Riyadh_City.jpg"
    ];
    if (legacyIllustrations.some(file => path.endsWith('/' + file))) return "";
    return url.href;
  } catch { return ""; }
}
window.getPlaceImage = getPlaceImage;

function formatTripDuration(days) {
  const count=Number(days), ar=document.documentElement?.lang==="ar";
  if(ar){if(count===1)return "يوم واحد";if(count===2)return "يومان";return `${count.toLocaleString("ar-SA")} ${count<=10?"أيام":"يومًا"}`;}
  return `${count} ${count===1?"day":"days"}`;
}
window.formatTripDuration=formatTripDuration;

function formatPlaceCount(value) {
  const count=Number(value),ar=document.documentElement?.lang==="ar";
  if(!ar)return `${count} ${count===1?"place":"places"}`;
  if(count===0)return "لا أماكن";if(count===1)return "مكان واحد";if(count===2)return "مكانان";
  const unit=({few:"أماكن",many:"مكانًا",other:"مكان"})[new Intl.PluralRules("ar").select(count)]||"مكان";
  return `${count.toLocaleString("ar-SA")} ${unit}`;
}
window.formatPlaceCount=formatPlaceCount;

function replacePageUrl(url) {
  history.replaceState(null,"",url);
  // Language switching must follow the live URL, not a consumed save/place intent
  // from the server-rendered page that would repeat an action after switching.
  const next=location.pathname.replace(/^\/ar(?=\/)/,"")+location.search+location.hash;
  document.querySelectorAll('.language-form input[name="next"]').forEach(input=>{input.value=next;});
}
window.replacePageUrl=replacePageUrl;

const tripCoverCache=new Map();
function hydrateTripCover(image,item,currentTrip=null) {
  async function load(){
    try {
      const key=`${item.id}:${item.revision}`;
      let photo=tripCoverCache.get(key);
      if(photo===undefined){const data=currentTrip||await apiGet(`/api/trips/${encodeURIComponent(item.id)}/`);photo=window.TizahabPhotos?.tripPhoto(data)||null;if(tripCoverCache.size>64)tripCoverCache.clear();tripCoverCache.set(key,photo);}
      if(!photo||!image.isConnected)return;
      image.src=photo.src;image.srcset=photo.srcset;image.sizes="(min-width:900px) 32vw, (min-width:640px) 48vw, 100vw";image.alt=photo.title;
    }catch{/* A failed cover request keeps the licensed Riyadh skyline fallback. */}
  }
  if(typeof IntersectionObserver==="undefined"){load();return;}
  const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting)){observer.disconnect();load();}},{rootMargin:"100px"});observer.observe(image);
}
window.hydrateTripCover=hydrateTripCover;

// Keep the save intent when switching between sign-in and registration.
document.addEventListener("DOMContentLoaded", () => {
  const next = safeInternalRedirect(new URLSearchParams(location.search).get("next"));
  if (!next) return;
  document.querySelectorAll('a[href$="/signup/"], a[href$="/login/"]').forEach(link => {
    link.href += "?next=" + encodeURIComponent(next);
  });
});

function catIcon(category) {
  return ({culture:'landmark', heritage:'landmark', food:'utensils', nature:'trees',
    shopping:'shopping-bag', events:'ticket', family:'users', entertainment:'sparkles'})[category] || 'compass';
}
window.catIcon = catIcon;
