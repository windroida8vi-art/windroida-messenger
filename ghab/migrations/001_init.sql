-- 001: جدول‌های اولیه قاب
create table if not exists users(id integer primary key, username text unique not null, pass text not null,
  name text default '', bio text default '', avatar text, created real);
create table if not exists posts(id integer primary key, user_id integer not null references users(id) on delete cascade,
  file text not null, kind text not null, caption text default '', created real);
create table if not exists likes(user_id integer references users(id) on delete cascade,
  post_id integer references posts(id) on delete cascade, primary key(user_id, post_id));
create table if not exists saves(user_id integer references users(id) on delete cascade,
  post_id integer references posts(id) on delete cascade, primary key(user_id, post_id));
create table if not exists comments(id integer primary key, post_id integer references posts(id) on delete cascade,
  user_id integer references users(id) on delete cascade, text text not null, created real);
create table if not exists follows(follower integer references users(id) on delete cascade,
  followee integer references users(id) on delete cascade, primary key(follower, followee));
create table if not exists stories(id integer primary key, user_id integer references users(id) on delete cascade,
  file text not null, kind text not null, created real);
create table if not exists messages(id integer primary key, sender integer references users(id) on delete cascade,
  receiver integer references users(id) on delete cascade, text text default '', post_id integer references posts(id) on delete set null,
  created real, seen integer default 0);
create index if not exists msg_rx on messages(receiver, seen);
