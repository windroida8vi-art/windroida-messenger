-- 007: نسخه سبک ویدیو (low)، عکس ۷۲۰ پیکسلی (mid) و نرخ بیت هر نسخه (kbps) برای انتخاب کیفیت متناسب با سرعت اینترنت
-- null = هنوز بررسی نشده، '' = لازم نبود
alter table posts add column low text;
alter table posts add column mid text;
alter table posts add column kbps integer;
alter table posts add column lkbps integer;
