/* Small, shared renderer for real destination data on the landing and home pages. */
(function () {
  "use strict";
  const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[char]));
  window.renderDiscoveryPlaces = function (data) {
    const grid = document.getElementById("recommendedPlaces");
    if (!grid) return;
    const ar = document.documentElement.lang === "ar";
    const places = (Array.isArray(data) ? data : data?.results || []).filter(place => place?.id && place?.title).slice(0, 3);
    if (!places.length) {
      grid.innerHTML = `<div class="card p-8 col-span-full text-center"><p>${ar ? "لا توجد أماكن لعرضها الآن." : "No places to show right now."}</p><a class="text-link inline-block mt-3" href="${ar ? '/ar' : ''}/events/page/">${ar ? "افتح دليل الأماكن" : "Open the destination directory"} ↗</a></div>`;
      return;
    }
    grid.innerHTML = places.map(place => `<a class="destination-card" href="${ar ? '/ar' : ''}/events/page/${encodeURIComponent(place.id)}/">
      ${getPlaceImage(place,true) ? `<img src="${escape(getPlaceImage(place,true))}" ${window.TizahabPhotos?.photo(place) ? `srcset="${escape(TizahabPhotos.photo(place).srcset)}" sizes="(min-width:900px) 32vw, (min-width:640px) 48vw, 100vw"` : ""} decoding="async" alt="${escape(place.title)}" width="640" height="420" loading="lazy" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><div hidden class="destination-image-fallback"><i data-lucide="${catIcon(place.category)}" aria-hidden="true"></i></div>` : `<div class="destination-image-fallback"><i data-lucide="${catIcon(place.category)}" aria-hidden="true"></i></div>`}
      <div class="destination-card-content"><span class="category-label">${escape(catLabel(place.category))}</span><h3 data-user-content>${escape(place.title)}</h3><p>${escape(place.area || place.location || (ar ? "الرياض" : "Riyadh"))}</p><div class="flex justify-between gap-4 mt-5 pt-4 border-t"><span class="text-xs text-gray-500">${escape(formatEventPrice(place.price))}</span><span class="text-link">${ar ? "اكتشف المكان" : "Discover place"} ↗</span></div></div></a>`).join("");
    if (window.lucide) lucide.createIcons();
  };
  document.addEventListener("DOMContentLoaded", async () => {
    if (document.getElementById("planCard")) return;
    try { const data=await apiGet("/api/events/?page_size=100"); const places=Array.isArray(data)?data:data.results||[]; const unique=new Map();places.forEach(place=>{const photo=window.TizahabPhotos?.photo(place);if(photo&&!unique.has(photo.slug))unique.set(photo.slug,place);}); const photographed=[...unique.values()]; window.renderDiscoveryPlaces([...photographed,...places.filter(place=>!photographed.includes(place))]); }
    catch {
      const grid = document.getElementById("recommendedPlaces");
      if (grid) grid.innerHTML = `<div role="alert" class="card p-8 col-span-full text-center"><p>${document.documentElement.lang === 'ar' ? "تعذّر تحميل الأماكن. حاول إعادة تحميل الصفحة." : "We couldn't load places. Please reload the page to try again."}</p></div>`;
    }
  });
})();
