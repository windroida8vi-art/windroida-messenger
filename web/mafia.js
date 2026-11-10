'use strict';
/* Mafia inside a watch-room. The SERVER is the narrator and the only judge; this file just draws the view the server sends to ME
   (it never sees anybody else's role) and sends my choices (night target, "ready", vote). */
const MF={v:undefined,at:0,draft:'',timer:null,el:null};
const MFROLE={mafia:'مافیا 😈',doctor:'دکتر 🩺',detective:'کارآگاه 🕵️',citizen:'شهروند 🙂'};
const MFHELP={
  mafia:'شب‌ها با هم‌تیمی‌هات یه نفر رو انتخاب کن تا کشته بشه (اگه نظرتون یکی نباشه کسی کشته نمی‌شه). روز خودت رو شهروند نشون بده.',
  doctor:'هر شب یه نفر رو نجات بده. خودت رو فقط یک بار می‌تونی نجات بدی.',
  detective:'هر شب از یه نفر بپرس مافیاست یا نه؛ جواب فقط به خودت می‌رسه.',
  citizen:'شب‌ها می‌خوابی. روز با بقیه بحث کن و مافیا رو پیدا کن.'};
const MFPHASE={lobby:'منتظر بازیکن‌ها',night:'🌙 شب',day:'☀️ روز؛ بحث',vote:'🗳 رأی‌گیری',over:'پایان بازی'};
const mfName=(v,id)=>{const p=v.players.find(x=>x.id===id);return p?p.name:'؟'};
const mfLeft=()=>{const v=MF.v;if(!v||!v.left)return 0;return Math.max(0,v.left-Math.floor((Date.now()-MF.at)/1000))};
async function mfLoad(){
  if(!R.on)return;
  try{const r=await call('room_mafia',{room:R.id,a:'get'});MF.v=r.mafia;MF.at=Date.now()}catch{}
  mfRedraw()}
function mfAct(a,extra){
  return call('room_mafia',{room:R.id,a,...(extra||{})}).then(r=>{MF.v=r.mafia;MF.at=Date.now();mfRedraw();return r}).catch(e=>{toast(e.message)})}
function mfMeAlive(v){return !!(v&&v.me&&v.me.alive)}
/* tell the player when something happened while he is on another tab */
function mfNotify(old,nw){
  if(!nw||!R.on)return;
  const was=old&&old.phase,now=nw.phase;
  if(was===now&&old&&old.round===nw.round)return;
  const inGame=!!nw.me;
  if(now==='night'&&(was==='lobby'||!old)&&inGame){R.tab='games';rDrawTabs();rDrawPane();if(R.min){R.min=false;rShow()}toast('🎭 بازی مافیا شروع شد؛ نقش تو: '+MFROLE[nw.me.role],false);return}
  if(R.tab!=='games'&&inGame&&nw.me.alive){
    if(now==='night')toast('🌙 شب شد',false);else if(now==='day')toast('☀️ صبح شد؛ بحث شروع شد',false);
    else if(now==='vote')toast('🗳 وقت رأی‌گیریه',false);else if(now==='over')toast(nw.winner==='citizens'?'🎉 شهروندها بردن':'😈 مافیا برد',false)}
  try{if(typeof sfx==='function'&&R.tab==='games')sfx('recv')}catch{}}
function mfTick(){
  const v=MF.v;if(!v||!MF.el)return;const c=MF.el.querySelector('.mfclock');if(c)c.textContent=v.left?fa(mfLeft())+' ثانیه':''}
function mfRedraw(){
  if(!R.on||R.tab!=='games'||!MF.el||!MF.el.isConnected)return;
  const act=document.activeElement,had=act&&act.id==='mfin',val=had?act.value:MF.draft;
  MF.el.replaceChildren(mfBody());
  const i=MF.el.querySelector('#mfin');if(i){i.value=val||'';if(had)try{i.focus({preventScroll:true})}catch{}}
  mfTick()}
function mfPlayers(v,pick,mine){
  const box=h('div',{class:'mfpl'});
  v.players.forEach(p=>{
    const votes=v.votes?Object.values(v.votes).filter(t=>t===p.id).length:0;
    const can=pick&&pick(p);
    const chosen=mine===p.id;
    const row=h(can?'button':'div',{class:'mfp'+(p.alive?'':' dead')+(chosen?' pick':'')+(can?' act':''),onclick:can?()=>pick(p,true):null},
      h('span',{class:'mfn'},(p.id===S.me.id?p.name+' (تو)':p.name)),
      h('small',{},p.alive?(p.role&&p.id===S.me.id?MFROLE[p.role]:p.role?MFROLE[p.role]:''):'✝ '+(p.role?MFROLE[p.role]:'')+(p.out==='voted'?' · با رأی':p.out==='shot'?' · کشته شد':p.out==='left'?' · رفت':'')),
      votes?h('i',{class:'bd'},fa(votes)):null);
    box.append(row)});
  return box}
