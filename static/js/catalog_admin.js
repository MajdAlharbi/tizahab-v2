(function () {
  "use strict";
  const ar=document.documentElement.lang==="ar";
  const t=(en,arabic)=>ar?arabic:en;
  const $=id=>document.getElementById(id);
  const node=(tag,text,className)=>{const item=document.createElement(tag);if(text!==undefined)item.textContent=text;if(className)item.className=className;return item;};
  const action=(text,callback)=>{const item=node("button",text,"btn-outline");item.type="button";item.addEventListener("click",async()=>{item.disabled=true;try{await callback();}catch(error){$("catalogStatus").textContent=error.message;}finally{item.disabled=false;}});return item;};
  let queueUrl="/api/events/admin/review/";
  async function confirmation(text){const dialog=$("catalogDecision");$("catalogDecisionText").textContent=text;dialog.returnValue="cancel";dialog.showModal();return new Promise(resolve=>dialog.addEventListener("close",()=>resolve(dialog.returnValue==="confirm"),{once:true}));}
  window.confirmContentAction=confirmation;
  async function loadSources(){
    const target=$("catalogSources");target.replaceChildren(node("p",t("Loading sources…","جارٍ تحميل المصادر…")));
    try{
      const sources=await apiGet("/api/events/admin/sources/");target.replaceChildren();
      sources.forEach(source=>{const card=node("article",undefined,"card p-4 space-y-3");card.append(node("h3",source.provider));
        card.append(node("p",source.enabled?t("Enabled","مفعّل"):t("Disabled — local catalogue stays available","معطّل — الدليل المحلي ما زال متاحًا"),"text-sm"));
        const run=source.last_run;card.append(node("p",run?`${run.status} · ${t("Received","مستلم")}: ${run.received} · ${t("For review","للمراجعة")}: ${run.queued}`:t("No sync has run yet.","لم تُنفذ مزامنة بعد."),"text-sm"));
        if(run?.error)card.append(node("p",run.error,"text-sm"));
        if(source.next_sync_at)card.append(node("p",t("Next due: ","الموعد التالي: ")+new Date(source.next_sync_at).toLocaleString(ar?"ar-SA-u-ca-gregory":"en-GB"),"text-sm"));
        card.append(action(t("Run due sync","تشغيل المزامنة المستحقة"),async()=>{try{const result=await apiPost(`/api/events/admin/sources/${source.id}/sync/`,{});$("catalogStatus").textContent=result.detail;}finally{await loadSources();await loadQueue();}}));target.append(card);
      });
    }catch(error){target.replaceChildren(node("p",error.message));}
  }
  async function loadQueue(){
    const target=$("reviewQueue");target.replaceChildren(node("p",t("Loading review queue…","جارٍ تحميل قائمة المراجعة…")));
    try{
      const url=new URL(queueUrl,location.origin);if(url.origin!==location.origin)throw new Error("Invalid review page");
      const data=await apiGet(url.pathname+url.search);target.replaceChildren();
      $("reviewCount").textContent=`${data.count} ${t("awaiting review","بانتظار المراجعة")}`;
      if(!data.results.length)target.append(node("p",t("Nothing awaiting review. New source data appears here after a successful sync.","لا توجد بيانات بانتظار المراجعة. تظهر سجلات المصادر هنا بعد مزامنة ناجحة.")));
      for(const record of data.results){
        const card=node("article",undefined,"card p-4 space-y-3");card.append(node("h3",record.payload.title));card.append(node("p",`${record.source} · ${record.external_id} · ${record.payload.source_license||t("License unspecified","الترخيص غير محدد")}`,"text-sm"));
        card.append(node("p",record.current?t("Update to an existing place — published content stays unchanged until approval.","تحديث لمكان موجود — لا يتغير المنشور قبل الموافقة."):t("New place — not public yet.","مكان جديد — غير منشور بعد."),"text-sm"));
        const detail=node("details");detail.append(node("summary",t("Compare current and proposed data","مقارنة البيانات الحالية والمقترحة")));
        const pre=node("pre",JSON.stringify({current:record.current,proposed:record.payload},null,2));pre.dir="ltr";pre.style.cssText="white-space:pre-wrap;overflow-wrap:anywhere;max-height:340px;overflow:auto;font-size:12px;padding:1rem";detail.append(pre);card.append(detail);
        const controls=node("div",undefined,"flex gap-3 flex-wrap");
        for(const decision of ["approve","reject"])controls.append(action(decision==="approve"?t("Approve and publish","موافقة ونشر"):t("Reject change","رفض التغيير"),async()=>{
          if(!await confirmation(decision==="approve"?t("Publish these reviewed changes? Existing user plans will refer to the updated place.","نشر هذه التغييرات بعد مراجعتها؟ ستعرض الخطط المحفوظة بيانات المكان المحدثة."):t("Reject this proposal and keep current published content?","رفض المقترح والإبقاء على البيانات المنشورة؟")))return;
          await apiPost(`/api/events/admin/review/${record.id}/`,{decision,last_seen_at:record.last_seen_at});$("catalogStatus").textContent=t("Review saved.","تم حفظ قرار المراجعة.");await Promise.all([loadQueue(),loadAudit()]);if(window.loadEvents)await window.loadEvents();if(window.loadStats)await window.loadStats();
        }));card.append(controls);target.append(card);
      }
      if(data.next)target.append(action(t("Next review page","صفحة المراجعة التالية"),async()=>{queueUrl=data.next;await loadQueue();}));
      if(queueUrl!=="/api/events/admin/review/")target.append(action(t("First page","الصفحة الأولى"),async()=>{queueUrl="/api/events/admin/review/";await loadQueue();}));
    }catch(error){target.replaceChildren(node("p",error.message));}
  }
  async function loadAudit(){
    const target=$("contentAudit");
    try{const data=await apiGet("/api/events/admin/audit/");target.replaceChildren();if(!data.results.length)target.append(node("p",t("No content changes recorded yet.","لم تُسجل تغييرات محتوى بعد.")));
      for(const entry of data.results){const detail=node("details",undefined,"py-2 border-b");detail.append(node("summary",`${entry.action} · ${entry.target} · ${entry.actor||"—"} · ${new Date(entry.created_at).toLocaleString(ar?"ar-SA-u-ca-gregory":"en-GB")}`));const pre=node("pre",JSON.stringify({before:entry.before,after:entry.after},null,2));pre.dir="ltr";pre.style.cssText="white-space:pre-wrap;overflow-wrap:anywhere;max-height:280px;overflow:auto;font-size:12px";detail.append(pre);target.append(detail);}
    }catch(error){target.replaceChildren(node("p",error.message));}
  }
  document.addEventListener("DOMContentLoaded",()=>{loadSources();loadQueue();loadAudit();});
})();
