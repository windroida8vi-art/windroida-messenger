'use strict';
/* Mensch (Ludo) inside a watch-room. The SERVER rolls the dice and judges every move; this file draws the view the server sends and
   animates what happened (dice roll, pawn walking cell by cell, captures). Board = SVG 15x15; ring of 52 cells, 4 yards, 4 home columns. */
const MN={v:undefined,at:0,el:null,timer:null,svg:null,key:'',pawns:{},disp:null,seq:0,q:[],busy:false,dice:null,note:'',rolls:{}};
const MNCOL={red:'#ef4444',green:'#22c55e',yellow:'#facc15',blue:'#3b82f6'};
const MNDARK={red:'#b91c1c',green:'#15803d',yellow:'#a16207',blue:'#1d4ed8'};
const MNFA={red:'قرمز',green:'سبز',yellow:'زرد',blue:'آبی'};
const MNCOLS=['red','green','yellow','blue'];
const MNENTRY=[1,14,27,40];
const MNRP=(()=>{const r=[];
  for(let x=0;x<=5;x++)r.push([x,6]);for(let y=5;y>=0;y--)r.push([6,y]);r.push([7,0]);
  for(let y=0;y<=5;y++)r.push([8,y]);for(let x=9;x<=14;x++)r.push([x,6]);r.push([14,7]);
  for(let x=14;x>=9;x--)r.push([x,8]);for(let y=9;y<=14;y++)r.push([8,y]);r.push([7,14]);
  for(let y=14;y>=9;y--)r.push([6,y]);for(let x=5;x>=0;x--)r.push([x,8]);r.push([0,7]);return r})();
const MNHC=[[1,2,3,4,5].map(x=>[x,7]),[1,2,3,4,5].map(y=>[7,y]),[13,12,11,10,9].map(x=>[x,7]),[13,12,11,10,9].map(y=>[7,y])];
const MNYARD=[[0,0],[9,0],[9,9],[0,9]];
const MNSLOT=[[2,2],[4,2],[2,4],[4,4]];
const MNGOAL=[[6.45,7.5],[7.5,6.45],[8.55,7.5],[7.5,8.55]];
const MNFACE={1:[4],2:[0,8],3:[0,4,8],4:[0,2,6,8],5:[0,2,4,6,8],6:[0,2,3,5,6,8]};
const MNSAFE=new Set([...MNENTRY,...MNENTRY.map(e=>e+8)]);
const mnLeft=()=>{const v=MN.v;if(!v||!v.left)return 0;return Math.max(0,v.left-Math.floor((Date.now()-MN.at)/1000))};
const mnSleep=ms=>new Promise(r=>setTimeout(r,ms));
const SVGNS='http://www.w3.org/2000/svg';
function sv(tag,attrs,...kids){const e=document.createElementNS(SVGNS,tag);for(const [k,v] of Object.entries(attrs||{}))e.setAttribute(k,v);for(const k of kids.flat())if(k)e.append(k);return e}
function svt(attrs,txt){const e=sv('text',attrs);e.textContent=txt;return e}

/* ---------------- sound (synthesised with WebAudio: no files) + haptics ---------------- */
const MNS={ctx:null,on:(()=>{try{return localStorage.getItem('wd-mn-snd')!=='0'}catch{return true}})()};
function mnCtx(){if(!MNS.ctx){try{MNS.ctx=new (window.AudioContext||window.webkitAudioContext)()}catch{return null}}if(MNS.ctx.state==='suspended')MNS.ctx.resume().catch(()=>{});return MNS.ctx}
function mnTone(f,t0,dur,type,vol,f2){const c=mnCtx();if(!c)return;const o=c.createOscillator(),g=c.createGain();o.type=type||'sine';o.frequency.setValueAtTime(f,c.currentTime+t0);
  if(f2)o.frequency.exponentialRampToValueAtTime(f2,c.currentTime+t0+dur);g.gain.setValueAtTime(0.0001,c.currentTime+t0);g.gain.exponentialRampToValueAtTime(vol||.2,c.currentTime+t0+.01);g.gain.exponentialRampToValueAtTime(.0001,c.currentTime+t0+dur);
  o.connect(g).connect(c.destination);o.start(c.currentTime+t0);o.stop(c.currentTime+t0+dur+.05)}
