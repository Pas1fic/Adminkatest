'use strict';
/* МОК-СЛОЙ вместо бэкенда. Интерфейс общается только через методы API ниже.
   Когда появится сервер, каждый метод заменяется на fetch к реальному эндпоинту,
   остальной код менять не нужно. Права, сессия и журнал здесь лишь имитация:
   настоящая проверка всегда на сервере. */
const API=(()=>{
const TTL=30*60e3,PAGE=10,SUPER=['journal','scan','admins'];
const N=['alex','maria','ivan','olga','denis','kate','sergey','nina','pavel','lena'];
const P=(a,i)=>a[i%a.length],D=i=>'2026-11-'+String(1+i%11).padStart(2,'0');
const R=(n,f,b=1)=>Array.from({length:n},(_,i)=>({id:b+i,...f(i)}));
const db={
users:R(55,i=>({nick:P(N,i)+i,email:P(N,i)+i+'@mail.test',balance:i*37%900,status:i%13?'active':'blocked'}),1000),
lots:R(70,i=>({title:'Лот №'+(i+1),seller:P(N,i)+i%55,price:100+i*17%900,status:P(['active','active','hidden','sold'],i),fake:i%11==0}),5000),
news:R(3,i=>({title:'Новость '+(i+1),text:'Текст новости '+(i+1),date:D(i)})),
support:R(25,i=>({from:P(N,i)+i,date:D(i),status:P(['new','in_work','closed'],i),text:'Не получается оплатить заказ №'+(900+i)}),300),
banners:R(2,i=>({place:i?'внутри раздела':'между страницами',title:'Баннер '+(i+1),from:'2026-11-01',to:'2026-12-01',active:true})),
complaints:R(20,i=>({type:P(['lot','user','shop','message'],i),target:'#'+(1000+i*3),status:P(['new','new','accepted','rejected'],i),text:'Подозрение на мошенничество'}),700),
promo:R(3,i=>({item:'Лот №'+(i+4),slot:P(['Товар дня','Топ выдачи 1','Топ выдачи 2'],i),until:'2026-11-2'+i,paid:500+i*250})),
shops:R(12,i=>({name:'Магазин '+(i+1),owner:P(N,i)+i,status:i%7?'active':'blocked',promoted:i%4==0}),200),
refunds:R(14,i=>({user:P(N,i)+i,amount:200+i*45,reason:P(['Не получен товар','Брак','Ошибка оплаты'],i),status:P(['pending','done','rejected'],i)}),400),
admins:[{id:1,login:'super',role:'super',status:'active',sections:'все'},
 {id:2,login:'moder',role:'admin',status:'active',sections:'users,lots,news,support,complaints,assistant,stats'}],
audit:[]};
const USERS={super:'Super#Pass12345',moder:'Moder#Pass12345'};
let S=null,tmp=null,fails={},meaning={};
const lag=()=>new Promise(r=>setTimeout(r,120));
const err=(m,code)=>Object.assign(new Error(m),{code});
const live=()=>!!S&&Date.now()-S.last<TTL;
const can=s=>live()&&(S.role=='super'||(!SUPER.includes(s)&&S.perms.includes(s)));
const key=c=>c=='audit'?'journal':c;
function need(s){if(!live())throw err('Сессия истекла',401);if(!can(s))throw err('Нет прав на этот раздел',403);S.last=Date.now()}
function mut(c){need(key(c));if(c=='audit')throw err('Журнал нельзя изменять',403)}
const log=(a,d)=>db.audit.unshift({id:db.audit.length+1,time:new Date().toISOString().slice(0,16).replace('T',' '),admin:S?S.login:'—',action:a,detail:d});
const OPS=[
{id:'delfake',t:'Удалить все фейковые лоты',c:'lots',m:x=>x.fake,run:x=>db.lots.splice(db.lots.indexOf(x),1)},
{id:'unhide',t:'Вернуть в продажу скрытые лоты',c:'lots',m:x=>x.status=='hidden',run:x=>{x.status='active'}},
{id:'closesup',t:'Закрыть все обращения в поддержку',c:'support',m:x=>x.status!='closed',run:x=>{x.status='closed'}},
{id:'rejnew',t:'Отклонить все новые жалобы',c:'complaints',m:x=>x.status=='new',run:x=>{x.status='rejected'}}];
const ACT={accept:'accepted',reject:'rejected',measure:'action'};
const KW=[['пользоват','users'],['лот','lots'],['новост','news'],['обращен|саппорт|поддерж','support'],['баннер','banners'],['жалоб','complaints'],['продвиж|товар дня','promo'],['массов','bulk'],['магазин','shops'],['возврат','refunds'],['прибыл','profit'],['статист','stats'],['журнал','journal'],['скан','scan'],['админист','admins']];
return{
can:s=>can(s),
me:()=>S&&{login:S.login,role:S.role},
left:()=>live()?Math.ceil((TTL-(Date.now()-S.last))/1000):0,
touch(){if(live())S.last=Date.now()},
logout(){if(live())log('logout','');S=null},
async login(l,p){await lag();const f=fails[l]||{n:0,t:0};
 if(f.t>Date.now())throw err('Слишком много попыток. Подождите минуту.');
 if(USERS[l]!==p){if(++f.n>=5){f.t=Date.now()+60e3;f.n=0}fails[l]=f;log('login_fail',l);throw err('Неверный логин или пароль')}
 fails[l]={n:0,t:0};tmp=l},
async verify(c){await lag();if(!tmp||c!=='000000')throw err('Неверный код');
 const a=db.admins.find(x=>x.login==tmp);if(a.status!='active')throw err('Учётная запись заблокирована');
 S={login:tmp,role:a.role,perms:a.sections.split(','),last:Date.now()};tmp=null;log('login','вход выполнен')},
async list(c,o={}){await lag();need(key(c));let r=db[c];const q=(o.q||'').toLowerCase();
 if(q)r=r.filter(x=>Object.values(x).some(v=>String(v).toLowerCase().includes(q)));
 for(const k in o.f||{})if(o.f[k])r=r.filter(x=>String(x[k])===o.f[k]);
 if(o.from&&o.dk)r=r.filter(x=>x[o.dk]>=o.from);
 if(o.all)return{rows:r.map(x=>({...x}))};
 const pages=Math.max(1,Math.ceil(r.length/PAGE)),pg=Math.min(o.page||1,pages);
 return{rows:r.slice((pg-1)*PAGE,pg*PAGE).map(x=>({...x})),total:r.length,pages}},
async save(c,id,p){await lag();mut(c);const r=db[c].find(x=>x.id==id);if(!r)throw err('Запись не найдена');
 const ch=Object.keys(p).filter(k=>r[k]!==p[k]).map(k=>k+': '+r[k]+' → '+p[k]);
 Object.assign(r,p);log('edit '+c+'#'+id,ch.join('; ')||'без изменений')},
async add(c,p){await lag();mut(c);const id=Math.max(0,...db[c].map(x=>x.id))+1;
 db[c].push({id,...p,...(c=='admins'?{status:'active'}:c=='banners'?{active:true}:{})});log('add '+c+'#'+id,JSON.stringify(p))},
async del(c,id){await lag();mut(c);const r=db[c].find(x=>x.id==id);if(!r)throw err('Запись не найдена');
 if(c=='admins'&&r.login==S.login)throw err('Нельзя удалить себя');
 db[c].splice(db[c].indexOf(r),1);log('delete '+c+'#'+id,JSON.stringify(r))},
async act(c,id,a){await lag();mut(c);const r=db[c].find(x=>x.id==id);
 if(ACT[a])r.status=ACT[a];log(a+' '+c+'#'+id,a=='reset'?'новый пароль отправлен на почту':'статус: '+r.status)},
async stats(){await lag();need('stats');const n=(c,f)=>db[c].filter(f||(()=>1)).length;
 return{upd:'по расписанию, раз в 15 минут',items:[['Пользователей',n('users')],['Активных',n('users',x=>x.status=='active')],['Лотов',n('lots')],['Фейковых лотов',n('lots',x=>x.fake)],['Новых жалоб',n('complaints',x=>x.status=='new')],['Новых обращений',n('support',x=>x.status=='new')]]}},
async profit(p){await lag();need('profit');
 const m={'Дни':['Пн','Вт','Ср','Чт','Пт','Сб','Вс'],'Недели':['Н1','Н2','Н3','Н4'],'Месяцы':['Авг','Сен','Окт','Ноя']}[p];
 const k=p=='Дни'?1:p=='Недели'?7:30,rows=m.map((l,i)=>[l,k*(120+i*53%90)]);
 return{rows,total:rows.reduce((a,x)=>a+x[1],0)}},
async bulk(id,cb){await lag();need('bulk');
 if(!id)return OPS.map(o=>({id:o.id,t:o.t,n:db[o.c].filter(o.m).length}));
 const o=OPS.find(x=>x.id==id),t=db[o.c].filter(o.m);
 for(let i=0;i<t.length;i+=10){t.slice(i,i+10).forEach(o.run);cb&&cb(Math.min(i+10,t.length));await new Promise(r=>setTimeout(r,150))}
 log('bulk '+id,'затронуто записей: '+t.length)},
async scan(){await lag();need('scan');const t={};
 for(const c of['users','lots','shops','refunds'])t[c]=Object.keys(db[c][0]);t.users.push('pwd_hash');
 return{tables:t,saved:{...meaning}}},
async saveScan(m){await lag();need('scan');meaning={...m};log('scan','сохранено полей: '+Object.keys(m).length)},
async ask(t){await lag();need('assistant');t=t.toLowerCase();
 const m=KW.find(([k])=>new RegExp(k).test(t));
 if(!m)return{text:'Пока не понял, о чём речь. Назовите раздел или действие, например: «как найти пользователя» или «где жалобы».'};
 return{go:m[1],text:(/удал|очист|массов/.test(t)?'Опасные действия я сам не выполняю: их делаете вы, после подтверждения. ':'')+'Это делается в отдельном разделе, кнопка ниже откроет его.'}}
};})();
