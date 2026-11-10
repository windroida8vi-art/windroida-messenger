-- 002: ایندکس‌ها برای سرعت (فید، ریلز، شمارش لایک و نظر، چت)
create index if not exists idx_posts_user on posts(user_id, id desc);
create index if not exists idx_posts_kind on posts(kind, id desc);
create index if not exists idx_comments_post on comments(post_id);
create index if not exists idx_comments_user on comments(user_id);
create index if not exists idx_likes_post on likes(post_id);
create index if not exists idx_saves_post on saves(post_id);
create index if not exists idx_follows_followee on follows(followee);
create index if not exists idx_stories_created on stories(created);
create index if not exists idx_msg_pair on messages(sender, receiver, id);