function mnSnd(k,i){
  if(!MNS.on)return;const buzz=n=>{try{navigator.vibrate&&navigator.vibrate(n)}catch{}};
  if(k==='roll'){for(let j=0;j<7;j++)mnTone(300+Math.random()*500,j*.07,.05,'square',.07);buzz(25)}
  else if(k==='step')mnTone(520+(i||0)*14,0,.06,'triangle',.12);
  else if(k==='land'){mnTone(220,0,.12,'sine',.25,140);buzz(15)}
  else if(k==='hit'){mnTone(180,0,.25,'sawtooth',.22,60);mnTone(90,0,.3,'sine',.3);buzz([40,30,60])}
  else if(k==='home'){[523,659,784,1047].forEach((f,j)=>mnTone(f,j*.09,.18,'triangle',.18));buzz(40)}
  else if(k==='win'){[523,659,784,1047,784,1047,1319].forEach((f,j)=>mnTone(f,j*.13,.28,'triangle',.2));buzz([60,40,60,40,120])}
  else if(k==='turn'){mnTone(880,0,.12,'sine',.2);mnTone(1175,.12,.18,'sine',.2);buzz(30)}
  else if(k==='bad'){mnTone(140,0,.18,'square',.12);buzz(20)}}

/* ---------------- geometry ---------------- */
function mnXY(seat,p,i){
  if(p<0){const o=MNYARD[seat],s=MNSLOT[i];return [o[0]+s[0],o[1]+s[1]]}
  if(p<=50){const c=MNRP[(MNENTRY[seat]+p)%52];return [c[0]+.5,c[1]+.5]}
  if(p<=55){const c=MNHC[seat][p-51];return [c[0]+.5,c[1]+.5]}
  const g=MNGOAL[seat];return [g[0]+((i%2)-.5)*.34,g[1]+((i>>1)-.5)*.34]}
function mnPositions(v){const d={};for(const p of v.players)d[p.id]=p.pawns.slice();return d}

