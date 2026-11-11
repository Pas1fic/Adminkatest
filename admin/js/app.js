'use strict';
const $=document.getElementById('app'),root=document.documentElement;
const st={d:{},chat:[]}; // состояние в памяти: фильтры, страницы, чат. Живёт до конца сессии
let tm;
const h=(t,a={},...c)=>{const e=document.createElement(t);
 for(const k in a){const v=a[k];if(k.startsWith('on')){v&&e.addEventListener(k.slice(2),v)}else if(v!==false&&v!=null)e.setAttribute(k,v===true?'':v)}
 for(const x of c.flat(9)){if(x===false||x==null)continue;e.append(x.nodeType?x:String(x))}return e};
const ls=(k,v)=>{try{return v?localStorage.setItem(k,v):localStorage.getItem(k)}catch{}};
root.dataset.theme=ls('th')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
const theme=()=>{root.dataset.theme=root.dataset.theme=='dark'?'light':'dark';ls('th',root.dataset.theme)};
addEventListener('pointerdown',()=>API.touch(),true);addEventListener('keydown',()=>API.touch(),true);

function toast(t){const e=h('div',{class:'toast',role:'status'},t);document.body.append(e);setTimeout(()=>e.remove(),3000)}
function dlg(...c){const d=h('dialog',{},...c);d.addEventListener('close',()=>d.remove());document.body.append(d);d.showModal();return d}
const ask=m=>new Promise(r=>{const d=dlg(h('h3',{},'Подтвердите действие'),h('p',{},m),h('div',{class:'row'},
 h('button',{class:'btn t',onclick:()=>d.close()},'Отмена'),h('button',{class:'btn',onclick:()=>{r(true);d.close()}},'Подтвердить')));
 d.addEventListener('close',()=>r(false))});
function fail(e){e.code==401?expire():toast(e.message||'Ошибка')}
function expire(){clearInterval(tm);API.logout();login('Сессия завершена: 30 минут без действий. Войдите снова.')}

function formDlg(title,fields,labels,vals,ok){
 const ins={};
 const rows=Object.entries(fields).map(([k,t])=>{let el;
  if(Array.isArray(t)){el=h('select',{},t.map(o=>h('option',{},o)));el.value=vals[k]??t[0]}
  else if(t=='bool'){el=h('input',{type:'checkbox'});el.checked=!!vals[k]}
  else if(t=='area'){el=h('textarea',{rows:4,required:true});el.value=vals[k]??''}
  else{el=h('input',{type:t||'text',required:true});el.value=vals[k]??''}
  ins[k]=el;return h('label',{class:'f'},h('span',{},labels[k]),el)});
 const d=dlg(h('form',{method:'dialog',onsubmit:async e=>{e.preventDefault();const p={};
  for(const k in ins){const t=fields[k],v=ins[k];p[k]=t=='bool'?v.checked:t=='number'?Number(v.value):v.value.trim()}
  if(await ok(p)!==false)d.close()}},h('h3',{},title),rows,
  h('div',{class:'row'},h('button',{type:'button',class:'btn t',onclick:()=>d.close()},'Отмена'),h('button',{class:'btn'},'Сохранить'))));
}

function shell(title,body,back=true){
 const tmr=h('span',{class:'tm',title:'До автоматического выхода'});
 const tick=()=>{const s=API.left();if(s<=0)return expire();tmr.textContent='⏱ '+Math.floor(s/60)+':'+String(s%60).padStart(2,'0')};
 clearInterval(tm);tm=setInterval(tick,1000);tick();
 $.replaceChildren(h('header',{class:'top'},back&&h('button',{class:'btn t',onclick:menu},'← В меню'),h('b',{class:'ttl'},title),h('span',{class:'sp'}),tmr,
  h('button',{class:'ib',title:'Светлая / тёмная тема','aria-label':'Сменить тему',onclick:theme},'◐'),
  h('button',{class:'btn t',onclick:()=>{clearInterval(tm);API.logout();login()}},'Выйти')),h('main',{},body));
}

/* ---------- Вход ---------- */
function stub(){ // нейтральная страница площадки; 10 нажатий за 4 с на иконку профиля открывают запрос кода
 let t=[];
 const ic=h('button',{class:'ib','aria-label':'Профиль',onclick:()=>{const n=Date.now();t=t.filter(x=>n-x<4000);t.push(n);if(t.length>=10){t=[];gate()}}},'👤');
 $.replaceChildren(h('header',{class:'top'},h('b',{class:'ttl'},'Площадка'),h('span',{class:'sp'}),ic),
  h('main',{},h('div',{class:'card'},h('h2',{},'Каталог'),h('p',{class:'mt'},'Здесь будет витрина площадки.'))));
}
function gate(){const i=h('input',{type:'password',inputmode:'numeric',autocomplete:'off','aria-label':'Код доступа'});
 const d=dlg(h('form',{method:'dialog',onsubmit:e=>{e.preventDefault();d.close();if(i.value===CODE)login()}},h('p',{},'Код доступа'),i,h('button',{class:'btn'},'OK')))}
