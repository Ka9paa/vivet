const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];

function openDialog(id){ const d=document.getElementById(id); if(d?.showModal) d.showModal(); }
function closeDialog(el){ el.closest('dialog')?.close(); }

document.addEventListener('click', (event) => {
  const opener=event.target.closest('[data-open]');
  if(opener){ event.preventDefault(); openDialog(opener.dataset.open); }
  const closer=event.target.closest('[data-close]');
  if(closer){ event.preventDefault(); closeDialog(closer); }
});

$$('dialog.modal').forEach(d=>d.addEventListener('click',e=>{if(e.target===d)d.close()}));

document.addEventListener('submit', (event) => {
  const message=event.target.dataset.confirm;
  if(message && !window.confirm(message)){event.preventDefault();return;}
  const submit=event.target.querySelector('button[type="submit"]');
  if(submit){submit.disabled=true;submit.dataset.original=submit.textContent;submit.textContent='Working…';}
});

const sidebar=$('#sidebar'), overlay=$('#sidebar-overlay');
$('#menu-toggle')?.addEventListener('click',()=>{sidebar?.classList.add('open');overlay?.classList.add('show')});
overlay?.addEventListener('click',()=>{sidebar?.classList.remove('open');overlay.classList.remove('show')});

// Real SVG line chart.
$$('.line-chart').forEach(chart=>{
  const values=JSON.parse(chart.dataset.values||'[]').map(Number);
  const svg=$('svg',chart), line=$('.chart-line',chart), area=$('.chart-area',chart), points=$('.chart-points',chart);
  if(!svg||!values.length)return;
  const max=Math.max(...values,1), w=1000, top=25, bottom=265, step=w/(values.length-1||1);
  const coords=values.map((v,i)=>[i*step,bottom-(v/max)*(bottom-top)]);
  const d=coords.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  line.setAttribute('d',d); area.setAttribute('d',d+` L ${w} ${bottom} L 0 ${bottom} Z`);
  points.innerHTML=coords.map(p=>`<circle cx="${p[0]}" cy="${p[1]}" r="4"/>`).join('');
});

// Table search.
$$('[data-table-search]').forEach(input=>input.addEventListener('input',()=>{
  const table=document.getElementById(input.dataset.tableSearch), q=input.value.toLowerCase().trim();
  $$('tbody tr',table).forEach(row=>row.hidden=!row.textContent.toLowerCase().includes(q));
}));

// Command palette.
const palette=$('#command-palette'), commandInput=$('#command-input'), results=$('#command-results');
const commands=$$('.sidebar-nav a').map(a=>({label:a.textContent.trim(),href:a.href}));
function renderCommands(q=''){results.innerHTML=commands.filter(c=>c.label.toLowerCase().includes(q.toLowerCase())).map(c=>`<a href="${c.href}">↗ &nbsp; ${c.label}</a>`).join('')||'<div class="mini-empty">No results.</div>'}
function showPalette(){palette.hidden=false;renderCommands();setTimeout(()=>commandInput?.focus(),10)}
function hidePalette(){palette.hidden=true;commandInput.value=''}
$('#command-open')?.addEventListener('click',showPalette);
commandInput?.addEventListener('input',()=>renderCommands(commandInput.value));
palette?.addEventListener('click',e=>{if(e.target===palette)hidePalette()});
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();showPalette()}if(e.key==='Escape'){hidePalette();$$('dialog[open]').forEach(d=>d.close())}});

// Theme and button feedback.
$('.theme-toggle')?.addEventListener('click',()=>{document.body.classList.toggle('oled');localStorage.setItem('vivet-oled',document.body.classList.contains('oled')?'1':'0')});
if(localStorage.getItem('vivet-oled')==='1')document.body.classList.add('oled');

function toast(message){const stack=$('#toast-stack');if(!stack)return;const node=document.createElement('div');node.className='toast-message';node.textContent=message;stack.append(node);setTimeout(()=>node.remove(),3000)}
$$('[data-copy]').forEach(btn=>btn.addEventListener('click',async()=>{await navigator.clipboard.writeText(btn.dataset.copy);toast('Copied to clipboard')}));
