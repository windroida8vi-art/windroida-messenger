/* Polls (نظرسنجی): card inside a message bubble + creation dialog. Uses helpers from app.js (h, call, dialog, closeDialog, applyUpdate, toast, fa). */
(function(){
  const MINE={};            // poll id → my chosen option indexes (filled lazily from poll_get)
  const fetching=new Set();
  const pct=(n,t)=>t?Math.round(n*100/t):0;
  function canClose(m){const c=S.chats[m.chat_id]||{};return m.sender_id===S.me.id||(c.kind==='group'&&!c.channel&&(c.owner_id===S.me.id||c.my_role==='admin'||c.my_role==='owner'))}
  async function vote(m,i){
    const p=m.poll;if(p.closed)return;
    let mine=(MINE[p.id]||[]).slice();
    if(p.multi)mine=mine.includes(i)?mine.filter(x=>x!==i):[...mine,i];
    else mine=mine.includes(i)?[]:[i];
    try{const r=await call('poll_vote',{poll_id:p.id,options:mine});MINE[p.id]=r.mine;applyUpdate(r.message)}
    catch(e){toast(e.message)}}
  async function close(m){
    if(!confirm('نظرسنجی بسته بشه؟ بعدش کسی نمی‌تونه رأی بده.'))return;
    try{const r=await call('poll_close',{poll_id:m.poll.id});applyUpdate(r.message)}catch(e){toast(e.message)}}
  async function voters(m){
    try{const r=await call('poll_get',{poll_id:m.poll.id,voters:true});const p=m.poll,v=r.voters||{};
      dialog('رأی‌دهنده‌ها',...p.opts.map((o,i)=>h('div',{class:'pvrow'},h('b',{},o+' ('+fa(p.counts[i])+')'),h('div',{class:'muted'},(v[i]||[]).join('، ')||'—'))))}
    catch(e){toast(e.message)}}
  function card(m){
    const p=m.poll,mine=MINE[p.id],total=p.multi?p.voters:p.counts.reduce((a,b)=>a+b,0);
    const el=h('div',{class:'poll'+(p.closed?' closed':''),'data-poll':p.id},
      h('div',{class:'pq'},p.q),
      h('div',{class:'pmeta'},[p.anon?'ناشناس':'عمومی',p.multi?'چندانتخابی':'تک‌انتخابی',p.closed?'بسته شده':''].filter(Boolean).join(' · ')),
      ...p.opts.map((o,i)=>{const on=(mine||[]).includes(i),pc=pct(p.counts[i],total);
        return h('button',{type:'button',class:'popt'+(on?' on':''),disabled:p.closed,onclick:e=>{e.stopPropagation();vote(m,i)}},
          h('span',{class:'pbar',style:'width:'+pc+'%'}),
          h('span',{class:'ptxt'},(on?'✓ ':'')+o),h('span',{class:'pnum'},fa(pc)+'٪ · '+fa(p.counts[i])))}),
      h('div',{class:'pfoot'},h('span',{},fa(p.voters)+' نفر رأی دادن'),
        ...(!p.anon&&p.voters?[h('button',{type:'button',class:'plink',onclick:e=>{e.stopPropagation();voters(m)}},'کی رأی داده؟')]:[]),
        ...(!p.closed&&canClose(m)?[h('button',{type:'button',class:'plink',onclick:e=>{e.stopPropagation();close(m)}},'بستن')]:[])));
    if(mine===undefined&&!m.deleted&&!fetching.has(p.id)){fetching.add(p.id);
      call('poll_get',{poll_id:p.id}).then(r=>{MINE[p.id]=r.mine||[];fetching.delete(p.id);const old=document.querySelector(`.poll[data-poll="${p.id}"]`);if(old){const b=old.closest('[data-id]');const l=S.msgs[m.chat_id],mm=l&&l.find(x=>x.id===m.id);if(mm)old.replaceWith(card(mm))}})
        .catch(()=>{MINE[p.id]=[];fetching.delete(p.id)})}
    return el}
  function dlgCreate(){
    const q=h('input',{placeholder:'سؤال',maxlength:200}),err=h('div',{class:'msg'}),box=h('div',{class:'popts'});
    const multi=h('input',{type:'checkbox',style:'width:auto;margin-inline-end:6px'}),anon=h('input',{type:'checkbox',style:'width:auto;margin-inline-end:6px'});
    const add=()=>{if(box.children.length>=10)return;box.append(h('input',{placeholder:'گزینه '+fa(box.children.length+1),maxlength:100}))};
    add();add();
    const addb=h('button',{type:'button',class:'btn ghost',onclick:()=>{add();if(box.children.length>=10)addb.hidden=true}},'+ گزینه');
    const chat=S.current;
    dialog('نظرسنجی جدید',q,h('div',{style:'height:8px'}),box,addb,
      h('label',{style:'display:block;margin:8px 0;cursor:pointer'},multi,'چندانتخابی'),
      h('label',{style:'display:block;margin:8px 0;cursor:pointer'},anon,'ناشناس (کسی نمی‌بینه چه کسی رأی داده)'),err,
      h('button',{class:'btn',onclick:async()=>{
        const opts=[...box.children].map(i=>i.value.trim()).filter(Boolean);
        if(!q.value.trim())return err.textContent='سؤال رو بنویس';
        if(opts.length<2)return err.textContent='حداقل دو گزینه لازمه';
        try{const r=await call('poll_create',{chat_id:chat,question:q.value,options:opts,multi:multi.checked?1:0,anon:anon.checked?1:0});closeDialog();ingest(r.message)}
        catch(e){err.textContent=e.message}}},'ارسال'));
    q.focus()}
  window.POLL={card,dlgCreate};
})();
