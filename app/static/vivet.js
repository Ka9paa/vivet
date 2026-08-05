const $=(s,r=document)=>r.querySelector(s);const $$=(s,r=document)=>[...r.querySelectorAll(s)];
const sidebar=$('#sidebar'),overlay=$('#sidebar-overlay');
$('#menu-toggle')?.addEventListener('click',()=>{sidebar?.classList.add('open');overlay?.classList.add('show')});
overlay?.addEventListener('click',()=>{sidebar?.classList.remove('open');overlay?.classList.remove('show')});
$$('.sidebar-nav a').forEach(a=>a.addEventListener('click',()=>{sidebar?.classList.remove('open');overlay?.classList.remove('show')}));
const navSearch=$('#nav-search');navSearch?.addEventListener('input',()=>{const q=navSearch.value.toLowerCase();$$('.nav-link').forEach(a=>a.hidden=!a.dataset.navLabel.includes(q))});

document.addEventListener('click',e=>{const open=e.target.closest('[data-open]');if(open){const d=document.getElementById(open.dataset.open);d?.showModal()}const close=e.target.closest('[data-close]');if(close)close.closest('dialog')?.close()});
$$('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d)d.close()}));

const newMenu=$('#new-menu');$('#new-menu-toggle')?.addEventListener('click',e=>{e.stopPropagation();newMenu?.classList.toggle('show')});document.addEventListener('click',e=>{if(!e.target.closest('#new-menu')&&!e.target.closest('#new-menu-toggle'))newMenu?.classList.remove('show')});

const cmd=$('#command-dialog'),cmdInput=$('#command-input');function openCommand(){cmd?.showModal();setTimeout(()=>cmdInput?.focus(),20)}$('#command-trigger')?.addEventListener('click',openCommand);document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCommand()}if(e.key==='Escape'&&cmd?.open)cmd.close()});cmdInput?.addEventListener('input',()=>{const q=cmdInput.value.toLowerCase();$$('[data-command]',cmd).forEach(a=>a.hidden=!a.dataset.command.includes(q))});

$('#theme-toggle')?.addEventListener('click',()=>{document.body.classList.toggle('theme-soft');localStorage.setItem('vivet-theme',document.body.classList.contains('theme-soft')?'soft':'dark')});if(localStorage.getItem('vivet-theme')==='soft')document.body.classList.add('theme-soft');

$$('[data-password-toggle]').forEach(b=>b.addEventListener('click',()=>{const i=document.getElementById(b.dataset.passwordToggle);if(!i)return;i.type=i.type==='password'?'text':'password';b.textContent=i.type==='password'?'Show':'Hide'}));

function toast(title,detail=''){const stack=$('#toast-stack');if(!stack)return;const el=document.createElement('div');el.className='toast-message';el.innerHTML=`<strong>${title}</strong>${detail?`<small>${detail}</small>`:''}`;stack.append(el);setTimeout(()=>el.remove(),2800)}
$$('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(b.dataset.copy);const old=b.textContent;b.textContent='Copied';toast('Copied to clipboard');setTimeout(()=>b.textContent=old,1200)}catch{toast('Copy failed','Select and copy the value manually.')}}));

$$('[data-table-search]').forEach(input=>input.addEventListener('input',()=>{const table=input.closest('.surface')?.querySelector('tbody');if(!table)return;const q=input.value.toLowerCase();[...table.rows].forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q))}));

let pendingForm=null;const confirmDialog=$('#confirm-action'),confirmMessage=$('#confirm-message');document.addEventListener('submit',e=>{const f=e.target;if(f.dataset.confirm&&!f.dataset.confirmed){e.preventDefault();pendingForm=f;confirmMessage.textContent=f.dataset.confirm;confirmDialog?.showModal();return}const btn=f.querySelector('.modal-submit');if(btn){btn.disabled=true;btn.classList.add('loading');const s=btn.querySelector('span');if(s){btn.dataset.old=s.textContent;s.textContent='Working…'}}});$('#confirm-submit')?.addEventListener('click',e=>{e.preventDefault();if(!pendingForm)return confirmDialog?.close();pendingForm.dataset.confirmed='1';confirmDialog.close();pendingForm.requestSubmit();pendingForm=null});

$$('button.primary,.new-button,.secondary-btn,.mini-btn').forEach(b=>{b.addEventListener('pointerdown',()=>b.style.transform='scale(.98)');['pointerup','pointerleave'].forEach(x=>b.addEventListener(x,()=>b.style.transform=''))});
window.addEventListener('load',()=>document.body.classList.add('ready'));

// Settings workspace
$$('[data-settings-tab]').forEach(button=>button.addEventListener('click',()=>{
  $$('[data-settings-tab]').forEach(x=>x.classList.toggle('active',x===button));
  $$('[data-settings-panel]').forEach(panel=>panel.classList.toggle('active',panel.dataset.settingsPanel===button.dataset.settingsTab));
}));
const newPassword=$('#new-password');
newPassword?.addEventListener('input',()=>{
  const value=newPassword.value;let score=0;
  if(value.length>=8)score++;if(/[A-Z]/.test(value)&&/[a-z]/.test(value))score++;if(/\d/.test(value))score++;if(/[^A-Za-z0-9]/.test(value))score++;
  $$('.password-strength i').forEach((bar,index)=>bar.classList.toggle('on',index<score));
  const labels=['Password strength','Weak','Fair','Good','Strong'];
  const label=$('#password-strength-label');if(label)label.textContent=labels[score];
});
$$('[data-theme-choice]').forEach(card=>card.addEventListener('click',()=>{
  const choice=card.dataset.themeChoice;
  document.body.classList.toggle('theme-soft',choice==='soft');
  localStorage.setItem('vivet-theme',choice);
  $$('[data-theme-choice]').forEach(x=>x.classList.toggle('selected',x===card));
  toast('Appearance updated',choice==='soft'?'Soft Dark enabled':'Vivet Dark enabled');
}));
const savedTheme=localStorage.getItem('vivet-theme')||'dark';
$$('[data-theme-choice]').forEach(x=>x.classList.toggle('selected',x.dataset.themeChoice===savedTheme));
const reducedMotion=$('#reduced-motion');
if(reducedMotion){reducedMotion.checked=localStorage.getItem('vivet-reduced-motion')==='1';document.body.classList.toggle('reduce-motion',reducedMotion.checked);reducedMotion.addEventListener('change',()=>{document.body.classList.toggle('reduce-motion',reducedMotion.checked);localStorage.setItem('vivet-reduced-motion',reducedMotion.checked?'1':'0');toast('Preference saved')})}
const compactNav=$('#compact-navigation');
const shell=$('.app-shell');
if(compactNav&&shell){compactNav.checked=localStorage.getItem('vivet-compact-nav')==='1';shell.classList.toggle('compact-nav',compactNav.checked);compactNav.addEventListener('change',()=>{shell.classList.toggle('compact-nav',compactNav.checked);localStorage.setItem('vivet-compact-nav',compactNav.checked?'1':'0');toast('Navigation updated')})}
