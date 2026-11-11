'use strict';
/* Конфигурация разделов. c — колонки, q — по чему поиск, f — фильтры, dk — поле для фильтра по дате,
   e — редактируемые поля, a — поля формы добавления, act — действия в строке, del — удаление, x — экспорт.
   Типы полей: '' текст, 'number', 'date', 'email', 'bool', 'area' или массив значений для списка.
   Состав полей уточнится после согласования API-контракта (раздел 12 ТЗ). */
const CODE='1111'; // первая стадия входа; в реальной системе задаётся в конфигурации сервера
const MEAN=['— не указано','ID','Название / имя','Цена / сумма','Дата','Текст','Статус','Служебное, скрыть'];
const ST3=['new','in_work','closed'];
const SEC={
users:{t:'Пользователи',i:'👤',q:'ник, почта, ID',c:{id:'ID',nick:'Ник',email:'Почта',balance:'Баланс',status:'Статус'},e:{nick:'',email:'email',balance:'number',status:['active','blocked']},f:{status:['active','blocked']}},
lots:{t:'Лоты',i:'🏷️',q:'название, продавец, ID',c:{id:'ID',title:'Название',seller:'Продавец',price:'Цена',status:'Статус',fake:'Фейк'},e:{title:'',price:'number',status:['active','hidden','sold'],fake:'bool'},f:{status:['active','hidden','sold'],fake:['true','false']}},
news:{t:'Новости',i:'📰',c:{id:'ID',title:'Заголовок',text:'Текст',date:'Дата'},a:{title:'',text:'area',date:'date'},del:1},
support:{t:'Саппорт',i:'🎧',q:'кто, текст',c:{id:'ID',from:'От кого',date:'Дата',status:'Статус',text:'Текст'},e:{status:ST3},f:{status:ST3},dk:'date'},
banners:{t:'Баннеры',i:'🖼️',c:{id:'ID',place:'Место',title:'Название',from:'С',to:'По',active:'Включён'},a:{place:['между страницами','внутри раздела'],title:'',from:'date',to:'date'},e:{active:'bool',from:'date',to:'date'},del:1},
complaints:{t:'Жалобы',i:'⚠️',c:{id:'ID',type:'Тип',target:'Объект',status:'Статус',text:'Текст'},f:{type:['lot','user','shop','message'],status:['new','accepted','rejected','action']},act:[['accept','Принять'],['reject','Отклонить'],['measure','Применить меру']]},
promo:{t:'Продвижение',i:'⭐',c:{id:'ID',item:'Товар',slot:'Место',until:'До',paid:'Оплачено'},a:{item:'',slot:['Товар дня','Топ выдачи 1','Топ выдачи 2'],until:'date',paid:'number'},del:1},
bulk:{t:'Массовые операции',i:'⚙️'},
shops:{t:'Магазины',i:'🏬',q:'название, владелец',c:{id:'ID',name:'Название',owner:'Владелец',status:'Статус',promoted:'Продвигается'},e:{name:'',status:['active','blocked'],promoted:'bool'},f:{status:['active','blocked']}},
assistant:{t:'Помощник',i:'💬'},
refunds:{t:'Возвраты',i:'↩️',c:{id:'ID',user:'Пользователь',amount:'Сумма',reason:'Причина',status:'Статус'},e:{status:['pending','done','rejected']},f:{status:['pending','done','rejected']}},
profit:{t:'Прибыль',i:'💰'},
stats:{t:'Статистика',i:'📊'},
journal:{t:'Журнал действий',i:'📜',co:'audit',q:'админ, действие',c:{id:'№',time:'Время',admin:'Админ',action:'Действие',detail:'Подробности'},f:{admin:['super','moder']},dk:'time',x:1},
scan:{t:'Сканирование БД',i:'🔍'},
admins:{t:'Администраторы',i:'🛡️',c:{id:'ID',login:'Логин',role:'Роль',status:'Статус',sections:'Разделы'},a:{login:'',role:['admin','super'],sections:''},e:{status:['active','blocked'],sections:''},act:[['reset','Сбросить пароль']],del:1}
};