/* ---------------- board ---------------- */
function mnBuildBoard(v){
  const svg=sv('svg',{viewBox:'0 0 15 15',class:'mnsvg',role:'img','aria-label':'صفحه‌ی منچ'});
  const defs=sv('defs',{});
  for(const c of MNCOLS){
    const g=sv('radialGradient',{id:'mng-'+c,cx:'35%',cy:'30%',r:'75%'});
    g.append(sv('stop',{offset:'0','stop-color':'#fff','stop-opacity':'.9'}),sv('stop',{offset:'.35','stop-color':MNCOL[c]}),sv('stop',{offset:'1','stop-color':MNDARK[c]}));defs.append(g)}
  svg.append(defs);
  // wooden board: warm gradient + grain + a darker frame
  const wg=sv('linearGradient',{id:'mnwood',x1:'0',y1:'0',x2:'1',y2:'1'});
  wg.append(sv('stop',{offset:'0','stop-color':'#ecce98'}),sv('stop',{offset:'.5','stop-color':'#dcae70'}),sv('stop',{offset:'1','stop-color':'#e6c088'}));defs.append(wg);
  svg.append(sv('rect',{x:0,y:0,width:15,height:15,fill:'url(#mnwood)'}));
  for(let k=0;k<34;k++){const y=.2+k*.44+Math.sin(k*2.3)*.12,a=.05+((k*37)%7)/70,w=.025+((k*13)%5)/160;
    svg.append(sv('path',{d:'M0 '+y.toFixed(2)+' C 4 '+(y+Math.sin(k)*.25).toFixed(2)+' 9 '+(y-Math.cos(k*1.7)*.25).toFixed(2)+' 15 '+(y+Math.sin(k*.6)*.18).toFixed(2),fill:'none',stroke:k%3?'#8a5a26':'#fff3d6','stroke-opacity':a,'stroke-width':w}))}
  svg.append(sv('rect',{x:.09,y:.09,width:14.82,height:14.82,rx:.25,fill:'none',stroke:'#5a3719','stroke-width':.2}));
  // yards: a faint coloured field and four round slots
  MNCOLS.forEach((c,s)=>{const o=MNYARD[s];
    svg.append(sv('rect',{x:o[0]+.45,y:o[1]+.45,width:5.1,height:5.1,rx:.9,fill:MNCOL[c],'fill-opacity':.16,stroke:MNDARK[c],'stroke-opacity':.45,'stroke-width':.07}));
    MNSLOT.forEach(sl=>{const cx=o[0]+sl[0]-.5+.5,cy=o[1]+sl[1];
      svg.append(sv('circle',{cx:cx+.03,cy:cy+.06,r:.7,fill:'#000','fill-opacity':.25}),sv('circle',{cx,cy,r:.7,fill:MNCOL[c],'fill-opacity':.9,stroke:MNDARK[c],'stroke-width':.07}),sv('circle',{cx,cy,r:.46,fill:'#fff','fill-opacity':.22}))})});
  // ring cells: round holes
  MNRP.forEach((c,i)=>{
    const ent=MNENTRY.indexOf(i),cx=c[0]+.5,cy=c[1]+.5;
    svg.append(sv('circle',{cx:cx+.02,cy:cy+.05,r:.42,fill:'#000','fill-opacity':.28}),
      sv('circle',{cx,cy,r:.41,fill:ent>=0?MNCOL[MNCOLS[ent]]:'#fff',stroke:ent>=0?MNDARK[MNCOLS[ent]]:'#a47a46','stroke-width':.05}));
    if(ent<0&&MNSAFE.has(i))svg.append(svt({x:cx,y:cy,'text-anchor':'middle','dominant-baseline':'central','font-size':.62,fill:'#b08a5a'},'★'));
    if(ent>=0)svg.append(svt({x:cx,y:cy,'text-anchor':'middle','dominant-baseline':'central','font-size':.5,fill:'#fff',transform:'rotate('+ent*90+' '+cx+' '+cy+')'},'➜'))});
  // home columns
  MNHC.forEach((col,s)=>col.forEach(c=>svg.append(
    sv('circle',{cx:c[0]+.52,cy:c[1]+.55,r:.42,fill:'#000','fill-opacity':.28}),
    sv('circle',{cx:c[0]+.5,cy:c[1]+.5,r:.41,fill:MNCOL[MNCOLS[s]],stroke:MNDARK[MNCOLS[s]],'stroke-width':.05}),
    sv('circle',{cx:c[0]+.5,cy:c[1]+.5,r:.22,fill:'#fff','fill-opacity':.28}))));
  // centre: four triangles
  const T=[[[6,6],[9,6],[7.5,7.5]],[[9,6],[9,9],[7.5,7.5]],[[9,9],[6,9],[7.5,7.5]],[[6,9],[6,6],[7.5,7.5]]];
  const order=[1,2,3,0];                       // top=green, right=yellow, bottom=blue, left=red
  T.forEach((t,i)=>svg.append(sv('polygon',{points:t.map(p=>p.join(',')).join(' '),fill:MNCOL[MNCOLS[order[i]]],stroke:'#5a3719','stroke-width':.08,'stroke-linejoin':'round'})));
  svg.append(sv('circle',{cx:7.5,cy:7.5,r:.45,fill:'#fff','fill-opacity':.9,stroke:'#5a3719','stroke-width':.06}));
  // pawns
  MN.pawns={};
  const layer=sv('g',{class:'mnlayer'});svg.append(layer);
  for(const p of v.players){if(p.seat==null)continue;const c=MNCOLS[p.seat];
    for(let i=0;i<4;i++){
      const g=sv('g',{class:'mnp'}),sh=sv('ellipse',{cx:0,cy:.2,rx:.34,ry:.14,fill:'#000','fill-opacity':.25}),
        b=sv('circle',{r:.36,cy:-.05,fill:'url(#mng-'+c+')',stroke:'#fff','stroke-width':.07}),
        t=sv('circle',{r:.13,cy:-.1,fill:'#fff','fill-opacity':.55});
      g.append(sh,b,t);g.dataset.u=p.id;g.dataset.i=i;layer.append(g);MN.pawns[p.id+':'+i]=g}}
  return svg}
