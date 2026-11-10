-- 004: مسدود کردن کاربر و آخرین بازدید (برای دیتا شیت)
alter table users add column banned integer default 0;
alter table users add column last_seen real;
