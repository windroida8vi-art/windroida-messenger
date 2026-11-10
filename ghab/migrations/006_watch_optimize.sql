-- 006: رفتار تماشای ریلز (برای الگوریتم پیشنهاد) و علامت «فشرده‌شده» روی ویدیوها
create table if not exists watch(
  user_id integer references users(id) on delete cascade,
  post_id integer references posts(id) on delete cascade,
  secs real, dur real, plays integer default 1, created real,
  primary key(user_id, post_id));
create index if not exists idx_watch_post on watch(post_id);
alter table posts add column optimized integer default 0;
alter table stories add column optimized integer default 0;
-- عکس‌ها نیازی به فشرده‌سازی ویدیو ندارند
update posts set optimized=1 where kind='image';
update stories set optimized=1 where kind='image';
