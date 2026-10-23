/* Device-local guest drafts; reading never extends the seven-day lifetime. */
(function (root) {
  const KEY = "tizahab_guest_trip_v1";
  const TTL = 7 * 24 * 60 * 60 * 1000;
  function load(storage, now = Date.now()) {
    try {
      const draft = JSON.parse(storage.getItem(KEY) || "null");
      if (!draft || !Number.isFinite(draft.editedAt) || now - draft.editedAt >= TTL || draft.editedAt > now || !draft.trip) {
        storage.removeItem(KEY);
        return null;
      }
      return draft.trip;
    } catch { return null; }
  }
  function save(storage, trip, now = Date.now()) {
    storage.setItem(KEY, JSON.stringify({editedAt: now, trip}));
  }
  const PENDING_KEY = "tizahab_pending_trips_v1";
  const pendingId = (owner, id) => Number.isSafeInteger(+owner) && +owner > 0 && Number.isSafeInteger(+id) && +id > 0 ? `${owner}:${id}` : null;
  function pendingEntries(storage) {
    const entries=JSON.parse(storage.getItem(PENDING_KEY)||"{}");
    return entries && typeof entries === "object" && !Array.isArray(entries) ? entries : {};
  }
  function savePending(storage, owner, trip, revision, confirmed, now=Date.now()) {
    const key=pendingId(owner,trip.id);
    if(!key || !Number.isSafeInteger(+revision) || +revision < 1) throw new Error("Recovery owner or revision unavailable");
    const entries=pendingEntries(storage);
    entries[key]={trip,revision:+revision,confirmed:Boolean(confirmed),editedAt:now};
    storage.setItem(PENDING_KEY,JSON.stringify(entries));
  }
  function loadPending(storage, owner, id, now=Date.now()) {
    try {
      const key=pendingId(owner,id);if(!key)return null;
      const entry=pendingEntries(storage)[key];
      if(!entry || !Number.isFinite(entry.editedAt) || now-entry.editedAt>=TTL || entry.editedAt>now || +entry.trip?.id!==+id || !Number.isSafeInteger(entry.revision) || entry.revision<1)return null;
      return entry;
    }catch{return null;}
  }
  function clearPending(storage, owner, id) {
    const entries=pendingEntries(storage);delete entries[pendingId(owner,id)];
    if(Object.keys(entries).length)storage.setItem(PENDING_KEY,JSON.stringify(entries));
    else storage.removeItem(PENDING_KEY);
  }
  function riyadhDate(date = new Date()) {
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en", {timeZone:"Asia/Riyadh",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(date).filter(part=>part.type!=="literal").map(part=>[part.type,part.value]));
    return `${parts.year}-${parts.month}-${parts.day}`;
  }
  const api = {KEY, TTL, load, save, riyadhDate, PENDING_KEY, savePending, loadPending, clearPending};
  if (typeof module !== "undefined") module.exports = api;
  else root.TripDrafts = api;
})(typeof window === "undefined" ? this : window);