function authCard(title,note,fields,onok,hint){
 const er=h('p',{class:'er',role:'alert'},note||'');
 const f=h('form',{class:'card auth',onsubmit:async e=>{e.preventDefault();try{await onok(...fields.map(x=>x.value))}catch(x){er.textContent=x.message}}},
  h('h2',{},title),fields.map(x=>h('label',{class:'f'},h('span',{},x.dataset.l),x)),er,h('button',{class:'btn'},'Далее'),hint&&h('p',{class:'mt'},hint));
 $.replaceChildren(h('main',{class:'c'},f));fields[0].focus();
}
function login(note){clearInterval(tm);
 const u=h('input',{required:true,autocomplete:'username','data-l':'Логин'}),p=h('input',{type:'password',required:true,autocomplete:'current-password','data-l':'Пароль'});
 authCard('Вход',note,[u,p],async(l,pw)=>{await API.login(l,pw);code()},'Демо: super / Super#Pass12345 или moder / Moder#Pass12345');
}
function code(){const c=h('input',{required:true,inputmode:'numeric',autocomplete:'one-time-code','data-l':'Код из письма'});
 authCard('Подтверждение',0,[c],async v=>{await API.verify(v);menu()},'Демо-код: 000000')}

/* ---------- Меню и разделы ---------- */
function menu(){shell('Меню · '+API.me().login,h('div',{class:'tiles'},Object.entries(SEC).filter(([k])=>API.can(k)).map(([k,s])=>
 h('button',{class:'tile',onclick:()=>open(k)},h('span',{class:'ic'},s.i),s.t))),false)}
function open(k){const box=h('div');shell(SEC[k].t,box);({bulk,assistant,profit,stats,scan}[k]||listView)(k,box)}

const GOOD=/^(active|done|accepted)$/,BAD=/^(blocked|rejected|new|pending)$/;
const cell=v=>typeof v=='boolean'?(v?'✓':'—'):typeof v=='string'&&(GOOD.test(v)||BAD.test(v))?h('span',{class:'bd '+(GOOD.test(v)?'ok':'bad')},v):v;