function mnPlace(){
  const v=MN.v;if(!v||!MN.svg||!MN.disp)return;
  const spots={},s3=[];
  for(const p of v.players){if(p.seat==null)continue;const d=MN.disp[p.id]||p.pawns;
    d.forEach((pos,i)=>{const xy=mnXY(p.seat,pos,i),k=xy[0].toFixed(2)+','+xy[1].toFixed(2);(spots[k]=spots[k]||[]).push([p.id,i,xy,pos])})}
  for(const k in spots){const a=spots[k],n=a.length;
    a.forEach(([u,i,xy,pos],j)=>{const g=MN.pawns[u+':'+i];if(!g)return;
      let x=xy[0],y=xy[1];if(n>1&&pos>=0&&pos<56){const ang=j/n*Math.PI*2;x+=Math.cos(ang)*.2;y+=Math.sin(ang)*.2}
      s3.push({u,i,x,y,pos,n});
      g.style.transform='translate('+x+'px,'+y+'px) scale('+(n>1&&pos>=0?.8:1)+')'})}
  if(MN3.canvas)MN3.place(s3)}
function mnMarkLegal(){
  const v=MN.v;if(!v)return;
  for(const k in MN.pawns){MN.pawns[k].classList.remove('can');MN.pawns[k].onclick=null}
  const keys=[];
  if(v.me&&v.phase==='play'&&v.turn===v.me.id&&v.stage==='move'&&!MN.busy)
    for(const i of v.legal){const g=MN.pawns[v.me.id+':'+i];if(g){g.classList.add('can');g.onclick=()=>mnAct('move',{pawn:i});keys.push(v.me.id+':'+i)}}
  if(MN3.canvas)MN3.setLegal(keys)}

/* ---------------- dice ---------------- */
function mnDice(face,rolling){
  const d=h('div',{class:'mndice'+(rolling?' roll':'')});
  const on=new Set(MNFACE[face]||[]);for(let i=0;i<9;i++)d.append(h('i',{class:on.has(i)?'on':''}));return d}

/* ---------------- talking to the server ---------------- */
async function mnLoad(){
  if(!R.on)return;
  try{const r=await call('room_mensch',{room:R.id,a:'get'});mnSync(r.mensch)}catch{}}
function mnAct(a,extra){
  return call('room_mensch',{room:R.id,a,...(extra||{})}).then(r=>{mnSync(r.mensch);return r}).catch(e=>{toast(e.message)})}

/* ---------------- animation of what just happened ---------------- */
function mnSync(nv){
  const old=MN.v;MN.v=nv;MN.at=Date.now();
  if(!nv){MN.disp=null;MN.seq=0;MN.q=[];MN.svg=null;MN.key='';MN.dice=null;MN.busy=false;MN3.destroy();mnRedraw();return}
  const fresh=!MN.disp||!old||old.phase==='lobby'||nv.phase==='lobby';
  if(fresh){MN.q=[];MN.busy=false;MN.disp=mnPositions(nv);MN.seq=nv.last?nv.last.seq:0;MN.dice=nv.last&&nv.phase!=='lobby'?{uid:nv.last.uid,roll:nv.last.roll}:null;mnNotify(old,nv);mnRedraw();return}
  mnNotify(old,nv);
  const l=nv.last;
  if(l&&l.seq>MN.seq){
    if(l.seq===MN.seq+1&&!document.hidden){MN.q.push({l,pos:mnPositions(nv)});mnRun()}
    else{MN.disp=mnPositions(nv);MN.seq=l.seq;MN.dice={uid:l.uid,roll:l.roll}}}
  else if(!MN.busy&&!MN.q.length)MN.disp=mnPositions(nv);
  mnRedraw()}
