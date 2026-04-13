# Meme Bot V3 Starter

نسخة Starter منظمة لبوت رادار + تقييم + paper trading لعملات الميم على سولانا.

## التشغيل

1. انسخ `.env.example` إلى `.env`
2. ضع Telegram token جديد وآمن
3. ثبّت المتطلبات:
   ```bash
   pip install -r requirements.txt
   ```
4. شغّل:
   ```bash
   python app.py
   ```

## الموجود في هذه النسخة
- اكتشاف أولي من DexScreener boosts
- إثراء بيانات pairs
- فلترة أولية
- safety score
- total scoring
- signal classification
- Telegram bot commands
- SQLite storage
- paper trading skeleton

## ملاحظات
- هذه نسخة تأسيسية وليست جاهزة لتداول حقيقي.
- لازم تغيّر التوكن القديم المكشوف وتستخدم توكن جديد داخل `.env`.
