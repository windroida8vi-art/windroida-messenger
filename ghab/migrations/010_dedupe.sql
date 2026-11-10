-- 010: اثر انگشت (sha1) فایل ویدیو تا آپلودهای تکراریِ یک فایل دوباره‌دوباره در ریلز نیایند
alter table posts add column sha text;
create index if not exists idx_posts_sha on posts(sha);
