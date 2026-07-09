import feedparser
import anthropic
import os
import json
import re
from datetime import datetime, timedelta, timezone
from telegram import Bot
import asyncio

# ─────────────────────────────────────────
#  НАСТРОЙКИ — заполни своими значениями
# ─────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "ВАШ_ТОКЕН_БОТА")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "ВАШ_CHAT_ID")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY",  "ВАШ_ANTHROPIC_KEY")
NETLIFY_SITE_ID    = os.environ.get("NETLIFY_SITE_ID",    "ВАШ_SITE_ID")
NETLIFY_TOKEN      = os.environ.get("NETLIFY_TOKEN",      "ВАШ_NETLIFY_TOKEN")

DESIGN_CHANNELS = [
    "pdigest", "figmadesign", "nowhow", "design_translator", "conceptui",
    "dnative", "mellow_io", "ludochka_plugins", "setters", "goodux",
    "lookziner", "uxcall", "visualkava", "queeriosity", "poyasnizaux",
    "poledsgn", "DesignDictatorship", "designpub", "meow_design",
    "aniaamelnik", "mozhno", "chem_dokazhesh", "product_thoughts",
    "microcopy", "slashdesigner", "neural_prosecco", "AI_Handler",
    "girlsvibecode", "imageryna", "iiiiiiija", "ProductsAndStartups",
]

OTHER_CHANNELS = [
    "TatFeodoridy", "olga_career", "osoznatorika", "Katerinalengold",
    "notburningout", "svetlana_psyhodietolog", "adhd_pokus",
    "trevozhnie_sirniky", "luv_coach", "DissectedPsychologist",
    "zeniasofronovHQ", "turyatka", "concertzaal", "coachpolishuk", "ohwrld",
]

RSSHUB_BASE = "https://rsshub.app/telegram/channel"

# ─────────────────────────────────────────
#  ШАГИ
# ─────────────────────────────────────────

def fetch_posts_from_channel(username: str, hours: int = 24) -> list[dict]:
    """Читает RSS канала и возвращает посты за последние hours часов."""
    url = f"{RSSHUB_BASE}/{username}"
    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    posts = []
    for entry in feed.entries:
        published = entry.get("published_parsed")
        if published:
            pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue
        text = entry.get("summary", "") or entry.get("title", "")
        # убираем HTML-теги
        text = re.sub(r"<[^>]+>", " ", text).strip()
        link = entry.get("link", f"https://t.me/{username}")
        title = entry.get("title", "")
        title = re.sub(r"<[^>]+>", " ", title).strip()
        posts.append({"text": text, "link": link, "title": title})
    return posts


