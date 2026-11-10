-- 005: بازیابی رمز با سوال امنیتی + ثبت بازدید استوری
alter table users add column sec_q text;
alter table users add column sec_a text;
create table if not exists story_views(
  story_id integer references stories(id) on delete cascade,
  viewer integer references users(id) on delete cascade,
  created real,
  primary key(story_id, viewer));
create index if not exists idx_sv_viewer on story_views(viewer);
