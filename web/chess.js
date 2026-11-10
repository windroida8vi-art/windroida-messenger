/* Windroida chess — everything is local: vector pieces, sounds synthesized with WebAudio, no fonts/CDN/downloads, so it works
   when the international internet is cut. The SERVER judges every move; this file only draws the board and asks for moves. */
(()=>{
'use strict';
const P={
 p:'<circle cx="50" cy="30" r="12.5"/><path d="M38 46h24l-3 6c8 7 12 17 12 28H29c0-11 4-21 12-28z"/><rect x="27" y="78" width="46" height="9" rx="4.5"/>',
 r:'<path d="M29 18h11v8h6v-8h8v8h6v-8h11v22l-6 7v26l7 7H28l7-7V47l-6-7z"/><rect x="25" y="78" width="50" height="10" rx="5"/>',
 n:'<path d="M26 79c1-16 4-28 15-37-8 0-14 4-19 11l-8-6c5-11 14-20 28-26l3-10 8 8c18 3 31 18 31 40 0 8-1 14-1 20z"/><rect x="25" y="78" width="52" height="10" rx="5"/><circle class="eye" cx="55" cy="33" r="3.2"/>',
 b:'<circle cx="50" cy="13" r="5.5"/><path d="M50 19c15 9 22 22 15 35-2 4-4 7-4 11H39c0-4-2-7-4-11-7-13 0-26 15-35z"/><path d="M33 66h34l5 12H28z"/><rect x="25" y="78" width="50" height="10" rx="5"/><path class="eye" d="M44 36l12 12" fill="none"/>',
 q:'<circle cx="19" cy="30" r="5.5"/><circle cx="35" cy="20" r="5.5"/><circle cx="50" cy="16" r="5.5"/><circle cx="65" cy="20" r="5.5"/><circle cx="81" cy="30" r="5.5"/><path d="M22 36l14 24 8-30 6 28 6-28 8 30 14-24-6 42H28z"/><rect x="24" y="78" width="52" height="10" rx="5"/>',
 k:'<path d="M46 6h8v8h8v8h-8v7h-8v-7h-8v-8h8z"/><path d="M50 30c10 0 20 7 22 17 1 8-4 14-8 18l6 13H30l6-13c-4-4-9-10-8-18 2-10 12-17 22-17z"/><rect x="24" y="78" width="52" height="10" rx="5"/>'};
const NS='http://www.w3.org/2000/svg';
const FILES='abcdefgh';
const START_COUNT={p:8,n:2,b:2,r:2,q:1};
const VAL={p:1,n:3,b:3,r:5,q:9};
const REASON={checkmate:'مات',stalemate:'پات (بی‌حرکت)',insufficient:'مهره‌ی کافی نیست',fifty:'قانون ۵۰ حرکت',repetition:'تکرار سه‌باره',resign:'تسلیم',agreed:'توافق',maxlen:'طولانی‌شدن بازی'};
const THEMES={wood:'چوب',green:'سبز',blue:'آبی',night:'شب'};
const LS=(k,v)=>{try{if(v===undefined)return localStorage.getItem(k);localStorage.setItem(k,v)}catch{return null}};
const fa=s=>String(s).replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d]);

/* ---- shared drawing pieces (one hidden <svg> with gradients + a <symbol> per piece) ---- */
function ensureDefs(){
  if(document.getElementById('chess-defs'))return;
  const s=document.createElementNS(NS,'svg');s.id='chess-defs';s.setAttribute('width','0');s.setAttribute('height','0');s.style.cssText='position:absolute;width:0;height:0';
  s.innerHTML='<defs><linearGradient id="cgw" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fffdf4"/><stop offset=".55" stop-color="#eadfc2"/><stop offset="1" stop-color="#b9a980"/></linearGradient>'+
   '<linearGradient id="cgb" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6d7284"/><stop offset=".5" stop-color="#2b2d38"/><stop offset="1" stop-color="#0a0b10"/></linearGradient></defs>'+
   Object.entries(P).map(([k,v])=>`<symbol id="cs-${k}" viewBox="0 0 100 100">${v}</symbol>`).join('');
  document.body.prepend(s)}
const pieceSvg=(ch)=>{const white=ch===ch.toUpperCase();const s=document.createElementNS(NS,'svg');s.setAttribute('viewBox','0 0 100 100');s.setAttribute('class','cpv '+(white?'w':'b'));
  const u=document.createElementNS(NS,'use');u.setAttribute('href','#cs-'+ch.toLowerCase());s.append(u);return s};
const sqName=i=>FILES[i&7]+((i>>3)+1);
const sqIdx=n=>(+n[1]-1)*8+FILES.indexOf(n[0]);
function parseFen(fen){const m={};const rows=fen.split(' ')[0].split('/');
  for(let i=0;i<8;i++){let f=0;for(const c of rows[i]){if(/\d/.test(c))f+=+c;else{m[(7-i)*8+f]=c;f++}}}return m}