def summarise_channel(client: anthropic.Anthropic, channel: str, posts: list[dict]) -> dict | None:
    """Отправляет посты в Claude и получает саммари. Возвращает None если только реклама."""
    posts_text = "\n\n---\n\n".join(
        f"Пост {i+1} (ссылка: {p['link']}):\n{p['text']}"
        for i, p in enumerate(posts)
    )
    prompt = f"""Ты помогаешь составить ежедневный дайджест Telegram-каналов.

Канал: @{channel}
Посты за сегодня:

{posts_text}

Твоя задача:
1. Проигнорируй рекламные посты. Признаки рекламы: слова "реклама", "партнёрский материал", "erid", "спонсор", "запишись", "купи", "успей", "осталось мест", "#реклама", "#ad", ссылки на оплату или регистрацию на курс, промокоды.
2. Если все посты рекламные — верни JSON: {{"skip": true}}
3. Если есть нерекламные посты — объедини их в одно краткое описание (2-4 предложения), что обсуждалось в канале сегодня. Пиши живо и по существу, без воды.
4. Верни JSON строго в таком формате (без markdown, без пояснений):
{{"skip": false, "summary": "текст саммари", "first_post_link": "ссылка на первый нерекламный пост"}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if data.get("skip"):
        return None
    return {
        "summary": data.get("summary", ""),
        "link": data.get("first_post_link", f"https://t.me/{channel}"),
    }


def get_channel_title(username: str) -> str:
    """Берёт официальное название канала из RSS."""
    url = f"{RSSHUB_BASE}/{username}"
    feed = feedparser.parse(url)
    title = feed.feed.get("title", username)
    title = re.sub(r"<[^>]+>", "", title).strip()
    # RSSHub часто добавляет «- Telegram» в конец
    title = re.sub(r"\s*[-–]\s*Telegram\s*$", "", title, flags=re.IGNORECASE)
    return title or username


def build_html(design_cards: list[dict], other_cards: list[dict]) -> str:
    """Собирает HTML-страницу дайджеста."""
    today = datetime.now()
    weekdays_ru = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
    months_ru   = ["января","февраля","марта","апреля","мая","июня",
                   "июля","августа","сентября","октября","ноября","декабря"]
    date_str = f"{weekdays_ru[today.weekday()]}, {today.day} {months_ru[today.month-1]} {today.year}"
    total_channels = len(design_cards) + len(other_cards)
    time_str = today.strftime("%H:%M")

    def cards_html(cards: list[dict]) -> str:
        html = ""
        for c in cards:
            count_label = f"{c['count']} {'пост' if c['count'] == 1 else 'поста' if c['count'] in [2,3,4] else 'постов'}"
            html += f"""
        <div style="margin-bottom:1rem;padding:1rem 1.25rem;background:#FFFFFD;border-radius:12px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
            <span style="font-size:15px;font-weight:500;color:#1a1a1a;">{c['title']}</span>
            <span style="font-size:12px;color:#999;">{count_label}</span>
          </div>
          <p style="font-size:14px;color:#555;margin:0 0 12px;line-height:1.7;">{c['summary']}</p>
          <a href="{c['link']}" style="font-size:13px;color:#378ADD;text-decoration:none;">читать пост</a>
        </div>"""
        return html

    design_section = ""
    if design_cards:
        design_section = f"""
      <div style="margin-bottom:2.5rem;">
        <div style="margin-bottom:1.25rem;padding-bottom:10px;border-bottom:0.5px solid #e0e0e0;">
          <h2 style="font-size:18px;font-weight:500;margin:0;color:#1a1a1a;">Чем порадуют сегодня новости дизайна</h2>
        </div>
        {cards_html(design_cards)}
      </div>"""

    other_section = ""
    if other_cards:
        other_section = f"""
      <div style="margin-bottom:2.5rem;">
        <div style="margin-bottom:1.25rem;padding-bottom:10px;border-bottom:0.5px solid #e0e0e0;">
          <h2 style="font-size:18px;font-weight:500;margin:0;color:#1a1a1a;">Что ещё творится в мире</h2>
        </div>
        {cards_html(other_cards)}
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Дайджест {date_str}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #F8FEFF;
      color: #1a1a1a;
      padding: 2rem 1rem;
    }}
    .container {{
      max-width: 680px;
      margin: 0 auto;
    }}
    a {{ color: #378ADD; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="container">

    <div style="margin-bottom:2.5rem;">
      <p style="font-size:13px;color:#999;margin-bottom:6px;">{date_str}</p>
      <h1 style="font-size:22px;font-weight:500;margin-bottom:8px;color:#1a1a1a;">Дайджест телеграма за день для моей госпожи 👑</h1>
      <p style="font-size:14px;color:#666;">{total_channels} каналов · реклама отфильтрована</p>
    </div>

    {design_section}
    {other_section}

    <div style="margin-top:2rem;padding-top:1rem;border-top:0.5px solid #e0e0e0;">
      <p style="font-size:12px;color:#aaa;">Сгенерировано в {time_str} · следующий дайджест завтра утром</p>
    </div>

  </div>
</body>
</html>"""


def deploy_to_netlify(html: str, site_id: str, token: str) -> str:
    """Деплоит index.html на Netlify и возвращает URL."""
    import urllib.request
    import zipfile
    import io
    import hashlib

    # Создаём zip с index.html
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", html.encode("utf-8"))
    buf.seek(0)
    zip_bytes = buf.read()

    url = f"https://api.netlify.com/api/v1/sites/{site_id}/deploys"
    req = urllib.request.Request(
        url,
        data=zip_bytes,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/zip",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data.get("deploy_ssl_url") or data.get("url", "")


async def send_telegram_message(token: str, chat_id: str, text: str):
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


def main():
    print("▶ Запускаю дайджест...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    design_cards = []
    other_cards  = []

    all_channels = [("design", ch) for ch in DESIGN_CHANNELS] + \
                   [("other",  ch) for ch in OTHER_CHANNELS]

    for group, username in all_channels:
        print(f"  → {username}")
        posts = fetch_posts_from_channel(username)
        if not posts:
            print(f"     нет постов, пропускаю")
            continue

        result = summarise_channel(client, username, posts)
        if not result:
            print(f"     только реклама, пропускаю")
            continue

        title = get_channel_title(username)
        card = {
            "title":   title,
            "summary": result["summary"],
            "link":    result["link"],
            "count":   len(posts),
        }
        if group == "design":
            design_cards.append(card)
        else:
            other_cards.append(card)
        print(f"     ✓ {title}")

    if not design_cards and not other_cards:
        print("Нет контента для дайджеста.")
        return

    print("▶ Собираю HTML...")
    html = build_html(design_cards, other_cards)

    # Сохраняем локально для проверки
    with open("output/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("  ✓ output/index.html сохранён")

    print("▶ Деплою на Netlify...")
    page_url = deploy_to_netlify(html, NETLIFY_SITE_ID, NETLIFY_TOKEN)
    print(f"  ✓ {page_url}")

    print("▶ Отправляю в Telegram...")
    message = f"☀️ Дайджест готов\n{page_url}"
    asyncio.run(send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message))
    print("  ✓ Сообщение отправлено")
    print("✅ Готово!")


if __name__ == "__main__":
    main()
