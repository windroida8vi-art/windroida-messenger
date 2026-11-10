-- 011: ورود یکپارچه با حساب ویندروید. wd_name = نام دقیق کاربر در ویندروید؛ اکانتِ قاب فقط از روی همین پیدا می‌شود
alter table users add column wd_name text;
create unique index if not exists users_wd on users(wd_name);