/* ---- sounds (all synthesized) ---- */
let AC=null;
const soundOn=()=>LS('chess_snd')!=='0';
function ctx(){try{AC=AC||new(window.AudioContext||window.webkitAudioContext)();AC.resume&&AC.resume();return AC}catch{return null}}
function tone(f,st,d,v=.12,type='sine',slide=0){const a=ctx();if(!a)return;const t=a.currentTime+st,o=a.createOscillator(),g=a.createGain();o.type=type;o.frequency.setValueAtTime(f,t);if(slide)o.frequency.exponentialRampToValueAtTime(Math.max(30,f+slide),t+d);
  g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(v,t+.008);g.gain.exponentialRampToValueAtTime(.0001,t+d);o.connect(g);g.connect(a.destination);o.start(t);o.stop(t+d+.03)}
function thud(st,d,v,cut){const a=ctx();if(!a)return;const n=Math.floor(a.sampleRate*d),b=a.createBuffer(1,n,a.sampleRate),x=b.getChannelData(0);
  for(let i=0;i<n;i++)x[i]=(Math.random()*2-1)*Math.pow(1-i/n,3);
  const s=a.createBufferSource();s.buffer=b;const f=a.createBiquadFilter();f.type='lowpass';f.frequency.value=cut;const g=a.createGain();g.gain.value=v;s.connect(f);f.connect(g);g.connect(a.destination);s.start(a.currentTime+st)}
function sound(k){if(!soundOn())return;
  if(k==='move'){thud(0,.07,.9,1400);tone(210,0,.07,.1,'triangle',-60)}
  else if(k==='capture'){thud(0,.12,1.3,2600);tone(150,0,.12,.16,'triangle',-70);tone(95,.02,.14,.1,'sine')}
  else if(k==='castle'){thud(0,.06,.8,1300);thud(.11,.07,.9,1500);tone(210,0,.06,.08,'triangle')}
  else if(k==='check'){thud(0,.09,1,2000);tone(620,.05,.12,.1);tone(830,.15,.2,.1)}
  else if(k==='promote'){[523,659,784,1047].forEach((f,i)=>tone(f,i*.07,.14,.1,'triangle'))}
  else if(k==='start'){tone(523,0,.15,.09);tone(784,.12,.25,.09)}
  else if(k==='win'){[523,659,784,1047,1319].forEach((f,i)=>tone(f,i*.11,.28,.11,'triangle'))}
  else if(k==='lose'){[392,330,262,196].forEach((f,i)=>tone(f,i*.16,.3,.1,'sawtooth',-8))}
  else if(k==='draw'){tone(440,0,.25,.09);tone(440,.25,.3,.09)}
  else if(k==='notify'){tone(880,0,.1,.08);tone(1175,.09,.16,.07)}
  else if(k==='illegal'){tone(140,0,.12,.1,'square')}}
const buzz=n=>{try{if(window.WD&&WD.vibrate){WD.vibrate(Array.isArray(n)?Math.min(400,n.filter((_,i)=>i%2===0).reduce((x,y)=>x+y,0)):n)}else navigator.vibrate&&navigator.vibrate(n)}catch{}};
const awake=on=>{try{window.WD&&WD.keepAwake&&WD.keepAwake(!!on)}catch{}};

/* ---- state ---- */
let G=null;                    // the open game: {id, view, flip, sel, els:Map(sqIdx->el), busy}
let UI=null;                   // DOM refs of the game screen
const me=()=>S.me.id;
const toastErr=e=>toast(e&&e.message||'خطا');

/* =====================================================================  chat integration */
function cardStatus(g){
  if(g.status==='invite')return g.inviter+' شما رو به شطرنج دعوت کرده';
  if(g.status==='cancelled')return 'دعوت لغو شد';
  if(g.status==='active')return `${g.white} (سفید) ⚔ ${g.black} (سیاه) · ${fa(g.plies)} حرکت`;
  const sc={'1-0':'۱–۰','0-1':'۰–۱','1/2-1/2':'½–½'}[g.result]||'';
  return `${g.white} ${sc} ${g.black} · ${REASON[g.reason]||''}`}
function miniBoard(fen){ensureDefs();const m=parseFen(fen||'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1');const d=h('div',{class:'cmini'});
  for(let r=7;r>=0;r--)for(let f=0;f<8;f++){const q=r*8+f,s=h('i',{class:(f+r)%2?'chl':'chd'});if(m[q])s.append(pieceSvg(m[q]));d.append(s)}return d}
function card(m){
  const g=m.game;const el=h('div',{class:'gcard','data-gcard':g.id});fillCard(el,m);return el}
function fillCard(el,m){
  const g=m.game,mine=m.sender_id===me();el.replaceChildren();
  el.append(h('div',{class:'gc-t'},h('span',{class:'gc-ic'},'♟'),h('b',{},'شطرنج')),
    miniBoard(g.fen),h('div',{class:'gc-s'},cardStatus(g)));
  const row=h('div',{class:'gc-a'});
  if(g.status==='invite'){
    if(!mine)row.append(h('button',{class:'btn',onclick:e=>{e.stopPropagation();acceptGame(g.id)}},'قبول و شروع'),h('button',{class:'btn soft',onclick:e=>{e.stopPropagation();cancelGame(g.id)}},'رد'));
    else row.append(h('button',{class:'btn soft',onclick:e=>{e.stopPropagation();cancelGame(g.id)}},'لغو دعوت'))}
  else if(g.status==='active')row.append(h('button',{class:'btn',onclick:e=>{e.stopPropagation();open(g.id)}},'باز کردن بازی'));
  else if(g.status==='finished')row.append(h('button',{class:'btn soft',onclick:e=>{e.stopPropagation();open(g.id)}},'مشاهده'));
  if(row.children.length)el.append(row)}
