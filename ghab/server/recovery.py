"""سوال‌های امنیتی و نرمال‌سازی جواب (تا «علی»، «علي» و « علی » یکی حساب شوند)."""
import re
import unicodedata

from werkzeug.security import check_password_hash, generate_password_hash

QUESTIONS = [
    'اسم اولین مدرسه‌ات چی بود؟',
    'اسم حیوان خانگی دوران بچگی‌ات چی بود؟',
    'مادرت در کدام شهر به دنیا آمده؟',
    'اسم بهترین دوست دوران کودکی‌ات چی بود؟',
    'لقب بچگی‌ات چی بود؟',
    'اسم خیابانی که بچگی در آن بزرگ شدی چی بود؟',
    'اولین ماشینی که سوارش شدی چی بود؟',
]
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def norm(a):
    a = unicodedata.normalize('NFKC', a or '').lower().translate(_DIGITS)
    a = a.replace('ي', 'ی').replace('ك', 'ک')
    return re.sub(r'[\s\u200c\u200d.,،؛!؟?\-_]+', '', a)


def hash_answer(a):
    return generate_password_hash(norm(a))


def check_answer(h, a):
    return bool(h) and bool(norm(a)) and check_password_hash(h, norm(a))
