/* Trip-first experience. DOM text nodes keep destination/provider data inert. */
(async function () {
  "use strict";
  const ar = document.documentElement.lang === "ar";
  const t = (en, arabic) => ar ? arabic : en;
  const prefix = ar ? "/ar" : "";
  const $ = id => document.getElementById(id);
  const categories = {culture:t("Culture","ثقافة"),heritage:t("Heritage","تراث"),nature:t("Nature","طبيعة"),food:t("Food","مطاعم"),shopping:t("Shopping","تسوق"),family:t("Family","عائلة"),events:t("Events","فعاليات"),entertainment:t("Entertainment","ترفيه")};
  let trip;
  let defaultPreferences=null;
  let savedId = null;
  let currentUserId = null;
  let revision = null;
  let dirty = false;
  let recoveryStored = false;
  let saving = false;
  let confirmedRemoval = false;
  let version = 0;
  let timer;
  let pickerContext = null;
  let searchVersion = 0;
  let busy = false;
  let activeDay = 0;
  let builderStep = 0;
  let planningComplete = false;
  let editingDetails = false;
  let libraryOpen = new URLSearchParams(location.search).get("view") === "saved";
  let showArchived = false;
  const clone = value => JSON.parse(JSON.stringify(value));
  const today = () => TripDrafts.riyadhDate();
  function element(tag, text, className) { const node=document.createElement(tag); if(text !== undefined) node.textContent=text; if(className) node.className=className; return node; }
  function button(text, action, className="btn-outline") { const node=element("button",text,className); node.type="button"; node.addEventListener("click",()=>Promise.resolve(action()).catch(showError)); return node; }
  function message(text="") { $("tripMessage").textContent=text;$("tripMessage").setAttribute("role","status"); }
  function showError(error) { message(error.message || t("Unable to complete this action. Your selections are still here.","تعذر إكمال الإجراء. اختياراتك ما زالت محفوظة هنا."));$("tripMessage").setAttribute("role","alert");$("tripMessage").scrollIntoView({block:"center"}); }
  function status(state) {
    const labels = {loading:t("Loading trip…","جارٍ تحميل الرحلة…"),saving:t("Saving…","جارٍ الحفظ…"),saved:t("Saved","تم الحفظ"),failed:recoveryStored?t("Save failed. Your edits can be recovered in this tab. Retry when connected.","فشل الحفظ. يمكن استعادة تعديلاتك في علامة التبويب هذه. أعد المحاولة عند عودة الاتصال."):t("Save failed. Your edits remain on this page.","فشل الحفظ. تعديلاتك ما زالت في هذه الصفحة."),draft:t("Draft on this device · 7 days after last edit","مسودة على هذا الجهاز · ٧ أيام من آخر تعديل"),unsaved:t("Unsaved changes","تعديلات غير محفوظة")};
    $("saveState").textContent=labels[state] || state;
    $("saveState").dataset.status=state;
    $("saveTrip").hidden=Boolean(savedId&&state==="saved");
  }
  async function confirmChange(text, list=[]) {
    const dialog=$("tripConfirm");
    $("confirmTitle").textContent=t("Review this change","راجع التغيير");
    $("confirmText").textContent=text;
    $("confirmList").replaceChildren(...list.map(value=>element("li",value)));
    dialog.returnValue="cancel";
    dialog.showModal();
    return new Promise(resolve=>dialog.addEventListener("close",()=>resolve(dialog.returnValue==="confirm"),{once:true}));
  }
  async function request(url, method="GET", data) {
    let response=await fetch(url,{method,credentials:"same-origin",headers:authHeaders(url),...(data===undefined?{}:{body:JSON.stringify(data)})});
    if(response.status===401 && (await _tryRefresh() || await _trySessionToken())) response=await fetch(url,{method,credentials:"same-origin",headers:authHeaders(url),...(data===undefined?{}:{body:JSON.stringify(data)})});
    if(!response.ok) {
      const body=await response.json().catch(()=>({}));
      const error=new Error(extractApiErrorMessage(body,t("Request failed. Please try again.","تعذر إكمال الطلب. حاول مجددًا.")));
      error.status=response.status; throw error;
    }
    return response.status===204?null:response.json();
  }
  function newDocument() { const defaults=defaultPreferences?.interests?.length ? {interests:[...defaultPreferences.interests],budget_min:defaultPreferences.budget_min??null,budget_max:defaultPreferences.budget_max??null,min_rating:defaultPreferences.min_rating==null?null:+defaultPreferences.min_rating} : {}; return {name:t("My Riyadh trip","رحلتي إلى الرياض"),start_date:today(),duration:1,preferences:{interests:["culture","heritage","nature"],budget_min:null,budget_max:null,min_rating:null,preferred_language:ar?"ar":"en",...defaults},days:[{date:today(),items:[]}],unscheduled:[]}; }
  function saveLocal() {
    try {
      if(savedId) {TripDrafts.savePending(sessionStorage,currentUserId,{...trip,id:savedId},revision,confirmedRemoval);recoveryStored=true;}
      else {TripDrafts.save(localStorage,trip);status("draft");}
    } catch {
      recoveryStored=false;status("failed");message(t("Device storage is unavailable. Keep this page open and save to your account.","تخزين الجهاز غير متاح. أبقِ الصفحة مفتوحة واحفظ في حسابك."));
    }
  }
  function setBusy(value) {
    busy=value;
    $("tripApp").setAttribute("aria-busy",String(value));
    $("tripLoading").hidden=!value;
    if($("siteLanguage"))$("siteLanguage").disabled=value||saving;
    document.querySelectorAll("#tripApp button, #tripApp input, #tripApp select").forEach(control=>{control.disabled=value;});
    if(!value && savedId && dirty && !saving) {clearTimeout(timer);timer=setTimeout(save,650);}
  }
  function changed({destructive=false}={}) {
    dirty=true; version++; confirmedRemoval ||= destructive;
    saveLocal();
    if(savedId) { status("unsaved"); clearTimeout(timer); timer=setTimeout(save,650); }
    render();
  }
  async function save() {
    if(saving || busy) return;
    if(!isLoggedIn()) {
      saveLocal();
      window.location.href=`${prefix}/login/?next=${encodeURIComponent(prefix+"/trips/?save=1")}`;
      return;
    }
    const currentVersion=version;
    const isNewTrip=!savedId;
    const body={...clone(trip),...(revision?{revision}:{}),confirmed:confirmedRemoval};
    saving=true; status("saving");if($("siteLanguage"))$("siteLanguage").disabled=true;
    try {
      const result=await request(savedId?`/api/trips/${savedId}/`:"/api/trips/",savedId?"PUT":"POST",body);
      savedId=result.id; revision=result.revision;
      if(currentVersion===version) { trip=result; dirty=false; confirmedRemoval=false; try{TripDrafts.clearPending(sessionStorage,currentUserId,savedId);}catch{} render(); status("saved"); message(""); }
      else { status("unsaved"); }
      if(isNewTrip) { try {localStorage.removeItem(TripDrafts.KEY);} catch {} }
      try {sessionStorage.setItem("tz_active_trip",String(savedId));} catch {}
      replacePageUrl(`${prefix}/trips/?trip=${savedId}`);
      await loadSaved();
    } catch(error) { status("failed"); showError(error); }
    finally { saving=false;if($("siteLanguage"))$("siteLanguage").disabled=busy; if(currentVersion!==version) { clearTimeout(timer); timer=setTimeout(save,650); } }
  }
  function fillForm() {
    $("tripName").value=trip.name; $("tripStart").value=trip.start_date; $("tripDuration").value=trip.duration;
    $("tripStart").min=planningComplete?"":today();
    const minimum=trip.preferences.min_rating;
    if(minimum!=null && ![...$("tripRating").options].some(option=>option.value===String(minimum))) $("tripRating").add(new Option(String(minimum),String(minimum)));
    $("tripMin").value=trip.preferences.budget_min ?? ""; $("tripMax").value=trip.preferences.budget_max ?? ""; $("tripRating").value=trip.preferences.min_rating ?? "";
    $("tripInterests").querySelectorAll("input").forEach(input=>{input.checked=trip.preferences.interests.includes(input.value);});
    $("applyTripDetails").textContent=planningComplete?t("Apply details","تطبيق التفاصيل"):t("Create my itinerary","أنشئ رحلتي");
  }
  function formatDay(date, options={day:"numeric",month:"short"}) { return new Intl.DateTimeFormat(ar?"ar-SA-u-ca-gregory":"en-GB",options).format(new Date(date+"T12:00:00")); }
  function showStep(index, focus=false) {
    builderStep=index;
    document.querySelectorAll(".builder-step").forEach(panel=>{panel.hidden=+panel.dataset.step!==index;});
    document.querySelectorAll("[data-wizard-step]").forEach(node=>{node.toggleAttribute("data-complete",+node.dataset.wizardStep<index);if(+node.dataset.wizardStep===index)node.setAttribute("aria-current","step");else node.removeAttribute("aria-current");});
    $("builderBack").hidden=index===0;$("builderNext").hidden=index===2;$("applyTripDetails").hidden=index!==2;$("builderError").hidden=true;
    if(focus){const heading=document.querySelector(`.builder-step[data-step="${index}"] h3`);heading?.focus({preventScroll:true});document.querySelector(`.builder-step[data-step="${index}"]`)?.scrollIntoView({block:"start",behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"instant":"smooth"});}
  }
  function validateStep() {
    const inputs=[...document.querySelector(`.builder-step[data-step="${builderStep}"]`).querySelectorAll("input,select")];
    for(const input of inputs){if(!input.reportValidity())return false;}
    if(builderStep===1&&!$("tripInterests").querySelector("input:checked")) {$("builderError").textContent=t("Choose at least one interest.","اختر اهتمامًا واحدًا على الأقل.");$("builderError").hidden=false;return false;}
    if(builderStep===2&&$("tripMin").value!==""&&$("tripMax").value!==""&&+$("tripMin").value>+$("tripMax").value){$("builderError").textContent=t("The minimum price must not exceed the maximum price.","يجب ألا يتجاوز أدنى سعر أعلى سعر.");$("builderError").hidden=false;return false;}
    return true;
  }
  function updateView() {
    $("savedTripsPanel").hidden=!libraryOpen;
    $("tripCreation").hidden=libraryOpen||(planningComplete&&!editingDetails);
    $("tripWorkspace").hidden=libraryOpen||!planningComplete||editingDetails;
    $("cancelTripDetails").hidden=!planningComplete;
    const itineraryVisible=planningComplete&&!editingDetails&&!libraryOpen;
    const libraryButton=$("showSavedTrips"),slot=itineraryVisible?$("itineraryLibrarySlot"):$("plannerIntro");
    const hadFocus=document.activeElement===libraryButton;
    if(libraryButton.parentElement!==slot){slot.append(libraryButton);if(hadFocus)libraryButton.focus({preventScroll:true});}
    $("tripApp").classList.toggle("has-itinerary",itineraryVisible);
    $("showSavedTrips").setAttribute("aria-expanded",String(libraryOpen));
  }
  async function loadSaved() {
    const target=$("savedTrips"); target.replaceChildren();$("archivedFilter").hidden=!isLoggedIn();
    if(!isLoggedIn()) { const empty=element("div",undefined,"trip-library-empty");empty.append(element("h3",t("Your next chapter starts here","حكايتك القادمة تبدأ هنا")),element("p",t("Plan freely as a guest. Sign in to find the trips saved to your account.","خطّط بحرية كضيف. سجّل الدخول لعرض الرحلات المحفوظة في حسابك.")));const login=element("a",t("Sign in","تسجيل الدخول"),"btn-outline");login.href=prefix+"/login/?next="+encodeURIComponent(prefix+"/trips/?view=saved");empty.append(login);target.append(empty);return; }
    try {
      target.append(element("p",t("Loading trips…","جارٍ تحميل الرحلات…"),"trip-note"));
      const trips=await request("/api/trips/"+(showArchived?"?archived=1":""));target.replaceChildren();
      if(!trips.length) target.append(element("p",showArchived?t("No archived trips.","لا توجد رحلات مؤرشفة."):t("No saved trips yet.","لا توجد رحلات محفوظة بعد."),"trip-note"));
      for(const item of trips) {
        const node=button("",()=>showArchived?restoreTrip(item):openTrip(item.id),"saved-trip-card");
        const cover=element("img");cover.src=new URL("../riyadh-skyline.webp",TizahabPhotos.photo({title:"At-Turaif UNESCO Site"}).src).href;cover.alt=t("Riyadh skyline","أفق الرياض");cover.width=640;cover.height=360;cover.loading="lazy";cover.className="saved-trip-cover";
        const copy=element("span",undefined,"saved-trip-copy");const name=element("strong",item.name);name.dataset.userContent="";name.dir="auto";copy.append(name,element("span",`${formatDay(item.start_date)} · ${formatTripDuration(item.duration)}`));node.append(cover,copy);
        if(showArchived)copy.append(element("span",t("Restore trip ↗","استعادة الرحلة ↗"),"text-link"));
        node.setAttribute("aria-current",String(item.id===savedId)); target.append(node);
        hydrateTripCover(cover,item,item.id===savedId?trip:null);
      }
    } catch(error) { target.replaceChildren(button(t("Could not load trips. Retry","تعذر تحميل الرحلات. إعادة المحاولة"),loadSaved)); }
  }
  async function openTrip(id) {
    if(saving || busy) return;
    if(dirty && !await confirmChange(t("Leave these unsaved edits? The current guest draft remains on this device.","مغادرة التعديلات غير المحفوظة؟ تبقى مسودة الضيف الحالية على هذا الجهاز."))) return;
    clearTimeout(timer);message("");setBusy(true);
    try {
      const data=await request(`/api/trips/${id}/`);
      if(data.is_archived){showArchived=true;$("showArchivedTrips").checked=true;libraryOpen=true;updateView();await loadSaved();message(t("This trip is archived. Restore it from your collection to edit it.","هذه الرحلة مؤرشفة. استعدها من قائمتك لتعديلها."));return;}
      if(!currentUserId)currentUserId=(await request("/api/auth/me/")).id;
      savedId=data.id;try{sessionStorage.setItem("tz_active_trip",String(savedId));}catch{}
      revision=data.revision;trip=data;dirty=false;confirmedRemoval=false;version++;planningComplete=true;editingDetails=false;libraryOpen=false;activeDay=0;
      const pending=TripDrafts.loadPending(sessionStorage,currentUserId,id);
      if(pending){
        const conflict=pending.revision!==data.revision;
        const prompt=conflict?t("This trip changed elsewhere. Restore your unsaved edits as a separate draft? The saved version will stay unchanged.","تغيرت الرحلة في جلسة أخرى. استعادة تعديلاتك غير المحفوظة كمسودة مستقلة؟ تبقى النسخة المحفوظة دون تغيير."):t("Unsaved edits were recovered in this tab. Restore them and retry saving? Cancel keeps the saved version; the recovery copy stays in this tab.","عُثر على تعديلات غير محفوظة في علامة التبويب هذه. استعادتها وإعادة محاولة الحفظ؟ الإلغاء يعرض النسخة المحفوظة، وتبقى نسخة الاستعادة في علامة التبويب.");
        if(await confirmChange(prompt)){
          trip=clone(pending.trip);dirty=true;confirmedRemoval=pending.confirmed;version++;
          if(conflict){savedId=null;revision=null;delete trip.id;delete trip.revision;try{sessionStorage.removeItem("tz_active_trip");}catch{}}
          saveLocal();
          if(conflict)message(t("Recovered as a separate draft. Save it when you are ready.","استُعيدت التعديلات كمسودة مستقلة. احفظها عندما تكون جاهزًا."));
        }
      }
      fillForm();render();status(dirty?(savedId?"unsaved":"draft"):"saved");replacePageUrl(savedId?`${prefix}/trips/?trip=${id}`:prefix+"/trips/");await loadSaved();
    } finally {setBusy(false);}
  }

  function eventWarnings(event) {
    const warnings=[]; const prefs=trip.preferences;
    if(prefs.interests.length && !prefs.interests.includes(event.category)) warnings.push(t("Outside selected interests","خارج الاهتمامات المختارة"));
    if(event.price!==null && event.price!==undefined) { if(prefs.budget_min!==null && +event.price<+prefs.budget_min) warnings.push(t("Below your price range","أقل من نطاق السعر")); if(prefs.budget_max!==null && +event.price>+prefs.budget_max) warnings.push(t("Above your price range","أعلى من نطاق السعر")); }
    if(prefs.min_rating!==null && (event.rating===null || +event.rating<+prefs.min_rating)) warnings.push(t("Below your minimum rating or rating unknown","أقل من التقييم المحدد أو التقييم مجهول"));
    return warnings;
  }
  function placeMedia(event, className="activity-media") {
    const media=element("div",undefined,className);
    const fallback=element("div",undefined,"destination-image-fallback");
    const symbol=element("i");symbol.dataset.lucide=catIcon(event.category);symbol.setAttribute("aria-hidden","true");fallback.append(symbol);
    const caption=element("span",t("Photo not yet available","الصورة غير متوفرة بعد"),"photo-unavailable");fallback.append(caption);media.append(fallback);
    const photo=window.TizahabPhotos?.photo(event);const src=getPlaceImage(event,true);
    if(src){media.classList.add("has-photo");fallback.hidden=true;const image=element("img");image.src=src;image.alt=event.title||"";image.width=960;image.height=640;image.loading="lazy";image.decoding="async";if(photo){image.srcset=photo.srcset;image.sizes="(min-width:900px) 300px, (min-width:640px) 45vw, 100vw";}image.addEventListener("error",()=>{image.remove();media.classList.remove("has-photo");media.closest(".trip-activity")?.classList.add("without-photo");fallback.hidden=false;},{once:true});media.append(image);}
    return media;
  }
  function periodLabel(slot) { return ({breakfast:t("Morning · breakfast","صباحًا · فطور"),activity:t("Daytime · explore","خلال اليوم · اكتشاف"),lunch:t("Midday · lunch","منتصف اليوم · غداء"),evening:t("Evening · unwind","مساءً · استمتع")})[slot]||t("Explore","اكتشاف"); }
  function renderActivity(item, dayIndex, position) {
    const event=item.event || {id:item.event_id,title:t("Place","مكان")};
    const row=element("article",undefined,"trip-activity");row.dataset.activityKey=item.key;
    const media=placeMedia(event);
    row.classList.toggle("without-photo",!media.classList.contains("has-photo"));
    const lock=button(item.locked?t("Locked","مقفول"):t("Lock","قفل"),()=>{item.locked=!item.locked;changed();},"activity-lock");lock.setAttribute("aria-pressed",String(item.locked));lock.title=t("Locked places stay during regeneration","الأماكن المقفلة تبقى عند إعادة الإنشاء");media.append(lock);
    const info=element("div",undefined,"activity-content");
    const period=element("p",undefined,"activity-period");period.append(element("span",(position+1).toLocaleString(ar?"ar-SA":"en-GB"),"activity-number"),document.createTextNode(periodLabel(item.slot_type)));info.append(period);
    const title=element("h3",event.title);title.dataset.userContent="";title.dir="auto";info.append(title);
    const meta=element("p",[categories[event.category]||event.category,formatEventPrice(event.price)].filter(Boolean).join(" · "),"trip-note");info.append(meta);
    if(event.area||event.location)info.append(element("p",event.area||event.location,"activity-location"));
    if(event.rating!=null)info.append(element("p",`★ ${event.rating} · ${t("Catalogue rating","تقييم الدليل")}`,"activity-rating"));
    const warnings=eventWarnings(event);if(warnings.length)info.append(element("p",warnings.join(" · "),"activity-warning"));
    if(event.is_active===false)info.append(element("p",t("No longer published — move or replace before saving this day.","المكان غير منشور حاليًا — انقله أو استبدله قبل حفظ اليوم."),"activity-warning"));
    const links=element("div",undefined,"activity-links");
    if(event.is_active!==false){const details=element("a",t("Place details ↗","تفاصيل المكان ↗"),"text-link");details.href=`${prefix}/events/page/${item.event_id}/`;details.target="_blank";details.rel="noopener";links.append(details);}
    if(event.latitude!=null&&event.longitude!=null){const map=element("a",t("Map ↗","الخريطة ↗"),"text-link");map.href=`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(event.latitude+","+event.longitude)}`;map.target="_blank";map.rel="noopener noreferrer";links.append(map);}
    info.append(links);
    const menu=element("details",undefined,"activity-edit");const summary=element("summary",t("Edit activity","تعديل النشاط"));summary.setAttribute("aria-label",`${t("Edit activity","تعديل النشاط")}: ${event.title}`);menu.append(summary);
    const actions=element("div",undefined,"activity-edit-controls");
    if(dayIndex!==null)actions.append(button(t("Replace","استبدال"),()=>showPicker(dayIndex,item.key)));
    const select=element("select");select.setAttribute("aria-label",t("Move activity","نقل النشاط"));const placeholder=element("option",t("Move to…","نقل إلى…"));placeholder.value="";select.append(placeholder);
    trip.days.forEach((day,index)=>{if(index!==dayIndex){const opt=element("option",`${t("Day","اليوم")} ${index+1} · ${day.date}`);opt.value=index;select.append(opt);}});
    if(dayIndex!==null){const opt=element("option",t("Unscheduled Places","أماكن غير مجدولة"));opt.value="unscheduled";select.append(opt);}
    select.addEventListener("change",()=>moveItem(item,dayIndex,select.value).catch(error=>{select.value="";showError(error);}));actions.append(select);
    actions.append(button(t("Remove","إزالة"),async()=>{if(await confirmChange(t("Remove this selected place?","إزالة هذا المكان المختار؟"),[event.title])){const list=dayIndex===null?trip.unscheduled:trip.days[dayIndex].items;list.splice(list.indexOf(item),1);changed({destructive:true});}},"btn-outline activity-remove"));menu.append(actions);info.append(menu);
    row.append(media,info);return row;
  }
  function selectDay(index, focus=false) {
    activeDay=index;
    document.querySelectorAll("[data-day-panel]").forEach(panel=>{panel.hidden=+panel.dataset.dayPanel!==index;});
    $("unscheduledPanel").hidden=index!==-1;
    document.querySelectorAll("[data-day-tab]").forEach(tab=>{const active=+tab.dataset.dayTab===index;tab.setAttribute("aria-selected",String(active));tab.tabIndex=active?0:-1;if(active&&focus)tab.focus({preventScroll:true});});
  }
  function render() {
    if(!trip)return;
    const focused=document.activeElement;const focusedKey=focused?.closest?.("[data-activity-key]")?.dataset.activityKey;const lockFocus=focused?.classList?.contains("activity-lock");
    $("activeTripName").textContent=trip.name;
    const total=trip.days.reduce((count,day)=>count+day.items.length,0);
    $("tripSummary").textContent=`${formatDay(trip.start_date)} · ${formatTripDuration(trip.duration)} · ${formatPlaceCount(total)}`;
    $("saveTrip").textContent=savedId?t("Save now","حفظ الآن"):t("Save trip","حفظ الرحلة");
    $("archiveTrip").hidden=!savedId;
    $("tripDays").replaceChildren();$("tripDayNav").replaceChildren();
    trip.days.forEach((day,index)=>{
      const tab=button("",()=>selectDay(index),"day-tab");tab.id=`tripDayTab-${index}`;tab.dataset.dayTab=index;tab.setAttribute("role","tab");tab.setAttribute("aria-controls",`tripDay-${index}`);tab.append(element("strong",`${t("Day","اليوم")} ${(index+1).toLocaleString(ar?"ar-SA":"en-GB")}`),element("span",formatDay(day.date)));$("tripDayNav").append(tab);
      const panel=element("section",undefined,"trip-day");panel.id=`tripDay-${index}`;panel.dataset.dayPanel=index;panel.setAttribute("role","tabpanel");panel.setAttribute("aria-labelledby",tab.id);
      const toolbar=element("div",undefined,"trip-toolbar day-heading");const heading=element("div");heading.append(element("h2",formatDay(day.date,{weekday:"long",day:"numeric",month:"long"})),element("p",`${formatPlaceCount(day.items.length)} · ${t("at your own pace","على طريقتك")}`,"trip-note"));toolbar.append(heading);
      const actions=element("div",undefined,"trip-actions");actions.append(button(t("Add place","إضافة مكان"),()=>showPicker(index),"btn-primary"),button(t("Regenerate day","إعادة إنشاء اليوم"),()=>generate(index)));toolbar.append(actions);panel.append(toolbar);
      const cards=element("div",undefined,"activity-grid");
      if(!day.items.length){const empty=element("div",undefined,"day-empty");const icon=element("i");icon.dataset.lucide="compass";icon.setAttribute("aria-hidden","true");empty.append(icon,element("h3",t("A little room for discovery","مساحة لاكتشاف جديد")),element("p",t("Add a place you love, or generate ideas that match your interests.","أضف مكانًا تحبه أو أنشئ أفكارًا تناسب اهتماماتك.")),button(t("Find a place","اكتشف مكانًا"),()=>showPicker(index)));cards.append(empty);}
      day.items.forEach((item,position)=>cards.append(renderActivity(item,index,position)));panel.append(cards);$("tripDays").append(panel);
    });
    const unscheduled=button("",()=>selectDay(-1),"day-tab unscheduled-tab");unscheduled.id="unscheduledTab";unscheduled.dataset.dayTab=-1;unscheduled.setAttribute("role","tab");unscheduled.setAttribute("aria-controls","unscheduledPanel");unscheduled.append(element("strong",t("Unscheduled","غير مجدولة")),element("span",formatPlaceCount(trip.unscheduled.length)));$("tripDayNav").append(unscheduled);
    const target=$("unscheduledPlaces");target.replaceChildren();if(!trip.unscheduled.length)target.append(element("p",t("No unscheduled places. Activities moved out of a day will be kept here.","لا توجد أماكن غير مجدولة. تظهر هنا الأنشطة المنقولة من أيام الرحلة."),"day-empty"));trip.unscheduled.forEach((item,index)=>target.append(renderActivity(item,null,index)));
    if(activeDay>=trip.days.length)activeDay=trip.days.length-1;selectDay(activeDay);updateView();
    if(window.lucide)lucide.createIcons();
    if(focusedKey){const row=[...document.querySelectorAll("[data-activity-key]")].find(node=>node.dataset.activityKey===focusedKey);row?.querySelector(lockFocus?".activity-lock":"summary")?.focus({preventScroll:true});}
    if(busy)setBusy(true);
  }
  async function validatedChange(next, destructive=false) {
    const previousBusy=busy;setBusy(true);
    try {
      const response=await request("/api/trips/preview/","POST",{action:"validate",trip:next});
      trip=response.trip;changed({destructive});
    } finally {setBusy(previousBusy);}
  }
  async function moveItem(item, from, destination) {
    if(destination==="") return;
    const next=clone(trip); const source=from===null?next.unscheduled:next.days[from].items;
    const moved=source.splice(source.findIndex(value=>value.key===item.key),1)[0];
    const target=destination==="unscheduled"?next.unscheduled:next.days[Number(destination)].items;
    target.push(moved); await validatedChange(next);
  }
  async function generate(dayIndex=null) {
    if(busy || saving) return;
    setBusy(true); message(t("Finding places…","جارٍ البحث عن أماكن…"));
    const payload={action:"generate",trip:clone(trip),...(dayIndex===null?{}:{day_index:dayIndex})};
    try {
      let response=await request("/api/trips/preview/","POST",payload);
      let destructive=false;
      if(response.requires_confirmation) {
        if(!await confirmChange(t("Regenerate unlocked activities? Locked places stay. If there are no suitable alternatives, existing places remain.","إعادة إنشاء الأنشطة غير المقفلة؟ تبقى الأماكن المقفلة، وتبقى الاختيارات الحالية إذا لم توجد بدائل مناسبة."),response.conflicts.map(item=>item.title))) {message("");return;}
        destructive=true; response=await request("/api/trips/preview/","POST",{...payload,confirmed:true});
      }
      trip=response.trip;planningComplete=true;editingDetails=false;libraryOpen=false;fillForm();changed({destructive});
      const total=trip.days.reduce((n,day)=>n+day.items.length,0);
      message(response.preserved_days?.length && total > 0 ? t("Some days kept their existing selections. Unlock activities or adjust preferences to request different choices.","احتفظت بعض الأيام باختياراتها الحالية. افتح قفل الأنشطة أو عدّل التفضيلات لطلب بدائل مختلفة.") : total?t("Trip ready. Edit any day or save it to your account.","رحلتك جاهزة. عدّل الأيام أو احفظها في حسابك."):t("No suitable places found. Try different interests, dates, or constraints.","لم نجد أماكن مناسبة. جرّب اهتمامات أو تواريخ أو قيودًا أخرى."));
    } finally { setBusy(false); }
  }
  $("reviewAvailability").addEventListener("click",async()=>{
    if(busy || saving)return;
    setBusy(true);
    const payload={action:"dates",trip:clone(trip),start_date:trip.start_date,duration:trip.duration};
    try {
      let response=await request("/api/trips/preview/","POST",payload);
      if(response.requires_confirmation){
        if(!await confirmChange(t("Move these unavailable activities to Unscheduled Places, preserving their locks?","نقل هذه الأنشطة غير المتاحة إلى أماكن غير مجدولة مع حفظ القفل؟"),response.conflicts.map(item=>item.title)))return;
        response=await request("/api/trips/preview/","POST",{...payload,confirmed:true});
      }
      trip=response.trip;changed();fillForm();message(t("Date checks complete. Confirm venue opening and availability with the source before visiting.","اكتملت مراجعة التواريخ. تحقّق من ساعات العمل والتوافر لدى المصدر قبل الزيارة."));
    }catch(error){showError(error);}finally{setBusy(false);}
  });
  $("tripForm").addEventListener("submit",async event=>{
    event.preventDefault(); if(busy || saving) return;
    if(builderStep<2){if(validateStep())showStep(builderStep+1,true);return;}
    if(!$("tripForm").reportValidity()||!validateStep())return;
    if(!$("tripInterests").querySelector("input:checked")){showStep(1);validateStep();return;}
    const firstGeneration=!planningComplete;
    const preferences={interests:Array.from($("tripInterests").querySelectorAll("input:checked"),input=>input.value),budget_min:$("tripMin").value===""?null:+$("tripMin").value,budget_max:$("tripMax").value===""?null:+$("tripMax").value,min_rating:$("tripRating").value===""?null:+$("tripRating").value,preferred_language:ar?"ar":"en"};
    try {
      setBusy(true);
      let next=clone(trip);next.name=$("tripName").value.trim();
      if(next.start_date!==$("tripStart").value || +next.duration!==+$("tripDuration").value) {
        const payload={action:"dates",trip:next,start_date:$("tripStart").value,duration:+$("tripDuration").value};
        let response=await request("/api/trips/preview/","POST",payload);
        if(response.requires_confirmation) {
          if(!await confirmChange(t("These activities will move to Unscheduled Places, keeping their lock status. Apply the date change?","ستُنقل الأنشطة التالية إلى أماكن غير مجدولة مع حفظ القفل. تطبيق التغيير؟"),response.conflicts.map(item=>item.title))) {fillForm();return;}
          response=await request("/api/trips/preview/","POST",{...payload,confirmed:true});
        }
        next=response.trip;
      }
      next.preferences=preferences;
      // Preference changes don't regenerate or remove chosen places.
      for(const item of [...next.days.flatMap(day=>day.items),...next.unscheduled]) item.override_preferences=true;
      await validatedChange(next);editingDetails=false;fillForm();updateView();message(t("Details updated. Existing selections were preserved.","تم تحديث التفاصيل مع الاحتفاظ باختياراتك."));
      if(firstGeneration){setBusy(false);await generate();}
    } catch(error) {showError(error);} finally {setBusy(false);}
  });
  async function showPicker(dayIndex, replaceKey=null) {
    pickerContext={dayIndex,replaceKey};$("placeQuery").value="";$("placePicker").showModal();await searchPlaces();
  }
  async function searchPlaces() {
    const current=++searchVersion;const context=pickerContext;if(!context)return;
    const results=$("placeResults");results.replaceChildren(element("p",t("Loading…","جارٍ التحميل…")));
    try {
      const data=await request(`/api/events/?date=${trip.days[context.dayIndex].date}&search=${encodeURIComponent($("placeQuery").value)}&page_size=100`);
      if(current!==searchVersion)return;
      const ids=new Set(trip.days[context.dayIndex].items.map(item=>item.event_id));
      const events=(data.results||data).filter(event=>!ids.has(event.id));results.replaceChildren();
      if(!events.length)results.append(element("p",t("No matching places. Try another search.","لا توجد أماكن مطابقة. جرّب بحثًا آخر.")));
      for(const event of events){const row=element("div",undefined,"trip-picker-item");const info=element("div");info.append(element("strong",event.title),element("p",[categories[event.category],formatEventPrice(event.price)].join(" · "),"trip-note"));row.append(placeMedia(event,"picker-media"),info,button(t("Choose","اختيار"),()=>choosePlace(event,context)));results.append(row);}
      if(window.lucide)lucide.createIcons();
      if(data.next)results.append(element("p",t("Showing the first 100 matches. Narrow your search for more places.","تظهر أول ١٠٠ نتيجة. حدّد البحث للوصول لأماكن أخرى."),"trip-note"));
    } catch(error){results.replaceChildren(element("p",error.message));}
  }
  async function choosePlace(event, context) {
    const warnings=eventWarnings(event);
    const existing=trip.days[context.dayIndex].items.find(item=>item.key===context.replaceKey);
    if(existing || warnings.length) {
      // Close the search dialog before opening a separate confirmation dialog.
      $("placePicker").close();
      if(!await confirmChange(t("Use this manual selection? It may exceed your preferences. Automatic generation will continue to follow your constraints.","استخدام هذا الاختيار اليدوي؟ قد يتجاوز تفضيلاتك. يستمر التوليد التلقائي في الالتزام بقيودك."),[event.title,...warnings])) return;
    } else $("placePicker").close();
    const next=clone(trip);const items=next.days[context.dayIndex].items;
    const item={key:crypto.randomUUID(),event_id:event.id,slot_type:existing?.slot_type||"activity",locked:existing?.locked||false,source:"manual",override_preferences:warnings.length>0};
    if(context.replaceKey)items.splice(items.findIndex(value=>value.key===context.replaceKey),1,item);else items.push(item);
    await validatedChange(next,Boolean(existing));planningComplete=true;editingDetails=false;libraryOpen=false;render();
  }
  $("closePicker").addEventListener("click",()=>$("placePicker").close());
  $("placeQuery").addEventListener("input",()=>{clearTimeout(timerSearch);timerSearch=setTimeout(searchPlaces,300);});let timerSearch;
  $("generateTrip").addEventListener("click",()=>generate().catch(showError));$("saveTrip").addEventListener("click",save);
  const tripOptions=document.querySelector(".trip-options");
  tripOptions.addEventListener("click",event=>{if(event.target.closest("button"))tripOptions.open=false;});
  document.addEventListener("click",event=>{if(!event.target.closest(".trip-options"))tripOptions.open=false;});
  tripOptions.addEventListener("keydown",event=>{if(event.key==="Escape"){tripOptions.open=false;tripOptions.querySelector("summary").focus();}});
  $("newTrip").addEventListener("click",async()=>{if(saving||busy)return;if((dirty||(!savedId&&(trip.days.some(day=>day.items.length)||trip.unscheduled.length)))&&!await confirmChange(t("Start a new draft? Save the current trip first if you want to keep it.","بدء مسودة جديدة؟ احفظ الرحلة الحالية أولًا إذا أردت الاحتفاظ بها.")))return;clearTimeout(timer);trip=newDocument();savedId=null;try{sessionStorage.removeItem("tz_active_trip");}catch{}revision=null;dirty=false;confirmedRemoval=false;planningComplete=false;editingDetails=false;libraryOpen=false;activeDay=0;version++;showStep(0);fillForm();changed();message("");replacePageUrl(prefix+"/trips/");});
  $("builderNext").addEventListener("click",()=>{if(validateStep())showStep(builderStep+1,true);});
  $("builderBack").addEventListener("click",()=>showStep(Math.max(0,builderStep-1),true));
  $("tripForm").addEventListener("input",()=>{
    // An unfinished guest wizard is a draft too. Existing itineraries only change
    // after the validated Apply action and its date-conflict confirmation.
    if(planningComplete||savedId||!trip)return;
    if(!$("tripStart").value||!$("tripDuration").checkValidity())return;
    trip.name=$("tripName").value;
    trip.start_date=$("tripStart").value;trip.duration=+$("tripDuration").value;
    trip.days=Array.from({length:trip.duration},(_,index)=>{const date=new Date(trip.start_date+"T12:00:00Z");date.setUTCDate(date.getUTCDate()+index);return {date:date.toISOString().slice(0,10),items:[]};});
    trip.preferences.interests=[...$("tripInterests").querySelectorAll("input:checked")].map(input=>input.value);
    for(const [id,key] of [["tripMin","budget_min"],["tripMax","budget_max"],["tripRating","min_rating"]]){if($(id).checkValidity())trip.preferences[key]=$(id).value===""?null:+$(id).value;}
    dirty=true;version++;saveLocal();
  });
  $("editTripDetails").addEventListener("click",()=>{editingDetails=true;fillForm();showStep(0);updateView();$("tripName").focus();});
  $("cancelTripDetails").addEventListener("click",()=>{editingDetails=false;fillForm();updateView();$("editTripDetails").focus();});
  function navigateLibrary(open){libraryOpen=open;updateView();replacePageUrl(prefix+"/trips/"+(open?"?view=saved":savedId?`?trip=${savedId}`:""));document.querySelectorAll('.mobile-travel-nav a[href*="/trips/"]').forEach(link=>{if(link.href.includes("view=saved")===open)link.setAttribute("aria-current","page");else link.removeAttribute("aria-current");});if(open)loadSaved();}
  $("showSavedTrips").addEventListener("click",()=>navigateLibrary(!libraryOpen));
  $("showArchivedTrips").addEventListener("change",event=>{showArchived=event.target.checked;loadSaved();});
  async function restoreTrip(item){
    if(busy||saving)return;
    if(!await confirmChange(t("Restore this trip to your collection? All activities and locks will be kept.","استعادة هذه الرحلة إلى قائمتك؟ تبقى جميع الأنشطة والأقفال محفوظة."),[item.name]))return;
    setBusy(true);
    try{await request(`/api/trips/${item.id}/`,"PATCH",{action:"restore",confirmed:true,revision:item.revision});showArchived=false;$("showArchivedTrips").checked=false;await loadSaved();}finally{setBusy(false);}
    await openTrip(item.id);
  }
  $("archiveTrip").addEventListener("click",async()=>{
    if(!savedId||busy||saving)return;
    if(dirty){showError(new Error(t("Save your edits before archiving this trip.","احفظ تعديلاتك قبل أرشفة الرحلة.")));return;}
    if(!await confirmChange(t("Archive this trip? It will leave your main collection. You can restore it with all days, places and locks from archived trips.","أرشفة هذه الرحلة؟ ستخرج من القائمة الرئيسية، ويمكن استعادتها بكل الأيام والأماكن والأقفال من الرحلات المؤرشفة."),[trip.name]))return;
    setBusy(true);
    try{await request(`/api/trips/${savedId}/`,"DELETE",{confirmed:true,revision});savedId=null;revision=null;try{sessionStorage.removeItem("tz_active_trip");}catch{}trip=newDocument();dirty=false;version++;planningComplete=false;libraryOpen=true;showArchived=false;$("showArchivedTrips").checked=false;fillForm();render();status("draft");replacePageUrl(prefix+"/trips/?view=saved");await loadSaved();message(t("Trip archived. Use Show archived trips to restore it.","تمت أرشفة الرحلة. اعرض الرحلات المؤرشفة لاستعادتها."));}catch(error){showError(error);}finally{setBusy(false);}
  });
  $("backToTrip").addEventListener("click",()=>navigateLibrary(false));
  $("tripDayNav").addEventListener("keydown",event=>{if(event.ctrlKey||event.metaKey||event.altKey)return;if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;event.preventDefault();const tabs=[...$("tripDayNav").querySelectorAll("[data-day-tab]")];const current=tabs.findIndex(tab=>tab.getAttribute("aria-selected")==="true");const direction=(event.key==="ArrowRight"?1:-1)*(ar?-1:1);const next=event.key==="Home"?0:event.key==="End"?tabs.length-1:(current+direction+tabs.length)%tabs.length;selectDay(+tabs[next].dataset.dayTab,true);tabs[next].scrollIntoView({block:"nearest",inline:"nearest"});});
  for(const [value,label] of Object.entries(categories)){const wrapper=element("label",undefined,"trip-interest");const input=element("input");input.type="checkbox";input.value=value;const icon=element("i");icon.dataset.lucide=catIcon(value);icon.setAttribute("aria-hidden","true");wrapper.append(input,icon,element("span",label));$("tripInterests").append(wrapper);}
  showStep(0);
  window.addEventListener("beforeunload",event=>{if(savedId && dirty && !recoveryStored){event.preventDefault();event.returnValue="";}});
  let guestDraft=null;
  setBusy(true);status("loading");
  try {
    if(isLoggedIn()) {try {currentUserId=(await request("/api/auth/me/")).id;defaultPreferences=await request("/api/auth/preferences/");} catch {}}
    guestDraft=TripDrafts.load(localStorage);
    trip=guestDraft||newDocument();planningComplete=trip.days.some(day=>day.items.length)||trip.unscheduled.length>0;fillForm();render();status("draft");await loadSaved();
  } catch(error) {
    trip=newDocument();dirty=Boolean(guestDraft);fillForm();render();status("failed");showError(error);
  } finally {setBusy(false);}
  const params=new URLSearchParams(location.search);
  let previousTrip=null; try {previousTrip=sessionStorage.getItem("tz_active_trip");} catch {}
  if(params.has("trip")) await openTrip(Number(params.get("trip"))).catch(showError);
  else if(!libraryOpen && !guestDraft && !params.has("save") && isLoggedIn() && previousTrip) await openTrip(Number(previousTrip)).catch(showError);
  else if(params.has("save")&&isLoggedIn()) await save();
  if(params.has("trip") && !savedId) return;
  if(params.has("place")) { const event=await request(`/api/events/${encodeURIComponent(params.get("place"))}/`).catch(error=>{showError(error);return null;}); if(event) await choosePlace(event,{dayIndex:0,replaceKey:null}).catch(showError); }
})();