async function acceptGame(id){try{const r=await call('game_accept',{game_id:id});open(id,r.game);sound('start')}catch(e){toastErr(e)}}
async function cancelGame(id){try{await call('game_cancel',{game_id:id})}catch(e){toastErr(e)}}

/* composer button + chooser */
function installButton(){
  const w=document.querySelector('.cwrap');if(!w||document.getElementById('gamebtn'))return;
  const b=h('button',{class:'iconbtn',id:'gamebtn',title:'بازی',type:'button',style:'font-size:20px;line-height:1'},'🎮');
  b.onclick=chooser;const emo=document.getElementById('emo');w.insertBefore(b,emo)}
async function chooser(){
  if(!S.current)return;const chat=S.chats[S.current];
  if(chat&&chat.channel)return toast('تو کانال نمی‌شه بازی کرد');
  const ov=h('div',{class:'cov',onclick:e=>{if(e.target===ov)ov.remove()}});
  const listBox=h('div',{class:'cg-list'});
  const pick=c=>async()=>{ov.remove();try{const r=await call('game_invite',{chat_id:S.current,color:c});window.__live=Date.now();ingest(r.message);sound('notify');toast('دعوت فرستاده شد؛ منتظر حریف…',false)}catch(e){toastErr(e)}};
  const box=h('div',{class:'cdlg'},h('h3',{},'🎮 بازی'),h('div',{class:'cg-chess'},miniBoard(),h('div',{},h('b',{},'شطرنج'),h('small',{},'قواعد کامل · بدون نیاز به اینترنت جهانی'))),
    h('div',{class:'cg-col'},h('span',{},'رنگ تو:'),
      h('button',{class:'btn soft',onclick:pick('white')},'⚪ سفید'),h('button',{class:'btn soft',onclick:pick('black')},'⚫ سیاه'),h('button',{class:'btn',onclick:pick('random')},'🎲 تصادفی')),
    listBox,h('button',{class:'btn soft',onclick:()=>ov.remove()},'بستن'));
  ov.append(box);document.body.append(ov);
  try{const r=await call('game_list',{chat_id:S.current});
    if(r.games.length){listBox.append(h('small',{},'بازی‌های جاری این گفتگو:'));
      for(const g of r.games){const w=g.white?g.white.name:'—',b=g.black?g.black.name:'—';
        listBox.append(h('button',{class:'cg-row',onclick:()=>{ov.remove();open(g.id,g)}},g.status==='invite'?'⏳ دعوت: '+(g.inviter_id===me()?'منتظر حریف':'منتظر جواب تو'):`♟ ${w} ⚔ ${b}`,
          g.status==='active'&&g.you===g.turn?h('span',{class:'cg-turn'},'نوبت توئه'):null))}}}catch{}}

/* =====================================================================  game screen */
async function open(id,view){
  ensureDefs();
  if(!view){try{view=(await call('game_get',{game_id:id})).game}catch(e){return toastErr(e)}}
  if(view.status==='invite'&&view.inviter_id!==me()){if(!view.room||view.invitee_id===me())return acceptGame(id);return toast('دعوت هنوز جواب داده نشده',false)}
  if(G)close();
  G={id:view.id,view:null,flip:view.you==='b'||LS('chess_flip_'+view.id)==='1',sel:null,els:new Map(),busy:false,pend:null};
  buildUI();awake(true);render(view,false)}
function close(){awake(false);
  if(UI&&UI.root)UI.root.remove();UI=null;G=null;document.removeEventListener('keydown',onKey);
  const c=document.getElementById('cnote');if(c)c.remove()}
function onKey(e){if(e.key==='Escape')close()}
function theme(){return THEMES[LS('chess_theme')]?LS('chess_theme'):'wood'}

