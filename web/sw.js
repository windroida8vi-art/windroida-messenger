/* Windroida service worker: shows notifications (works on Android Chrome where `new Notification` does not)
   and brings the app to the front when one is tapped. Pictures (avatars, thumbnails, wallpapers, photos) are kept in the browser: they are looked up WITHOUT the
   rotating media key (?k=), so a picture that did not change is never downloaded again. The app itself (html/js/css) is never cached here: updates stay instant. */
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('notificationclick',e=>{
  e.notification.close();const cid=e.notification.data&&e.notification.data.cid;
  e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(list=>{
    for(const c of list){if('focus' in c){c.postMessage({cid});return c.focus()}}
    return self.clients.openWindow('/')}))});

/* Web Push: the server sends a content-free wake-up when a message arrives and the app is closed/hidden */
self.addEventListener('push',e=>{
  e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(list=>{
    if(list.some(c=>c.visibilityState==='visible'))return;                 // you are looking at the app: it shows its own sound/notification
    return self.registration.showNotification('Windroida',{body:'پیام جدید داری',tag:'wd-push',renotify:true,icon:'/static/icon-192.png',badge:'/static/icon.svg',dir:'rtl',lang:'fa',data:{}})}))});
self.addEventListener('pushsubscriptionchange',e=>{e.waitUntil(self.clients.matchAll({includeUncontrolled:true}).then(l=>l.forEach(c=>c.postMessage({resub:true}))))});

/* Chrome wants a fetch handler before it offers "Install app"; we simply let the network answer. */
const IMG='wd-img-v1',MAXN=1500;
const imgKey=u=>{const x=new URL(u);x.searchParams.delete('k');return x.origin+x.pathname+x.search};
const isPic=r=>{const u=new URL(r.url);if(u.origin!==self.location.origin||r.method!=='GET'||r.headers.has('range'))return false;
  return /^\/(avatar|thumb|wall|userwall)\//.test(u.pathname)||u.pathname==='/userwall'||(r.destination==='image'&&/^\/media\//.test(u.pathname))};
async function trim(c){const ks=await c.keys();if(ks.length>MAXN)for(const k of ks.slice(0,ks.length-MAXN+100))await c.delete(k)}
self.addEventListener('fetch',e=>{
  const r=e.request;if(!isPic(r))return;
  e.respondWith((async()=>{
    const c=await caches.open(IMG),key=imgKey(r.url),hit=await c.match(key);
    if(hit)return hit;
    const res=await fetch(r);
    if(res.ok&&res.status===200&&res.type!=='opaque'){try{await c.put(key,res.clone());trim(c)}catch{}}
    return res})())});
self.addEventListener('message',e=>{if(e.data&&e.data.clearImages)e.waitUntil(caches.delete(IMG))});
