'use strict';
/* Конфигурация разделов. c — колонки, q — по чему поиск, f — фильтры, dk — поле для фильтра по дате,
   e — редактируемые поля, a — поля формы добавления, act — действия в строке, del — удаление, x — экспорт.
   Типы полей: '' текст, 'number', 'date', 'email', 'bool', 'area' или массив значений для списка.
   Состав полей уточнится после согласования API-контракта (раздел 12 ТЗ). */
const CODE='1111'; // первая стадия входа; в реальной системе задаётся в конфигурации сервера
const MEAN=['— не указано','ID','Название / имя','Цена / сумма','Дата','Текст','Статус','Служебное, скрыть'];
const ST3=['new','in_work','closed'];
const SEC={
users:{t:'Пользователи',i:'👤',q:'никнейму, почте, ID или магазину',c:{id:'ID',nick:'Ник',email:'Почта',balance:'Баланс',status:'Статус',fake:'Фейк',last_login:'Последний вход'},e:{nick:'',email:'email',balance:'number',status:['active','blocked'],fake:'bool',last_login:'date'},f:{status:['active','blocked']}},
lots:{t:'Лоты',i:'🏷️',q:'название, продавец, ID, категория',c:{id:'ID',title:'Название',seller:'Продавец',price:'Цена',status:'Статус',fake:'Фейк',category:'Категория',subcategory:'Подкатегория',auction_date:'Аукцион'},e:{title:'',seller:'',price:'number',status:['active','hidden','sold'],fake:'bool',category:'',subcategory:'',auction_date:'date'},f:{status:['active','hidden','sold'],fake:['true','false']}},
news:{t:'Новости',i:'📰',q:'заголовок, описание, текст новости',c:{id:'ID',cat:'Категория',badge:'Метка',title:'Заголовок',desc:'Описание',published:'Дата публикации'},defaults:{cat:'update',badge:'',desc:'',body:'',img:'',read_time:'2 мин'},a:{cat:'',badge:'',title:'',desc:'area',body:'area',img:'',read_time:'',published:''},e:{cat:'',badge:'',title:'',desc:'area',body:'area',img:'',read_time:'',published:''},del:1,x:1},
support:{t:'Саппорт',i:'🎧',q:'имя, почта, заголовок, сообщение',c:{id:'ID',date_message:'Дата',header_message:'Тема',priority:'Приоритет',message:'Сообщение',user_name:'Пользователь',user_mail:'Почта',proof:'Вложение'},defaults:{priority:'mid',user_id:'none',user_name:'',user_mail:''},a:{date_message:'',header_message:'',message:'area',priority:['low','mid','high'],proof:'blob',user_id:'',user_name:'',user_mail:''},e:{date_message:'',header_message:'',message:'area',priority:['low','mid','high'],proof:'blob',user_id:'',user_name:'',user_mail:''},del:1,x:1},
banners:{t:'Баннеры',i:'🖼️',c:{id:'ID',place:'Место',title:'Название',from:'С',to:'По',active:'Включён',paid:'Оплачен',amount:'Доход'},a:{place:['category','header','category_header','footer','home_carousel','home_current','mobile_super'],title:'',from:'date',to:'date',active:'bool',paid:'bool',amount:'number'},e:{place:['category','header','category_header','footer','home_carousel','home_current','mobile_super'],title:'',from:'date',to:'date',active:'bool',paid:'bool',amount:'number'},del:1},
complaints:{t:'Жалобы',i:'⚠️',q:'причина, сообщение, пользователь, почта',c:{id:'ID',date_message:'Дата',reason:'Причина',message:'Сообщение',link_proof:'Ссылка',email_user:'Почта',user_name:'Пользователь',proof:'Вложение'},defaults:{link_proof:'none',user_id:'none',user_name:''},a:{date_message:'',reason:'',message:'area',proof:'blob',link_proof:'',email_user:'',user_id:'',user_name:''},e:{date_message:'',reason:'',message:'area',proof:'blob',link_proof:'',email_user:'',user_id:'',user_name:''},del:1,x:1},
promotion:{t:'Продвижение',i:'⭐',c:{id:'ID',item:'Товар',slot:'Место',until:'До',paid:'Оплачено'},a:{item:'',slot:['Товар дня','Топ выдачи 1','Топ выдачи 2'],until:'date',paid:'number'},del:1},
bulk:{t:'Массовые операции',i:'⚙️'},
shops:{t:'Магазины',i:'🏬',q:'название, владелец',c:{id:'ID',name:'Название',owner:'Владелец',status:'Статус',promoted:'Продвигается'},e:{name:'',owner:'',status:['active','blocked'],promoted:'bool'},f:{status:['active','blocked']}},
assistant:{t:'Помощник',i:'💬'},
refunds:{t:'Возвраты',i:'↩️',c:{id:'ID',user:'Пользователь',amount:'Сумма',reason:'Причина',status:'Статус'},e:{status:['pending','done','rejected']},f:{status:['pending','done','rejected']}},
profit:{t:'Прибыль',i:'💰'},
stats:{t:'Статистика',i:'📊'},
journal:{t:'Журнал действий',i:'📜',co:'audit',q:'админ, действие',c:{id:'№',time:'Время',admin:'Админ',action:'Действие',detail:'Подробности'},f:{admin:['super','moder']},dk:'time',x:1},
scan:{t:'Сканирование БД',i:'🔍'},
admins:{t:'Администраторы',i:'🛡️',q:'логин, email',c:{id:'ID',login:'Логин',email:'Email',role:'Роль',status:'Статус',sections:'Разделы'},a:{login:'',email:'email',password:'password',role:['admin','super'],sections:''},e:{login:'',email:'email',role:['admin','super'],status:['active','blocked'],sections:''},f:{role:['admin','super']},logs:1},
currencies:{t:'Курсы валют',i:'💱',c:{id:'ID',code:'Валюта',rate:'Единиц за 1 USD',updated:'Обновлено'},e:{rate:'number'},a:{code:'',rate:'number'},del:1},
newsletter:{t:'Подписчики рассылки',i:'✉️',q:'почта',c:{id:'ID',email:'Почта',status:'Подписка',joined:'Дата подписки'},f:{status:['active','unsubscribed']}},
transactions:{t:'Лог транзакций',i:'🧾',q:'пользователь, операция, ID',c:{id:'ID',date:'Дата',user:'Пользователь',type:'Операция',amount:'Сумма',status:'Статус'},f:{status:['success','pending','failed']}}
};