function buildUI(){
  const root=h('div',{class:'cscreen',id:'cscreen'});
  const top=h('div',{class:'ctop'},
    h('button',{class:'iconbtn',title:'بستن',onclick:close},'✕'),
    h('div',{class:'ctitle'},h('b',{},'♟ شطرنج'),h('small',{id:'cstat'},'')),
    h('button',{class:'iconbtn',title:'چرخاندن صفحه',onclick:()=>{G.flip=!G.flip;LS('chess_flip_'+G.id,G.flip?'1':'0');rebuildBoard();updateBars();drawHints()}},'⇅'),
    h('button',{class:'iconbtn',title:'تم صفحه',onclick:cycleTheme},'🎨'),
    h('button',{class:'iconbtn',id:'csnd',title:'صدا',onclick:()=>{LS('chess_snd',soundOn()?'0':'1');UI.snd.textContent=soundOn()?'🔊':'🔇';if(soundOn())sound('notify')}},soundOn()?'🔊':'🔇'));
  const bar=(cls)=>h('div',{class:'cbar '+cls},h('div',{class:'cav'}),h('div',{class:'cnm'},h('b',{class:'cn'}),h('span',{class:'ccap'})),h('span',{class:'cturn'}));
  root.dataset.theme=theme();
  const board=h('div',{class:'chb','data-theme':theme(),dir:'ltr'});
  const grid=h('div',{class:'cgrid'}),layer=h('div',{class:'cpieces'});
  board.append(grid,layer);
  const moves=h('div',{class:'cmoves',dir:'ltr'});
  const offer=h('div',{class:'coffer',hidden:true});
  const acts=h('div',{class:'cacts'},
    h('button',{class:'btn soft',id:'cdraw',onclick:draw},'🤝 پیشنهاد مساوی'),
    h('button',{class:'btn danger',id:'cres',onclick:resign},'🏳 تسلیم'));
  const over=h('div',{class:'cover',hidden:true});
  const wrap=h('div',{class:'cwrapb'},bar('opp'),board,bar('me'));
  root.append(top,wrap,moves,offer,acts,over,h('canvas',{class:'cconf',hidden:true}));
  document.body.append(root);
  UI={root,board,grid,layer,moves,offer,acts,over,opp:root.querySelector('.cbar.opp'),me:root.querySelector('.cbar.me'),stat:root.querySelector('#cstat'),snd:root.querySelector('#csnd'),
      draw:root.querySelector('#cdraw'),res:root.querySelector('#cres'),conf:root.querySelector('.cconf')};
  rebuildBoard();
  bindBoard();
  document.addEventListener('keydown',onKey)}
function cycleTheme(){const ks=Object.keys(THEMES);const n=ks[(ks.indexOf(theme())+1)%ks.length];LS('chess_theme',n);UI.board.dataset.theme=n;UI.root.dataset.theme=n;toast('تم صفحه: '+THEMES[n],false)}

/* board geometry: every piece is an absolutely positioned 12.5% cell moved with transform (so moves can slide) */
const colOf=sq=>G.flip?7-(sq&7):(sq&7), rowOf=sq=>G.flip?(sq>>3):7-(sq>>3);
function place(el,sq){el.style.transform=`translate(${colOf(sq)*100}%,${rowOf(sq)*100}%)`;el.dataset.sq=sq}
function rebuildBoard(){
  const {grid,layer}=UI;grid.replaceChildren();layer.replaceChildren();G.els.clear();
  for(let r=0;r<8;r++)for(let c=0;c<8;c++){
    const f=G.flip?7-c:c,rk=G.flip?r:7-r,sq=rk*8+f;
    const s=h('div',{class:'chsq '+((f+rk)%2?'chl':'chd'),'data-sq':sq});
    if(c===0)s.append(h('span',{class:'chrk'},String(rk+1)));if(r===7)s.append(h('span',{class:'chfl'},FILES[f]));
    s.append(h('i',{class:'chhint'}));grid.append(s)}
  if(G.view){const m=parseFen(G.view.fen);for(const [sq,ch] of Object.entries(m))addPiece(+sq,ch)}}
function addPiece(sq,ch){const el=h('div',{class:'cp','data-ch':ch});el.append(pieceSvg(ch));place(el,sq);UI.layer.append(el);G.els.set(sq,el);return el}
const sqEl=sq=>UI.grid.children[rowOf(sq)*8+colOf(sq)];

/* apply a move to the pieces on screen with animation (falls back to a plain redraw if it does not match the new FEN) */
function applyAnim(uci,fen){
  const from=sqIdx(uci.slice(0,2)),to=sqIdx(uci.slice(2,4)),promo=uci[4];
  const el=G.els.get(from);let captured=!!G.els.get(to),kind='move';
  if(!el)return false;
  const ch=el.dataset.ch;
  if(captured){const v=G.els.get(to);v.classList.add('chcap');setTimeout(()=>v.remove(),260);G.els.delete(to)}
  else if(ch.toLowerCase()==='p'&&(from&7)!==(to&7)){const cs=(from&~7)|(to&7),v=G.els.get(cs);if(v){v.classList.add('chcap');setTimeout(()=>v.remove(),260);G.els.delete(cs);captured=true}}
  G.els.delete(from);G.els.set(to,el);el.style.zIndex=5;place(el,to);setTimeout(()=>{el.style.zIndex=''},320);
  if(ch.toLowerCase()==='k'&&Math.abs(to-from)===2){const rf=to>from?from+3:from-4,rt=to>from?from+1:from-1,re=G.els.get(rf);if(re){G.els.delete(rf);G.els.set(rt,re);place(re,rt)}kind='castle'}
  if(promo){const nc=ch===ch.toUpperCase()?promo.toUpperCase():promo;el.dataset.ch=nc;el.replaceChildren(pieceSvg(nc));el.classList.add('chpromo');setTimeout(()=>el.classList.remove('chpromo'),700);kind='promote'}
  // verify against the authoritative position
  const want=parseFen(fen);let ok=Object.keys(want).length===G.els.size;
  if(ok)for(const [sq,c] of Object.entries(want)){const e=G.els.get(+sq);if(!e||e.dataset.ch!==c){ok=false;break}}
  if(!ok){rebuildBoard();}
  return captured&&kind==='move'?'capture':kind}

