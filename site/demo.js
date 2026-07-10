/* docuchat.app live demo — looped four-beat animation for the hero iframe.
   Beat 1: ask a question, watch the cited answer stream in.
   Beat 2: drop a whole folder into the Document Hub.
   Beat 3: connect Gmail with an app password, watch documents import.
   Beat 4: one-click in-place update above Billing.
   Vanilla, no deps, no network. CSP: script-src 'self'. */

// ---- fit the fixed 1120x700 stage into whatever size the iframe/window is ----
const stage = document.getElementById('stage');
function fit(){
  const s = Math.min(window.innerWidth/1120, window.innerHeight/700);
  stage.style.transform = 'scale('+s+')';
  const offx = Math.max(0,(window.innerWidth - 1120*s)/2);
  const offy = Math.max(0,(window.innerHeight - 700*s)/2);
  stage.style.left = offx+'px'; stage.style.top = offy+'px';
}
window.addEventListener('resize', fit); fit();

const $ = id => document.getElementById(id);
const wait = ms => new Promise(r=>setTimeout(r,ms));

const NAVS = {chat:$('nav-chat'), hub:$('nav-hub'), conn:$('nav-set')};
const VIEWS = {chat:$('view-chat'), hub:$('view-hub'), conn:$('view-conn')};
function show(name){
  Object.keys(VIEWS).forEach(k=>{
    VIEWS[k].classList.toggle('on', k===name);
    NAVS[k] && NAVS[k].classList.toggle('active', k===name);
  });
}

/* ---------------- beat 1: cited answer ---------------- */
const chat = $('chat'), field = $('field'), ph = $('ph'), caret = $('caret'), ask = $('ask');
const QUESTION = "What are the indemnification obligations, and where are they stated?";
const ANSWER = [
  "The agreement imposes ","**mutual** ","indemnification. ","Each party ","(the “Indemnifying Party”) ",
  "must “defend, ","indemnify, ","and hold harmless” ","the other party, ","its officers, ","directors, ",
  "and employees ","from third-party claims, ","damages, ","and reasonable ","attorneys’ fees ",
  "arising out of ","that party’s ","gross negligence, ","willful misconduct, ","or breach."
];

function typeNode(){
  ph.style.display='none'; caret.style.display='inline-block';
  let t=document.createElement('span'); t.id='typed';
  field.insertBefore(t, caret); return t;
}
async function typeText(node, text, perChar){
  for(let i=0;i<text.length;i++){ node.textContent += text[i]; await wait(perChar + (text[i]===' '?12:0)); }
}
function bubble(text){
  const row=document.createElement('div'); row.className='row user';
  const b=document.createElement('div'); b.className='bubble'; b.textContent=text;
  row.appendChild(b); chat.appendChild(row); return row;
}
function answerShell(){
  const row=document.createElement('div'); row.className='row';
  const a=document.createElement('div'); a.className='ans';
  a.innerHTML='<div class="dots"><span></span><span></span><span></span></div>';
  row.appendChild(a); chat.appendChild(row); return a;
}
async function streamAnswer(a){
  a.innerHTML=''; const p=document.createElement('p'); a.appendChild(p);
  for(const w of ANSWER){
    const s=document.createElement('span'); s.className='reveal-w';
    if(w.startsWith('**')){ const b=document.createElement('strong'); b.textContent=w.replace(/\*\*/g,''); s.appendChild(b); }
    else s.textContent=w;
    p.appendChild(s); await wait(95);
  }
  await wait(250);
  const sep=document.createElement('div'); sep.className='sep'; a.appendChild(sep);
  const src=document.createElement('div'); src.className='src';
  src.innerHTML='Sources: <span class="chip pulse">SYNTHETIC_Pemberton_MSA.pdf&nbsp;·&nbsp;p.1&nbsp;·&nbsp;§4 Indemnification</span>';
  a.appendChild(src);
}
async function beatChat(){
  show('chat');
  chat.innerHTML=''; field.querySelector('#typed')?.remove();
  ph.style.display='inline'; caret.style.display='none';
  await wait(800);
  const t=typeNode();
  await typeText(t, QUESTION, 30);
  await wait(400);
  ask.classList.add('press'); await wait(120);
  t.remove(); ph.style.display='inline'; caret.style.display='none'; ask.classList.remove('press');
  bubble(QUESTION);
  await wait(500);
  const a=answerShell();
  await wait(1000);
  await streamAnswer(a);
  await wait(2200);
  chat.querySelectorAll('.row').forEach(r=>r.classList.add('fade-out'));
  await wait(500);
}

