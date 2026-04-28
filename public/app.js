const app = document.getElementById('app');
let adminToken = localStorage.getItem('adminToken') || '';

const state = {
  page: 'list', crossword: null, activeWordId: null, solved: {}, revealed: {}, shownDescription: {}, filteredLetters: {},
  answer: [], selectedCell: 0, hintsUsed: 0, timer: 0, startedAt: null, done: false, msg: '', fact: ''
};

const api = async (url, opts={}) => {
  const res = await fetch(url, { ...opts, headers: { ...(opts.headers||{}), 'Content-Type': opts.body && !(opts.body instanceof FormData) ? 'application/json' : undefined, 'X-Admin-Token': adminToken || '' }});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Ошибка');
  return data;
};

function setTheme(skin){
  if (!skin || !skin.colors) return;
  const c=skin.colors; const root=document.documentElement.style;
  root.setProperty('--bg', c.background||'#DFF6FF'); root.setProperty('--panel', c.sidePanel||'#fff'); root.setProperty('--main', c.textMain||'#173052');
  root.setProperty('--active', c.activeCell||'#FFD95A'); root.setProperty('--good', c.correctCell||'#DFFFCF'); root.setProperty('--bad', c.wrongCell||'#FFD9D9');
  root.setProperty('--btn', c.primaryButton||'#48C83E'); root.setProperty('--hint', c.hintButton||'#FFC64A');
}

function format(sec){ const m=Math.floor(sec/60), s=sec%60; return `${m}:${String(s).padStart(2,'0')}`; }

async function renderList(){
  const list = await api('/api/crosswords');
  app.innerHTML = `<div class="container"><div class="card"><h1>Детские кроссворды</h1><p>Выбери кроссворд и начинай игру!</p>
  <p><a href="#admin">Вход для администратора</a></p></div>
  ${list.map(c=>`<div class='card'><h3>${c.title}</h3><p>${c.description||''}</p><button class='btn-main' onclick="location.hash='game/${c.id}'">Играть</button><button class='btn-alt' onclick="location.hash='rating/${c.id}'">Рейтинг</button></div>`).join('')}
  </div>`;
}

function coordsForWord(w){
  const out=[]; let r=w.row,c=w.col; const d=w.direction==='across'?[0,1]:[1,0];
  for(const ch of w.answer){ out.push([r,c]); r+=d[0]; c+=d[1]; } return out;
}

function wordLetters(w){
  const base=[...w.answer.split(''), ...(w.extraLetters||[])];
  return state.filteredLetters[w.id] ? [...w.answer.split('')] : base;
}

function selectWord(id){
  state.activeWordId=id; const w=state.crossword.words.find(x=>x.id===id); state.answer = new Array(w.answer.length).fill('');
  Object.entries(state.revealed[id]||{}).forEach(([i, ch])=> state.answer[+i]=ch);
  state.selectedCell = state.answer.findIndex(x=>!x); if (state.selectedCell<0) state.selectedCell=0;
}

function startTimer(){
  if(state.startedAt) return; state.startedAt = Date.now() - state.timer*1000;
  state.ticker=setInterval(()=>{ state.timer=Math.floor((Date.now()-state.startedAt)/1000); document.querySelector('#timer') && (document.querySelector('#timer').textContent=format(state.timer)); },1000);
}

function maybeFinish(){
  if(Object.keys(state.solved).length===state.crossword.words.length){
    state.done=true; clearInterval(state.ticker); location.hash='finish';
  }
}

async function renderGame(id){
  state.crossword = await api(`/api/crosswords/${id}`);
  setTheme(state.crossword.skin);
  state.activeWordId ||= state.crossword.words[0].id;
  state.crossword.words.forEach(w=>{ state.revealed[w.id] ||= {}; });
  if(!state.answer.length) selectWord(state.activeWordId);
  const w = state.crossword.words.find(x=>x.id===state.activeWordId);
  const letters = wordLetters(w);

  const gw=state.crossword.gridWidth;
  const grid = state.crossword.grid.map((row,r)=>row.map((v,c)=>{
    if(v==='#') return `<div class='cell black'></div>`;
    let cls='cell';
    if(coordsForWord(w).some(([rr,cc])=>rr===r&&cc===c)) cls+=' active';
    if(Object.values(state.solved).flat().some(([rr,cc])=>rr===r&&cc===c)) cls+=' solved';
    return `<div class='${cls}' onclick="pickByCell(${r},${c})"></div>`;
  }).join('')).join('');

  app.innerHTML = `<div class='container'><div class='card'><h2>${state.crossword.title}</h2>
  <div>Прогресс: ${Object.keys(state.solved).length} из ${state.crossword.words.length} слов · Таймер: <b id='timer'>${format(state.timer)}</b> · Осталось подсказок: <b>${state.crossword.hintLimit-state.hintsUsed}</b></div></div>
  <div class='crossword-layout'><div class='card'><div class='crossword-grid' style='grid-template-columns:repeat(${gw},44px)'>${grid}</div></div>
  <div class='card'><h3>Слово №${w.number||''}</h3>
  ${w.image ? `<img src='${w.image}' alt='${w.imageAlt||""}' style='max-width:100%;border-radius:12px' onclick='openDescription()'/>` : ''}
  <p><b>Вопрос:</b> ${w.question}</p>
  <button class='btn-hint' onclick='openDescription()'>Описание</button>
  ${state.shownDescription[w.id] ? `<p class='small'>${w.descriptionHint}</p>`:''}
  <div class='word-cells'>${state.answer.map((ch,i)=>`<div class='answer-cell ${(state.revealed[w.id]||{})[i]?'locked':''}' onclick='state.selectedCell=${i};render()'>${ch||''}</div>`).join('')}</div>
  <div class='letters'>${letters.map((l,i)=>`<button onclick='pickLetter(${JSON.stringify(l)},${i})'>${l}</button>`).join('')}</div>
  <div class='toolbar'>
    <button class='btn-hint' onclick='hintShowLetter()'>Показать букву</button>
    <button class='btn-hint' onclick='hintOnlyWord()' ${state.filteredLetters[w.id]?'disabled':''}>Только буквы слова</button>
    <button class='btn-main' onclick='checkWord()'>Проверить</button>
    <button onclick='location.hash="rating/${state.crossword.id}"'>Рейтинг</button>
  </div>
  ${state.msg ? `<div class='msg ${state.msgGood?'good':'bad'}'>${state.msg}</div>` : ''}
  ${state.fact ? `<div class='msg good'>${state.fact}</div>` : ''}
  </div></div></div>`;
}