/* ---- render a server view ---- */
function render(v,animate){
  const old=G.view;G.view=v;const first=!old;
  let snd=null;
  if(first||!animate||!old||v.ply<old.ply||v.ply>old.ply+1||(v.ply===old.ply&&v.fen!==old.fen)){
    if(UI.layer.children.length===0||first||!animate||v.fen!==(old&&old.fen)){G.els.clear();UI.layer.replaceChildren();for(const [sq,ch] of Object.entries(parseFen(v.fen)))addPiece(+sq,ch)}}
  else if(v.ply===old.ply+1&&v.last){snd=applyAnim(v.last,v.fen)}
  if(v.status==='finished'&&(!old||old.status!=='finished')&&old)snd=snd||null;
  G.sel=null;
  paintStatic();updateBars();updateMoves();drawHints();updateButtons();
  if(snd){sound(v.check?'check':snd);if(v.check||snd==='capture')buzz(v.check?[30,40,30]:20)}
  else if(v.check&&old&&v.ply!==old.ply)sound('check');
  if(v.status==='finished')showOver(first||!old||old.status!=='finished',old&&old.status!=='finished')
  else UI.over.hidden=true}
function paintStatic(){
  const v=G.view;[...UI.grid.children].forEach(s=>{s.classList.remove('chlm','chchk','chsel','chtg','chtc')});
  if(v.last){sqEl(sqIdx(v.last.slice(0,2))).classList.add('chlm');sqEl(sqIdx(v.last.slice(2,4))).classList.add('chlm')}
  if(v.check){const m=parseFen(v.fen),k=v.turn==='w'?'K':'k';for(const [sq,c] of Object.entries(m))if(c===k)sqEl(+sq).classList.add('chchk')}}
function drawHints(){
  [...UI.grid.children].forEach(s=>s.classList.remove('chsel','chtg','chtc'));
  if(G.sel==null)return;const v=G.view,from=sqName(G.sel),m=parseFen(v.fen);
  sqEl(G.sel).classList.add('chsel');
  for(const t of (v.legal[from]||[])){const ti=sqIdx(t);const isCap=!!m[ti]||(m[G.sel]&&m[G.sel].toLowerCase()==='p'&&(ti&7)!==(G.sel&7));sqEl(ti).classList.add(isCap?'chtc':'chtg')}}
function capturedOf(fen){
  const m=parseFen(fen),cnt={w:{p:0,n:0,b:0,r:0,q:0},b:{p:0,n:0,b:0,r:0,q:0}};
  for(const c of Object.values(m)){const k=c.toLowerCase();if(k==='k')continue;cnt[c===c.toUpperCase()?'w':'b'][k]++}
  const lost={w:[],b:[]};let mat={w:0,b:0};
  for(const k of 'qrbnp'){for(let i=cnt.w[k];i<START_COUNT[k];i++)lost.w.push(k);for(let i=cnt.b[k];i<START_COUNT[k];i++)lost.b.push(k)}
  for(const c of 'wb')for(const k of 'pnbrq')mat[c]+=cnt[c][k]*VAL[k];
  return {lost,diff:mat.w-mat.b}}
function updateBars(){
  const v=G.view;
  const userOf=s=>s==='w'?v.white:v.black;
  const cap=capturedOf(v.fen);
  const setBar=(bar,side)=>{
    const u=userOf(side)||{id:0,name:'—',avatar_at:0};
    const av=bar.querySelector('.cav');av.replaceChildren(avatar('u',u.id,u.name,u.avatar_at,38,false));
    bar.querySelector('.cn').textContent=(u.id===me()?'تو':u.name)+(side==='w'?' ⚪':' ⚫');
    const taken=cap.lost[side==='w'?'b':'w'];const capEl=bar.querySelector('.ccap');capEl.replaceChildren();
    for(const k of taken){const s=pieceSvg(side==='w'?k.toLowerCase():k.toUpperCase());s.classList.add('mini');capEl.append(s)}
    const adv=side==='w'?cap.diff:-cap.diff;if(adv>0)capEl.append(h('em',{},'+'+fa(adv)));
    bar.classList.toggle('chturn',v.status==='active'&&v.turn===side)};
  // the board is drawn from MY point of view unless flipped
  const bottom=G.flip?'b':'w',topSide=bottom==='w'?'b':'w';
  setBar(UI.me,bottom);setBar(UI.opp,topSide);
  const t=v.status==='active'?(v.you?(v.turn===v.you?'نوبت توئه':'نوبت حریف'):('نوبت '+(v.turn==='w'?'سفید':'سیاه'))):v.status==='finished'?'تمام شد':'';
  UI.stat.textContent=(v.status==='active'?t+(v.check?' · کیش!':''):t)+(v.you?'':' · تماشاچی')}
