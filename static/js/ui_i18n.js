/* Bilingual labels for legacy vanilla-JS renderers. Static copy uses Django gettext. */
(function () {
  "use strict";
  const messages = window.TZ_UI_MESSAGES || {};
  function translate(text) {
    const value = String(text).trim();
    if (messages[value]) return String(text).replace(value, messages[value]);
    if (value.endsWith(':') && messages[value.slice(0, -1)]) return messages[value.slice(0, -1)] + ':';
    if (/^[\d., –-]+ SAR$/.test(value)) return value.replace(/SAR$/, 'ر.س');
    let match;
    if ((match = value.match(/^(\d+)(m|h|d) ago$/))) return `منذ ${match[1]} ${({m:"دقيقة",h:"ساعة",d:"يوم"})[match[2]]}`;
    if ((match = value.match(/^Showing (\d+)[–-](\d+) of (\d+) events$/))) return `عرض ${match[1]}–${match[2]} من ${match[3]} مكان`;
    if ((match = value.match(/^Page (\d+) of (\d+)$/))) return `الصفحة ${match[1]} من ${match[2]}`;
    if ((match = value.match(/^(\d+) of (\d+) users$/))) return `${match[1]} من ${match[2]} مستخدمين`;
    if ((match = value.match(/^(\d+)% of events$/))) return `${match[1]}% من الأماكن`;
    if ((match = value.match(/^(\d+) times$/))) return `${match[1]} مرات`;
    if ((match = value.match(/^Edit (.+)$/))) return `تعديل ${match[1]}`;
    if ((match = value.match(/^Delete user (.+)$/))) return `حذف المستخدم ${match[1]}`;
    if ((match = value.match(/^Delete (.+)$/))) return `حذف ${match[1]}`;
    if ((match = value.match(/^(\d{2}:\d{2}) (AM|PM)$/))) return `${match[1]} ${match[2] === 'AM' ? 'ص' : 'م'}`;
    if ((match = value.match(/^(\d+) activit(?:y|ies)$/))) return `${match[1]} أنشطة`;
    if ((match = value.match(/^(\d+) favorites$/))) return `${match[1]} أماكن مفضلة`;
    if ((match = value.match(/^Day (\d+) of (\d+)$/))) return `اليوم ${match[1]} من ${match[2]}`;
    if ((match = value.match(/^Day (\d+)$/))) return `اليوم ${match[1]}`;
    if ((match = value.match(/^Step (\d+) of 5$/))) return `الخطوة ${match[1]} من 5`;
    if ((match = value.match(/^(\d+) activit(?:y|ies) planned$/))) return `${match[1]} أنشطة في الخطة`;
    if ((match = value.match(/^Showing (\d+) of (\d+) places$/))) return `عرض ${match[1]} من ${match[2]} مكان`;
    if ((match = value.match(/^(\d+) places(?: found)?$/))) return `${match[1]} مكان`;
    if ((match = value.match(/^Load More \((\d+) remaining\)$/))) return `عرض المزيد (${match[1]} متبقٍ)`;
    if ((match = value.match(/^Rating ([\d.]+)$/))) return `التقييم ${match[1]}`;
    if ((match = value.match(/^No (breakfast|activity|lunch|evening) planned yet$/))) return `لم تُضف ${messages[match[1]] || match[1]} بعد`;
    if ((match = value.match(/^Add to (Breakfast|Activity|Lunch|Evening)$/))) return `أضف إلى ${messages[match[1]] || match[1]}`;
    if ((match = value.match(/^(\d+) days?$/))) return Number(match[1]) === 1 ? "يوم واحد" : Number(match[1]) === 2 ? "يومان" : `${match[1]} ${Number(match[1]) <= 10 ? "أيام" : "يومًا"}`;
    if ((match = value.match(/^Active filters: (.+)$/))) return 'الفلاتر النشطة: ' + match[1].split(' + ').map(part => messages[part] || part).join(' + ');
    return text;
  }
  window.tzTranslateText = translate;
  document.addEventListener('DOMContentLoaded', () => {
    if (document.documentElement.lang !== 'ar') return;
    function localize(root) {
      if (root.nodeType === 3) {
        if (root.parentElement?.closest('script,style,textarea,[data-user-content]')) return;
        const translated = translate(root.nodeValue);
        if (translated !== root.nodeValue) root.nodeValue = translated;
        return;
      }
      if (root.nodeType !== 1 || root.matches('script,style,textarea,[data-user-content]')) return;
      for (const attr of ['placeholder','aria-label','title']) {
        if (root.hasAttribute(attr)) {
          const original = root.getAttribute(attr), translated = translate(original);
          if (translated !== original) root.setAttribute(attr,translated);
        }
      }
      // Keep internal navigation on the language currently selected in Django.
      if (root.matches('a[href]')) {
        const href = root.getAttribute('href');
        if (/^\/(?:home|daily-plan|events\/page|onboarding|profile|settings|travel-guide|booking|car-rental|login|signup)(?:\/|\?|$)/.test(href)) root.setAttribute('href','/ar' + href);
      }
      root.childNodes.forEach(localize);
    }
    localize(document.body);
    new MutationObserver(records => {
      for (const record of records) {
        if (record.type === 'characterData') localize(record.target);
        else if (record.type === 'attributes') localize(record.target);
        else record.addedNodes.forEach(localize);
      }
    }).observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','aria-label','title']});
  });
})();