window.pickByCell=(r,c)=>{
  const w=state.crossword.words.find(word=>coordsForWord(word).some(([rr,cc])=>rr===r&&cc===c) && !state.solved[word.id]);
  if(w){ selectWord(w.id); render(); }
};
window.pickLetter=(l)=>{
  startTimer();
  const w=state.crossword.words.find(x=>x.id===state.activeWordId);
  while((state.revealed[w.id]||{})[state.selectedCell] && state.selectedCell < state.answer.length-1) state.selectedCell++;
  if((state.revealed[w.id]||{})[state.selectedCell]) return;
  state.answer[state.selectedCell]=l;
  if(state.selectedCell<state.answer.length-1) state.selectedCell++;
  render();
};
window.openDescription=()=>{
  const w=state.crossword.words.find(x=>x.id===state.activeWordId);
  if(!state.shownDescription[w.id]){
    if(state.hintsUsed>=state.crossword.hintLimit) return alert('Подсказки закончились');
    state.hintsUsed++; state.shownDescription[w.id]=true;
  }
  render();
};
window.hintShowLetter=()=>{
  startTimer();
  const w=state.crossword.words.find(x=>x.id===state.activeWordId);
  const idx = state.answer.findIndex((ch,i)=>!ch && !(state.revealed[w.id]||{})[i]);
  if(idx<0) return;
  if(state.hintsUsed>=state.crossword.hintLimit) return alert('Подсказки закончились');
  state.hintsUsed++; state.answer[idx]=w.answer[idx]; state.revealed[w.id][idx]=w.answer[idx]; render();
};
window.hintOnlyWord=()=>{
  const w=state.crossword.words.find(x=>x.id===state.activeWordId);
  const hasExtra=(w.extraLetters||[]).length>0;
  if(!hasExtra || state.filteredLetters[w.id]) return;
  if(state.hintsUsed>=state.crossword.hintLimit) return alert('Подсказки закончились');
  state.hintsUsed++; state.filteredLetters[w.id]=true; render();
};
window.checkWord=()=>{
  startTimer();
  const w=state.crossword.words.find(x=>x.id===state.activeWordId);
  if(state.answer.join('')!==w.answer){ state.msg='Пока не верно. Попробуй ещё раз'; state.msgGood=false; state.fact=''; return render(); }
  state.solved[w.id]=coordsForWord(w); state.msg='Отлично! Слово разгадано.'; state.msgGood=true; state.fact=w.fact;
  maybeFinish();
  const next=state.crossword.words.find(x=>!state.solved[x.id]);
  if(next) selectWord(next.id);
  render();
};

async function renderFinish(){
  const words=Object.keys(state.solved).length;
  app.innerHTML = `<div class='container'><div class='card'><h2>Кроссворд завершён!</h2>
  <p>Время: <b>${format(state.timer)}</b></p><p>Использовано подсказок: <b>${state.hintsUsed}</b></p><p>Решено слов: <b>${words}</b></p>
  <input id='playerName' placeholder='Твоё имя' maxlength='30'/>
  <button class='btn-main' onclick='saveResult()'>Отправить результат</button>
  <button onclick='location.hash="rating/${state.crossword.id}"'>Смотреть рейтинг</button>
  </div></div>`;
}
window.saveResult=async()=>{
  const name=document.getElementById('playerName').value.trim();
  await api(`/api/leaderboard/${state.crossword.id}`, {method:'POST', body:JSON.stringify({name,timeSeconds:state.timer,hintsUsed:state.hintsUsed,wordsSolved:Object.keys(state.solved).length})});
  location.hash=`rating/${state.crossword.id}`;
};

