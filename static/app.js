'use strict';
const $ = (id) => document.getElementById(id);
let key = '', problems = [], nextCursor = null, eventCursor = 0, selected = null, busy = false;
let toastTimer, pendingSubmission = null;
const terminal = new Set(['accepted','wrong_answer','time_limit','memory_limit','output_limit','runtime_error','system_error','cancelled']);
const names = {queued:'Kuyrukta',running:'Çalışıyor',accepted:'Başarılı',wrong_answer:'Yanlış cevap',time_limit:'Süre sınırı',memory_limit:'Bellek sınırı',output_limit:'Çıktı sınırı',runtime_error:'Çalıştırma hatası',system_error:'Altyapı hatası',cancelled:'İptal edildi'};
function element(tag, text, cls) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; }
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 6500); }
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Authorization':'Bearer '+key, 'Content-Type':'application/json', ...options.headers}, signal:AbortSignal.timeout(10000)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'İstek reddedildi ('+response.status+')');
  return data;
}
function countBytes() { $('byte-count').textContent = new TextEncoder().encode($('source').value).length.toLocaleString('tr-TR')+' / 16.000 bayt'; }
function starter() { const p = problems.find(p => p.id === $('problem').value); if (p) $('source').value = p.starters[$('language').value]; $('filename').textContent = $('language').value === 'python' ? 'solution.py' : 'solution.js'; countBytes(); }
function renderProblem() {
  const p = problems.find(p => p.id === $('problem').value); if (!p) return;
  $('problem-title').textContent = p.title; $('statement').textContent = p.statement; $('difficulty').textContent = p.difficulty; $('constraints').textContent = p.constraints;
  $('samples').replaceChildren(...p.samples.map(c => { const row = element('div',undefined,'sample'); for (const [label,value] of [['GİRDİ',c.input],['ÇIKTI',c.expected]]) { const col = element('div'); col.append(element('small',label),element('pre',value || '(boş)')); row.append(col); } return row; })); starter();
}
function badge(status) { return element('span',names[status] || status,'status '+status); }
function time(value) { return new Date(value * 1000).toLocaleTimeString('tr-TR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
function renderRows(data, append) {
  if (!append) $('submissions').replaceChildren();
  for (const job of data.items) { const row = element('tr'); const id = element('td'); const link = element('button','#'+job.id.slice(0,8),'job-link'); link.addEventListener('click',() => showDetail(job.id).catch(e => toast(e.message))); id.append(link);
    const status = element('td'); status.append(badge(job.status)); row.append(id,element('td',problems.find(p => p.id === job.problem_id)?.title || job.problem_id),element('td',job.language === 'python' ? 'Python' : 'JavaScript'),status,element('td',String(job.attempts)),element('td',time(job.created))); $('submissions').append(row);
  }
  if (!$('submissions').children.length) { const row = element('tr'); const cell = element('td','Henüz gönderim yok. İlk çözümünü yukarıdan gönder.','empty'); cell.colSpan=6; row.append(cell); $('submissions').append(row); }
  nextCursor=data.next_cursor; $('more').hidden=!nextCursor;
}
async function refresh() {
  if (!key || busy) return; busy=true;
  try { const [stats,list] = await Promise.all([api('/api/stats'),api('/api/submissions')]);
    for (const name of ['queued','running','accepted']) $(name).textContent=stats.counts[name] || 0;
    $('total').textContent=stats.total; $('worker-count').textContent=stats.workers.length; $('engine-state').textContent=stats.workers.length ? 'Çalıştırma motoru hazır' : 'Worker bağlantısı bekleniyor'; $('engine-dot').classList.toggle('active',stats.workers.length>0); $('sync-state').textContent='Son kontrol '+new Date().toLocaleTimeString('tr-TR'); renderRows(list,false);
    if ($('detail-dialog').open && selected) await showDetail(selected.id);
  } finally { busy=false; }
}
async function showDetail(id) {
  const job=await api('/api/submissions/'+id); selected=job; $('detail-title').textContent=job.title; $('detail-meta').replaceChildren(badge(job.status),document.createTextNode('  #'+job.id.slice(0,8)+' · '+job.language+' · sürüm '+job.version+' · '+job.attempts+' deneme'));
  $('case-results').replaceChildren();
  if (!job.cases.length) $('case-results').append(element('p',job.status==='cancelled' ? 'Gönderim iptal edildi.' : job.status==='system_error' ? 'Worker altyapısını kontrol edin. Test sonucu üretilemedi.' : 'Sonuçlar worker testleri tamamladığında burada görünecek.'));
  for (const c of job.cases) { const card=element('div',undefined,'case'); const top=element('div',undefined,'case-top'); top.append(element('span','Test '+(c.index+1)+' · '+(c.public ? 'Örnek' : 'Gizli')),badge(c.verdict),element('span',Math.round(c.elapsed_ms)+' ms')); card.append(top);
    if(c.public) { const d=element('details'); d.append(element('summary','Çıktıyı göster'),element('pre','stdout\n'+(c.stdout || '(boş)')+'\n\nstderr\n'+(c.stderr || '(boş)'))); card.append(d); } $('case-results').append(card);
  }
  $('timeline').replaceChildren(...job.events.map(e=>element('li',time(e.at)+' · '+e.detail))); $('submitted-source').textContent=job.source; $('cancel-job').hidden=terminal.has(job.status); if(!$('detail-dialog').open) $('detail-dialog').showModal();
}
$('connect').addEventListener('click',()=>{$('api-key').value='';$('auth-error').textContent='';$('auth-dialog').showModal();});
$('auth-close').addEventListener('click',()=>$('auth-dialog').close());
$('auth-form').addEventListener('submit',async e=>{e.preventDefault(); const old=key; key=$('api-key').value.trim(); try { problems=await api('/api/problems'); $('problem').replaceChildren(...problems.map(p=>{const o=element('option',p.title);o.value=p.id;return o;}));renderProblem();await refresh();$('auth-dialog').close();$('api-key').value='';$('submit').disabled=false;$('connect').textContent='Anahtarı değiştir';eventCursor=0; } catch(error){key=old;$('auth-error').textContent=error.message;}});
$('problem').addEventListener('change',renderProblem);$('language').addEventListener('change',starter);$('starter').addEventListener('click',starter);$('source').addEventListener('input',countBytes);
$('submit').addEventListener('click',async()=>{ $('submit').disabled=true; const body=JSON.stringify({problem_id:$('problem').value,language:$('language').value,source:$('source').value}); if(!pendingSubmission || pendingSubmission.body!==body) pendingSubmission={body,id:crypto.randomUUID()};
  try{const result=await api('/api/submissions',{method:'POST',headers:{'Idempotency-Key':pendingSubmission.id},body});pendingSubmission=null;toast('Çözüm kuyruğa alındı.');await refresh();await showDetail(result.id);}catch(e){toast(e.message);}finally{$('submit').disabled=false;}
});
$('refresh').addEventListener('click',()=>refresh().catch(e=>toast(e.message)));$('detail-close').addEventListener('click',()=>$('detail-dialog').close());
$('more').addEventListener('click',async()=>{try{renderRows(await api('/api/submissions?before='+nextCursor),true);}catch(e){toast(e.message);}});
$('cancel-job').addEventListener('click',async()=>{try{await api('/api/submissions/'+selected.id+'/cancel',{method:'POST'});await refresh();}catch(e){toast(e.message);}});
$('reuse').addEventListener('click',()=>{$('problem').value=selected.problem_id;renderProblem();$('language').value=selected.language;starter();$('source').value=selected.source;countBytes();$('detail-dialog').close();$('source').focus();});
let ticks=0;
setInterval(async()=>{if(!key || document.hidden || busy)return;try{const events=await api('/api/events?after='+eventCursor);eventCursor=events.next_cursor;if(events.items.length || ++ticks%5===0)await refresh();}catch(e){$('sync-state').textContent='Bağlantı kesildi; yeniden deneniyor';}},2000);