/* ---------------- beat 2: folder drop into the Hub ---------------- */
const HUBFILES = [
  ["Pemberton_MSA_v4.pdf","pdf"],
  ["Deposition_Hargrove_2026-05-12.pdf","transcript"],
  ["Counteroffer_email_thread.eml","eml"],
  ["Zoom_call_2026-06-02.vtt","vtt"],
  ["Damages_worksheet.csv","csv"],
];
async function beatHub(){
  show('hub');
  const dz=$('dz'), hint=$('dzhint'), fcard=$('fcard'), rows=$('hubrows');
  rows.innerHTML=''; fcard.classList.remove('fly'); hint.style.display='';
  await wait(900);
  dz.classList.add('hot'); hint.style.display='none';
  fcard.classList.add('fly');
  await wait(1250);
  dz.classList.remove('hot');
  for(const [nm] of HUBFILES){
    const r=document.createElement('div'); r.className='hubrow in';
    r.innerHTML='<svg viewBox="0 0 24 24"><path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/></svg>'+
      '<span class="nm">'+nm+'</span><span class="st">indexing</span>';
    rows.appendChild(r); await wait(320);
  }
  await wait(700);
  const sts=[...rows.querySelectorAll('.st')];
  for(const st of sts){ st.textContent='in the matter'; st.classList.add('ok'); await wait(240); }
  await wait(1900);
}

/* ---------------- beat 3: connect Gmail ---------------- */
async function beatConnectors(){
  show('conn');
  const btn=$('gm-btn'), key=$('gm-key'), msg=$('gm-msg');
  btn.textContent='Connect'; btn.classList.add('gold');
  key.style.display='none'; key.textContent=''; msg.textContent=''; msg.classList.add('dim');
  await wait(1100);
  btn.classList.remove('gold'); btn.textContent='…';
  key.style.display='block';
  const APPPW='app password  ••••  ••••  ••••  ••••';
  for(let i=0;i<APPPW.length;i++){ key.textContent+=APPPW[i]; await wait(26); }
  await wait(500);
  key.style.display='none';
  msg.textContent='testing the key…';
  await wait(900);
  msg.classList.remove('dim');
  msg.textContent='Connected · importing 12 documents…';
  btn.textContent='Manage';
  await wait(1700);
  msg.textContent='Connected · 12 documents in the matter';
  await wait(2100);
}

/* ---------------- beat 4: one-click update ---------------- */
async function beatUpdate(){
  show('chat');
  const upd=$('upd'), txt=$('updtext'), ver=$('updver');
  upd.classList.remove('ok'); ver.style.display='';
  txt.textContent='Update available'; ver.textContent='v0.3.0';
  upd.classList.add('show');
  await wait(1400);
  ver.style.display='none';
  for(const pct of [12,34,58,81,97]){ txt.textContent='Downloading… '+pct+'%'; await wait(330); }
  txt.textContent='Verifying signature…'; await wait(750);
  txt.textContent='Installing…'; await wait(750);
  upd.classList.add('ok');
  txt.textContent='Up to date ✓'; await wait(1500);
  upd.classList.remove('show','ok');
}

async function run(){
  while(true){
    await beatChat();
    await beatHub();
    await beatConnectors();
    await beatUpdate();
    await wait(400);
  }
}
run();