function mfBody(){
  const v=MF.v,box=h('div',{class:'mf'});
  const head=h('div',{class:'rgt'},h('span',{class:'rgi'},'🕵️'),h('b',{},'مافیا'),h('small',{},v?'':'بازی گروهی؛ سرور راوی و داوره و نقش‌ها فقط به خود هر نفر نشون داده می‌شه.'));
  box.append(head);
  const nPeople=(R.members||[]).length;
  if(!v){
    box.append(h('div',{class:'hint'},'حداقل ۵ بازیکن لازمه (اتاق الان '+fa(nPeople)+' نفره). بقیه‌ی اتاق می‌تونن تماشا کنن.'),
      h('button',{class:'btn',onclick:()=>mfAct('open')},'🎭 ساخت بازی مافیا'));
    return box}
  const me=v.me,iAmHost=v.host===S.me.id||(R.st&&R.st.host===S.me.id);
  box.append(h('div',{class:'mfph'},h('b',{},MFPHASE[v.phase]+(v.round&&v.phase!=='lobby'&&v.phase!=='over'?' '+fa(v.round):'')),h('span',{class:'mfclock'},'')));
  if(v.phase==='lobby'){
    const inn=v.players.some(p=>p.id===S.me.id);
    box.append(h('div',{class:'muted',style:'font-size:13px'},'بازیکن‌ها ('+fa(v.players.length)+'/'+fa(v.max)+')؛ حداقل '+fa(v.min)+' نفر:'),mfPlayers(v));
    box.append(h('div',{class:'mfbtns'},
      inn?h('button',{class:'btn soft',onclick:()=>mfAct('leave')},'خروج از بازی'):h('button',{class:'btn',onclick:()=>mfAct('join')},'پیوستن به بازی'),
      v.host===S.me.id?h('button',{class:'btn',disabled:v.players.length<v.min,onclick:()=>mfAct('start')},'▶ شروع بازی'+(v.players.length<v.min?' (کمه)':'')):h('small',{},'سازنده: '+mfName(v,v.host)),
      (v.host===S.me.id||iAmHost)?h('button',{class:'btn soft',onclick:()=>{if(confirm('بازی بسته بشه؟'))mfAct('end')}},'بستن بازی'):null));
    return box}
  // --- running or finished
  if(v.phase==='over'){
    box.append(h('div',{class:'mfwin'},v.winner==='citizens'?'🎉 شهروندها بردن':'😈 مافیا برد'));
  }
  if(me){
    box.append(h('div',{class:'mfrole'},h('b',{},'نقش تو: '+MFROLE[me.role]),me.alive?null:h('small',{},'✝ تو از بازی بیرون رفتی؛ فقط تماشا کن'),v.phase!=='over'&&me.alive?h('small',{},MFHELP[me.role]):null));
  }else box.append(h('div',{class:'hint'},'تماشاچی هستی؛ نقش‌ها پنهانه تا آخر بازی.'));
  // night actions
  let pick=null,mine=null;
  if(v.phase==='night'&&mfMeAlive(v)){
    const r=me.role;
    if(r==='citizen')box.append(h('div',{class:'hint'},'🌙 شبه؛ همه خوابن. صبر کن تا صبح بشه…'));
    else{
      const q={mafia:'کی کشته بشه؟',doctor:'کی رو نجات بدی؟',detective:'از کی بپرسی مافیاست؟'}[r];
      box.append(h('div',{class:'mfq'},q));
      mine=me.night_target;
      pick=(p,click)=>{
        if(!p.alive)return false;
        if(r==='mafia'&&p.role==='mafia')return false;
        if(r==='detective'&&p.id===S.me.id)return false;
        if(r==='doctor'&&p.id===S.me.id&&me.can_self_save===false)return false;
        if(click)mfAct('night',{target:p.id});return true}}}
  if(v.phase==='vote'&&mfMeAlive(v)){
    box.append(h('div',{class:'mfq'},'به کی رأی می‌دی؟ (رأی‌ها برای همه پیداست)'));
    mine=v.votes&&v.votes[S.me.id];
    pick=(p,click)=>{if(!p.alive||p.id===S.me.id)return false;if(click)mfAct('vote',{target:p.id});return true}}
  box.append(mfPlayers(v,pick,mine));
  if(v.phase==='vote'&&mfMeAlive(v))box.append(h('button',{class:'btn soft',onclick:()=>mfAct('vote',{target:0})},(v.votes&&v.votes[S.me.id]===0?'✓ ':'')+'رأی نمی‌دم (ممتنع)'));
  if(v.phase==='night'&&mfMeAlive(v)&&me.role==='mafia'&&me.team_votes){
    const tv=Object.entries(me.team_votes).map(([u,t])=>mfName(v,+u)+' ← '+mfName(v,t));
    if(tv.length)box.append(h('small',{class:'muted'},'انتخاب تیم: '+tv.join(' · ')));
    const log=h('div',{class:'mfwh'});(me.team_chat||[]).forEach(m=>log.append(h('div',{},h('b',{},m.name+': '),h('span',{dir:'auto'},m.text))));
    box.append(h('small',{class:'muted'},'چت مخفی مافیا (فقط شما می‌بینید):'),log,
      h('div',{class:'mfsend'},h('input',{id:'mfin',maxlength:200,placeholder:'پیام به هم‌تیمی‌ها…',oninput:e=>{MF.draft=e.target.value},onkeydown:e=>{if(e.key==='Enter'){e.preventDefault();mfSay()}}}),h('button',{class:'btn',onclick:mfSay},'ارسال')))}
  if(v.phase==='day'&&mfMeAlive(v)){
    box.append(h('div',{class:'hint'},'☀️ همه‌ی زنده‌ها می‌تونن چت کنن و با میکروفون حرف بزنن.'),
      h('button',{class:'btn'+(me.ready?' soft':''),disabled:me.ready,onclick:()=>mfAct('ready')},me.ready?'✓ آماده‌ای ('+fa(v.ready)+'/'+fa(v.alive_n)+')':'آماده‌ی رأی‌گیری ('+fa(v.ready)+'/'+fa(v.alive_n)+')'))}
  if(me&&me.private&&me.private.length)box.append(h('div',{class:'mfpriv'},h('b',{},'🕵️ نتیجه‌ی استعلام‌ها (فقط برای تو):'),...me.private.map(t=>h('div',{},t))));
  const log=h('div',{class:'mflog'});v.log.slice().reverse().forEach(x=>log.append(h('div',{},h('small',{},fa(x.r)+'· '),x.text)));
  box.append(h('small',{class:'muted'},'گزارش بازی:'),log);
  const bt=h('div',{class:'mfbtns'});
  if(v.phase==='over')bt.append(h('button',{class:'btn',onclick:()=>mfAct('end')},'بستن و بازی جدید'));
  else{if(me&&me.alive)bt.append(h('button',{class:'btn soft',onclick:()=>{if(confirm('از بازی خارج بشی؟ دیگه نمی‌تونی برگردی.'))mfAct('leave')}},'ترک بازی'));
    if(v.host===S.me.id||iAmHost)bt.append(h('button',{class:'btn soft',onclick:()=>{if(confirm('بازی برای همه تموم بشه؟'))mfAct('end')}},'پایان اجباری بازی'))}
  box.append(bt);
  return box}