function updateMoves(){
  const v=G.view,box=UI.moves;box.replaceChildren();
  for(let i=0;i<v.sans.length;i+=2){
    box.append(h('span',{class:'chmn'},fa(i/2+1)+'.'),h('span',{class:'chmv'+(i===v.sans.length-1?' chnow':'')},v.sans[i]));
    if(v.sans[i+1])box.append(h('span',{class:'chmv'+(i+1===v.sans.length-1?' chnow':'')},v.sans[i+1]))}
  box.scrollLeft=box.scrollWidth}
function updateButtons(){
  const v=G.view,playing=v.you&&v.status==='active';
  UI.acts.hidden=!playing;
  const off=v.draw_offer;UI.draw.disabled=!!off;UI.draw.textContent=off===me()?'⏳ پیشنهاد مساوی فرستاده شد':'🤝 پیشنهاد مساوی';
  UI.offer.hidden=!(playing&&off&&off!==me());
  if(!UI.offer.hidden){UI.offer.replaceChildren(h('span',{},'حریف پیشنهاد مساوی داده'),h('button',{class:'btn',onclick:()=>drawAct('accept')},'قبول'),h('button',{class:'btn soft',onclick:()=>drawAct('decline')},'رد'))}}

/* ---- input: tap-to-move and drag ---- */
function squareAt(e){const r=UI.board.getBoundingClientRect(),x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;
  if(x<0||x>=1||y<0||y>=1)return null;const c=Math.floor(x*8),rw=Math.floor(y*8);
  const f=G.flip?7-c:c,rk=G.flip?rw:7-rw;return rk*8+f}
function bindBoard(){
  let drag=null;
  UI.board.addEventListener('pointerdown',e=>{
    if(!G||e.button>0)return;const v=G.view;if(v.status!=='active'||v.you!==v.turn||G.busy)return;
    const sq=squareAt(e);if(sq==null)return;const m=parseFen(v.fen),from=sqName(sq);
    if(G.sel!=null&&(v.legal[sqName(G.sel)]||[]).includes(from)){e.preventDefault();tryMove(G.sel,sq);return}
    if(m[sq]&&v.legal[from]){G.sel=sq;drawHints();
      const el=G.els.get(sq);drag={sq,el,x0:e.clientX,y0:e.clientY,moved:false,id:e.pointerId};try{UI.board.setPointerCapture(e.pointerId)}catch{}}
    else{G.sel=null;drawHints()}});
  UI.board.addEventListener('pointermove',e=>{
    if(!drag||e.pointerId!==drag.id)return;const dx=e.clientX-drag.x0,dy=e.clientY-drag.y0;
    if(!drag.moved&&Math.hypot(dx,dy)<6)return;
    if(!drag.moved){drag.moved=true;drag.el.classList.add('chdrag');drag.el.style.transition='none'}
    const r=UI.board.getBoundingClientRect(),cell=r.width/8;
    drag.el.style.transform=`translate(${(e.clientX-r.left-cell/2)/cell*100}%,${(e.clientY-r.top-cell/2)/cell*100}%)`;
    const t=squareAt(e);[...UI.grid.children].forEach(s=>s.classList.remove('chover'));if(t!=null)sqEl(t).classList.add('chover')});
  const end=e=>{
    if(!drag||e.pointerId!==drag.id)return;const d=drag;drag=null;[...UI.grid.children].forEach(s=>s.classList.remove('chover'));
    try{UI.board.releasePointerCapture(e.pointerId)}catch{}
    if(!d.moved)return;d.el.classList.remove('chdrag');d.el.style.transition='';
    const t=squareAt(e);
    if(t!=null&&t!==d.sq&&(G.view.legal[sqName(d.sq)]||[]).includes(sqName(t)))tryMove(d.sq,t);
    else{place(d.el,d.sq);sound('illegal');}};
  UI.board.addEventListener('pointerup',end);UI.board.addEventListener('pointercancel',end)}

function tryMove(from,to){
  const v=G.view,m=parseFen(v.fen),ch=m[from];
  const promo=ch&&ch.toLowerCase()==='p'&&((to>>3)===7||(to>>3)===0);
  if(promo)return pickPromo(ch===ch.toUpperCase(),p=>sendMove(from,to,p));
  sendMove(from,to,'')}
function pickPromo(white,cb){
  const ov=h('div',{class:'cpromo'});
  const box=h('div',{class:'cpbox'},h('b',{},'ارتقا به:'));
  for(const k of 'qrbn'){const b=h('button',{class:'cpb',onclick:()=>{ov.remove();cb(k)}});b.append(pieceSvg(white?k.toUpperCase():k));box.append(b)}
  ov.append(box);ov.onclick=e=>{if(e.target===ov){ov.remove();G.sel=null;drawHints();rebuildBoard()}};UI.root.append(ov)}
async function sendMove(from,to,promo){
  const v=G.view,uci=sqName(from)+sqName(to)+promo;G.busy=true;G.sel=null;
  // optimistic: slide the piece now, the server confirms (or we resync)
  try{
    const ptr=applyLocal(uci);sound(ptr);
    const r=await call('game_move',{game_id:G.id,move:uci,ply:v.ply});
    if(G&&G.id===r.game.id){G.view=r.game;paintStatic();updateBars();updateMoves();drawHints();updateButtons();
      if(r.game.check)sound('check');if(r.game.status==='finished')showOver(true,true)}
  }catch(e){toastErr(e);sound('illegal');await resync()}
  if(G)G.busy=false}
