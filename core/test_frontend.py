import json
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.files.base import ContentFile
from django.test import SimpleTestCase
from whitenoise.storage import CompressedManifestStaticFilesStorage


class SharedJavaScriptTests(SimpleTestCase):
    def test_bundled_icons_can_be_processed_by_production_manifest_storage(self):
        asset = "js/vendor/lucide-0.468.0.min.js"
        with TemporaryDirectory(dir=settings.BASE_DIR) as folder:
            storage = CompressedManifestStaticFilesStorage(location=folder)
            storage.save(
                asset,
                ContentFile((Path(settings.BASE_DIR) / "static" / asset).read_bytes()),
            )
            processed = list(storage.post_process({asset: (storage, asset)}))
            failures = [
                result for _, _, result in processed if isinstance(result, Exception)
            ]
            self.assertEqual(failures, [])
            self.assertTrue(storage.exists(storage.stored_name(asset)))

    def test_settings_cannot_mistake_guest_selections_for_temporary_cache(self):
        template = (Path(settings.BASE_DIR) / "templates/settings.html").read_text(
            encoding="utf-8"
        )
        source = template.split("<script>")[-1].split("</script>")[0]
        self.run_js(
            """
const handlers = {}, nodes = new Map();
const element = () => ({style:{},classList:{add(){},remove(){},toggle(){}},
  addEventListener(type, fn){this[type]=fn;}});
document.addEventListener = (name, fn) => handlers[name] = fn;
document.getElementById = id => {if(!nodes.has(id)) nodes.set(id,element()); return nodes.get(id);};
document.querySelectorAll = () => [];
document.documentElement = {lang:'en',setAttribute(){}};
window.matchMedia = () => ({matches:false});
global.confirm = () => true;
const draft = JSON.stringify({name:'My private draft',days:[{items:[{event_id:9,locked:true}]}]});
localStorage.setItem('tizahab_guest_trip_v1',draft);
localStorage.setItem('tizahab_favorites','[9]');
// Model browser Storage enumeration as well as getItem/setItem.
Object.defineProperty(localStorage,'tizahab_guest_trip_v1',{enumerable:true});
Object.defineProperty(localStorage,'tizahab_favorites',{enumerable:true});
"""
            + "vm.runInThisContext("
            + json.dumps(source)
            + ");\n"
            + """
handlers.DOMContentLoaded();
// A cache action must never erase user selections, even if reintroduced.
nodes.get('clearCacheBtn')?.click?.();
setLang('ar');
applyTheme('light');
assert.equal(localStorage.getItem('tizahab_guest_trip_v1'),draft);
assert.equal(localStorage.getItem('tizahab_favorites'),'[9]');
"""
        )

    def test_discovery_search_summary_uses_the_active_interface_language(self):
        self.run_js(
            """
const summary={textContent:''},bar={classList:{toggle(){}}};
document.getElementById=id=>id==='activeFilterText'?summary:id==='activeFilterBar'?bar:null;
"""
            + "vm.runInThisContext(fs.readFileSync("
            + json.dumps(str(Path(settings.BASE_DIR) / "static/js/events.js"))
            + ", 'utf8'));\n"
            + """
_currentSearch='Museum';
document.documentElement.lang='ar';updateActiveFilterBar();
assert.match(summary.textContent,/البحث/);assert.doesNotMatch(summary.textContent,/Search|Active filters/);
document.documentElement.lang='en';updateActiveFilterBar();
assert.equal(summary.textContent,'Active filters: Search: "Museum"');
"""
        )

    def test_cancel_classic_generation_does_not_save_or_overwrite_anything(self):
        self.run_js(
            """
window.confirm=()=>false;
global.isLoggedIn=()=>true;
global.apiPost=async()=>{throw new Error('No write is allowed after cancellation');};
"""
            + "vm.runInThisContext("
            + json.dumps(self.preferences_submit_script())
            + ");\n"
            + """
await window.testSubmit();
assert.equal(storage.size,0);
assert.equal(window.location.href,undefined);
"""
        )

    def test_discovery_keeps_the_latest_search_when_responses_arrive_out_of_order(self):
        self.run_js(
            """
document.getElementById=()=>null;
"""
            + "vm.runInThisContext(fs.readFileSync("
            + json.dumps(str(Path(settings.BASE_DIR) / "static/js/events.js"))
            + ", 'utf8'));\n"
            + """
showGridSkeletons=renderAreaCards=renderEventsGrid=renderTrendingRow=updateAreaControls=updateLoadMoreState=()=>{};
const requests=[];global.apiGet=async()=>new Promise(resolve=>requests.push(resolve));
_currentSearch='first';const first=loadEvents();
_currentSearch='latest';const latest=loadEvents();
requests[1]({results:[{id:2,title:'Latest result',category:'nature'}],count:1});await latest;
requests[0]({results:[{id:1,title:'Stale result',category:'nature'}],count:1});await first;
assert.deepEqual(_allEvents.map(place=>place.id),[2]);
"""
        )

    def test_discovery_network_failure_replaces_loading_state_with_a_retry_action(self):
        self.run_js(
            """
let retry;const grid={innerHTML:'Loading skeleton',querySelector(){return {addEventListener(_type,handler){retry=handler;}};}};const count={textContent:''};
document.getElementById=id=>id==='eventsGrid'?grid:id==='countText'?count:null;
"""
            + "vm.runInThisContext(fs.readFileSync("
            + json.dumps(str(Path(settings.BASE_DIR) / "static/js/events.js"))
            + ", 'utf8'));\n"
            + """
showGridSkeletons=()=>{};
global.apiGet=async()=>{throw new Error('Network unavailable');};
await loadEvents();
assert.match(grid.innerHTML,/role="alert"/);assert.match(grid.innerHTML,/data-retry-events/);assert.doesNotMatch(grid.innerHTML,/Loading skeleton/);
assert.equal(count.textContent,'Results unavailable');assert.equal(typeof retry,'function');
"""
        )

    def test_favorites_outside_loaded_discovery_page_remain_visible(self):
        self.run_js(
            """
const grid={innerHTML:'',children:[],appendChild(value){this.children.push(value);}};
document.getElementById=id=>id==='favoritesGrid'?grid:null;
global.isLoggedIn=()=>true;
global.apiGet=async()=>[{event:{id:999,title:'Saved outside current page',category:'heritage'}}];
"""
            + "vm.runInThisContext(fs.readFileSync("
            + json.dumps(str(Path(settings.BASE_DIR) / "static/js/events.js"))
            + ", 'utf8'));\n"
            + """
buildEventCard=event=>({id:event.id});
await loadFavoriteIds();
renderFavoritesSection();
assert.equal(grid.children.length,1);
assert.equal(grid.children[0].id,999);
"""
        )

    def run_js(self, script):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for JavaScript regression tests")
        api_path = Path(settings.BASE_DIR) / "static/js/api.js"
        harness = """
const fs = require('fs');
const vm = require('vm');
const assert = require('assert').strict;
const storage = new Map();
global.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: key => storage.delete(key)
};
global.window = {location: {origin: 'https://tizahab.test', pathname: '/login/'}};
global.document = {cookie: 'csrftoken=test-csrf', documentElement:{lang:'en'}, addEventListener() {}};
vm.runInThisContext(fs.readFileSync(API_PATH, 'utf8'));
""".replace(
            "API_PATH", json.dumps(str(api_path))
        )
        result = subprocess.run(
            [node, "-"],
            input=harness
            + "\n(async () => {\n"
            + script
            + "\n})().catch(error => {console.error(error); process.exit(1);});",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def preferences_submit_script(self):
        source = (Path(settings.BASE_DIR) / "static/js/preferences.js").read_text(
            encoding="utf-8"
        )
        return source.replace(
            'document.addEventListener("DOMContentLoaded", init);',
            'window.testSubmit = handleSubmit; formData.startDate = "2099-11-01"; '
            'formData.endDate = "2099-11-03"; formData.interests.add("nature");',
        )

    def test_onboarding_generates_before_redirecting(self):
        self.run_js(
            """
const nodes = new Map(), scheduled = [], calls = [];
document.getElementById = id => {
  if (!nodes.has(id)) nodes.set(id,{disabled:false,textContent:'',classList:{add(){},remove(){}}});
  return nodes.get(id);
};
global.setTimeout = fn => scheduled.push(fn);
global.isLoggedIn = () => true;
let completeGeneration;
global.apiPost = async (url,payload) => {
  calls.push({url,payload});
  if (url.includes('preferences')) return payload;
  return new Promise(resolve => completeGeneration=resolve);
};
"""
            + "vm.runInThisContext("
            + json.dumps(self.preferences_submit_script())
            + ");\n"
            + """
const submitting = window.testSubmit();
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(calls.map(call=>call.url), ['/api/auth/preferences/','/api/daily-plan/generate-multiday/']);
assert.equal(calls[1].payload.trip_duration,3);
assert.equal(scheduled.length,0);
assert.equal(nodes.get('submit-btn').disabled,true);
completeGeneration({plans:[{date:'2099-11-01'}]});
await submitting;
assert.equal(scheduled.length,1);
scheduled[0]();
assert.equal(window.location.href,'/daily-plan/');
"""
        )

    def test_onboarding_generation_failure_stays_visible_and_can_be_retried(self):
        self.run_js(
            """
const nodes = new Map();
document.getElementById = id => {
  if(!nodes.has(id)) nodes.set(id,{disabled:false,textContent:'',classList:{add(){},remove(){}}});
  return nodes.get(id);
};
global.isLoggedIn = () => true;
global.apiPost = async url => {
  if (url.includes('preferences')) return {interests:['nature']};
  throw new Error('No recommendations match');
};
"""
            + "vm.runInThisContext("
            + json.dumps(self.preferences_submit_script())
            + ");\n"
            + """
await window.testSubmit();
assert.equal(window.location.href,undefined);
assert.equal(nodes.get('submit-btn').disabled,false);
assert.equal(nodes.get('pref-message').textContent,'No recommendations match');
"""
        )

    def test_trip_badge_tracks_selected_day_instead_of_current_date(self):
        source = Path(settings.BASE_DIR) / "static/js/daily_plan_integration.js"
        self.run_js(
            """
const nodes = new Map();
document.getElementById = id => {
  if(!nodes.has(id)) nodes.set(id,{textContent:'',classList:{add(){},remove(){}}});
  return nodes.get(id);
};
localStorage.setItem('tz_plan_start_date','2099-11-01');
localStorage.setItem('tz_plan_end_date','2099-11-03');
localStorage.setItem('tz_trip_duration','3');
"""
            + "vm.runInThisContext(fs.readFileSync("
            + json.dumps(str(source))
            + ", 'utf8'));\n"
            + """
updateHero(1);
assert.equal(nodes.get('dayBadge').textContent,'Day 2 of 3');
updateHero(2);
assert.equal(nodes.get('dayBadge').textContent,'Day 3 of 3');
"""
        )

    def test_saved_plan_link_opens_its_date_including_older_trips(self):
        source = Path(settings.BASE_DIR) / "static/js/daily_plan_integration.js"
        for selected, expected_index, expected_duration in [
            ("2099-11-03", 2, 3),
            ("2098-04-05", 0, 1),
            (None, 0, 3),
        ]:
            self.run_js(
                """
document.getElementById = () => null;
global.apiGet = async url => url.includes('/me/')
  ? {interests:['nature'],start_date:'2099-11-01',end_date:'2099-11-03',trip_duration:3}
  : [{id:3,date:SELECTED_DATE || '2099-11-01',events:[{id:4,title:'Saved Park',category:'nature'}]}];
window.location.search = SELECTED_DATE ? '?date=' + SELECTED_DATE : '';
localStorage.setItem('tz_selected_plan_date','2098-04-05');
""".replace(
                    "SELECTED_DATE", json.dumps(selected)
                )
                + "vm.runInThisContext(fs.readFileSync("
                + json.dumps(str(source))
                + ", 'utf8'));\n"
                + """
renderDayTabs = () => {};
renderTimeline = () => {};
await loadCurrentPlan();
assert.equal(getSelectedPlanDate(),SELECTED_DATE || '2099-11-01');
assert.equal(currentDayIndex,EXPECTED_INDEX);
assert.equal(getTripDuration(),EXPECTED_DURATION);
assert.equal(_currentPlan.id,3);
assert.equal(multiDayPlans[currentDayIndex][0].id,4);
assert.equal(localStorage.getItem('tz_plan_start_date'),'2099-11-01');
assert.equal(localStorage.getItem('tz_plan_end_date'),'2099-11-03');
""".replace(
                    "SELECTED_DATE", json.dumps(selected)
                )
                .replace("EXPECTED_INDEX", str(expected_index))
                .replace("EXPECTED_DURATION", str(expected_duration))
            )

    def test_login_redirect_rejects_external_and_ambiguous_urls(self):
        self.run_js(
            r"""
for (const target of ['https://evil.test', '//evil.test/path', '/\\evil.test',
  'javascript:alert(1)', '/\n/evil.test', '/\t/evil.test', null, '', 'home/']) {
  assert.equal(safeInternalRedirect(target), null, String(target));
}
for (const target of ['/', '/home/', '/ar/profile/?tab=saved#plans', '/events/?q=Riyadh']) {
  assert.equal(safeInternalRedirect(target), target);
}
"""
        )
        template = (Path(settings.BASE_DIR) / "templates/login.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("safeInternalRedirect(rawNextParam)", template)

    def test_home_plan_card_opens_the_date_it_displays(self):
        source = Path(settings.BASE_DIR) / "static/js/home.js"
        self.run_js(
            """
let ready;
const nodes = new Map([['planCard',{innerHTML:''}]]);
document.documentElement = {lang:'ar'};
document.addEventListener = (_, callback) => ready = callback;
document.getElementById = id => nodes.get(id) || null;
global.apiGet = async url => url.includes('daily-plan')
  ? [{id:3,date:'2099-11-03',events:[{id:4,title:'Park',category:'nature'}]}] : [];
"""
            + "vm.runInThisContext(fs.readFileSync("
            + json.dumps(str(source))
            + ", 'utf8'));\n"
            + """
await ready();
assert.ok(nodes.get('planCard').innerHTML.includes('href="/ar/daily-plan/?date=2099-11-03"'));
"""
        )

    def test_unknown_prices_are_distinct_from_free_in_both_languages(self):
        self.run_js(
            """
for (const price of [null, undefined, '', ' ', 'invalid', -1]) {
  assert.equal(formatEventPrice(price), 'Price unknown');
}
assert.equal(formatEventPrice(0), 'Free');
assert.equal(formatEventPrice('0.00'), 'Free');
assert.equal(formatEventPrice('25.50'), '25.5 SAR');
document.documentElement = {lang:'ar'};
assert.equal(formatEventPrice(null), 'السعر غير معروف');
assert.equal(formatEventPrice(0), 'مجاني');
"""
        )

    def test_events_and_daily_plan_use_the_shared_price_formatter(self):
        for filename, invocation in [
            ("events.js", "getPriceText({price: null})"),
            ("daily_plan_integration.js", "formatPrice(null)"),
        ]:
            source = (Path(settings.BASE_DIR) / "static/js" / filename).read_text(
                encoding="utf-8"
            )
            self.run_js(
                "vm.runInThisContext("
                + json.dumps(source)
                + ");\n"
                + "assert.equal("
                + invocation
                + ", 'Price unknown');"
            )

    def test_settings_save_failure_is_visible_and_does_not_submit_language_form(self):
        template = (Path(settings.BASE_DIR) / "templates/settings.html").read_text(
            encoding="utf-8"
        )
        source = template.split("<script>")[-1].split("</script>")[0]
        self.run_js(
            """
const handlers = {}, nodes = new Map();
let submitted = false, toast = '';
const element = () => ({style:{}, classList:{add(){},remove(){},toggle(){}},
  addEventListener(type, fn){this[type]=fn;}, submit(){submitted=true;}});
document.addEventListener = (name, fn) => handlers[name] = fn;
document.getElementById = id => {if(!nodes.has(id)) nodes.set(id,element()); return nodes.get(id);};
document.querySelectorAll = () => [];
document.documentElement = {lang:'en',setAttribute(){}};
window.matchMedia = () => ({matches:false});
"""
            + "vm.runInThisContext("
            + json.dumps(source)
            + ");\n"
            + """
showToast = message => toast = message;
handlers.DOMContentLoaded();
setLang('ar');
global.isLoggedIn = () => true;
global.apiPut = async () => {throw new Error('Server unavailable');};
await nodes.get('saveSettingsBtn').click();
assert.equal(submitted,false);
assert.equal(toast,'Server unavailable');
assert.equal(nodes.get('saveSettingsBtn').disabled,false);
global.apiPut = async () => ({preferred_language:'ar'});
document.getElementById('settingsLanguageForm').elements = {language:{value:''}};
await nodes.get('saveSettingsBtn').click();
assert.equal(submitted,true);
assert.equal(nodes.get('settingsLanguageForm').elements.language.value,'ar');
"""
        )

    def test_header_query_initializes_the_actual_explore_search(self):
        source = Path(settings.BASE_DIR) / "static/js/events.js"
        self.run_js(
            """
let ready, loaded = false;
const nodes = new Map(['eventsGrid','searchInput','clearSearchBtn'].map(id =>
  [id,{value:'',classList:{toggle(){}},addEventListener(){}}]));
window.location.search = '?search=Riyadh%20Museum&category=heritage';
document.addEventListener = (_, callback) => ready = callback;
document.getElementById = id => nodes.get(id) || null;
document.querySelectorAll = () => [];
"""
            + "vm.runInThisContext(fs.readFileSync("
            + json.dumps(str(source))
            + ", 'utf8'));\n"
            + """
migrateLegacyFavorites = async () => {};
loadFavoriteIds = async () => {};
fetchAreaEvents = async () => [];
renderAreaCards = () => {};
updateLoadMoreState = () => {};
loadEvents = async () => {loaded=true; assert.equal(_currentSearch,'Riyadh Museum'); assert.equal(_currentCategory,'heritage');};
ready();
await new Promise(resolve => setImmediate(resolve));
assert.equal(loaded,true);
assert.equal(nodes.get('searchInput').value,'Riyadh Museum');
"""
        )

    def test_logout_closes_session_before_clearing_browser_state(self):
        self.run_js(
            """
localStorage.setItem('access', 'access-token');
localStorage.setItem('refresh', 'refresh-token');
window.TZ_SESSION_AUTHENTICATED = true;
global.fetch = async (url, options) => {
  assert.equal(url, '/logout/');
  assert.equal(options.method, 'POST');
  assert.equal(options.credentials, 'include');
  assert.equal(options.headers['X-CSRFToken'], 'test-csrf');
  assert.equal(localStorage.getItem('access'), 'access-token');
  return {ok: true};
};
assert.equal(await logout(), true);
assert.equal(localStorage.getItem('access'), null);
assert.equal(localStorage.getItem('refresh'), null);
assert.equal(window.TZ_SESSION_AUTHENTICATED, false);
assert.equal(window.location.href, '/login/');
"""
        )

    def test_failed_logout_preserves_state_and_reports_failure(self):
        self.run_js(
            """
let message = '';
window.alert = value => message = value;
localStorage.setItem('access', 'access-token');
global.fetch = async () => ({ok: false, status: 403, text: async () => '{}'});
assert.equal(await logout(), false);
assert.equal(localStorage.getItem('access'), 'access-token');
assert.equal(window.location.href, undefined);
assert.match(message, /try again/);
"""
        )

    def test_delete_failure_rejects_instead_of_reporting_success(self):
        self.run_js(
            """
global.fetch = async () => ({ok: false, status: 404, text: async () => '{"detail":"Not found"}'});
await assert.rejects(apiDelete('/api/events/favorites/123/'), /Not found/);
global.fetch = async () => ({ok: false, status: 401, text: async () => '{}'});
await assert.rejects(apiDelete('/api/events/favorites/123/', false), /session has expired/);
"""
        )

    def test_profile_uses_event_id_and_retains_card_after_failed_request(self):
        template = (Path(settings.BASE_DIR) / "templates/profile.html").read_text(
            encoding="utf-8"
        )
        script = template.split("<script>")[-1].split("</script>")[0]
        # Execute the real profile handler with different favorite and event IDs.
        self.run_js(
            """
const listeners = {};
let removed = false, message = '';
const nodes = new Map();
const element = () => ({innerHTML:'', textContent:'', classList:{toggle(){},add(){},remove(){}},
  addEventListener(type, handler){this[type] = handler;}, appendChild(){}, append(){}, replaceChildren(){}});
document.getElementById = id => {if(!nodes.has(id)) nodes.set(id, element()); return nodes.get(id);};
document.querySelectorAll = () => [1];
document.createElement = element;
document.addEventListener = (type, handler) => listeners[type] = handler;
window.alert = value => message = value;
global.isLoggedIn = () => true;
global.apiGet = async url => url.includes('favorites') ? [{id: 900, event:{id:123,title:'Place'}}] : [];
"""
            + "\nvm.runInThisContext("
            + json.dumps(script)
            + ");\n"
            + """
listeners.DOMContentLoaded();
await new Promise(resolve => setImmediate(resolve));
assert.match(buildFavCard({id:900,event:{id:123,title:'Place'}}).innerHTML, /data-fav-remove="123"/);
assert.match(buildPlanCard({date:'2099-11-03',events:[]}).href, /[?]date=2099-11-03$/);
const button = {dataset:{favRemove:'123'}, closest:() => ({remove(){removed=true;}})};
global.apiDelete = async url => {assert.equal(url,'/api/events/favorites/123/'); throw new Error('Delete failed');};
await nodes.get('favsGrid').click({target:{closest:()=>button}});
assert.equal(removed,false);
assert.equal(button.disabled,false);
assert.equal(nodes.get('statFavs').textContent,1);
assert.equal(message,'Delete failed');
global.apiDelete = async () => null;
await nodes.get('favsGrid').click({target:{closest:()=>button}});
assert.equal(removed,true);
assert.equal(nodes.get('statFavs').textContent,0);
global.apiGet = async () => {throw new Error('Network unavailable');};
await loadMe(); await loadPrefs(); await loadPlans(); await loadFavs();
assert.match(nodes.get('profileName').textContent, /Unable to load/);
assert.match(nodes.get('prefChips').textContent, /Unable to load/);
assert.match(nodes.get('pastPlansGrid').innerHTML, /role="alert"/);
assert.match(nodes.get('favsGrid').innerHTML, /role="alert"/);
assert.equal(nodes.get('statFavs').textContent,'—');
"""
        )

    def test_live_arabic_labels_preserve_place_content(self):
        self.run_js(
            r"""
for (const file of ['ui_messages.js', 'ui_i18n.js']) {
  vm.runInThisContext(fs.readFileSync(API_PATH.replace('api.js', file), 'utf8'));
}
assert.equal(window.tzTranslateText('Day 2 of 3'), 'اليوم 2 من 3');
assert.equal(window.tzTranslateText('Step 4 of 5'), 'الخطوة 4 من 5');
assert.equal(window.tzTranslateText('No breakfast planned yet'), 'لم تُضف إفطارًا بعد');
assert.equal(window.tzTranslateText('Price unknown'), 'السعر غير معروف');
assert.equal(window.tzTranslateText('Al Masmak Palace'), 'Al Masmak Palace');
assert.equal(window.tzTranslateText('My own place description'), 'My own place description');
""".replace(
                "API_PATH",
                json.dumps(str(Path(settings.BASE_DIR) / "static/js/api.js")),
            )
        )

    def test_destination_details_use_real_data_without_invented_suitability(self):
        source = (Path(settings.BASE_DIR) / "static/js/events.js").read_text(
            encoding="utf-8"
        )
        self.run_js(
            'const details = {innerHTML: ""}; document.getElementById = () => details;\n'
            + source
            + r"""
renderEventDetails({id: 42, title: 'Real venue', description: 'Actual description',
 category: 'culture', price: null, source_url: 'javascript:alert(1)'});
assert.match(details.innerHTML, /Real venue/);
assert.match(details.innerHTML, /Actual description/);
assert.match(details.innerHTML, /Price unknown/);
assert.match(details.innerHTML, /id="detailAddToPlanBtn"/);
assert.doesNotMatch(details.innerHTML, /Suitable for all ages|Family Friendly|Typical Schedule|javascript:/);
"""
        )

    def test_place_photos_do_not_use_generic_category_illustrations(self):
        self.run_js(
            r"""
assert.equal(getPlaceImage({}), '');
assert.equal(getPlaceImage({image_url:'https://www.atlastravels.com/public/upload/atlas/travelogues/descriptionimage/descriptionimage_1727952417.jpg'}), '');
assert.equal(getPlaceImage({image_url:'javascript:alert(1)'}), '');
assert.equal(getPlaceImage({image_url:'https://photos.example.invalid/actual-venue.webp'}), 'https://photos.example.invalid/actual-venue.webp');
"""
        )

    def test_timeline_is_chronological_without_changing_replacement_indices(self):
        source = Path(settings.BASE_DIR) / "static/js/daily_plan_integration.js"
        self.run_js(
            "vm.runInThisContext(fs.readFileSync("
            + json.dumps(str(source))
            + ", 'utf8'));\n"
            + """
const slots = [
  {key:'breakfast',items:[{id:1}]},
  {key:'activity',items:[{id:2},{id:3},{id:4}]},
  {key:'lunch',items:[{id:5}]},
  {key:'evening',items:[{id:6},{id:7},{id:8}]}
];
const before = JSON.stringify(slots);
const entries = getTimelineEntries(slots);
assert.deepEqual(entries.map(row => row.event.id),[1,2,3,5,4,6,7,8]);
assert.equal(entries.find(row => row.event.id === 4).slotIndex,2);
assert.equal(entries.find(row => row.event.id === 4).slotKey,'activity');
assert.equal(JSON.stringify(slots),before);
assert.deepEqual(getTimelineEntries([]),[]);
"""
        )

    def test_legacy_flat_plan_preserves_its_third_meal_in_the_visible_timeline(self):
        source = Path(settings.BASE_DIR) / "static/js/daily_plan_integration.js"
        self.run_js(
            "vm.runInThisContext(fs.readFileSync("
            + json.dumps(str(source))
            + ", 'utf8'));\n"
            + """
const events = [
  {id:1,category:'food'}, {id:2,category:'food'}, {id:3,category:'food'},
  {id:4,category:'culture'}, {id:5,category:'nature'}, {id:6,category:'nature'}
];
const entries = getTimelineEntries(buildStructuredSlots(events));
assert.deepEqual(entries.map(row => row.event.id),[1,4,5,2,6,3]);
assert.equal(entries.find(row => row.event.id === 3).slotKey,'evening');
assert.equal(new Set(entries.map(row => row.event.id)).size,events.length);
"""
        )

    def test_timeline_does_not_hide_saved_items_exceeding_the_add_slot_limit(self):
        source = Path(settings.BASE_DIR) / "static/js/daily_plan_integration.js"
        self.run_js(
            "vm.runInThisContext(fs.readFileSync("
            + json.dumps(str(source))
            + ", 'utf8'));\n"
            + """
const events = Array.from({length:4},(_,index)=>({id:index+1,slot_type:'activity',item_order:index}));
const visible = getTimelineEntries(buildStructuredSlots(events)).filter(row => !row.event._placeholder);
assert.deepEqual(visible.map(row => row.event.id),[1,2,3,4]);
assert.equal(visible[3].slotIndex,3);
assert.equal(visible[3].event.item_order,3);
assert.equal(events.length,4);
"""
        )


class DestinationPhotographyTests(SimpleTestCase):
    def test_saved_trip_recovery_is_scoped_to_owner_trip_and_original_revision(self):
        SharedJavaScriptTests.run_js(
            self,
            """
const drafts=require('./static/js/trip_drafts.js');
const memory=new Map(),store={getItem:k=>memory.get(k),setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
drafts.savePending(store,7,{id:20,name:'Edits awaiting save'},3,true,1000);
drafts.savePending(store,7,{id:21,name:'Other pending trip'},8,false,1000);
assert.equal(drafts.loadPending(store,8,20,1001),null);
assert.equal(drafts.loadPending(store,7,22,1001),null);
const recovered=drafts.loadPending(store,7,20,1001);
assert.equal(recovered.trip.name,'Edits awaiting save');
assert.equal(recovered.revision,3);assert.equal(recovered.confirmed,true);
assert.equal(drafts.loadPending(store,7,20,1000+drafts.TTL),null);
assert.equal(drafts.loadPending(store,7,20,999),null);
drafts.clearPending(store,7,20);
assert.equal(drafts.loadPending(store,7,20,1001),null);
assert.equal(drafts.loadPending(store,7,21,1001).trip.name,'Other pending trip');
drafts.clearPending(store,7,21);assert.equal(memory.size,0);
""",
        )

    def test_invalid_recovery_storage_cannot_supply_another_trip_or_execute_code(self):
        SharedJavaScriptTests.run_js(
            self,
            """
const drafts=require('./static/js/trip_drafts.js');
const memory=new Map(),store={getItem:k=>memory.get(k),setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
store.setItem(drafts.PENDING_KEY,'not JSON');assert.equal(drafts.loadPending(store,7,20,1001),null);
store.setItem(drafts.PENDING_KEY,JSON.stringify({'7:20':{trip:{id:21},revision:3,editedAt:1000}}));
assert.equal(drafts.loadPending(store,7,20,1001),null);
store.removeItem(drafts.PENDING_KEY);
assert.throws(()=>drafts.savePending(store,null,{id:20},3,false,1000));
const failing={getItem:()=>null,setItem(){throw new Error('Quota exceeded');}};
assert.throws(()=>drafts.savePending(failing,7,{id:20},3,false,1000));
""",
        )

    def test_language_switch_does_not_replay_a_consumed_add_place_intent(self):
        SharedJavaScriptTests.run_js(
            self,
            """
const next={value:'/trips/?trip=4&place=6'};
global.location={pathname:'/ar/trips/',search:'?trip=4&place=6',hash:''};
global.history={replaceState(_state,_title,url){const parsed=new URL(url,'https://tizahab.test');location.pathname=parsed.pathname;location.search=parsed.search;location.hash=parsed.hash;}};
document.querySelectorAll=()=>[next];
replacePageUrl('/ar/trips/?trip=4');
assert.equal(next.value,'/trips/?trip=4');
assert.doesNotMatch(next.value,/place=/);
replacePageUrl('/ar/trips/?view=saved');
assert.equal(next.value,'/trips/?view=saved');
replacePageUrl('/trips/');
assert.equal(next.value,'/trips/');
""",
        )

    def test_trip_duration_uses_natural_arabic_and_english_labels(self):
        SharedJavaScriptTests.run_js(
            self,
            """
assert.equal(formatTripDuration(1),'1 day');
assert.equal(formatTripDuration(3),'3 days');
assert.equal(formatPlaceCount(1),'1 place');
assert.equal(formatPlaceCount(15),'15 places');
document.documentElement.lang='ar';
assert.equal(formatTripDuration(1),'يوم واحد');
assert.equal(formatTripDuration(2),'يومان');
assert.match(formatTripDuration(3),/أيام$/);
assert.match(formatTripDuration(14),/يومًا$/);
assert.equal(formatPlaceCount(0),'لا أماكن');
assert.equal(formatPlaceCount(1),'مكان واحد');
assert.equal(formatPlaceCount(2),'مكانان');
assert.match(formatPlaceCount(5),/أماكن$/);
assert.match(formatPlaceCount(15),/مكانًا$/);
""",
        )

    def test_photography_matches_the_destination_and_never_just_its_category(self):
        SharedJavaScriptTests.run_js(
            self,
            r"""
const photos=require('./static/js/place_photos.js');
window.TizahabPhotos=photos;
assert.match(getPlaceImage({title:'  Al Masmak Fortress  ',category:'heritage'}), /masmak-960\.webp$/);
assert.match(getPlaceImage({title:'وادي حنيفة',category:'nature'}), /wadi-hanifa-960\.webp$/);
assert.equal(getPlaceImage({title:'Different heritage place',category:'heritage'}),'');
assert.equal(getPlaceImage({title:'National Museum of Saudi Arabia<script>alert(1)</script>',category:'culture'}),'');
assert.equal(photos.photo({title:'Unverified venue',image_url:'https://photos.example.invalid/place.webp'}),null);
assert.equal(getPlaceImage({title:'Unverified venue',image_url:'https://photos.example.invalid/place.webp'},true),'');
assert.match(photos.photo({title:'At-Turaif UNESCO Site'}).srcset,/480w, .*960w, .*1280w$/);
""",
        )

    def test_trip_cover_uses_a_place_in_that_trip_and_never_an_unverified_url(self):
        SharedJavaScriptTests.run_js(
            self,
            """
const photos=require('./static/js/place_photos.js');
assert.equal(photos.tripPhoto({days:[{items:[{event:{title:'Unknown place',image_url:'https://photos.example.invalid/place.webp'}}]}]}),null);
const trip={days:[{items:[{event:{title:'Unknown place'}},{event:{title:'Wadi Hanifa'}}]}],unscheduled:[{event:{title:'Al Masmak Fortress'}}]};
assert.equal(photos.tripPhoto(trip).title,'Wadi Hanifa');
assert.match(photos.tripPhoto(trip).src,/wadi-hanifa/);
assert.equal(photos.tripPhoto({days:[],unscheduled:[]}),null);
""",
        )

    def test_each_bundled_photo_has_provenance_and_all_responsive_sizes(self):
        folder = Path(settings.BASE_DIR) / "static/images/places"
        credits = json.loads((folder / "credits.json").read_text(encoding="utf-8"))
        self.assertEqual(len({row["slug"] for row in credits}), len(credits))
        for row in credits:
            with self.subTest(photo=row["slug"]):
                self.assertTrue(
                    row["source"].startswith("https://commons.wikimedia.org/wiki/File:")
                )
                self.assertTrue(row["author"])
                self.assertIn(
                    row["license"], ("CC BY 2.0", "CC BY-SA 2.0", "CC BY-SA 4.0")
                )
                self.assertTrue(
                    row["license_url"].startswith("https://creativecommons.org/")
                )
                self.assertTrue(row["changes"])
                for width in (480, 960, 1280):
                    data = (folder / f"{row['slug']}-{width}.webp").read_bytes()
                    self.assertEqual(data[:4], b"RIFF")
                    self.assertEqual(data[8:12], b"WEBP")
                    self.assertLess(len(data), 300000)

    def test_both_public_planners_keep_every_editing_control_and_guest_entry(self):
        for path, direction in (("/trips/", "ltr"), ("/ar/trips/", "rtl")):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'dir="{direction}"')
                for control in (
                    "tripForm",
                    "builderNext",
                    "builderBack",
                    "tripInterests",
                    "tripDayNav",
                    "saveTrip",
                    "generateTrip",
                    "reviewAvailability",
                    "unscheduledPlaces",
                    "savedTrips",
                    "placePicker",
                    "tripConfirm",
                ):
                    self.assertContains(response, f'id="{control}"')
                self.assertContains(response, 'role="tablist"')
                self.assertContains(response, 'data-step="0"')
                self.assertContains(response, 'data-step="1"')
                self.assertContains(response, 'data-step="2"')
