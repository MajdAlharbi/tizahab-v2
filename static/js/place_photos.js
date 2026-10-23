/* Exact destination matches only. Rights and original files: images/places/credits.json. */
(function (root) {
  "use strict";
  const base = typeof document !== "undefined" && document.currentScript
    ? new URL("../images/places/", document.currentScript.src).href : "/static/images/places/";
  const normalize = value => String(value || "").normalize("NFKC").toLowerCase().trim().replace(/\s+/g, " ");
  const entries = [
    ["at-turaif", ["At-Turaif UNESCO Site", "At-Turaif District", "حي الطريف"]],
    ["masmak", ["Al Masmak Fortress", "Al Masmak Palace", "Masmak Fort", "قصر المصمك"]],
    ["national-museum", ["National Museum of Saudi Arabia", "Saudi National Museum", "المتحف الوطني السعودي"]],
    ["murabba", ["Murabba Palace", "قصر المربع"]],
    ["wadi-hanifa", ["Wadi Hanifa", "وادي حنيفة"]],
    ["wadi-namar", ["Wadi Namar", "Wadi Nemar", "وادي نمار"]],
    ["kingdom-centre", ["Kingdom Centre", "Sky Bridge Kingdom Centre", "برج المملكة"]],
    ["faisaliyah", ["Al Faisaliyah Tower", "Al Faisaliah Tower", "برج الفيصلية"]]
  ];
  const catalogue = new Map(entries.flatMap(([slug, titles]) => titles.map(title => [normalize(title), slug])));
  function photo(event) {
    const slug = catalogue.get(normalize(event?.title || event?.name));
    if (!slug) return null;
    return {slug, src:base + slug + "-960.webp", srcset:[480,960,1280].map(width => `${base}${slug}-${width}.webp ${width}w`).join(", ")};
  }
  function tripPhoto(trip) {
    const items=[...(trip?.days||[]).flatMap(day=>day.items||[]),...(trip?.unscheduled||[])];
    for(const item of items){const result=photo(item.event);if(result)return {...result,title:item.event.title};}
    return null;
  }
  root.TizahabPhotos = {photo,tripPhoto};
  if (typeof module !== "undefined") module.exports = {photo,tripPhoto};
})(typeof window === "undefined" ? globalThis : window);