function listView(k,box){
 const s=SEC[k],co=s.co||k,d=st.d[k]??={q:'',page:1,f:{},from:''};
 const tw=h('div',{class:'tw'}),pg=h('div',{class:'pg'}),bar=h('div',{class:'bar'});
 const load=async()=>{try{draw(await API.list(co,{...d,dk:s.dk}))}catch(e){fail(e)}};
 const btn=(t,on,fn)=>h('button',{class:'btn t',disabled:!on,onclick:fn},t);
 const edit=r=>formDlg('Запись #'+r.id,s.e,s.c,r,async p=>{try{await API.save(co,r.id,p);toast('Сохранено');load()}catch(e){fail(e);return false}});
 const run=(label,r,fn)=>async()=>{if(await ask(label+' · запись #'+r.id+'?'))try{await fn();toast('Готово');load()}catch(e){fail(e)}};
 const draw=r=>{const cols=Object.keys(s.c),has=s.act||s.del;d.page=Math.min(d.page,r.pages);
  tw.replaceChildren(h('table',{},h('thead',{},h('tr',{},cols.map(c=>h('th',{},s.c[c])),has&&h('th',{},''))),
   h('tbody',{},r.rows.length?r.rows.map(r=>h('tr',{class:s.e?'cl':'',onclick:s.e&&(()=>edit(r))},cols.map(c=>h('td',{},cell(r[c]))),
    has&&h('td',{onclick:e=>e.stopPropagation()},(s.act||[]).map(([a,l])=>h('button',{class:'btn t sm',onclick:run(l,r,()=>API.act(co,r.id,a))},l)),
     s.del&&h('button',{class:'btn t sm',onclick:run('Удалить',r,()=>API.del(co,r.id))},'Удалить')))):
    h('tr',{},h('td',{colspan:cols.length+1},'Ничего не найдено. Измените поиск или фильтры.')))));
  pg.replaceChildren(btn('←',d.page>1,()=>{d.page--;load()}),h('span',{},`стр. ${d.page} из ${r.pages} · всего ${r.total}`),btn('→',d.page<r.pages,()=>{d.page++;load()}))};
 if(s.q){const q=h('input',{type:'search',placeholder:'Поиск: '+s.q,'aria-label':'Поиск'});q.value=d.q;let t;
  q.oninput=()=>{clearTimeout(t);t=setTimeout(()=>{d.q=q.value;d.page=1;load()},250)};bar.append(q)}
 for(const[fk,o]of Object.entries(s.f||{})){const f=h('select',{'aria-label':s.c[fk]},h('option',{value:''},s.c[fk]+': все'),o.map(v=>h('option',{},v)));
  f.value=d.f[fk]||'';f.onchange=()=>{d.f[fk]=f.value;d.page=1;load()};bar.append(f)}
 if(s.dk){const f=h('input',{type:'date','aria-label':'С даты',title:'С даты'});f.value=d.from;f.onchange=()=>{d.from=f.value;d.page=1;load()};bar.append(f)}
 if(s.a)bar.append(h('button',{class:'btn',onclick:()=>formDlg('Добавить',s.a,s.c,{},async p=>{try{await API.add(co,p);toast('Добавлено');load()}catch(e){fail(e);return false}})},'+ Добавить'));
 if(s.x)bar.append(h('button',{class:'btn t',onclick:async()=>{try{const{rows}=await API.list(co,{...d,all:true,dk:s.dk}),cols=Object.keys(s.c);
  const csv=[cols.map(c=>s.c[c]),...rows.map(r=>cols.map(c=>r[c]))].map(r=>r.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\n');
  const a=h('a',{href:URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv'})),download:co+'.csv'});a.click();URL.revokeObjectURL(a.href)}catch(e){fail(e)}}},'Экспорт CSV'));
 box.append(bar,tw,pg);load();
}

/* ---------- Особые разделы ---------- */
async function stats(k,box){try{const r=await API.stats();
 box.append(h('p',{class:'mt'},'Данные обновляются '+r.upd+', а не при каждом открытии.'),h('div',{class:'cards'},r.items.map(([l,v])=>h('div',{class:'card st'},h('b',{},v),h('span',{},l)))))}catch(e){fail(e)}}

async function profit(k,box){const d=st.d.profit??={p:'Дни'},out=h('div');
 box.append(h('div',{class:'bar'},['Дни','Недели','Месяцы'].map(p=>h('button',{class:'btn'+(p==d.p?'':' t'),onclick:()=>{d.p=p;box.replaceChildren();profit(k,box)}},p))),out);
 try{const r=await API.profit(d.p),m=Math.max(...r.rows.map(x=>x[1]));
  out.append(h('div',{class:'card st'},h('b',{},r.total),h('span',{},'Прибыль за период')),
   h('div',{class:'card chart'},r.rows.map(([l,v])=>{const i=h('i');i.style.height=v/m*80+'%';return h('div',{class:'col'},v,i,l)})))}catch(e){fail(e)}}

async function bulk(k,box){try{const ops=await API.bulk();
 box.append(h('p',{class:'mt'},'Перед запуском показывается, сколько записей затронет операция. Выполняется пакетами по 10.'),
 ops.map(o=>h('div',{class:'card row2'},h('div',{},h('b',{},o.t),h('div',{class:'mt'},'Будет затронуто записей: '+o.n)),
  h('button',{class:'btn',disabled:!o.n,onclick:async()=>{
   if(!await ask(`«${o.t}»: будет затронуто записей: ${o.n}. Выполнить?`))return;
   const pr=h('progress',{max:o.n,value:0}),d=dlg(h('h3',{},o.t),pr);
   try{await API.bulk(o.id,n=>{pr.value=n});toast('Готово')}catch(e){fail(e)}
   d.close();box.replaceChildren();bulk(k,box)}},'Выполнить'))))}catch(e){fail(e)}}

async function scan(k,box){try{const r=await API.scan(),sel={};
 box.append(h('p',{class:'mt'},'Для каждого поля укажите, что это. Ответы запоминаются и при следующих сканированиях подставляются сами.'),
 Object.entries(r.tables).map(([t,fs])=>h('details',{class:'card',open:t=='users'},h('summary',{},t+' · полей: '+fs.length),
  fs.map(f=>{const s=h('select',{'aria-label':t+'.'+f},MEAN.map(m=>h('option',{},m)));s.value=r.saved[t+'.'+f]||MEAN[0];sel[t+'.'+f]=s;
   return h('label',{class:'f in'},h('code',{},f),s)}))),
 h('button',{class:'btn',onclick:async()=>{const m={};for(const x in sel)m[x]=sel[x].value;try{await API.saveScan(m);toast('Сохранено')}catch(e){fail(e)}}},'Сохранить ответы'))}catch(e){fail(e)}}

function assistant(k,box){
 if(!st.chat.length)st.chat.push({w:'b',t:'Здравствуйте! Спросите, где что найти или как выполнить действие. Я подскажу и открою нужный раздел.'});
 const log=h('div',{class:'chat','aria-live':'polite'}),inp=h('input',{placeholder:'Например: где жалобы?','aria-label':'Вопрос помощнику'});
 const draw=()=>log.replaceChildren(...st.chat.map(m=>h('div',{class:'m '+m.w},m.t,m.go&&API.can(m.go)&&h('div',{},h('button',{class:'btn',onclick:()=>open(m.go)},'Открыть: '+SEC[m.go].t)))));
 box.append(log,h('form',{class:'send',onsubmit:async e=>{e.preventDefault();const t=inp.value.trim();if(!t)return;inp.value='';
  st.chat.push({w:'u',t});draw();try{const r=await API.ask(t);st.chat.push({w:'b',...r});draw()}catch(x){fail(x)}}},inp,h('button',{class:'btn'},'Отправить')));
 draw();
}

stub();