function mfSay(){const i=MF.el&&MF.el.querySelector('#mfin');if(!i)return;const t=i.value.trim();if(!t)return;MF.draft='';i.value='';mfAct('team',{text:t})}
/* called by the room's games tab: returns the persistent element */
function mfCard(){
  if(!MF.el||!MF.el.isConnected){MF.el=h('div',{class:'rgcard mfcard'})}
  MF.el.replaceChildren(mfBody());
  if(MF.v===undefined)mfLoad();
  clearInterval(MF.timer);MF.timer=setInterval(()=>{if(!R.on||R.tab!=='games'||!MF.el||!MF.el.isConnected){clearInterval(MF.timer);return}mfTick()},1000);
  setTimeout(mfTick,0);return MF.el}
const _onEventMf=onEvent;
onEvent=function(e){
  if(e.event==='room_mafia'){
    if(R.on&&e.room===R.id){const old=MF.v;MF.v=e.mafia;MF.at=Date.now();mfNotify(old,e.mafia);mfRedraw();rDrawTabs()}
    return}
  return _onEventMf(e)};

/* on a phone the video area would squeeze the game panel: while a mafia game exists and its tab is open, give the panel the room */
function mfLayout(){if(R.root)R.root.classList.toggle('mfon',!!((MF.v||(typeof MN!=='undefined'&&MN.v&&MN.v.phase!=='lobby'))&&R.tab==='games'))}
