-- 008: ویژگی‌های اینستاگرام: اعلان‌ها، پاسخ و لایک نظر، گزارش، حذف پیام
create table if not exists notifications(
  id integer primary key,
  user_id integer references users(id) on delete cascade,
  actor integer references users(id) on delete cascade,
  type text not null,
  post_id integer references posts(id) on delete cascade,
  comment_id integer,
  created real,
  seen integer default 0);
create index if not exists idx_notif_user on notifications(user_id, id desc);
alter table comments add column parent_id integer;
create table if not exists comment_likes(
  comment_id integer references comments(id) on delete cascade,
  user_id integer references users(id) on delete cascade,
  primary key(comment_id, user_id));
create table if not exists reports(
  id integer primary key,
  reporter integer references users(id) on delete cascade,
  kind text, ref_id integer, reason text, created real, status text default 'open');
alter table messages add column deleted integer default 0;

-- فایل‌های قدیمی دست‌نخورده می‌مانند: همه «پردازش‌شده» علامت می‌خورند تا نه خودکار و نه با دکمه ادمین دوباره فشرده/بازسازی نشوند
update posts set optimized=1 where optimized=0;
update stories set optimized=1 where optimized=0;
update posts set low='' where low is null and kind='video';
update posts set mid='' where mid is null and kind='image';