function applyLocal(uci){ // moves pieces locally without needing the new FEN (verified later by the server's view)
  const from=sqIdx(uci.slice(0,2)),to=sqIdx(uci.slice(2,4)),promo=uci[4],el=G.els.get(from);if(!el)return 'move';
  const ch=el.dataset.ch;let kind='move';
  if(G.els.get(to)){const v=G.els.get(to);v.classList.add('chcap');setTimeout(()=>v.remove(),260);G.els.delete(to);kind='capture'}
  else if(ch.toLowerCase()==='p'&&(from&7)!==(to&7)){const cs=(from&~7)|(to&7),v=G.els.get(cs);if(v){v.classList.add('chcap');setTimeout(()=>v.remove(),260);G.els.delete(cs);kind='capture'}}
  G.els.delete(from);G.els.set(to,el);place(el,to);
  if(ch.toLowerCase()==='k'&&Math.abs(to-from)===2){const rf=to>from?from+3:from-4,rt=to>from?from+1:from-1,re=G.els.get(rf);if(re){G.els.delete(rf);G.els.set(rt,re);place(re,rt)}kind='castle'}
  if(promo){const nc=ch===ch.toUpperCase()?promo.toUpperCase():promo;el.dataset.ch=nc;el.replaceChildren(pieceSvg(nc));kind='promote'}
  [...UI.grid.children].forEach(s=>s.classList.remove('chlm','chsel','chtg','chtc','chchk'));sqEl(from).classList.add('chlm');sqEl(to).classList.add('chlm');
  return kind}
async function resync(){if(!G)return;try{const r=await call('game_get',{game_id:G.id});G.view=null;render(r.game,false)}catch(e){}}

/* ---- resign / draw ---- */
function confirmBox(text,yes,cb){
  const ov=h('div',{class:'cpromo'},h('div',{class:'cpbox'},h('b',{},text),h('div',{class:'cpr'},h('button',{class:'btn danger',onclick:()=>{ov.remove();cb()}},yes),h('button',{class:'btn soft',onclick:()=>ov.remove()},'انصراف'))));
  ov.onclick=e=>{if(e.target===ov)ov.remove()};UI.root.append(ov)}
function resign(){confirmBox('مطمئنی تسلیم می‌شی؟','تسلیم',async()=>{try{const r=await call('game_resign',{game_id:G.id});G.view=null;render(r.game,false)}catch(e){toastErr(e)}})}
async function drawAct(a){try{const r=await call('game_draw',{game_id:G.id,action:a});if(G){const old=G.view;G.view=null;render(r.game,false)}}catch(e){toastErr(e)}}
function draw(){drawAct('offer');toast('پیشنهاد مساوی فرستاده شد',false)}

/* ---- end of game ---- */
function showOver(announce,fresh){
  const v=G.view;UI.over.hidden=false;UI.over.replaceChildren();
  const win=v.result==='1/2-1/2'?0:((v.result==='1-0')===(v.you==='w'))?1:-1;
  const title=v.result==='1/2-1/2'?'مساوی 🤝':!v.you?(v.result==='1-0'?'سفید برنده شد':'سیاه برنده شد'):win>0?'بردی! 🏆':'باختی';
  const box=h('div',{class:'cob '+(win>0?'win':win<0?'lose':'draw')},h('div',{class:'cot'},title),h('div',{class:'cor'},(REASON[v.reason]||'')+' · '+fa(Math.ceil(v.ply/2))+' حرکت'));
  const row=h('div',{class:'cpr'});
  if(v.you)row.append(h('button',{class:'btn',onclick:rematch},'🔁 بازی دوباره'));
  row.append(h('button',{class:'btn soft',onclick:()=>{UI.over.hidden=true}},'دیدن صفحه'),h('button',{class:'btn soft',onclick:close},'بستن'));
  box.append(row);UI.over.append(box);
  if(fresh&&announce){sound(win>0?'win':win<0?'lose':'draw');if(win>0){confetti();buzz([40,60,40,60,120])}}}
async function rematch(){
  const v=G.view;const color=v.you==='w'?'black':'white';const chat=v.chat_id;
  try{const r=await call('game_invite',{chat_id:chat,color});close();if(S.current===chat){window.__live=Date.now();ingest(r.message)}toast('دعوت دوباره فرستاده شد',false)}catch(e){toastErr(e)}}
