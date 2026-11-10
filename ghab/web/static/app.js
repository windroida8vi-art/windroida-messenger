/* ---- رویدادهای درون‌خطی بدون eval: CSP دیگر 'unsafe-inline' برای اسکریپت ندارد.
   صفت data-onXXX فقط «نامِ تابعِ خودِ برنامه + آرگومان‌های ساده» را می‌پذیرد (رشته/عدد/this/event/this.value/this.checked)؛
   تابع بومی (eval، Function، …) و هر چیز دیگری اجرا نمی‌شود. ---- */
function togSpf(el){const x=document.getElementById('spf');if(x)x.hidden=!el.checked}
const wdRun=(code,el,ev)=>{
  const splitTop=(s,ch)=>{const out=[];let cur='',q='',d=0;for(let i=0;i<s.length;i++){const c=s[i];if(q){cur+=c;if(c==='\\'){cur+=s[++i]||''}else if(c===q)q=''}else if(c==="'"||c==='"'){q=c;cur+=c}else if(c==='('){d++;cur+=c}else if(c===')'){d--;cur+=c}else if(c===ch&&d===0){out.push(cur);cur=''}else cur+=c}if(cur.trim())out.push(cur);return out};
  const val=t=>{t=t.trim();if(/^-?\d+(\.\d+)?$/.test(t))return +t;let m=t.match(/^'((?:[^'\\]|\\.)*)'$/)||t.match(/^"((?:[^"\\]|\\.)*)"$/);if(m)return m[1].replace(/\\(.)/g,'$1');
    if(t==='this')return el;if(t==='event')return ev;if(t==='this.value')return el.value;if(t==='this.checked')return el.checked;if(t==='true')return true;if(t==='false')return false;if(t==='null')return null;throw new Error('arg')};
  for(let st of splitTop(code,';')){st=st.trim();if(!st)continue;
    if(st==='return false'){ev.preventDefault();continue}
    let m=st.match(/^if\(event\.key===(?:'|")(\w+)(?:'|")\)([\s\S]+)$/);if(m){if(ev.key===m[1])wdRun(m[2],el,ev);continue}
    if(st==='event.stopPropagation()'){ev._wdStop=true;ev.stopPropagation();continue}
    if(st==='event.preventDefault()'){ev.preventDefault();continue}
    if(st==="this.classList.toggle('open')"){el.classList.toggle('open');continue}
    m=st.match(/^([A-Za-z_$][\w$]*)\(([\s\S]*)\)$/);if(!m)continue;
    const fn=window[m[1]];if(typeof fn!=='function'||/\[native code\]/.test(Function.prototype.toString.call(fn)))continue;
    let args;try{args=splitTop(m[2],',').map(val)}catch{continue}
    fn.apply(null,args)}
};
for(const [t,cap,evn] of [['click',0,'click'],['keydown',0,'keydown'],['change',0,'change'],['input',0,'input'],['dblclick',0,'dblclick'],['scroll',1,'scroll'],['focus',1,'focusin'],['blur',1,'focusout']])
  document.addEventListener(evn,ev=>{const at='data-on'+t;let el=ev.target;if(!(el instanceof Element))return;
    for(;el&&el!==document.documentElement;el=el.parentElement){if(el.hasAttribute(at)){try{wdRun(el.getAttribute(at),el,ev)}catch(e){console.error(e)}}if(ev._wdStop||ev.cancelBubble)break}},!!cap);
const $=s=>document.querySelector(s), app=$('#app');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fa=n=>Number(n).toLocaleString('fa-IR');
let me=null, ST=[], RL=[], RT='all', MUTED=true;
const icons={home:'<path d="M3 11l9-8 9 8v9a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1z"/>',search:'<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',plus:'<rect x="3" y="3" width="18" height="18" rx="5"/><path d="M12 8v8M8 12h8"/>',plus2:'<path d="M12 4v16M4 12h16"/>',reels:'<rect x="3" y="3" width="18" height="18" rx="5"/><path d="M3 9h18M9 3l3 6M15 3l3 6"/><path d="M10.5 12.5l4 2.5-4 2.5z"/>',heart:'<path d="M12 21s-8-5.3-8-11a4.5 4.5 0 018-2.8A4.5 4.5 0 0120 10c0 5.7-8 11-8 11z"/>',chat:'<path d="M21 12a8 8 0 01-11.6 7.1L4 20l1-4.6A8 8 0 1121 12z"/>',share:'<path d="M22 3L2 10l8 3 3 8z"/><path d="M10 13l12-10"/>',bookmark:'<path d="M6 3h12v18l-6-4-6 4z"/>',user:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/>',play:'<path d="M7 4l13 8-13 8z"/>',vol:'<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 8.5a5 5 0 010 7M19 6a8.5 8.5 0 010 12"/>',mute:'<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M17 9l5 6M22 9l-5 6"/>',link:'<path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"/>',story:'<circle cx="12" cy="12" r="8" stroke-dasharray="3 3"/><path d="M12 8v8M8 12h8"/>',back:'<path d="M9 5l7 7-7 7"/>',check:'<path d="M5 12l5 5 9-10"/>'};
const ic=(n,on)=>`<svg class="ic${on?' on':''}" viewBox="0 0 24 24" aria-hidden="true">${icons[n]}</svg>`;
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');clearTimeout(t.h);t.h=setTimeout(()=>t.classList.remove('show'),2200)}
async function api(p,o={}){const r=await fetch('/api'+p,{credentials:'same-origin',...o});let d={};try{d=await r.json()}catch{}if(!r.ok){if((r.status===401||r.status===403)&&me){me=null;route()}const er=new Error(d.error||'خطا');if(d.fb)er.fb=1;throw er}return d}
const post=(p,b)=>api(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
const upl=(p,fd)=>api(p,{method:'POST',body:fd});
function timeAgo(t){const s=Math.floor(Date.now()/1000-t);if(s<60)return'همین الان';if(s<3600)return fa(Math.floor(s/60))+' دقیقه پیش';if(s<86400)return fa(Math.floor(s/3600))+' ساعت پیش';if(s<604800)return fa(Math.floor(s/86400))+' روز پیش';return new Date(t*1000).toLocaleDateString('fa-IR')}
const av=(u,c='')=>u.avatar?`<img class="av ${c}" src="/media/${u.avatar}" alt="">`:`<span class="av ph ${c}">${esc((u.username||'?')[0]).toUpperCase()}</span>`;
const pst=p=>p.poster?`poster="/media/${esc(p.poster)}"`:'';
const lowAttr=p=>p.low?`data-low="/media/${esc(p.low)}" data-kb="${p.kbps||0}"`:'';
const carHtml=(p,d)=>`<div class="car" data-onclick="mTap(event,${p.id},this)" data-onscroll="carDots(this)">${p.media.map((m,i)=>`<img src="/media/${d||bigImg()?m.file:(m.mid||m.file)}" loading="${i?'lazy':'eager'}" decoding="async" alt="" ${m.poster?`style="background:var(--line) url('/media/${esc(m.poster)}') center/cover"`:''}>`).join('')}</div><div class="dots">${p.media.map((_,i)=>`<i class="${i?'':'on'}"></i>`).join('')}</div>`;
function carDots(c){const i=Math.round(Math.abs(c.scrollLeft)/c.clientWidth),d=c.nextElementSibling;if(d)[...d.children].forEach((x,k)=>x.classList.toggle('on',k===i))}
const media=(p,d)=>p.media&&p.media.length>1?carHtml(p,d):p.kind==='video'?(d?`<video src="/media/${p.file}" controls playsinline preload="metadata"></video>`:`<video data-auto data-src="/media/${p.file}" ${lowAttr(p)} ${pst(p)} muted loop playsinline disablepictureinpicture preload="metadata" ></video>`):`<img data-onclick="mTap(event,${p.id},this)" src="/media/${d||bigImg()?p.file:(p.mid||p.file)}" loading="lazy" decoding="async" alt="" ${p.poster?`style="background:var(--line) url('/media/${esc(p.poster)}') center/cover"`:''}>`;
const thumb=p=>`<a href="#/p/${p.id}">${p.poster?`<img src="/media/${p.poster}" loading="lazy" decoding="async" alt="">`:p.kind==='video'?`<video data-src="/media/${p.file}#t=0.1" muted preload="metadata"></video>`:`<img src="/media/${p.file}" loading="lazy" decoding="async" alt="">`}${p.kind==='video'?'<span class="vd">▶</span>':''}</a>`;
const grid=l=>l.length?`<div class="grid">${l.map(thumb).join('')}</div>`:'';

/* ---- video autoplay in feed ---- */
/* ---- تم، نصب برنامه (PWA) ---- */
let THEME='dark';try{THEME=localStorage.getItem('theme')||'dark'}catch{}
function applyTheme(){const light=THEME==='light'||(THEME==='system'&&matchMedia('(prefers-color-scheme: light)').matches);document.documentElement.dataset.theme=light?'light':'dark';document.querySelector('meta[name=theme-color]')?.setAttribute('content',light?'#f4f5f8':'#07090d')}
function setTheme(v){THEME=v;try{localStorage.setItem('theme',v)}catch{}applyTheme()}
applyTheme();
let IPROMPT=null;addEventListener('beforeinstallprompt',e=>{e.preventDefault();IPROMPT=e});
function installApp(){if(IPROMPT){IPROMPT.prompt();IPROMPT=null}else toast('از منوی مرورگر «Install / افزودن به صفحه اصلی» را بزن (آیفون: Share ← Add to Home Screen)')}
if('serviceWorker' in navigator&&(location.protocol==='https:'||/^(localhost|127\.0\.0\.1)$/.test(location.hostname)))navigator.serviceWorker.register('/sw.js').catch(()=>{});
/* ---- شبکه: سرعت را اندازه می‌گیریم و کیفیت را خودکار انتخاب می‌کنیم (مثل اینستاگرام) ---- */
let QP='auto';try{QP=localStorage.getItem('qp')||'auto'}catch{}
let BW=Math.min((navigator.connection?.downlink||5)*1000,20000);let bwOk=false;  // kbps؛ تا اولین اندازه‌گیری حدودی
async function probeBW(){try{const t0=performance.now(),r=await fetch('/api/speed?n=300000&t='+Date.now(),{cache:'no-store'}),b=await r.arrayBuffer();const k=b.byteLength*8/1000/Math.max((performance.now()-t0)/1000,.05);BW=bwOk?BW*.35+k*.65:k;bwOk=true;const dl=navigator.connection?.downlink;if(dl)BW=Math.min(BW,dl*1300)}catch{}}
const BWP=Promise.race([probeBW(),new Promise(r=>setTimeout(r,1500))]);
setInterval(()=>{if(!document.hidden)probeBW()},90000);
const lowNet=()=>QP==='low'||(QP==='auto'&&BW<2500);
const bigImg=()=>QP==='high'||(QP==='auto'&&BW>=8000);
function setQP(v){QP=v;try{localStorage.setItem('qp',v)}catch{}toast('کیفیت: '+({auto:'خودکار',low:'کم (صرفه‌جویی)',high:'بالا'})[v])}
/* ---- ویدیوی کم‌مصرف: فقط ویدیوهای نزدیک صفحه بار می‌شوند و دورها آزاد می‌شوند ---- */
/* نسخه‌ای را برمی‌داریم که نرخ بیتش حداکثر ۶۰٪ سرعت اندازه‌گرفته‌شده باشد (بقیه برای پیش‌بارگذاری و API می‌ماند) */
const vurl=v=>{const low=v.dataset.low;if(!low||QP==='high')return v.dataset.src;if(QP==='low')return low;const kb=+v.dataset.kb;return(kb?kb>BW*.6:lowNet())?low:v.dataset.src};
const loadV=v=>{if(!v.getAttribute('src')&&v.dataset.src){v.src=vurl(v);armStall(v)}};
function armStall(v){v.onwaiting=()=>{clearTimeout(v._st);v._st=setTimeout(()=>{if(!v.paused&&v.readyState<3)downshift(v)},1800)};v.onplaying=()=>clearTimeout(v._st)}
function downshift(v){const low=v.dataset.low;if(!low||v.src.endsWith(low))return;const t=v.currentTime;BW=Math.min(BW,1800);v.src=low;v.currentTime=t;v.play().catch(()=>{})}
const dropV=v=>{if(v.src){v.pause();v.removeAttribute('src');v.load()}};
const vload=new IntersectionObserver(es=>es.forEach(e=>e.isIntersecting?loadV(e.target):dropV(e.target)),{rootMargin:'100% 0px'});
const vdrop=new IntersectionObserver(es=>es.forEach(e=>{if(!e.isIntersecting)dropV(e.target)}),{rootMargin:'250% 0px'});
const lazyV=()=>document.querySelectorAll('video[data-src]:not([data-auto]):not([data-obs])').forEach(v=>{v.dataset.obs=1;vload.observe(v)});
let vo,ACT=null,ROBS=[];
function watchVideos(){vo?.disconnect();vo=new IntersectionObserver(es=>es.forEach(e=>{const v=e.target;if(e.isIntersecting){document.querySelectorAll('video[data-auto]').forEach(x=>{if(x!==v)x.pause()});loadV(v);v.muted=MUTED;v.play().catch(()=>{})}else v.pause()}),{threshold:.6});document.querySelectorAll('video[data-auto]').forEach(v=>{vo.observe(v);vdrop.observe(v)})}
let LT={id:0,t:0,h:0};
function mTap(e,id,el){const now=Date.now();if(LT.id===id&&now-LT.t<320){clearTimeout(LT.h);LT.t=0;burst(el);const p=PM[id];if(!p||!p.liked)like(id);return}LT={id,t:now,h:setTimeout(()=>{if(el.tagName==='VIDEO')tapMute(el)},320)}}
function burst(el){const a=el.closest('.post');if(!a)return;const h=document.createElement('div');h.className='hb';h.innerHTML=ic('heart',1);a.appendChild(h);setTimeout(()=>h.remove(),850)}
function tapMute(v){MUTED=!MUTED;document.querySelectorAll('video').forEach(x=>x.muted=MUTED);toast(MUTED?'صدا خاموش':'صدا روشن');const b=$('#mt');if(b)b.innerHTML=ic(MUTED?'mute':'vol')}

/* ---- متن غنی، منو، گزارش ---- */
const rich=s=>esc(s).replace(/(^|[^&\w])#([\w\u0600-\u06FF]{2,40})/g,'$1<a class="tg" href="#/tag/$2"><bdi>#$2</bdi></a>').replace(/(^|[^\w@])@([a-zA-Z0-9_][a-zA-Z0-9_.]{1,30}[a-zA-Z0-9_])/g,'$1<a class="tg" href="#/u/$2"><bdi>@$2</bdi></a>');
const patch=(p,b)=>api(p,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
const PM={};let MENU=[];
function sheetEl(){let s=$('#sheet');if(!s){s=document.createElement('div');s.id='sheet';document.body.appendChild(s)}return s}
function actionSheet(title,items){MENU=items;sheetEl().innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div>${title?`<h3>${esc(title)}</h3>`:''}<div class="menu">${items.map((it,i)=>`<button class="${it.danger?'dng':''}" data-onclick="menuDo(${i})">${it.label}</button>`).join('')}</div></div>`}
function menuDo(i){const it=MENU[i];closeCm();it.fn()}
async function copyLink(url){try{await navigator.clipboard.writeText(url);toast('لینک کپی شد')}catch{toast(url)}}
function postMenu(id){const p=PM[id];if(!p)return;const items=[{label:'افزودن به کالکشن',fn:()=>collSheet(id)},{label:'کپی لینک',fn:()=>copyLink(location.origin+'/p/'+id)}];
  if(p.mine){items.unshift({label:'آمار پست',fn:()=>insights(id)});items.unshift({label:'ویرایش توضیح',fn:()=>editCaption(id)});items.push({label:'حذف پست',danger:1,fn:()=>delPost(id)})}else items.push({label:'گزارش پست',danger:1,fn:()=>reportSheet('post',id)});actionSheet('',items)}
function reelMenu(id){const p=RL.find(x=>x.id===id);if(p){PM[id]=p;postMenu(id)}}
async function insights(id){try{const d=await api('/post/'+id+'/insights'),row=(l,v)=>`<div class="ir"><span>${l}</span><b>${v}</b></div>`;sheetEl().innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div><h3>آمار پست</h3><div class="ins">${row('دسترسی (افراد دیده‌اند)',fa(d.reach))}${d.kind==='video'?row('بازدید ریل',fa(d.plays))+row('میانگین تماشا',fa(d.avg_watch)+'٪')+row('کل زمان تماشا',fa(d.watch_minutes)+' دقیقه'):''}${row('پسند',fa(d.likes))}${row('نظر',fa(d.comments))}${row('ذخیره',fa(d.saves))}${row('بینندگان غیردنبال‌کننده',fa(d.non_followers)+'٪')}</div></div>`}catch(e){toast(e.message)}}
async function collSheet(pid){try{const cs=await api('/collections?post_id='+pid);sheetEl().innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div><h3>افزودن به کالکشن</h3><div class="menu">${cs.map(c=>`<button data-onclick="collToggle(${c.id},${pid},this)">${esc(c.name)} <span>${c.has?'✓':''}</span></button>`).join('')}<button data-onclick="collNew(${pid})">+ کالکشن جدید</button></div></div>`}catch(e){toast(e.message)}}
async function collToggle(cid,pid,b){try{const r=await post('/collections/'+cid+'/items',{post_id:pid});b.querySelector('span').textContent=r.has?'✓':''}catch(e){toast(e.message)}}
async function collNew(pid){const n=prompt('نام کالکشن');if(!n)return;try{const c=await post('/collections',{name:n});if(pid)await post('/collections/'+c.id+'/items',{post_id:pid});closeCm();toast('کالکشن ساخته شد');if(!pid)route()}catch(e){toast(e.message)}}
function reportSheet(kind,id){actionSheet('چرا گزارش می‌کنی؟',['اسپم','محتوای نامناسب','خشونت یا آزار','اطلاعات نادرست','دلیل دیگر'].map(r=>({label:r,fn:()=>sendReport(kind,id,r)})))}
async function sendReport(kind,id,r){try{await post('/report',{kind,ref_id:id,reason:r});toast('گزارش ثبت شد؛ ممنون')}catch(e){toast(e.message)}}
function editCaption(id){const p=PM[id];sheetEl().innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div><div class="form"><h3 style="border:0;padding:0">ویرایش توضیح</h3><textarea id="ec" maxlength="2200">${esc(p.caption)}</textarea><button class="btn block" data-onclick="saveCaption(${id})">ذخیره</button></div></div>`;$('#ec').focus()}
async function saveCaption(id){try{await patch('/posts/'+id,{caption:$('#ec').value});closeCm();toast('ذخیره شد');route()}catch(e){toast(e.message)}}
/* ---- posts ---- */
let REPLY=null;
function cmItem(c,p,isReply){const del=c.mine||p.mine;return `<div class="ci ${isReply?'rp':''}" id="c${c.id}"><a href="#/u/${esc(c.username)}" data-onclick="closeCm()">${av({username:c.username,avatar:c.avatar})}</a><div class="cb"><p><a href="#/u/${esc(c.username)}" data-onclick="closeCm()"><b>${esc(c.username)}</b></a> ${rich(c.text)}</p><small>${timeAgo(c.created)} · <a href="#" data-onclick="replyTo(${c.id},'${esc(c.username)}');return false">پاسخ</a>${del?` · <a href="#" data-onclick="cDel(${c.id},${p.id});return false">حذف</a>`:''}${c.mine?'':` · <a href="#" data-onclick="reportSheet('comment',${c.id});return false">گزارش</a>`}</small></div><button class="cl ${c.liked?'liked':''}" aria-label="پسندیدن نظر" data-onclick="cLike(${c.id},this)">${ic('heart',c.liked)}<i>${c.likes?fa(c.likes):''}</i></button></div>`}
function cmThread(p){const all=p.comments,top=all.filter(c=>!c.parent_id);return top.map(c=>cmItem(c,p)+all.filter(r=>r.parent_id===c.id).map(r=>cmItem(r,p,1)).join('')).join('')||'<p class="mute" style="padding:6px 0">هنوز نظری نیست. اولین نفر باش.</p>'}
function commentsHtml(p){return `<div class="cm" id="cmlist">${cmThread(p)}</div><div id="rchip" class="rchip" hidden></div><div class="cform"><input id="ci" maxlength="500" placeholder="نظرت را بنویس…" data-onkeydown="if(event.key==='Enter')addC(${p.id})"><button class="lnk" data-onclick="addC(${p.id})">ارسال</button></div>`}
function replyTo(id,name){REPLY={id,name};const i=$('#ci')||$('#si'),c=$('#rchip');if(c){c.hidden=false;c.innerHTML=`پاسخ به <b>@${esc(name)}</b> <button data-onclick="cancelReply()" aria-label="لغو">✕</button>`}if(i){i.value='@'+name+' ';i.focus()}}
function cancelReply(){REPLY=null;const c=$('#rchip');if(c)c.hidden=true}
const reloadCm=pid=>$('#sheet .pan.cmp')?openCm(pid):route();
async function sendComment(pid,input){const t=input.value.trim();if(!t)return;try{await post('/posts/'+pid+'/comments',{text:t,parent_id:REPLY?.id});REPLY=null;reloadCm(pid)}catch(e){toast(e.message)}}
async function cLike(cid,b){try{const r=await post('/comments/'+cid+'/like');b.className='cl '+(r.liked?'liked':'');b.innerHTML=ic('heart',r.liked)+'<i>'+(r.likes?fa(r.likes):'')+'</i>'}catch(e){toast(e.message)}}
async function cDel(cid,pid){if(!confirm('این نظر حذف شود؟'))return;try{await api('/comments/'+cid,{method:'DELETE'});reloadCm(pid)}catch(e){toast(e.message)}}
const actsHtml=p=>`<div class="acts"><button aria-label="پسندیدن" class="${p.liked?'liked':''}" data-onclick="like(${p.id})">${ic('heart',p.liked)}</button><a aria-label="نظرات" href="#/p/${p.id}">${ic('chat')}</a><button aria-label="ارسال" data-onclick="openShare(${p.id})">${ic('share')}</button><button class="sv" aria-label="ذخیره" data-onclick="save(${p.id})">${ic('bookmark',p.saved)}</button></div>`;
function postHtml(p,d){PM[p.id]=p;return `<article class="card post" id="post-${p.id}" data-d="${d?1:''}"><header><a class="who" href="#/u/${esc(p.user.username)}">${av(p.user)}<b>${esc(p.user.username)}</b></a><button class="mn" aria-label="گزینه‌ها" data-onclick="postMenu(${p.id})">⋯</button></header>${media(p,d)}${actsHtml(p)}<div class="body"><b class="cnt">${fa(p.likes)} پسند</b>${p.kind==='video'&&p.views?`<span class="mute" style="display:inline"> · ${fa(p.views)} بازدید</span>`:''}${p.caption?`<p><a href="#/u/${esc(p.user.username)}"><b>${esc(p.user.username)}</b></a> ${rich(p.caption)}</p>`:''}${!d&&p.ncomments?`<a class="mute" href="#/p/${p.id}">دیدن ${fa(p.ncomments)} نظر</a>`:''}<time>${timeAgo(p.created)}</time></div>${d?commentsHtml(p):''}</article>`}
function swap(p){PM[p.id]=p;const el=$('#post-'+p.id);if(!el)return;el.querySelector('.acts').outerHTML=actsHtml(p);el.querySelector('.cnt').textContent=fa(p.likes)+' پسند'}
async function like(id){try{swap(await post('/posts/'+id+'/like'))}catch(e){toast(e.message)}}
async function save(id){try{const p=await post('/posts/'+id+'/save');swap(p);toast(p.saved?'ذخیره شد':'از ذخیره‌ها برداشته شد')}catch(e){toast(e.message)}}
async function addC(id){await sendComment(id,$('#ci'))}
async function delPost(id){if(!confirm('این پست حذف شود؟'))return;try{await api('/posts/'+id,{method:'DELETE'});toast('حذف شد');location.hash='#/u/'+me.username}catch(e){toast(e.message)}}
async function shareP(id){const url=location.origin+'/p/'+id;try{if(navigator.share){await navigator.share({url})}else{await navigator.clipboard.writeText(url);toast('لینک کپی شد')}}catch{}}

/* ---- layout ---- */
function navHtml(tab){const it=[['home','#/','home'],['reels','#/reels','reels'],['plus','#/new','new'],['search','#/explore','explore']];return `<nav class="nav"><div class="wrap">${it.map(([i,h,t])=>`<a href="${h}" aria-label="${i}" class="${tab===t?'on':''}">${ic(i,tab===t&&i==='home')}</a>`).join('')}<a href="#/u/${esc(me.username)}" aria-label="پروفایل" class="${tab==='me'?'on':''}">${av(me)}</a></div></nav>`}
function shell(html,tab){app.innerHTML=`<div class="top"><div class="wrap"><a class="logo" href="#/">قاب<i>.</i></a><span class="tr"><a class="dm" href="#/activity" aria-label="اعلان‌ها">${ic('heart')}<i class="dmb" id="actb"></i></a></span></div></div><main class="wrap">${html}</main>${navHtml(tab||'')}`;scrollTo(0,0);pollUnread();lazyV()}

let QS=null,LASTPW='',NEXT='';
async function questions(){return QS||(QS=await api('/security/questions'))}
async function authView(mode='login'){
  try{const am=await api('/auth_mode');if(am.password_auth===false){app.innerHTML='<div class="auth"><h1>قاب<i>.</i></h1><div class="card form"><p class="mute" style="text-align:center;line-height:2;margin:0">برای ورود، تو ویندروید منوی ☰ را باز کن و «قاب» را بزن.<br>ورود با نام کاربری و رمز اینجا وجود ندارد.</p></div></div>';return}}catch{}
  if(mode==='forgot')return forgotView();
  const reg=mode==='register',qs=reg?await questions():[];
  app.innerHTML=`<div class="auth"><h1>قاب<i>.</i></h1><p class="sub">لحظه‌هایت را قاب کن و با دوستانت ببین.</p><div class="card form"><label>نام کاربری<input id="u" autocapitalize="none" autocomplete="username" dir="ltr"></label>${reg?'<label>نام نمایشی<input id="n" maxlength="40"></label>':''}<label>رمز عبور<input id="p" type="password" autocomplete="${reg?'new-password':'current-password'}" dir="ltr" data-onkeydown="if(event.key==='Enter')doAuth('${mode}')"></label>${reg?`<label>سوال امنیتی (برای بازیابی رمز)<select id="sq">${qs.map((x,i)=>`<option value="${i}">${esc(x)}</option>`).join('')}</select></label><label>جواب سوال<input id="sa" maxlength="60" autocomplete="off"></label>`:''}<div class="msg" id="m"></div><button class="btn block" data-onclick="doAuth('${mode}')">${reg?'ساخت حساب':'ورود'}</button>${reg?'':'<a class="lnk" style="text-align:center" href="#/forgot">رمز را فراموش کردم</a>'}</div><p class="sw">${reg?'حساب داری؟ <a class="lnk" href="#/login">وارد شو</a>':'حساب نداری؟ <a class="lnk" href="#/register">ثبت‌نام کن</a>'}</p><p class="sw" style="margin-top:6px"><a class="lnk" href="/trust">هشدار امنیتی مرورگر می‌بینی؟</a></p></div>`}
async function doAuth(mode){try{const pw=$('#p').value;me=await post('/'+mode,{username:$('#u').value,password:pw,name:$('#n')?.value,sec_q:+($('#sq')?.value||0),sec_a:$('#sa')?.value});LASTPW=pw;location.hash=NEXT||'#/';NEXT='';route()}catch(e){$('#m').textContent=e.message}}
function forgotView(){app.innerHTML=`<div class="auth"><h1>قاب<i>.</i></h1><p class="sub">بازیابی رمز عبور</p><div class="card form" id="fg"><label>نام کاربری<input id="u" dir="ltr" autocapitalize="none" data-onkeydown="if(event.key==='Enter')fgNext()"></label><div class="msg" id="m"></div><button class="btn block" data-onclick="fgNext()">ادامه</button></div><p class="sw"><a class="lnk" href="#/login">بازگشت به ورود</a></p></div>`}
async function fgNext(){const u=$('#u').value.trim();try{const r=await api('/reset/question?username='+encodeURIComponent(u));$('#fg').innerHTML=`<div><b>${esc(r.question)}</b></div><label>جواب<input id="a" autocomplete="off"></label><label>رمز جدید<input id="p" type="password" dir="ltr" autocomplete="new-password" data-onkeydown="if(event.key==='Enter')fgDo('${esc(u)}')"></label><div class="msg" id="m"></div><button class="btn block" data-onclick="fgDo('${esc(u)}')">تغییر رمز</button>`}catch(e){$('#m').textContent=e.message}}
async function fgDo(u){try{await post('/reset',{username:u,answer:$('#a').value,password:$('#p').value});toast('رمز عوض شد؛ حالا وارد شو');location.hash='#/login'}catch(e){$('#m').textContent=e.message}}
async function secPrompt(){if(!me||me.has_sec)return;const qs=await questions();let s=$('#sheet');if(!s){s=document.createElement('div');s.id='sheet';document.body.appendChild(s)}
s.innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div><div class="form"><h3 style="border:0;padding:0">🔐 بازیابی رمز عبور</h3><p class="mute" style="text-align:center;margin:0">یک سوال و جواب ثبت کن تا اگر رمزت را فراموش کردی خودت بتوانی برش گردانی.</p><label>سوال امنیتی<select id="sq3">${qs.map((x,i)=>`<option value="${i}">${esc(x)}</option>`).join('')}</select></label><label>جواب<input id="sa3" maxlength="60" autocomplete="off"></label>${LASTPW?'':'<label>رمز فعلی<input id="cp3" type="password" autocomplete="current-password" dir="ltr"></label>'}<div class="msg" id="m3"></div><button class="btn block" data-onclick="secSave()">ذخیره</button><button class="lnk" data-onclick="closeCm()">بعداً</button></div></div>`}
async function secSave(){try{await post('/me/security',{current:LASTPW||$('#cp3').value,sec_q:+$('#sq3').value,sec_a:$('#sa3').value});me.has_sec=true;closeCm();toast('بازیابی رمز فعال شد')}catch(e){$('#m3').textContent=e.message}}
async function changePw(){try{await post('/me/password',{current:$('#cp').value,password:$('#np').value});LASTPW=$('#np').value;$('#cp').value=$('#np').value='';toast('رمز تغییر کرد')}catch(e){toast(e.message)}}
async function saveSec(){try{await post('/me/security',{current:$('#cp').value,sec_q:+$('#sq2').value,sec_a:$('#sa2').value});me.has_sec=true;$('#sa2').value='';toast('سوال امنیتی ذخیره شد')}catch(e){toast(e.message)}}

/* ---- feed + stories ---- */
/* آمار «دسترسی»: پست‌هایی که ≥۵۰٪ دیده شدند (۱ ثانیه) دسته‌ای گزارش می‌شوند */
let IMPQ=new Set(),IMPO=null;const SEENI=new Set();
function trackImp(){IMPO?.disconnect();IMPO=new IntersectionObserver(es=>es.forEach(e=>{const el=e.target;if(e.isIntersecting)el._it=setTimeout(()=>{const id=+el.id.slice(5);if(!SEENI.has(id)){SEENI.add(id);IMPQ.add(id)}},900);else clearTimeout(el._it)}),{threshold:.5});document.querySelectorAll('.post').forEach(p=>IMPO.observe(p));ROBS.push(IMPO)}
setInterval(()=>{if(!IMPQ.size||!me)return;const ids=[...IMPQ].slice(0,30);IMPQ=new Set([...IMPQ].slice(30));fetch('/api/impressions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids}),credentials:'same-origin',keepalive:true}).catch(()=>{ids.forEach(i=>IMPQ.add(i))})},4000);
const flushImp=()=>{if(!IMPQ.size||!me)return;const ids=[...IMPQ];IMPQ=new Set();try{fetch('/api/impressions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:ids.slice(0,200)}),credentials:'same-origin',keepalive:true}).catch(()=>{})}catch{}};
addEventListener('pagehide',flushImp);document.addEventListener('visibilitychange',()=>{if(document.hidden)flushImp()});
/* افرادی که شاید بشناسی */
const sugHtml=l=>{let ds=[];try{ds=JSON.parse(localStorage.getItem('sugx')||'[]')}catch{}const x=l.filter(u=>!ds.includes(u.username));return x.length?`<div class="sug"><h3>افرادی که شاید بشناسی</h3><div class="sugl">${x.map(u=>`<div class="sg" id="sg-${esc(u.username)}"><button class="sx" aria-label="حذف" data-onclick="sugX('${esc(u.username)}')">✕</button><a href="#/u/${esc(u.username)}">${av(u,'lg')}<b>${esc(u.username)}</b></a><small>${esc(u.reason)}</small><button class="btn" data-onclick="followFrom('${esc(u.username)}',this)">${u.private?'درخواست':'دنبال کن'}</button></div>`).join('')}</div></div>`:''};
function sugX(u){let ds=[];try{ds=JSON.parse(localStorage.getItem('sugx')||'[]')}catch{}ds.push(u);try{localStorage.setItem('sugx',JSON.stringify(ds.slice(-200)))}catch{}document.getElementById('sg-'+u)?.remove()}
const storiesHtml=st=>{const hasMine=st[0]?.mine;
  const mine=`<div class="bub" data-onclick="${hasMine?'openStory(0)':'pickStory()'}"><span class="ring ${hasMine?'':'none'}">${av(me)}</span><em data-onclick="event.stopPropagation();pickStory()">+</em>${hasMine?'استوری تو':'افزودن'}</div>`;
  const others=st.map((g,i)=>g.mine?'':`<div class="bub" data-onclick="openStory(${i})"><span class="ring ${g.seen?'seen':''} ${g.close?'close':''}">${av(g)}</span>${esc(g.username)}</div>`).join('');
  return `<input id="sfile" type="file" accept="image/*,video/*" hidden data-onchange="addStory(this)">${mine}${others}`};
async function refreshStories(){const el=$('.stories');if(!el)return;try{ST=await api('/stories');el.innerHTML=storiesHtml(ST)}catch{}}
const pickStory=()=>$('#sfile').click();
async function feedView(){await BWP;const [st,ps,sg]=await Promise.all([api('/stories'),api('/feed?limit=8'),api('/suggestions').catch(()=>[])]);ST=st;
shell(`${me.has_sec?'':'<a class="card note" href="#/edit">🔐 برای بازیابی رمز، یک سوال امنیتی ثبت کن</a>'}<div class="stories">${storiesHtml(st)}</div>${sugHtml(sg)}${ps.map(p=>postHtml(p)).join('')||'<div class="empty">فید تو خالی است.<br>از بخش جستجو آدم‌ها را دنبال کن یا اولین پستت را بگذار.</div>'}<div id="more"></div>`,'home');FSEEN=ps.map(p=>p.id);watchVideos();bindFeedVideos();moreFeed();trackImp()}
let FSEEN=[],MORE=null;
function moreFeed(){const s=$('#more');if(!s)return;MORE=new IntersectionObserver(async es=>{if(!es[0].isIntersecting)return;MORE.unobserve(s);try{const ps=await api('/feed?limit=8&exclude='+FSEEN.join(','));if(!ps.length){s.remove();return}FSEEN.push(...ps.map(p=>p.id));s.insertAdjacentHTML('beforebegin',ps.map(p=>postHtml(p)).join(''));lazyV();watchVideos();bindFeedVideos();trackImp();MORE.observe(s)}catch{}},{rootMargin:'700px 0px'});ROBS.push(MORE);MORE.observe(s)}
let SFILE=null;
function addStory(i){const f=i.files[0];i.value='';if(!f)return;SFILE=f;sheetEl().innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div><div class="form"><h3 style="border:0;padding:0">استوری تازه</h3><label>برای چه کسانی؟<select id="sa"><option value="all">همه</option><option value="close">فقط دوستان نزدیک 💚</option></select></label><label style="display:flex;gap:8px;align-items:center;flex-direction:row"><input type="checkbox" id="spq" style="width:auto" data-onchange="togSpf(this)">افزودن نظرسنجی</label><div id="spf" class="pf" hidden><input id="spq1" maxlength="60" placeholder="سوال…"><input id="spa" maxlength="24" placeholder="گزینه اول"><input id="spb" maxlength="24" placeholder="گزینه دوم"></div><button class="btn block" data-onclick="sendStory()">اشتراک</button></div></div>`}
async function sendStory(){const fd=new FormData();fd.append('file',SFILE);fd.append('audience',$('#sa').value);if($('#spq').checked){fd.append('poll_q',$('#spq1').value);fd.append('poll_a',$('#spa').value);fd.append('poll_b',$('#spb').value)}closeCm();toast('در حال ارسال استوری…');try{await upl('/stories',fd);toast('استوری منتشر شد');refreshStories()}catch(e){toast(e.message)}}
function stickerHtml(g,s){const k=s.sticker;if(!k)return'';const v=k.votes,tot=v?v[0]+v[1]:0,pct=i=>tot?Math.round(100*v[i]/tot):0,res=g.mine||k.mine!=null;
  const btn=(i,l)=>res?`<div class="pb ${k.mine===i?'me':''}"><i style="width:${pct(i)}%"></i><span>${esc(l)}</span><b>${fa(pct(i))}٪</b></div>`:`<button class="pb" data-onclick="stVote(${s.id},${i})"><span>${esc(l)}</span></button>`;
  return `<div class="stk" id="stk"><p>${esc(k.q)}</p>${btn(0,k.a)}${btn(1,k.b)}</div>`}
async function stVote(id,i){try{const r=await post('/stories/'+id+'/vote',{choice:i}),g=ST[SV.i],s=g.items[SV.j];s.sticker.votes=r.votes;s.sticker.mine=r.mine;$('#stk').outerHTML=stickerHtml(g,s)}catch(e){toast(e.message)}}
async function openHighlight(id){try{const g=await api('/highlights/'+id);ST=[g];openStory(0)}catch(e){toast(e.message)}}
async function delHighlight(id){svPause(1);if(!confirm('این هایلایت حذف شود؟')){svPause(0);return}try{await api('/highlights/'+id,{method:'DELETE'});closeS();toast('حذف شد');route()}catch(e){toast(e.message);svPause(0)}}
async function hlSheet(sid){svPause(1);try{const l=await api('/highlights/mine');sheetEl().innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div><h3>افزودن به هایلایت</h3><div class="menu">${l.map(h=>`<button data-onclick="hlAdd(${h.id},${sid})">${esc(h.title)}</button>`).join('')}<button data-onclick="hlNew(${sid})">+ هایلایت جدید</button></div></div>`}catch(e){toast(e.message)}}
async function hlAdd(h,sid){try{await post('/highlights/'+h+'/add',{story_id:sid});closeCm();toast('به هایلایت اضافه شد')}catch(e){toast(e.message)}}
async function hlNew(sid){const n=prompt('نام هایلایت');if(!n)return;try{await post('/highlights',{title:n,story_id:sid});closeCm();toast('هایلایت ساخته شد')}catch(e){toast(e.message)}}
let SV=null;
function openStory(i,j){const g=ST[i];if(!g)return closeS();
  if(j===undefined){j=g.items.findIndex(x=>!x.seen);if(j<0)j=0}
  const s=g.items[j];if(!s)return openStory(i+1);
  SV={i,j};let o=$('#ov');if(!o){o=document.createElement('div');o.id='ov';document.body.appendChild(o);bindOv(o)}
  o.classList.remove('paused');const vid=s.kind==='video';
  const bars=g.items.map((x,k)=>`<i class="${k<j?'full':k===j?'cur'+(vid?' vid':''):''}"><b></b></i>`).join('');
  const foot=g.hid?(g.mine?`<button data-onclick="delHighlight(${g.hid})">حذف هایلایت</button>`:''):g.mine?`<button data-onclick="viewers(${s.id})">👁 ${fa(s.views||0)} بازدید</button><span style="flex:1"></span><button data-onclick="hlSheet(${s.id})">⭐ هایلایت</button><button data-onclick="delStory(${s.id})">حذف</button>`:`<input id="sr" maxlength="500" placeholder="پیام به ${esc(g.username)}…" autocomplete="off" data-onfocus="svPause(1)" data-onblur="svPause(0)" data-onkeydown="if(event.key==='Enter')sReply('${esc(g.username)}')">`;
  o.innerHTML=`<div class="sv-bars">${bars}</div><div class="sv-top">${av(g)}<b>${esc(g.username)}</b><span>${timeAgo(s.created)}</span><button aria-label="بستن" data-onclick="closeS()">✕</button></div><div class="sv-media">${vid?`<video src="/media/${s.file}" playsinline autoplay></video>`:`<img src="/media/${s.file}" alt="">`}</div><div class="sv-foot">${foot}</div>`;
  if(s.sticker)o.insertAdjacentHTML('beforeend',stickerHtml(g,s));
  const cur=o.querySelector('.cur b');
  if(vid){const v=o.querySelector('video');v.onended=svNext;v.ontimeupdate=()=>{cur.style.transform='scaleX('+(v.currentTime/(v.duration||1))+')'};v.play().catch(()=>{v.muted=true;v.play().catch(()=>{})})}
  else{const im=o.querySelector('img'),go=()=>{cur.parentNode.classList.add('go');cur.addEventListener('animationend',svNext,{once:true})};im.complete&&im.naturalWidth?go():(im.onload=go,im.onerror=svNext)}
  if(!g.mine&&!s.seen){s.seen=true;post('/stories/'+s.id+'/view').catch(()=>{})}
  const n=g.items[j+1];if(n&&n.kind!=='video')new Image().src='/media/'+n.file}
const svNext=()=>SV&&openStory(SV.i,SV.j+1);
function svPrev(){if(!SV)return;if(SV.j>0)openStory(SV.i,SV.j-1);else if(SV.i>0&&ST[SV.i-1])openStory(SV.i-1,ST[SV.i-1].items.length-1);else openStory(SV.i,0)}
function svPause(on){const o=$('#ov');if(!o)return;o.classList.toggle('paused',!!on);const v=o.querySelector('video');if(v)on?v.pause():v.play().catch(()=>{})}
function bindOv(o){let y0=0,tm=0,held=false;
  o.addEventListener('pointerdown',e=>{if(e.target.closest('button,input'))return;y0=e.clientY;held=false;tm=setTimeout(()=>{held=true;svPause(1)},260)});
  o.addEventListener('pointerup',e=>{if(e.target.closest('button,input'))return;clearTimeout(tm);if(held){held=false;svPause(0);return}if(e.clientY-y0>100)return closeS();const r=o.getBoundingClientRect();(e.clientX-r.left<r.width/2)?svNext():svPrev()});
  o.addEventListener('pointercancel',()=>{clearTimeout(tm);if(held){held=false;svPause(0)}})}
addEventListener('keydown',e=>{if(!$('#ov'))return;if(e.key==='Escape')closeS();else if(e.target.tagName==='INPUT')return;else if(e.key==='ArrowLeft')svNext();else if(e.key==='ArrowRight')svPrev()});
function closeS(){$('#ov')?.remove();SV=null;refreshStories()}
async function viewers(id){svPause(1);try{const l=await api('/stories/'+id+'/viewers');let s=$('#sheet');if(!s){s=document.createElement('div');s.id='sheet';document.body.appendChild(s)}
s.innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div><h3>${fa(l.length)} بازدید</h3><div class="list">${l.map(u=>`<a class="urow" style="padding:8px 0;border:0" href="#/u/${esc(u.username)}" data-onclick="closeCm();closeS()">${av(u)}<div><b>${esc(u.username)}</b><small>${timeAgo(u.at)}</small></div></a>`).join('')||'<p class="mute">هنوز کسی ندیده.</p>'}</div></div>`}catch(e){toast(e.message);svPause(0)}}
async function delStory(id){svPause(1);if(!confirm('این استوری حذف شود؟')){svPause(0);return}try{await api('/stories/'+id,{method:'DELETE'});toast('حذف شد');closeS()}catch(e){toast(e.message);svPause(0)}}
function sReply(username){const i=$('#sr'),x=i.value.trim();if(!x)return;i.value='';i.blur();wdChat(username,x)}

/* ---- reels ---- */
const railHtml=p=>`<div class="rail"><button class="${p.liked?'liked':''}" aria-label="پسندیدن" data-onclick="rLike(${p.id})">${ic('heart',p.liked)}<span>${fa(p.likes)}</span></button><button aria-label="نظرات" data-onclick="openCm(${p.id})">${ic('chat')}<span>${fa(p.ncomments)}</span></button><button aria-label="ارسال" data-onclick="openShare(${p.id})">${ic('share')}<span>ارسال</span></button><button aria-label="ذخیره" data-onclick="rSave(${p.id})">${ic('bookmark',p.saved)}<span>${p.saved?'ذخیره‌شد':'ذخیره'}</span></button><button aria-label="گزینه‌ها" data-onclick="reelMenu(${p.id})">⋯</button></div>`;
const reelHtml=(p,i)=>`<section class="reel" id="r${p.id}" data-id="${p.id}"><video data-src="/media/${p.file}" ${lowAttr(p)} ${pst(p)} loop playsinline muted disablepictureinpicture preload="metadata"></video><div class="shade"></div><div class="heart">${ic('heart',1)}</div><div class="pp">${ic('play',1)}</div>${railHtml(p)}<div class="meta"><div class="mrow"><a class="who" href="#/u/${esc(p.user.username)}">${av(p.user)}<b>${esc(p.user.username)}</b></a>${p.mine||p.followed?'':`<button class="fbtn" data-onclick="rFollow('${esc(p.user.username)}')">دنبال کن</button>`}</div>${p.caption?`<p class="cap" data-onclick="this.classList.toggle('open')">${rich(p.caption)}</p>`:''}</div><div class="prog"><i></i></div></section>`;
async function reelsView(tab){await BWP;if(tab)RT=tab;RL=await api('/reels?tab='+RT+'&limit=8');
app.innerHTML=`<div class="rtop"><a href="#/new" aria-label="پست تازه">${ic('plus2')}</a><div class="tabs"><button class="${RT==='all'?'on':''}" data-onclick="reelsView('all')">ریلز</button><button class="${RT==='following'?'on':''}" data-onclick="reelsView('following')">دنبال‌شده‌ها</button></div><button id="mt" aria-label="صدا" data-onclick="tapMute()">${ic(MUTED?'mute':'vol')}</button></div><div class="reels" id="reels">${RL.map(reelHtml).join('')||`<div class="rempty"><div style="text-align:center">${RT==='all'?'هنوز ویدیویی نیست.':'از دنبال‌شده‌ها ویدیویی نیست.'}</div><a class="btn" style="justify-self:center" href="#/new">ویدیو بگذار</a></div>`}</div>${navHtml('reels')}`;initReels()}
/* ریل بعدی فقط وقتی پیش‌بارگذاری می‌شود که ریل فعلی ۵ ثانیه جلوتر بافر شده باشد (روی اینترنت کند با ریل فعلی رقابت نکند) */
function schedNext(v,nx){if(!nx||nx.getAttribute('src'))return;
  const go=()=>{v.removeEventListener('progress',chk);v.removeEventListener('timeupdate',chk);loadV(nx);nx.preload='auto'};
  const chk=()=>{const b=v.buffered,end=b.length?b.end(b.length-1):0,dur=v.duration||0;if(dur&&(end>=Math.min(v.currentTime+5,dur-.2)||end>=dur-.3))go()};
  if(BW>=8000&&!lowNet())return go();v.addEventListener('progress',chk);v.addEventListener('timeupdate',chk);chk()}
let RATT=null,RBUSY=false,RDONE=false;
function initReels(){const box=$('#reels');if(!box)return;RBUSY=false;RDONE=false;
const ld=new IntersectionObserver(es=>es.forEach(e=>{if(!e.isIntersecting)dropV(e.target.querySelector('video'))}),{root:box,rootMargin:'250% 0px'});
const io=new IntersectionObserver(es=>es.forEach(e=>{const r=e.target,v=r.querySelector('video');if(e.isIntersecting){if(ACT&&ACT!==v)ACT.pause();ACT=v;loadV(v);v.preload='auto';if(v.currentTime>.3)v.currentTime=0;r._w=0;r._l=0;v.muted=MUTED;v.play().then(()=>r.classList.remove('paused')).catch(()=>{});schedNext(v,r.nextElementSibling?.querySelector('video'));if(RL.findIndex(x=>x.id==r.dataset.id)>=RL.length-3)moreReels()}else{v.pause();v.playbackRate=1;r.classList.remove('paused');sendWatch(r)}}),{root:box,threshold:.65});
ROBS.push(ld,io);
RATT=r=>{ld.observe(r);io.observe(r);const v=r.querySelector('video'),bar=r.querySelector('.prog i');v.ontimeupdate=()=>{const c=v.currentTime;bar.style.transform='scaleX('+(c/(v.duration||1))+')';if(c>=(r._l||0))r._w=(r._w||0)+(c-(r._l||0));r._l=c;r._d=v.duration};bindTap(r)};
box.querySelectorAll('.reel').forEach(RATT)}
function sendWatch(r){const secs=r._w||0,dur=r._d;r._w=0;if(secs<.12||!dur||!isFinite(dur))return;fetch('/api/reels/watch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({post_id:+r.dataset.id,secs,dur}),keepalive:true,credentials:'same-origin'}).catch(()=>{})}
async function moreReels(){if(RBUSY||RDONE)return;RBUSY=true;try{const ps=await api('/reels?tab='+RT+'&limit=8&exclude='+RL.map(x=>x.id).join(','));if(!ps.length)RDONE=true;else{RL.push(...ps);const box=$('#reels');box.insertAdjacentHTML('beforeend',ps.map(reelHtml).join(''));[...box.querySelectorAll('.reel')].slice(-ps.length).forEach(RATT)}}catch{}RBUSY=false}
/* حرکات ویدیو (هم ریلز، هم ویدیوهای فید):
   نگه‌داشتن نیمه راست = ۲×  |  نگه‌داشتن نیمه چپ = توقف  |  کشیدن چپ/راست = جلو/عقب بردن
   دابل‌تپ لبه راست = ۱۰ ثانیه جلو  |  لبه چپ = ۱۰ ثانیه عقب  |  دابل‌تپ وسط = لایک  |  یک‌ضربه = o.tap */
function bindGestures(el,v,o){const host=o.host||el;let st=null,last=0,lx=0,tmr=0;
  const fmt=s=>{s=Math.max(0,s|0);return fa(Math.floor(s/60))+':'+fa(String(s%60).padStart(2,'0'))};
  const note=(h,temp)=>{let n=host.querySelector(':scope>.gnote');if(!n){n=document.createElement('div');n.className='gnote';host.appendChild(n)}n.innerHTML=h;n.classList.add('on');clearTimeout(n._h);if(temp)n._h=setTimeout(()=>n.classList.remove('on'),750)};
  const hide=()=>host.querySelector(':scope>.gnote')?.classList.remove('on');
  const seek=t=>{if(!v.duration)return;t=Math.max(0,Math.min(v.duration-.05,t));if(o.onSeek)o.onSeek(t);v.currentTime=t};
  el.addEventListener('pointerdown',e=>{if(e.target.closest('button,a,.cap,.rail'))return;if(e.pointerType==='mouse'&&e.button!==0)return;
    const b=el.getBoundingClientRect();st={x:e.clientX,fx:(e.clientX-b.left)/b.width,mode:'',t0:v.currentTime,paused:v.paused,w:b.width};
    st.h=setTimeout(()=>{if(!st||st.mode)return;st.mode='hold';if(st.fx>.5){v.playbackRate=2;if(v.paused)v.play().catch(()=>{});note('⏩ ۲×')}else{v.pause();note('⏸')}},260)});
  el.addEventListener('pointermove',e=>{if(!st)return;const dx=e.clientX-st.x;
    if(!st.mode&&Math.abs(dx)>14){clearTimeout(st.h);st.mode='scrub';v.pause();try{el.setPointerCapture(e.pointerId)}catch{}}
    if(st.mode==='scrub'&&v.duration){const t=Math.max(0,Math.min(v.duration-.05,st.t0+dx/st.w*v.duration*1.2));seek(t);note(fmt(t)+' / '+fmt(v.duration));host.querySelector('.prog')?.classList.add('big')}});
  const end=cancel=>{if(!st)return;clearTimeout(st.h);const s=st;st=null;v.playbackRate=1;
    if(s.mode==='hold'){if(s.fx<=.5&&!s.paused)v.play().catch(()=>{});if(s.fx>.5&&s.paused)v.pause();hide();return}
    if(s.mode==='scrub'){host.querySelector('.prog')?.classList.remove('big');hide();if(!s.paused)v.play().catch(()=>{});return}
    if(cancel)return;const now=Date.now();
    if(now-last<300&&Math.abs(s.x-lx)<70){clearTimeout(tmr);last=0;
      if(s.fx<.3||s.fx>.7){const d=s.fx<.3?-10:10;seek(v.currentTime+d);note(d<0?'⏪ ۱۰ ثانیه':'⏩ ۱۰ ثانیه',1)}else o.dbl()}
    else{last=now;lx=s.x;tmr=setTimeout(()=>{last=0;o.tap()},300)}};
  el.addEventListener('pointerup',()=>end(false));el.addEventListener('pointercancel',()=>end(true));el.addEventListener('contextmenu',e=>e.preventDefault())}
function bindTap(r){const v=r.querySelector('video');bindGestures(r,v,{onSeek:t=>{r._l=t},
  tap:()=>{if(v.paused){v.play();r.classList.remove('paused')}else{v.pause();r.classList.add('paused')}},
  dbl:()=>{const it=RL.find(x=>x.id==r.dataset.id),h=r.querySelector('.heart');h.classList.remove('go');void h.offsetWidth;h.classList.add('go');if(it&&!it.liked)rLike(it.id)}})}
function bindFeedVideos(){document.querySelectorAll('.post video[data-auto]:not([data-g])').forEach(v=>{v.dataset.g=1;const post=v.closest('.post'),id=+post.id.slice(5);bindGestures(v,v,{host:post,tap:()=>tapMute(v),dbl:()=>{burst(v);const p=PM[id];if(!p||!p.liked)like(id)}})})}
function rSync(p){const it=RL.find(x=>x.id==p.id);if(it)Object.assign(it,{likes:p.likes,liked:p.liked,saved:p.saved,ncomments:p.ncomments});const r=$('#r'+p.id);if(r&&it)r.querySelector('.rail').outerHTML=railHtml(it)}
async function rLike(id){try{rSync(await post('/posts/'+id+'/like'))}catch(e){toast(e.message)}}
async function rSave(id){try{const p=await post('/posts/'+id+'/save');rSync(p);toast(p.saved?'ذخیره شد':'از ذخیره‌ها برداشته شد')}catch(e){toast(e.message)}}
async function rFollow(name){try{await post('/user/'+name+'/follow');RL.forEach(x=>{if(x.user.username===name)x.followed=true});document.querySelectorAll('.fbtn').forEach(b=>{if(b.getAttribute('onclick').includes("'"+name+"'"))b.remove()});toast('دنبال کردی')}catch(e){toast(e.message)}}
async function openCm(id){try{const p=await api('/post/'+id);let s=$('#sheet');if(!s){s=document.createElement('div');s.id='sheet';document.body.appendChild(s)}
s.innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan cmp"><div class="grab"></div><h3>${fa(p.ncomments)} نظر</h3><div class="list">${cmThread(p)}</div><div id="rchip" class="rchip" hidden></div><div class="cform"><input id="si" maxlength="500" placeholder="نظرت را بنویس…" data-onkeydown="if(event.key==='Enter')sendCm(${id})"><button class="lnk" data-onclick="sendCm(${id})">ارسال</button></div></div>`;rSync(p)}catch(e){toast(e.message)}}
function closeCm(){REPLY=null;$('#sheet')?.remove();if($('#ov'))svPause(0)}
async function sendCm(id){await sendComment(id,$('#si'))}

/* ---- اعلان‌ها ---- */
const actText={like:'پست تو را پسندید',comment:'زیر پست تو نظر داد',reply:'به نظر تو پاسخ داد',mention:'تو را منشن کرد',follow:'شروع به دنبال کردن تو کرد',comment_like:'نظر تو را پسندید',follow_request:'درخواست دنبال کردن فرستاد',follow_accept:'درخواست تو را پذیرفت'};
async function followFrom(u,b){try{const r=await post('/user/'+u+'/follow'),on=!!(r.followed||r.requested);b.classList.toggle('alt',on);b.textContent=r.requested?'درخواست شد':r.followed?'دنبال می‌کنی':'دنبال کن'}catch(e){toast(e.message)}}
async function ansReq(u,act,b){try{await post('/requests/'+u+'/'+act);b.parentElement.innerHTML=act==='accept'?'<small>تأیید شد</small>':'<small>حذف شد</small>'}catch(e){toast(e.message)}}
async function activityView(){const l=await api('/activity');
  shell(`<h2 style="padding:14px 4px 6px">اعلان‌ها</h2>${l.length?`<div class="card">${l.map(n=>`<a class="urow ${n.seen?'':'newn'}" href="${n.post?'#/p/'+n.post.id:'#/u/'+esc(n.actor.username)}">${av(n.actor)}<div style="flex:1;min-width:0"><b>${esc(n.actor.username)}</b> ${actText[n.type]||''}${n.text?`<small>«${esc(n.text)}»</small>`:''}<small>${timeAgo(n.created)}</small></div>${n.post?(n.post.poster||n.post.kind!=='video'?`<img class="nth" src="/media/${esc(n.post.poster||n.post.file)}" alt="">`:'<span class="nth">▶</span>'):(n.type==='follow_request'?`<span class="rqb"><button class="btn" data-onclick="event.preventDefault();ansReq('${esc(n.actor.username)}','accept',this)">تأیید</button><button class="btn alt" data-onclick="event.preventDefault();ansReq('${esc(n.actor.username)}','decline',this)">حذف</button></span>`:n.type==='follow'?`<button class="btn ${n.followed?'alt':''}" style="padding:5px 12px" data-onclick="event.preventDefault();followFrom('${esc(n.actor.username)}',this)">${n.followed?'دنبال می‌کنی':'دنبال کن'}</button>`:'')}</a>`).join('')}</div>`:'<div class="empty">هنوز اعلانی نداری.<br>وقتی کسی پست یا نظرت را بپسندد، اینجا می‌بینی.</div>'}`,'');
  post('/activity/seen').then(pollUnread).catch(()=>{})}
async function tagView(t){const d=await api('/tag/'+encodeURIComponent(t));shell(`<h2 style="padding:14px 4px 0">#${esc(d.tag)}</h2><p class="mute" style="padding:0 4px">${fa(d.count)} پست</p>${grid(d.posts)||'<div class="empty">پستی با این هشتگ نیست.</div>'}`,'explore')}
async function showPeople(name,kind){try{const l=await api('/user/'+encodeURIComponent(name)+'/'+kind);sheetEl().innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div><h3>${kind==='followers'?'دنبال‌کننده‌ها':'دنبال‌شده‌ها'}</h3><div class="list">${l.map(u=>`<div class="urow" style="border:0;padding:8px 0"><a href="#/u/${esc(u.username)}" data-onclick="closeCm()" style="display:flex;gap:12px;align-items:center;flex:1">${av(u)}<div><b>${esc(u.username)}</b><small>${esc(u.name)}</small></div></a>${u.me?'':`<button class="btn ${u.followed?'alt':''}" style="padding:5px 14px" data-onclick="followFrom('${esc(u.username)}',this)">${u.followed?'دنبال می‌کنی':'دنبال کن'}</button>`}</div>`).join('')||'<p class="mute">خالی است.</p>'}</div></div>`}catch(e){toast(e.message)}}
let PP2=[];function ptab(b,i){document.querySelectorAll('.ptabs button').forEach(x=>x.classList.toggle('on',x===b));$('#pg').innerHTML=grid(i?PP2.filter(p=>p.kind==='video'):PP2)||'<div class="empty">چیزی نیست.</div>';lazyV()}
/* ---- explore / profile / etc ---- */
async function exploreView(){const ps=await api('/explore');window.EXP=ps;shell(`<input class="search" id="sq" placeholder="جستجوی آدم‌ها و #هشتگ…" data-oninput="srch(this.value)"><div id="res">${grid(ps)||'<div class="empty">هنوز پستی منتشر نشده.</div>'}</div>`,'explore')}
let sT;function srch(v){clearTimeout(sT);sT=setTimeout(async()=>{const r=$('#res');if(!v.trim()){r.innerHTML=grid(EXP)||'';lazyV();return}try{const isTag=v.trim().startsWith('#'),[us,tg]=await Promise.all([isTag?[]:api('/search?q='+encodeURIComponent(v)),api('/search/tags?q='+encodeURIComponent(v.replace(/^#/,'')))]);
const tags=tg.map(x=>`<a class="urow" href="#/tag/${encodeURIComponent(x.tag)}"><span class="av ph">#</span><div><b>#${esc(x.tag)}</b><small>${fa(x.count)} پست</small></div></a>`).join(''),users=us.map(u=>`<a class="urow" href="#/u/${esc(u.username)}">${av(u)}<div><b>${esc(u.username)}</b><small>${esc(u.name)}</small></div></a>`).join('');
r.innerHTML=tags||users?`<div class="card" style="margin-top:12px">${tags}${users}</div>`:'<div class="empty">چیزی پیدا نشد.</div>'}catch(e){toast(e.message)}},250)}
let PS=null;
function openProfileStory(){if(PS){ST=[PS];openStory(0)}}
let PU=null;
async function profileView(name){const u=await api('/user/'+encodeURIComponent(name)),un=esc(u.username);PS=u.story;PU=u;
  const hls=u.highlights.length?`<div class="hls">${u.highlights.map(h=>`<div class="bub" data-onclick="openHighlight(${h.id})"><span class="ring seen">${h.cover?(h.cover.kind==='video'?'<span class="av ph">▶</span>':`<img class="av" src="/media/${esc(h.cover.file)}" alt="">`):'<span class="av ph">★</span>'}</span>${esc(h.title)}</div>`).join('')}</div>`:'';
  const actions=u.is_me?`<a class="btn alt block" style="text-align:center" href="#/edit">ویرایش پروفایل</a><a class="btn alt block" style="text-align:center" href="#/saved">ذخیره‌ها</a>`:u.blocked_by_me?`<button class="btn alt block" data-onclick="blockUser('${un}')">رفع بلاک</button>`:`<button class="btn ${u.followed||u.requested?'alt':''} block" data-onclick="follow('${un}')">${u.followed?'دنبال می‌کنی':u.requested?'درخواست شد':'دنبال کن'}</button><button class="btn alt block" data-onclick="wdChat('${un}')">پیام</button><button class="btn alt" aria-label="گزینه‌ها" data-onclick="userMenu('${un}')">⋯</button>`;
  const body=u.locked?`<div class="empty">🔒 این حساب خصوصی است.<br>برای دیدن پست‌ها درخواست دنبال کردن بفرست.</div>`:u.blocked_by_me?'<div class="empty">این کاربر را بلاک کرده‌ای.</div>':`<div class="ptabs"><button class="on" data-onclick="ptab(this,0)">پست‌ها</button><button data-onclick="ptab(this,1)">ریلز</button></div><div id="pg">${grid(u.posts)||'<div class="empty">هنوز پستی نیست.</div>'}</div>`;
  shell(`<div class="prof">${u.story?`<span class="ring big ${u.story.seen?'seen':''} ${u.story.close?'close':''}" data-onclick="openProfileStory()">${av(u,'lg')}</span>`:av(u,'lg')}<div><h2 style="font-size:18px">${un}${u.private?' 🔒':''}</h2><div class="stats"><div><b>${u.locked?'؟':fa(u.posts.length)}</b><span>پست</span></div><div class="clk" data-onclick="showPeople('${un}','followers')"><b>${fa(u.followers)}</b><span>دنبال‌کننده</span></div><div class="clk" data-onclick="showPeople('${un}','following')"><b>${fa(u.following)}</b><span>دنبال‌شده</span></div></div></div></div><div style="padding:4px 4px 10px"><b>${esc(u.name)}</b><p style="white-space:pre-wrap">${rich(u.bio)}</p></div>${hls}<div style="display:flex;gap:8px">${actions}</div>${body}`,u.is_me?'me':'');PP2=u.posts}
function userMenu(un){const u=PU;actionSheet('@'+un,[{label:u.muted?'لغو میوت':'میوت کردن (پست‌ها در فید نمی‌آیند)',fn:()=>muteUser(un)},{label:'بلاک کردن',danger:1,fn:()=>blockUser(un)},{label:'گزارش کاربر',danger:1,fn:()=>reportSheet('user',u.id)},{label:'کپی لینک پروفایل',fn:()=>copyLink(location.origin+'/u/'+un)}])}
async function blockUser(un){if(!PU?.blocked_by_me&&!confirm('این کاربر بلاک شود؟ نه پست‌هایت را می‌بیند نه می‌تواند پیام بدهد.'))return;try{const r=await post('/user/'+un+'/block');toast(r.blocked?'بلاک شد':'رفع بلاک شد');route()}catch(e){toast(e.message)}}
async function muteUser(un){try{const r=await post('/user/'+un+'/mute');toast(r.muted?'میوت شد':'میوت برداشته شد');route()}catch(e){toast(e.message)}}
async function follow(n){try{await post('/user/'+n+'/follow');route()}catch(e){toast(e.message)}}
async function postView(id){const p=await api('/post/'+id);shell(postHtml(p,true),'')}
async function savedView(cid){const [ps,cs]=await Promise.all([cid?api('/collections/'+cid):api('/saved'),api('/collections')]),list=cid?ps.posts:ps;
  shell(`<h2 style="padding:14px 4px 0">${cid?esc(ps.name):'ذخیره‌شده‌ها'}</h2><div class="chips"><a class="${cid?'':'on'}" href="#/saved">همه</a>${cs.map(c=>`<a class="${cid==c.id?'on':''}" href="#/saved/${c.id}">${esc(c.name)} <small>${fa(c.count)}</small></a>`).join('')}<button data-onclick="collNew(0)">+ کالکشن</button></div>${cid?`<button class="lnk" data-onclick="delColl(${cid})">حذف این کالکشن</button>`:''}${grid(list)||'<div class="empty">اینجا خالی است.</div>'}`,'');lazyV()}
async function delColl(id){if(!confirm('کالکشن حذف شود؟ (پست‌ها در ذخیره‌ها می‌مانند)'))return;try{await api('/collections/'+id,{method:'DELETE'});location.hash='#/saved'}catch(e){toast(e.message)}}
function newView(){shell(`<div class="card form"><h2>پست تازه</h2><label>عکس یا ویدیو (چند عکس = کاروسل؛ ویدیوها در ریلز هم می‌آیند)<input type="file" id="pf" accept="image/*,video/*" multiple data-onchange="prev(this)"></label><div id="pvw"></div><label>توضیح<textarea id="pc" maxlength="2200" placeholder="چه خبر؟"></textarea></label><button class="btn block" id="pb" data-onclick="sendPost()">منتشر کن</button></div>`,'new')}
let PP=null;
function genPoster(f){return new Promise(res=>{const v=document.createElement('video'),u=URL.createObjectURL(f);let fin=false;const done=b=>{if(fin)return;fin=true;URL.revokeObjectURL(u);res(b)};v.muted=true;v.playsInline=true;v.preload='auto';v.src=u;v.onerror=()=>done(null);v.onloadeddata=()=>{v.currentTime=Math.min(.5,(v.duration||1)/2)};v.onseeked=()=>{try{const w=Math.min(480,v.videoWidth),h=Math.round(v.videoHeight*w/v.videoWidth),c=document.createElement('canvas');c.width=w;c.height=h;c.getContext('2d').drawImage(v,0,0,w,h);c.toBlob(done,'image/jpeg',.72)}catch{done(null)}};setTimeout(()=>done(null),8000)})}
function prev(i){let fs=[...i.files];if(fs.length>1&&fs.some(f=>f.type.startsWith('video')))fs=[fs[0]];window.PF=fs.slice(0,10);const f=PF[0];PP=f&&f.type.startsWith('video')?genPoster(f):null;$('#pvw').innerHTML=!f?'':f.type.startsWith('video')?`<video class="pv" controls src="${URL.createObjectURL(f)}"></video>`:PF.length>1?`<div class="pgrid">${PF.map(x=>`<img src="${URL.createObjectURL(x)}">`).join('')}</div><p class="mute">${fa(PF.length)} عکس (کاروسل)</p>`:`<img class="pv" src="${URL.createObjectURL(f)}">`}
async function sendPost(){const fs=window.PF&&window.PF.length?window.PF:[...$('#pf').files],f=fs[0];if(!f)return toast('یک فایل انتخاب کن');const fd=new FormData();fs.forEach(x=>fd.append('file',x));fd.append('caption',$('#pc').value);{const pb=await PP;if(pb)fd.append('poster',pb,'poster.jpg')}$('#pb').disabled=true;$('#pb').textContent='در حال ارسال…';try{const r=await upl('/posts',fd);location.hash=f.type.startsWith('video')?'#/reels':'#/'}catch(e){toast(e.message);$('#pb').disabled=false;$('#pb').textContent='منتشر کن'}}
async function setPrivate(on){try{await post('/me/privacy',{private:on});me.private=on;toast(on?'حساب خصوصی شد':'حساب عمومی شد')}catch(e){toast(e.message)}}
async function requestsSheet(){try{const l=await api('/requests');sheetEl().innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div><h3>درخواست‌های دنبال کردن</h3><div class="list">${l.map(u=>`<div class="urow" style="border:0;padding:8px 0">${av(u)}<div style="flex:1"><b>${esc(u.username)}</b><small>${esc(u.name)}</small></div><span class="rqb"><button class="btn" data-onclick="ansReq('${esc(u.username)}','accept',this)">تأیید</button><button class="btn alt" data-onclick="ansReq('${esc(u.username)}','decline',this)">حذف</button></span></div>`).join('')||'<p class="mute">درخواستی نیست.</p>'}</div></div>`}catch(e){toast(e.message)}}
async function closeFriendsSheet(){try{const l=await api('/close-friends');window.CFL=l;sheetEl().innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div><h3>دوستان نزدیک 💚</h3><div class="list">${l.map(u=>`<label class="urow" style="border:0;padding:8px 0"><input type="checkbox" style="width:auto" data-id="${u.id}" ${u.close?'checked':''}>${av(u)}<div><b>${esc(u.username)}</b></div></label>`).join('')||'<p class="mute">اول چند نفر را دنبال کن.</p>'}</div><div class="send"><button class="btn" style="flex:1" data-onclick="saveCF()">ذخیره</button></div></div>`}catch(e){toast(e.message)}}
async function saveCF(){const ids=[...document.querySelectorAll('#sheet input[data-id]:checked')].map(x=>+x.dataset.id);try{await post('/close-friends',{ids});closeCm();toast('ذخیره شد')}catch(e){toast(e.message)}}
async function blockedSheet(){try{const d=await api('/blocked'),row=(u,k)=>`<div class="urow" style="border:0;padding:8px 0">${av(u)}<div style="flex:1"><b>${esc(u.username)}</b></div><button class="btn alt" data-onclick="${k}User('${esc(u.username)}');closeCm()">${k==='block'?'رفع بلاک':'لغو میوت'}</button></div>`;sheetEl().innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan"><div class="grab"></div><h3>بلاک‌شده‌ها و میوت‌ها</h3><div class="list">${d.blocked.map(u=>row(u,'block')).join('')}${d.muted.map(u=>row(u,'mute')).join('')||''}${!d.blocked.length&&!d.muted.length?'<p class="mute">خالی است.</p>':''}</div></div>`}catch(e){toast(e.message)}}
async function editView(){const qs=me.sso_only?[]:await questions();shell(`<div class="card form"><h2>ویرایش پروفایل</h2><div style="display:flex;align-items:center;gap:12px">${av(me,'lg')}<label style="flex:1">عکس پروفایل<input type="file" id="ea" accept="image/*"></label></div><label>نام<input id="en" maxlength="40" value="${esc(me.name)}"></label><label>بیو<textarea id="eb" maxlength="300">${esc(me.bio)}</textarea></label><button class="btn block" data-onclick="saveEdit()">ذخیره</button><button class="btn alt block" data-onclick="logout()">خروج از حساب</button></div>${me.sso_only?'':`<div class="card form"><h2>امنیت حساب</h2><label>رمز فعلی<input id="cp" type="password" autocomplete="current-password" dir="ltr"></label><label>رمز جدید<input id="np" type="password" autocomplete="new-password" dir="ltr"></label><button class="btn alt block" data-onclick="changePw()">تغییر رمز</button><label>سوال امنیتی ${me.has_sec?'(ثبت شده؛ برای تغییر دوباره بنویس)':'(ثبت نشده)'}<select id="sq2">${qs.map((x,i)=>`<option value="${i}">${esc(x)}</option>`).join('')}</select></label><label>جواب<input id="sa2" maxlength="60" autocomplete="off"></label><button class="btn alt block" data-onclick="saveSec()">ذخیره سوال امنیتی</button></div>`}<div class="card form"><h2>کیفیت و مصرف اینترنت</h2><label>کیفیت ویدیو و عکس<select data-onchange="setQP(this.value)"><option value="auto" ${QP==='auto'?'selected':''}>خودکار (متناسب با سرعت اینترنت)</option><option value="low" ${QP==='low'?'selected':''}>کم؛ صرفه‌جویی در اینترنت</option><option value="high" ${QP==='high'?'selected':''}>بالا</option></select></label><p class="mute" style="margin:0">سرعت اندازه‌گیری‌شده: حدود ${fa(Math.round(BW/100)/10)} مگابیت بر ثانیه</p></div><div class="card form"><h2>حریم خصوصی و ظاهر</h2><label style="flex-direction:row;display:flex;gap:10px;align-items:center;color:var(--ink)"><input type="checkbox" style="width:auto" ${me.private?'checked':''} data-onchange="setPrivate(this.checked)">حساب خصوصی (فقط دنبال‌کننده‌های تأییدشده پست‌هایم را ببینند)</label><button class="btn alt block" data-onclick="requestsSheet()">درخواست‌های دنبال کردن</button><button class="btn alt block" data-onclick="closeFriendsSheet()">دوستان نزدیک (استوری)</button><button class="btn alt block" data-onclick="blockedSheet()">بلاک‌شده‌ها و میوت‌ها</button><label>تم<select data-onchange="setTheme(this.value)"><option value="dark" ${THEME==='dark'?'selected':''}>تیره</option><option value="light" ${THEME==='light'?'selected':''}>روشن</option><option value="system" ${THEME==='system'?'selected':''}>مطابق گوشی</option></select></label><button class="btn alt block" data-onclick="installApp()">نصب قاب روی گوشی/کامپیوتر</button></div>`,'me')}
async function saveEdit(){const fd=new FormData();fd.append('name',$('#en').value);fd.append('bio',$('#eb').value);const f=$('#ea').files[0];if(f)fd.append('avatar',f);try{me=await upl('/me/update',fd);location.hash='#/u/'+me.username}catch(e){toast(e.message)}}
async function logout(){await post('/logout');me=null;location.hash='#/login';route()}


/* ---- share sheet: picking a friend opens the real (Windroida) chat with them, with the post link ready to send ---- */
let SH={id:0,list:[]};
async function openShare(id){SH={id,list:[]};let s=$('#sheet');if(!s){s=document.createElement('div');s.id='sheet';document.body.appendChild(s)}
s.innerHTML=`<div class="bk" data-onclick="closeCm()"></div><div class="pan sh"><div class="grab"></div><div class="shs"><input id="shq" placeholder="جستجو…" data-oninput="shSearch(this.value)"></div><div class="shg" id="shg"></div><div id="shb"></div></div>`;shBar();await shLoad('')}
async function shLoad(v){try{SH.list=await api('/share/suggest?q='+encodeURIComponent(v));shGrid()}catch(e){toast(e.message)}}
let shT;function shSearch(v){clearTimeout(shT);shT=setTimeout(()=>shLoad(v),220)}
function shGrid(){$('#shg').innerHTML=SH.list.length?SH.list.map(u=>`<button class="shu" data-onclick="shToFriend('${esc(u.username)}')"><span class="shav">${av(u)}</span><span class="shn">${esc(u.name||u.username)}</span></button>`).join(''):'<div class="empty" style="grid-column:1/-1">کسی پیدا نشد.</div>'}
function shBar(){const url=encodeURIComponent(location.origin+'/p/'+SH.id);
$('#shb').innerHTML=`<div class="shact"><button data-onclick="shStory()">${ic('story')}<span>به استوری</span></button><button data-onclick="shCopy()">${ic('link')}<span>کپی لینک</span></button><button data-onclick="shNative()">${ic('share')}<span>اشتراک‌گذاری</span></button><a class="wa" target="_blank" rel="noopener" href="https://wa.me/?text=${url}">${ic('chat')}<span>واتساپ</span></a><a class="tg" target="_blank" rel="noopener" href="https://t.me/share/url?url=${url}">${ic('share')}<span>تلگرام</span></a></div>`}
async function shToFriend(un){const u=SH.list.find(x=>x.username===un),id=SH.id;
  if(!u)return;
  /* the post link is sent for real into the friend's Windroida chat (server-to-server); only if that is impossible
     (fb) do we fall back to the old way: open their Windroida chat with the link ready in the composer */
  try{await post('/share/send',{post_id:id,to:u.id,origin:location.origin});closeCm();toast('برای '+(u.name||u.username)+' ارسال شد ✓')}
  catch(e){if(e.fb){wdChat(un,location.origin+'/p/'+id);closeCm()}else toast(e.message)}}
async function shStory(){try{await post('/posts/'+SH.id+'/story');closeCm();toast('به استوری اضافه شد')}catch(e){toast(e.message)}}
async function shCopy(){try{await navigator.clipboard.writeText(location.origin+'/p/'+SH.id);closeCm();toast('لینک کپی شد')}catch{toast('کپی نشد')}}
async function shNative(){try{await navigator.share({url:location.origin+'/p/'+SH.id})}catch{toast('این مرورگر اشتراک‌گذاری را ندارد')}}

/* ---- messaging: no DMs inside Ghab anymore — "message" always opens the real chat on Windroida (same account, SSO) ---- */
async function pollUnread(){if(!me||document.hidden)return;try{const r=await api('/unread');const b=$('#actb');if(b){b.textContent=r.activity>9?'+۹':fa(r.activity);b.style.display=r.activity?'grid':'none'}}catch{}}
/** opens the Windroida chat with this username (same device/browser or, inside the native app, the same app — it's
    usually already signed in); optional prefilled text (e.g. a post link) is put in the composer there, never sent
    automatically. A same-tab redirect (not window.open) on purpose: the embedded WebView the native app uses for
    Ghab has no popup/multi-window support, so a new-tab open would silently do nothing there. */
function wdChat(username,text){
  const port=app.dataset.wdport||8081,url=location.protocol+'//'+location.hostname+':'+port+'/#dm='+encodeURIComponent(username)+(text?'&t='+encodeURIComponent(text):'');
  location.href=url}

async function route(){$('#ov')?.remove();SV=null;closeCm();ROBS.forEach(o=>o.disconnect());ROBS=[];vload.disconnect();vdrop.disconnect();document.querySelectorAll('video[data-obs]').forEach(v=>delete v.dataset.obs);if(ACT){const r=ACT.closest('.reel');if(r)sendWatch(r)}ACT=null;document.body.classList.remove('ct');const [,a,b]=(location.hash||'#/').split('/');document.body.classList.toggle('rl',!!me&&a==='reels');
if(!me){const h=location.hash;if(/^#\/(p|u)\//.test(h))NEXT=h;return authView(h==='#/register'?'register':h==='#/forgot'?'forgot':'login')}
if(!me.has_sec&&!window.secShown){window.secShown=1;setTimeout(secPrompt,500)}
try{
if(a==='login'||a==='register'){location.hash='#/';return}
if(a==='reels')await reelsView();else if(a==='explore')await exploreView();else if(a==='u')await profileView(decodeURIComponent(b));else if(a==='p')await postView(b);else if(a==='new')newView();else if(a==='edit')await editView();else if(a==='saved')await savedView(b?+b:0);else if(a==='activity')await activityView();else if(a==='tag')await tagView(decodeURIComponent(b));else await feedView()
}catch(e){shell(`<div class="empty">${esc(e.message)}</div>`)}}
addEventListener('hashchange',route);
document.addEventListener('visibilitychange',()=>{if(document.hidden){if(ACT){const r=ACT.closest('.reel');if(r)sendWatch(r)}document.querySelectorAll('video').forEach(v=>v.pause())}else{if(ACT?.isConnected&&!ACT.closest('.reel')?.classList.contains('paused'))ACT.play().catch(()=>{});document.querySelectorAll('video[data-auto]').forEach(v=>{const r=v.getBoundingClientRect();if(r.top>=0&&r.bottom<=innerHeight+r.height*.4&&r.bottom>r.height*.6)v.play().catch(()=>{})})}});setInterval(pollUnread,15000);
api('/me').then(u=>me=u).catch(()=>me=null).finally(route);

// داخل اپ اندروید: اگر ویدیو توی WebView پخش نشد، با لمس در پخش‌کنندهٔ بومی باز می‌شود
document.addEventListener('error',e=>{const v=e.target;if(!v||v.tagName!=='VIDEO'||!(window.WD&&WD.playVideo)||v.dataset.nat)return;v.dataset.nat=1;const src=v.currentSrc||v.dataset.src||v.getAttribute('src');if(!src)return;(v.parentElement||v).addEventListener('click',()=>{try{WD.playVideo(new URL(src,location.href).pathname,'')}catch{}})},true);