async function renderRating(id){
  const rows=await api(`/api/leaderboard/${id}`);
  app.innerHTML=`<div class='container'><div class='card'><h2>Рейтинг</h2><button onclick='location.hash="list"'>К списку</button></div>
  <div class='card'><table style='width:100%'><tr><th>#</th><th>Имя</th><th>Время</th><th>Подсказки</th><th>Дата</th></tr>
  ${rows.map((r,i)=>`<tr><td>${i+1}</td><td>${r.player_name}</td><td>${format(r.time_seconds)}</td><td>${r.hints_used}</td><td>${new Date(r.created_at).toLocaleString('ru-RU')}</td></tr>`).join('')}
  </table></div></div>`;
}

async function renderAdmin(){
  if(!adminToken){
    app.innerHTML=`<div class='container'><div class='card'><h2>Вход администратора</h2>
    <input id='login' placeholder='Логин' value='admin'/><input id='password' placeholder='Пароль' type='password' value='kids123'/>
    <button class='btn-main' onclick='adminLogin()'>Войти</button><button onclick='location.hash="list"'>Назад</button></div></div>`;
    return;
  }
  const [crosswords, skins] = await Promise.all([api('/api/admin/crosswords'), api('/api/admin/skins')]);
  app.innerHTML=`<div class='container'><div class='card'><h2>Админ-панель</h2><button onclick='logout()'>Выйти</button></div>
  <div class='grid2'>
    <div class='card'><h3>Загрузить кроссворд (zip)</h3><input type='file' id='cwZip'/><button onclick='uploadCw()'>Загрузить</button>
      <h3>Кроссворды</h3>
      ${crosswords.map(c=>`<div class='card'><b>${c.title}</b> (${c.id})<br/>Статус: ${c.published?'Опубликован':'Черновик'}<br/>
      Тема: <select id='skin-${c.id}'>${['<option value="">Без темы</option>',...skins.map(s=>`<option value='${s.id}' ${c.skin_id===s.id?'selected':''}>${s.title}</option>`)].join('')}</select>
      <div class='toolbar'><button onclick='bindSkin("${c.id}")'>Привязать тему</button><button onclick='pub("${c.id}",${!c.published})'>${c.published?'Снять с публикации':'Опубликовать'}</button><button onclick='delCw("${c.id}")'>Удалить</button></div></div>`).join('')}
    </div>
    <div class='card'><h3>Загрузить тему (zip)</h3><input type='file' id='skinZip'/><button onclick='uploadSkin()'>Загрузить тему</button>
      <h3>Темы</h3>${skins.map(s=>`<div class='card'><b>${s.title}</b> (${s.id})<br/><button onclick='delSkin("${s.id}")'>Удалить тему</button></div>`).join('')}
    </div>
  </div></div>`;
}
window.adminLogin=async()=>{ const login=document.getElementById('login').value,password=document.getElementById('password').value; const r=await api('/api/admin/login',{method:'POST',body:JSON.stringify({login,password})}); adminToken=r.token; localStorage.setItem('adminToken',adminToken); render();};
window.logout=()=>{adminToken='';localStorage.removeItem('adminToken');render();};
window.uploadCw=async()=>{const f=document.getElementById('cwZip').files[0]; if(!f)return; const fd=new FormData(); fd.append('file',f); await api('/api/admin/upload-crossword',{method:'POST',body:fd,headers:{'X-Admin-Token':adminToken}}); alert('Кроссворд загружен'); render();};
window.uploadSkin=async()=>{const f=document.getElementById('skinZip').files[0]; if(!f)return; const fd=new FormData(); fd.append('file',f); await api('/api/admin/upload-skin',{method:'POST',body:fd,headers:{'X-Admin-Token':adminToken}}); alert('Тема загружена'); render();};
window.pub=async(id,published)=>{await api(`/api/admin/crosswords/${id}/publish`,{method:'POST',body:JSON.stringify({published})});render();};
window.bindSkin=async(id)=>{const skinId=document.getElementById(`skin-${id}`).value||null; await api(`/api/admin/crosswords/${id}/skin`,{method:'POST',body:JSON.stringify({skinId})}); render();};
window.delCw=async(id)=>{if(confirm('Удалить кроссворд?')){await api(`/api/admin/crosswords/${id}`,{method:'DELETE'});render();}};
window.delSkin=async(id)=>{if(confirm('Удалить тему?')){await api(`/api/admin/skins/${id}`,{method:'DELETE'});render();}};

async function render(){
  const hash = location.hash.replace('#','') || 'list';
  state.msg='';
  try{
    if(hash==='list') return await renderList();
    if(hash.startsWith('game/')) return await renderGame(hash.split('/')[1]);
    if(hash==='finish') return await renderFinish();
    if(hash.startsWith('rating/')) return await renderRating(hash.split('/')[1]);
    if(hash==='admin') return await renderAdmin();
    location.hash='list';
  }catch(e){ app.innerHTML=`<div class='container'><div class='card'><h3>Ошибка</h3><p>${e.message}</p></div></div>`; }
}
window.addEventListener('hashchange', render);
render();