function confetti(){
  const cv=UI.conf;cv.hidden=false;cv.width=innerWidth;cv.height=innerHeight;const c=cv.getContext('2d');
  const cols=['#ffd54a','#ff6b6b','#4ecdc4','#7c5cff','#4fae4e','#ff9f43'];
  const ps=Array.from({length:140},()=>({x:Math.random()*cv.width,y:-20-Math.random()*cv.height*.5,vx:(Math.random()-.5)*3,vy:2+Math.random()*4,r:4+Math.random()*5,c:cols[Math.random()*cols.length|0],a:Math.random()*6,va:(Math.random()-.5)*.3}));
  let t0=performance.now();
  (function f(t){if(!UI||cv.hidden)return;c.clearRect(0,0,cv.width,cv.height);
    for(const p of ps){p.x+=p.vx;p.y+=p.vy;p.a+=p.va;c.save();c.translate(p.x,p.y);c.rotate(p.a);c.fillStyle=p.c;c.fillRect(-p.r/2,-p.r/2,p.r,p.r*1.6);c.restore()}
    if(t-t0<3800)requestAnimationFrame(f);else{c.clearRect(0,0,cv.width,cv.height);cv.hidden=true}})(t0)}

/* ---- live events from the server ---- */
function onGame(v){
  refreshCards(v);
  if(G&&G.id===v.id){
    const old=G.view;
    if(old&&v.ply<old.ply)return;                          // stale
    if(G.busy&&old&&v.ply===old.ply+1)return;              // my own move, confirmed by the call() reply
    const anim=!!old&&v.ply===old.ply+1;
    if(old&&v.ply===old.ply&&v.status==='active'&&v.fen===old.fen){G.view=v;updateBars();updateButtons();UI.offer.hidden=!(v.you&&v.draw_offer&&v.draw_offer!==me());if(v.draw_offer&&v.draw_offer!==me()){updateButtons();sound('notify')}return}
    render(v,anim);return}
  // game screen closed: tell the user
  if(v.status==='invite'&&v.invitee_id===me()&&v.inviter_id!==me()){note(v,'♟ '+(v.inviter||'یه نفر')+' تو رو به شطرنج دعوت کرد');return}
  if(v.room&&v.status==='active'&&v.ply===0){
    if(v.you===v.turn||v.you){open(v.id,v);return}
    if(!v.you){note(v,'♟ '+(v.white?v.white.name:'')+' و '+(v.black?v.black.name:'')+' شروع کردن — تماشا');return}}
  if(v.status==='active'&&v.you&&v.you===v.turn&&v.ply>0)note(v,'♟ حریفت حرکت کرد — نوبت توئه');
  else if(v.status==='active'&&v.ply===0&&v.you)note(v,'♟ بازی شروع شد!');
  else if(v.status==='finished'&&v.you)note(v,'♟ بازی تموم شد');
  else if(v.draw_offer&&v.draw_offer!==me()&&v.you)note(v,'🤝 حریف پیشنهاد مساوی داده')}
/* ---- inside a watch-room: invite a room member / list running games to watch */
function roomInvite(room,uid,name){
  const ov=h('div',{class:'cov',onclick:e=>{if(e.target===ov)ov.remove()}});
  const pick=c=>async()=>{ov.remove();try{await call('room_game_invite',{room,user_id:uid,color:c});sound('notify');toast('دعوت برای '+name+' فرستاده شد',false)}catch(e){toastErr(e)}};
  ov.append(h('div',{class:'cdlg'},h('h3',{},'♟ شطرنج با '+name),h('small',{},'بقیه‌ی اتاق می‌تونن تماشا کنن'),
    h('div',{class:'cg-col'},h('span',{},'رنگ تو:'),h('button',{class:'btn soft',onclick:pick('white')},'⚪ سفید'),h('button',{class:'btn soft',onclick:pick('black')},'⚫ سیاه'),h('button',{class:'btn',onclick:pick('random')},'🎲 تصادفی')),
    h('button',{class:'btn soft',onclick:()=>ov.remove()},'بستن')));
  document.body.append(ov)}
function roomGames(room){
  const box=h('div',{class:'cg-list'});
  call('room_games',{room}).then(r=>{
    if(!r.games.length)return;box.append(h('small',{},'♟ بازی‌های شطرنج این اتاق:'));
    for(const g of r.games){const w=g.white?g.white.name:'—',b=g.black?g.black.name:'—';
      box.append(h('button',{class:'cg-row',onclick:()=>open(g.id,g)},g.status==='invite'?'⏳ دعوت '+(g.inviter||'')+' — منتظر قبول':`♟ ${w} ⚔ ${b}`,
        h('span',{class:'cg-turn'},g.you?'بازی':'تماشا')))}}).catch(()=>{});
  return box}
function note(v,text){
  sound('notify');let n=document.getElementById('cnote');if(n)n.remove();
  n=h('div',{class:'cnote',id:'cnote',onclick:()=>{n.remove();open(v.id,v)}},h('span',{},text),h('b',{},'باز کردن'));
  document.body.append(n);setTimeout(()=>n&&n.remove(),9000)}
function refreshCards(v){
  document.querySelectorAll(`[data-gcard="${v.id}"] .cmini`).forEach(old=>old.replaceWith(miniBoard(v.fen)))}

/* chat opened / list refreshed: make sure the 🎮 button exists */
const mo=new MutationObserver(()=>installButton());
function boot(){installButton();mo.observe(document.body,{childList:true,subtree:false})}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
setInterval(installButton,2500);

window.CHESS={roomInvite,roomGames,card,fillCard,onGame,open,close,isOpen:()=>!!G};
})();
