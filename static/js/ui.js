/* Shared navigation, theme and accessible overlay behavior. */
(function () {
  "use strict";
  window.toggleTheme = function (mode) {
    localStorage.setItem("tz_theme", mode);
    document.documentElement.dataset.theme = mode === "auto" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : mode;
  };
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (localStorage.getItem('tz_theme') === 'auto') window.toggleTheme('auto');
  });
  document.addEventListener("DOMContentLoaded", () => {
    if (window.lucide) lucide.createIcons();
    const drawer = document.getElementById("sidebar");
    const trigger = document.getElementById("mobileMenuBtn");
    const overlay = document.getElementById("sidebarOverlay");
    const close = document.getElementById("closeSidebarBtn");
    function closeDrawer() {
      drawer?.classList.remove("is-open");
      if (drawer) drawer.inert = true;
      overlay?.classList.add("hidden");
      document.body.classList.remove("drawer-open");
      trigger?.setAttribute("aria-expanded", "false");
      trigger?.focus();
    }
    trigger?.addEventListener("click", () => {
      drawer.inert = false;
      drawer.classList.add("is-open");
      overlay.classList.remove("hidden");
      document.body.classList.add("drawer-open");
      trigger.setAttribute("aria-expanded", "true");
      requestAnimationFrame(() => close?.focus());
    });
    close?.addEventListener("click", closeDrawer);
    overlay?.addEventListener("click", closeDrawer);
    const path = location.pathname.replace(/\/$/, "");
    document.querySelectorAll(".nav-item").forEach(link => {
      const target = link.getAttribute("href").replace(/\/$/, "");
      if (path === target || (target.includes('/events/page') && path.startsWith(target))) link.setAttribute("aria-current", "page");
    });
    document.querySelectorAll(".mobile-travel-nav .nav-item").forEach(link=>{
      const destination=new URL(link.href,location.origin);
      const currentPath=location.pathname.replace(/\/$/,"");
      const match=currentPath===destination.pathname.replace(/\/$/,"")&&((destination.searchParams.get("view")==="saved") === (new URLSearchParams(location.search).get("view")==="saved"));
      if(match)link.setAttribute("aria-current","page");else link.removeAttribute("aria-current");
    });
    const modals = [...document.querySelectorAll('#planDayModal, #addActivityModal')];
    let activeModal = null, previousFocus = null;
    const focusable = root => [...root.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),summary,[tabindex="0"]')].filter(el => el.getClientRects().length);
    modals.forEach(modal => {
      const heading = modal.querySelector('h3');
      if (heading) { heading.id ||= modal.id + 'Title'; modal.setAttribute('aria-labelledby', heading.id); }
      modal.setAttribute('role','dialog'); modal.setAttribute('aria-modal','true');
      modal.querySelector('button[id^="close"],#closeAddActivity')?.setAttribute('aria-label',document.documentElement.lang === 'ar' ? 'إغلاق' : 'Close');
      new MutationObserver(() => {
        if (!modal.classList.contains('hidden') && activeModal !== modal) {
          previousFocus = document.activeElement; activeModal = modal;
          focusable(modal)[0]?.focus();
        } else if (modal.classList.contains('hidden') && activeModal === modal) {
          activeModal = null; previousFocus?.focus();
        }
      }).observe(modal,{attributes:true,attributeFilter:['class']});
    });
    document.addEventListener('keydown', event => {
      const root = activeModal || (drawer?.classList.contains('is-open') ? drawer : null);
      if (!root) return;
      if (event.key === 'Escape') {
        if (activeModal) activeModal.querySelector('button[id^="close"],#closeAddActivity')?.click(); else closeDrawer();
      }
      if (event.key === 'Tab') {
        const items = focusable(root), first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault();last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault();first?.focus(); }
      }
    });
  });
})();
