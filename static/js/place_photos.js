/* Exact destination matches only. Rights and original files: images/places/credits.json. */
(function (root) {
  "use strict";
  const base = typeof document !== "undefined" && document.currentScript
    ? new URL("../images/places/", document.currentScript.src).href : "/static/images/places/";
  const normalize = value => String(value || "").normalize("NFKC").toLowerCase().trim().replace(/\s+/g, " ");
  const entries = [
    ["faisaliyah", ["Al Faisaliyah Tower", "Al Faisaliah Tower", "برج الفيصلية", "Al Faisaliah Mall"], [480, 960, 1280]],
    ["at-turaif", ["At-Turaif UNESCO Site", "At-Turaif District", "حي الطريف"], [480, 960, 1280]],
    ["kingdom-centre", ["Kingdom Centre", "Sky Bridge Kingdom Centre", "برج المملكة", "Kingdom Centre Mall"], [480, 960, 1280]],
    ["murabba", ["Murabba Palace", "قصر المربع"], [480, 960, 1280]],
    ["national-museum", ["National Museum of Saudi Arabia", "Saudi National Museum", "المتحف الوطني السعودي"], [480, 960, 1280]],
    ["wadi-hanifa", ["Wadi Hanifa", "وادي حنيفة"], [480, 960, 1280]],
    ["wadi-namar", ["Wadi Namar", "Wadi Nemar", "وادي نمار", "Lake Park Namars"], [480, 960, 1280]],
    ["masmak", ["Al Masmak Fortress", "Al Masmak Palace", "Masmak Fort", "قصر المصمك"], [480, 960, 1280]],
    ["historical-center", ["King Abdulaziz Historical Center", "مركز الملك عبدالعزيز التاريخي"], [480, 960, 1280]],
    ["king-fahd-library", ["King Fahad National Library", "King Fahd National Library", "مكتبه فهد", "مكتبة الملك فهد الوطنية"], [480, 960, 1280]],
    ["air-force-museum", ["Royal Saudi Air Force Museum", "Saqr Al-Jazira Aviation Museum", "Sakr al Jazeera Aviation Museum", "متحف صقر الجزيرة للطيران"], [480, 960, 1280]],
    ["boulevard-city", ["Boulevard City", "Boulevard Riyadh City", "بوليفارد سيتي"], [480, 960, 1280]],
    ["boulevard-world", ["Boulevard World", "بوليفارد وورلد"], [480, 960, 1280]],
    ["riyadh-zoo", ["Riyadh Zoo", "Malaz Zoo", "حديقة الحيوان بالرياض"], [480, 960, 1280]],
    ["via-riyadh", ["Via Riyadh", "ڤيا رياض", "فيا رياض"], [480, 960, 1280]],
    ["roshn-front", ["Roshn Front", "Riyadh Front", "واجهة روشن", "واجهة الرياض"], [480, 960, 1280]],
    ["riyadh-gallery", ["Riyadh Gallery", "Riyadh Gallery Mall", "الرياض جاليري"], [480, 960, 1280]],
    ["sahara-mall", ["Sahara Mall", "صحارى مول"], [480, 960, 1280]],
    ["nakheel-mall", ["Al Nakheel Mall", "Nakheel Mall", "النخيل مول"], [480, 600]],
    ["qasr-al-hukm", ["Qasr Al Hukm", "قصر الحكم"], [480, 960, 1280]],
    ["thumairi-gate", ["Al Thumairi gate", "بوابة الثميري"], [480, 960, 1280]],
    ["edge-of-the-world", ["Edge of the World", "حافة العالم"], [480, 960, 1280]],
    ["king-abdullah-park", ["King Abdullah Park", "منتزه الملك عبدالله", "حديقة الملك عبدالله"], [480, 960, 1280]],
    ["salam-park", ["Salam Park", "Al Salam Park", "منتزه سلام"], [480, 960, 1280]],
    ["manakh-park", ["Manakh Park", "منتزه المناخ"], [480, 960, 1280]],
    ["futah-park", ["Al Futah Park", "حديقة الفوطة"], [480, 960, 1280]],
    ["diriyah-old-town", ["Ad Diriyah", "Diriyah Old Town", "Diriyah Cultural Zone", "الدرعية التاريخية"], [480, 960, 1280]],
    ["salwa-palace", ["Salwa Palace", "قصر سلوى"], [480, 960, 1280]],
    ["deera-square", ["Deera Square", "ساحة الديرة"], [480, 960, 1280]],
    ["imam-turki-mosque", ["Imam Turki Grand Mosque", "جامع الإمام تركي بن عبدالله"], [480, 960, 1280]],
    ["thumairi-souq", ["Souq Al Thumairi", "سوق الثميري"], [480, 960, 1280]],
    ["al-hair-lake", ["Al Hair Lake", "بحيرة الحائر"], [480, 960, 1280]],
    ["red-dunes-riyadh", ["Red Sand Dunes", "الكثبان الرملية الحمراء"], [480, 960, 1000]],
    ["wadi-laban", ["Wadi Laban", "وادي لبن"], [480, 960, 1280]],
    ["granada-mall", ["Granada Center", "Granada Mall", "غرناطه مول", "غرناطة مول"], [480, 960, 1280]],
    ["remal-mall", ["Remal Mall", "Remal Centre", "الرمال مول"], [480, 960, 1280]],
    ["suweigah-souq", ["Swaigah Commercial Center", "سوق سويقة"], [480, 960, 1280]],
    ["historical-center-park", ["King Abdulaziz Historical Center Park"], [480, 960, 1280]],
    ["six-flags-qiddiya", ["Six Flags Qiddiya City", "Qiddiya City", "سيكس فلاجز القدية"], [480, 960, 1280]],
    ["hayat-mall", ["Hayat Mall", "حياة مول"], [400]],
    ["aquarabia", ["AquArabia Qiddiya City", "Aquarabia", "أكواريبيا القدية"], [480, 960, 1280]]
  ];
  const catalogue = new Map(entries.flatMap(([slug, titles, widths = [480, 960, 1280]]) => titles.map(title => [normalize(title), {slug, widths}])));
  function photo(event) {
    const entry = catalogue.get(normalize(event?.title || event?.name));
    if (!entry) return null;
    const {slug, widths} = entry;
    const displayWidth = widths.find(width => width >= 960) || widths[widths.length - 1];
    return {slug, src:`${base}${slug}-${displayWidth}.webp`, srcset:widths.map(width => `${base}${slug}-${width}.webp ${width}w`).join(", ")};
  }
  function tripPhoto(trip) {
    const items=[...(trip?.days||[]).flatMap(day=>day.items||[]),...(trip?.unscheduled||[])];
    for(const item of items){const result=photo(item.event);if(result)return {...result,title:item.event.title};}
    return null;
  }
  root.TizahabPhotos = {photo,tripPhoto};
  if (typeof module !== "undefined") module.exports = {photo,tripPhoto};
})(typeof window === "undefined" ? globalThis : window);