async function mnRun(){
  if(MN.busy)return;MN.busy=true;
  try{
    while(MN.q.length){
      const {l,pos}=MN.q.shift();MN.seq=l.seq;
      const who=MN.v&&MN.v.players.find(p=>p.id===l.uid);
      MN.note='';MN.dice={uid:l.uid,roll:l.roll,rolling:true};mnRedraw();
      mnSnd('roll');
      await mnSleep(520);MN.dice={uid:l.uid,roll:l.roll};
      if(l.note==='three6')MN.note='سه شش پشت‌هم؛ نوبت می‌سوزه';
      else if(l.note==='stuck')MN.note='حرکتی ممکن نیست';
      mnRedraw();
      if(l.note==='moved'&&who&&MN.disp&&MN.disp[l.uid]){
        await mnSleep(180);
        const arr=MN.disp[l.uid];
        if(l.frm===-1){arr[l.pawn]=0;mnPlace();mnSnd('land');await mnSleep(260)}
        else{for(let p=l.frm+1;p<=l.to;p++){arr[l.pawn]=p;mnPlace();mnSnd('step',p-l.frm);await mnSleep(150)}mnSnd('land')}
        for(const c of l.cap||[]){const g=MN.pawns[c.uid+':'+c.pawn];mnSnd('hit');if(g){g.classList.add('hit');await mnSleep(220);}
          if(MN.disp[c.uid])MN.disp[c.uid][c.pawn]=-1;mnPlace();if(g)setTimeout(()=>g.classList.remove('hit'),300)}
        if((l.cap||[]).length)await mnSleep(300);
        if(l.to===56)mnSnd('home');
      }else await mnSleep(l.note==='rolled'?100:700);
      MN.disp=pos;mnPlace()}
  }finally{MN.busy=false;MN.q=[];if(MN.v)MN.disp=mnPositions(MN.v);mnRedraw()}}
function mnNotify(old,nw){
  if(!nw||!R.on||!nw.me||!nw.me.in)return;
  const wasPlay=old&&old.phase==='play';
  if(nw.phase==='play'&&!wasPlay){R.tab='games';rDrawTabs();rDrawPane();if(R.min){R.min=false;rShow()}toast('🎲 بازی منچ شروع شد',false);return}
  if(nw.phase==='play'&&nw.turn===nw.me.id&&(!old||old.turn!==nw.turn||old.stage!==nw.stage)){
    if(R.tab!=='games')toast('🎲 نوبت توئه',false);
    mnSnd('turn')}
  if(nw.phase==='over'&&(!old||old.phase!=='over')){toast(nw.winner===nw.me.id?'🏆 تو بردی!':'🎲 بازی تموم شد',false);setTimeout(()=>mnSnd(nw.winner===nw.me.id?'win':'bad'),900)}}

/* ---------------- drawing ---------------- */
function mnTick(){
  const c=MN.el&&MN.el.querySelector('.mnclock');if(c&&MN.v)c.textContent=MN.v.phase==='play'&&MN.v.left?fa(mnLeft())+' ث':'';
  const b=MN.el&&MN.el.querySelector('.mntbar i');if(b&&MN.v)b.style.width=Math.max(0,Math.min(1,mnLeft()/25))*100+'%'}
function mnRedraw(){
  if(!R.on||R.tab!=='games'||!MN.el||!MN.el.isConnected){return}
  MN.el.replaceChildren(mnBody());mnTick()}
