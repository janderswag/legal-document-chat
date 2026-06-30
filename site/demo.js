/* docuchat.app live demo — looped typing/answer animation for the hero iframe.
   Extracted from an inline <script> so the page can ship a strict CSP (script-src 'self').
   Vanilla, no deps, no network. */

// ---- fit the fixed 1120x700 stage into whatever size the iframe/window is ----
const stage = document.getElementById('stage');
function fit(){
  const s = Math.min(window.innerWidth/1120, window.innerHeight/700);
  stage.style.transform = 'scale('+s+')';
  // center horizontally if there's slack
  const offx = Math.max(0,(window.innerWidth - 1120*s)/2);
  const offy = Math.max(0,(window.innerHeight - 700*s)/2);
  stage.style.left = offx+'px'; stage.style.top = offy+'px';
}
window.addEventListener('resize', fit); fit();

const chat = document.getElementById('chat');
const field = document.getElementById('field');
const ph = document.getElementById('ph');
const caret = document.getElementById('caret');
const ask = document.getElementById('ask');
const wait = ms => new Promise(r=>setTimeout(r,ms));

const QUESTION = "What are the indemnification obligations, and where are they stated?";
const ANSWER = [
  "The agreement imposes ","**mutual** ","indemnification. ","Each party ","(the “Indemnifying Party”) ",
  "must “defend, ","indemnify, ","and hold harmless” ","the other party, ","its officers, ","directors, ",
  "and employees ","from third-party claims, ","damages, ","and reasonable ","attorneys’ fees ",
  "arising out of ","that party’s ","gross negligence, ","willful misconduct, ","or breach."
];

function typeNode(){ // returns a span we grow
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
    p.appendChild(s); await wait(105);
  }
  await wait(250);
  const sep=document.createElement('div'); sep.className='sep'; a.appendChild(sep);
  const src=document.createElement('div'); src.className='src';
  src.innerHTML='Sources: <span class="chip pulse">SYNTHETIC_Pemberton_MSA.pdf&nbsp;·&nbsp;p.1&nbsp;·&nbsp;§4 Indemnification</span>';
  a.appendChild(src);
}

async function run(){
  while(true){
    // reset
    chat.innerHTML=''; field.querySelector('#typed')?.remove();
    ph.style.display='inline'; caret.style.display='none';
    await wait(900);

    // type the question
    const t=typeNode();
    await typeText(t, QUESTION, 34);
    await wait(450);

    // ask
    ask.classList.add('press'); await wait(120);
    t.remove(); ph.style.display='inline'; caret.style.display='none'; ask.classList.remove('press');
    bubble(QUESTION);
    await wait(550);

    // thinking, then answer
    const a=answerShell();
    await wait(1100);
    await streamAnswer(a);

    // hold, then fade out and loop
    await wait(2600);
    chat.querySelectorAll('.row').forEach(r=>r.classList.add('fade-out'));
    await wait(600);
  }
}
run();
