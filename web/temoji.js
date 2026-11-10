/* Telegram's animated emoji (the "telemoji" pack, Lottie/TGS files in /emoji/).
   - a message made only of 1-3 emoji is drawn as big animated emoji: it plays once when it appears, tap = play again
   - the emoji picker lists every emoji of the pack
   Needs the small lottie-web player (/static/lottie_light.js, downloaded once by the server). If anything is missing the
   plain emoji / old animated stickers are shown, nothing breaks. */
(function(){
const KEY=s=>s.replace(/\uFE0F/g,'');
let MAP=null,libState=0;                                   // libState: 0 not asked, 1 loading, 2 ready, -1 failed
const waiters=[];
const CLUSTER=/\p{Extended_Pictographic}(?:\uFE0F|\u200D\p{Extended_Pictographic}|[\u{1F3FB}-\u{1F3FF}])*|[0-9#*]\uFE0F?\u20E3/gu;
function clusters(t){
  if(window.Intl&&Intl.Segmenter){const out=[];for(const g of new Intl.Segmenter('en',{granularity:'grapheme'}).segment(t))out.push(g.segment);return out}
  return t.match(CLUSTER)||[]}
function loadLib(){
  if(window.lottie){libState=2;return}
  if(libState)return;libState=1;
  const s=document.createElement('script');s.src='/static/lottie_light.js';
  s.onload=()=>{libState=window.lottie?2:-1;if(libState===2)waiters.splice(0).forEach(f=>f())};
  s.onerror=()=>{libState=-1};document.head.append(s)}
fetch('/emoji/map.json').then(r=>r.ok?r.json():null).then(j=>{if(j&&typeof j==='object'){MAP=j;loadLib();fillPicker()}}).catch(()=>{});

const cache=new Map();
function animData(name){
  if(!cache.has(name))cache.set(name,fetch('/emoji/'+name+'.tgs').then(r=>{if(!r.ok)throw 0;return r.arrayBuffer()})
    .then(b=>new Response(new Blob([b]).stream().pipeThrough(new DecompressionStream('gzip'))).text()).then(JSON.parse)
    .catch(e=>{cache.delete(name);throw e}));
  return cache.get(name)}

const io='IntersectionObserver' in window?new IntersectionObserver(es=>{for(const e of es){const n=e.target;
  if(e.isIntersecting){if(!n._a)start(n);else if(n._a.isPaused&&!n._done)n._a.play()}else if(n._a&&!n._a.isPaused)n._a.pause()}},{threshold:.3}):null;
function start(n){
  if(n._busy)return;n._busy=true;
  animData(n.dataset.n).then(d=>{
    if(!n.isConnected&&!n._a){n._busy=false;return}
    n.textContent='';
    const a=window.lottie.loadAnimation({container:n,renderer:'svg',loop:false,autoplay:true,animationData:d,rendererSettings:{progressiveLoad:true,preserveAspectRatio:'xMidYMid meet'}});
    n._a=a;n._done=false;a.addEventListener('complete',()=>{n._done=true})
  }).catch(()=>{n._busy=false})}
function replay(n){if(n._a){n._done=false;n._a.goToAndPlay(0,true)}}
/* tap on a big emoji: a burst of the same emoji flies up over the whole screen (Telegram's emoji effect) */
function burst(n){
  if(matchMedia('(prefers-reduced-motion:reduce)').matches)return;
  const ch=n.dataset.c||'',r=n.getBoundingClientRect();if(!ch||!r.width)return;
  const ov=document.createElement('div');ov.className='teburst';document.body.append(ov);
  const W=innerWidth,cx=r.left+r.width/2,cy=r.top+r.height/2,N=16;
  for(let i=0;i<N;i++){const e=document.createElement('i'),sz=22+Math.random()*34,dx=(Math.random()-.5)*W*.9,dy=-(120+Math.random()*Math.min(420,cy));
    e.textContent=ch;e.style.cssText='left:'+(cx-sz/2)+'px;top:'+(cy-sz/2)+'px;font-size:'+sz+'px;--x:'+dx+'px;--y:'+dy+'px;--s:'+(.8+Math.random()*.9)+';--r:'+((Math.random()-.5)*70)+'deg;--d:'+(1100+Math.random()*900)+'ms;animation-delay:'+Math.round(Math.random()*180)+'ms';ov.append(e)}
  setTimeout(()=>ov.remove(),2400)}

/* can this text be drawn animated right now? (1-3 emoji, all in the pack, player ready) */
function parts(text){
  if(!MAP||libState<1||libState===-1)return null;
  const t=text.trim();if(!t||t.length>40)return null;
  const cs=clusters(t);if(cs.length<1||cs.length>3||cs.join('')!==t.replace(/\s+/g,'')&&cs.join('')!==t)return null;
  const names=cs.map(c=>MAP[KEY(c)]);return names.every(Boolean)?{cs,names}:null}
function has(text){return !!parts(text)&&(libState===2||!!window.lottie)}
function el(text){
  const p=parts(text);if(!p)return null;
  const size=p.cs.length===1?128:p.cs.length===2?96:76;
  const row=document.createElement('div');row.className='teemo';row.title='بزن تا دوباره حرکت کنه';
  p.cs.forEach((c,i)=>{
    const n=document.createElement('div');n.className='te1';n.dataset.n=p.names[i];n.style.width=n.style.height=size+'px';
    n.textContent=c;n.style.fontSize=Math.round(size*.7)+'px';           // plain emoji until the animation is loaded
    n.dataset.c=c;n.onclick=e=>{e.stopPropagation();replay(n);burst(n)};row.append(n);
    if(io)io.observe(n);else start(n)});
  return row}

/* the picker: add every pack emoji that is not there yet */
let pickerDone=false;
function fillPicker(){
  const emo=document.getElementById('emoji'),add=window.WD_addEmoji;
  if(pickerDone||!MAP||!emo||!add)return;pickerDone=true;
  const have=new Set([...emo.children].map(b=>KEY(b.textContent)));
  Object.keys(MAP).filter(k=>!/^[0-9#*]/.test(k)&&!have.has(k)).sort((a,b)=>a.codePointAt(0)-b.codePointAt(0)).forEach(k=>add(k))}
window.TE={has,el,clusters,fillPicker};
document.addEventListener('DOMContentLoaded',()=>{setTimeout(fillPicker,300);setTimeout(fillPicker,2000)});
})();