function mnName(v,id){const p=v.players.find(x=>x.id===id);return p?p.name:'؟'}
function mnHome(p){return p.pawns.filter(x=>x===56).length}
function mnBody(){
  const v=MN.v,box=h('div',{class:'mn'});
  if(v===undefined){box.append(h('div',{class:'hint'},'در حال بارگذاری…'));return box}
  const me=v?v.me:null,inGame=!!(me&&me.in);
  box.append(h('div',{class:'mnhead'},h('b',{},'🎲 منچ'),h('span',{class:'mnclock'}),MN3.supported()?h('button',{class:'iconbtn mnmode mn3t',type:'button',title:'سه‌بعدی / دوبعدی',onclick:()=>{MN3.on=!MN3.on;try{localStorage.setItem('wd-mn-3d',MN3.on?'1':'0')}catch{}if(!MN3.on)MN3.destroy();mnRedraw()}},MN3.on?'3D':'2D'):null,h('button',{class:'iconbtn mnsnd',type:'button',title:'صدا',onclick:()=>{MNS.on=!MNS.on;try{localStorage.setItem('wd-mn-snd',MNS.on?'1':'0')}catch{}if(MNS.on){mnSnd('turn')}mnRedraw()}},MNS.on?'🔊':'🔇')));
  if(!v){
    box.append(h('div',{class:'hint'},'منچ ۲ تا ۴ نفره؛ تاس رو سرور می‌ندازه و حرکت‌ها رو چک می‌کنه.'),
      h('button',{class:'btn',onclick:()=>mnAct('open')},'🎲 ساخت بازی منچ'));return box}
  if(v.phase==='lobby'){
    box.append(h('div',{class:'mnlobby'},v.players.map(p=>h('div',{class:'mnlp'},h('span',{class:'mndot',style:'background:#94a3b8'}),h('span',{class:'mnn'},p.name+(p.id===v.host?' 👑':''))))));
    box.append(h('div',{class:'hint'},fa(v.players.length)+' نفر؛ حداقل '+fa(v.min)+' و حداکثر '+fa(v.max)+' نفر'));
    const b=h('div',{class:'mnbtns'});
    if(!inGame)b.append(h('button',{class:'btn',onclick:()=>mnAct('join')},'پیوستن'));
    else b.append(h('button',{class:'btn ghost',onclick:()=>mnAct('leave')},'خروج'));
    if(inGame&&me.id===v.host)b.append(h('button',{class:'btn',disabled:v.players.length<v.min?true:null,onclick:()=>mnAct('start')},'🚀 شروع بازی'));
    if(me&&me.id===v.host||rhost())b.append(h('button',{class:'btn ghost',onclick:()=>mnAct('end')},'بستن'));
    box.append(b);return box}
  // board
  const key=v.players.map(p=>p.id+':'+p.seat).join('|');
  if(!MN.svg||MN.key!==key){MN.svg=mnBuildBoard(v);MN.key=key;if(!MN.disp)MN.disp=mnPositions(v);MN3.destroy()}
  let cv3=null;
  if(MN3.on&&MN3.supported()){
    const base=MN.svg.cloneNode(true);const ly=base.querySelector('.mnlayer');if(ly)ly.remove();
    cv3=MN3.build(v,base,null);if(cv3)MN3.onPick=i=>mnAct('move',{pawn:i})}
  mnPlace();mnMarkLegal();
  // players strip
  const strip=h('div',{class:'mnstrip'},v.players.map(p=>{
    const c=MNCOLS[p.seat],cur=v.phase==='play'&&v.turn===p.id;
    return h('div',{class:'mnpl'+(cur?' cur':'')+(p.out?' out':''),style:'--c:'+MNCOL[c]},
      h('span',{class:'mndot',style:'background:'+MNCOL[c]}),
      h('span',{class:'mnn'},p.name+(me&&p.id===me.id?' (تو)':'')),
      h('small',{},p.out?(p.out==='afk'?'💤':'🚪'):'🏠 '+fa(mnHome(p))+'/۴'))}));
  box.append(strip);
  const tl=v.phase==='play'?Math.max(0,Math.min(1,mnLeft()/25)):0;
  const my=v.phase==='play'&&me&&v.turn===me.id,d=MN.dice;
  if(v.phase==='lobby')MN.rolls={};
  if(d&&d.uid&&d.roll)MN.rolls[d.uid]=d.roll;
  const canRoll=my&&v.stage==='roll'&&!MN.busy;
  const turnTxt=v.phase==='over'?'':my?(v.stage==='roll'?'نوبت توئه؛ تاس بنداز':'یه مهره‌ی چشمک‌زن رو بزن'):'نوبت '+mnName(v,v.turn);
  // one die in the corner next to every seated player's yard (red top-left, green top-right, blue bottom-left, yellow bottom-right)
  const dieFor=seat=>{
    const p=v.players.find(x=>x.seat===seat);if(!p)return h('div',{class:'mncd none'});
    const cur=v.phase==='play'&&v.turn===p.id,isMe=!!(me&&p.id===me.id),rolling=!!(d&&d.rolling&&d.uid===p.id);
    const face=d&&d.uid===p.id&&d.roll?d.roll:(MN.rolls[p.id]||0);
    const cls='mncd'+(cur?' cur':'')+(isMe?' me':'')+(p.out?' out':''),st='--c:'+MNCOL[MNCOLS[seat]];
    if(!isMe)return h('div',{class:cls,style:st,title:p.name},mnDice(face,rolling));
    return h('button',{class:cls+' mndiebtn'+(canRoll?' go':''),style:st,'aria-disabled':canRoll?null:'true',title:'انداختن تاس',onclick:()=>{if(canRoll)mnAct('roll');else if(v.phase==='play'){mnSnd('bad');toast(MN.busy?'صبر کن…':my?'اول یه مهره رو حرکت بده':'نوبت '+mnName(v,v.turn)+' هست',false)}}},mnDice(face,rolling))};
  box.append(h('div',{class:'mnarena'},
    h('div',{class:'mndrow'},dieFor(0),dieFor(1)),
    h('div',{class:'mnboard'+(cv3?' d3':'')+(v.phase==='play'&&me&&v.turn===me.id?' mine':'')},cv3||MN.svg),
    h('div',{class:'mndrow'},dieFor(3),dieFor(2))),
    v.phase==='play'?h('div',{class:'mntbar'},h('i',{style:'width:'+tl*100+'%'})):null);
  box.append(h('div',{class:'mnctl'},h('div',{class:'mninfo'},
    h('b',{},turnTxt),h('small',{},MN.note||(d&&d.uid&&!d.rolling?mnName(v,d.uid)+' '+fa(d.roll)+' آورد':'')))));
  if(v.phase==='over'){
    box.append(h('div',{class:'mnwin'},v.winner?'🏆 '+mnName(v,v.winner)+' برنده شد!':'بازی تموم شد'),
      h('button',{class:'btn',onclick:()=>mnAct('end')},'بستن بازی'))}
  else if(me&&me.id===v.host||rhost())box.append(h('button',{class:'btn ghost mnend',onclick:()=>{if(confirm('بازی تموم بشه؟'))mnAct('end')}},'پایان بازی'));
  if(!inGame&&v.phase==='play')box.append(h('div',{class:'hint'},'تماشاچی هستی'));
  if(inGame&&v.phase==='play'&&me.id!==v.host)box.append(h('button',{class:'btn ghost mnend',onclick:()=>{if(confirm('از بازی بری بیرون؟'))mnAct('leave')}},'خروج از بازی'));
  if(v.log.length)box.append(h('div',{class:'mnlog'},v.log.slice(-4).reverse().map(t=>h('div',{},t))));
  return box}
function mnCard(){
  if(!MN.el||!MN.el.isConnected){MN.el=h('div',{class:'rgcard mncard'})}
  MN.el.replaceChildren(mnBody());
  if(MN.v===undefined)mnLoad();
  clearInterval(MN.timer);MN.timer=setInterval(()=>{if(!R.on||R.tab!=='games'||!MN.el||!MN.el.isConnected){clearInterval(MN.timer);return}mnTick()},1000);
  setTimeout(mnTick,0);return MN.el}
function mnReset(){MN3.destroy();MN.v=undefined;MN.el=null;MN.svg=null;MN.key='';MN.disp=null;MN.q=[];MN.busy=false;MN.dice=null;MN.rolls={};MN.seq=0;MN.note='';clearInterval(MN.timer)}
const _onEventMn=onEvent;
onEvent=function(e){
  if(e.event==='room_mensch'){
    if(R.on&&e.room===R.id){mnSync(e.mensch);rDrawTabs()}
    return}
  return _onEventMn(e)};
