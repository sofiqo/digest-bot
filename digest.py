import anthropic
import os
import json
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from telegram import Bot
import asyncio

# ─────────────────────────────────────────
#  НАСТРОЙКИ
# ─────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "ВАШ_ТОКЕН_БОТА")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "ВАШ_CHAT_ID")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY",  "ВАШ_ANTHROPIC_KEY")
GITHUB_REPO        = os.environ.get("GITHUB_REPO",        "sofiqo/digest-bot")
GITHUB_TOKEN       = os.environ.get("GITHUB_TOKEN",       "")

DESIGN_CHANNELS = [
    "pdigest", "figmadesign", "nowhow", "design_translator", "conceptui",
    "dnative", "mellow_io", "ludochka_plugins", "setters", "goodux",
    "lookziner", "uxcall", "visualkava", "queeriosity", "poyasnizaux",
    "poledsgn", "DesignDictatorship", "designpub", "meow_design",
    "aniaamelnik", "mozhno", "chem_dokazhesh", "product_thoughts",
    "microcopy", "slashdesigner", "neural_prosecco", "AI_Handler",
    "girlsvibecode", "imageryna", "iiiiiiija", "ProductsAndStartups", "study_kvo", "meow_design",
]

OTHER_CHANNELS = [
    "olga_career", "osoznatorika", "Katerinalengold",
    "notburningout", "adhd_pokus",
    "trevozhnie_sirniky", "luv_coach", "DissectedPsychologist",
    "zeniasofronovHQ", "turyatka", "concertzaal", "coachpolishuk", "myachPRO", "yurydud",
]

WTF_CHANNELS = [
    "varlamov_news",
]

EMIGRATION_CHANNELS = [
    "ArkHelp", "emigriceps_spain", "duditagain", "Psymigration",
    "emigriceps", "Oreshka_in_London", "smenastation", "iworldcom",
    "spain_simple", "ohwrld",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

# ─────────────────────────────────────────
#  ПАРСИНГ t.me/s/username
# ─────────────────────────────────────────

def fetch_posts_from_channel(username: str, hours: int = 36) -> list[dict]:
    """Парсит веб-версию Telegram-канала и возвращает посты за последние hours часов."""
    url = f"https://t.me/s/{username}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        print(f"     [debug] status={resp.status_code} len={len(resp.text)}")
        if resp.status_code != 200:
            return []
    except Exception as e:
        print(f"     [debug] request error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    posts = []

    for msg in soup.select(".tgme_widget_message"):
        # Дата поста
        time_tag = msg.select_one(".tgme_widget_message_date time")
        if time_tag and time_tag.get("datetime"):
            try:
                pub_dt = datetime.fromisoformat(time_tag["datetime"].replace("Z", "+00:00"))
                if pub_dt < cutoff:
                    continue
            except Exception:
                pass

        # Текст поста
        text_tag = msg.select_one(".tgme_widget_message_text")
        text = text_tag.get_text(separator=" ", strip=True) if text_tag else ""
        if not text:
            continue

        # Ссылка на пост
        link_tag = msg.select_one(".tgme_widget_message_date")
        link = link_tag["href"] if link_tag and link_tag.get("href") else f"https://t.me/{username}"

        posts.append({"text": text, "link": link})

    print(f"     [debug] found {len(posts)} posts")
    return posts


def get_channel_title(username: str) -> str:
    """Берёт официальное название канала с веб-страницы."""
    url = f"https://t.me/s/{username}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return username
        soup = BeautifulSoup(resp.text, "html.parser")
        title_tag = soup.select_one(".tgme_channel_info_header_title")
        if title_tag:
            return title_tag.get_text(strip=True)
    except Exception:
        pass
    return username


# ─────────────────────────────────────────
#  СУММАРИЗАЦИЯ
# ─────────────────────────────────────────

def summarise_channel(client: anthropic.Anthropic, channel: str, posts: list[dict]) -> dict | None:
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


# ─────────────────────────────────────────
#  HTML
# ─────────────────────────────────────────

def build_html(design_cards: list[dict], other_cards: list[dict], emigration_cards: list[dict], wtf_cards: list[dict]) -> str:
    today = datetime.now()
    weekdays_ru = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
    months_ru   = ["января","февраля","марта","апреля","мая","июня",
                   "июля","августа","сентября","октября","ноября","декабря"]
    date_str = f"{weekdays_ru[today.weekday()]}, {today.day} {months_ru[today.month-1]} {today.year}"
    total_channels = len(design_cards) + len(other_cards) + len(emigration_cards) + len(wtf_cards)
    time_str = today.strftime("%H:%M")

    def cards_html(cards):
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
          <h2 style="font-size:18px;font-weight:500;margin:0;color:#1a1a1a;">Новости дизайна</h2>
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

    emigration_section = ""
    if emigration_cards:
        emigration_section = f"""
      <div style="margin-bottom:2.5rem;">
        <div style="margin-bottom:1.25rem;padding-bottom:10px;border-bottom:0.5px solid #e0e0e0;">
          <h2 style="font-size:18px;font-weight:500;margin:0;color:#1a1a1a;">Эмигрейшн ✈️</h2>
        </div>
        {cards_html(emigration_cards)}
      </div>"""

    wtf_section = ""
    if wtf_cards:
        wtf_section = f"""
      <div style="margin-bottom:2.5rem;">
        <div style="margin-bottom:1.25rem;padding-bottom:10px;border-bottom:0.5px solid #e0e0e0;">
          <h2 style="font-size:18px;font-weight:500;margin:0;color:#1a1a1a;">Ну и пиздец</h2>
        </div>
        {cards_html(wtf_cards)}
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
    .container {{ max-width: 680px; margin: 0 auto; }}
    a {{ color: #378ADD; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="container">
    <div style="margin-bottom:2.5rem;">
      <p style="font-size:13px;color:#999;margin-bottom:6px;">{date_str}</p>
      <h1 style="font-size:22px;font-weight:500;margin-bottom:8px;color:#1a1a1a;">Что нового в телеграме</h1>
      <p style="font-size:14px;color:#666;">{total_channels} каналов · реклама отфильтрована</p>
    </div>
    {design_section}
    {other_section}
    {emigration_section}
    {wtf_section}
    <div style="margin-top:2rem;padding-top:1rem;border-top:0.5px solid #e0e0e0;">
      <p style="font-size:12px;color:#aaa;">Сгенерировано в {time_str} · следующий дайджест завтра утром</p>
    </div>
  </div>
</body>
</html>"""


# ─────────────────────────────────────────
#  NETLIFY + TELEGRAM
# ─────────────────────────────────────────

def deploy_to_github_pages(html: str, repo: str, token: str) -> str:
    """Деплоит index.html в ветку gh-pages через GitHub API."""
    import urllib.request, base64

    html_b64 = base64.b64encode(html.encode("utf-8")).decode("utf-8")
    api_base = f"https://api.github.com/repos/{repo}/contents/index.html"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }

    sha = None
    try:
        req = urllib.request.Request(
            api_base + "?ref=gh-pages",
            headers=headers,
            method="GET",
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            sha = data.get("sha")
    except Exception:
        pass

    payload = {
        "message": f"digest update {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}",
        "content": html_b64,
        "branch": "gh-pages",
    }
    if sha:
        payload["sha"] = sha

    req2 = urllib.request.Request(
        api_base,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="PUT",
    )
    with urllib.request.urlopen(req2) as resp:
        resp.read()

    username = repo.split("/")[0]
    reponame = repo.split("/")[1]
    return f"https://{username}.github.io/{reponame}/"

async def send_telegram_message(token: str, chat_id: str, text: str):
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────

def main():
    print("▶ Запускаю дайджест...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    design_cards      = []
    other_cards       = []
    wtf_cards         = []
    emigration_cards  = []

    all_channels = [("design",     ch) for ch in DESIGN_CHANNELS] +                    [("other",      ch) for ch in OTHER_CHANNELS] +                    [("emigration", ch) for ch in EMIGRATION_CHANNELS] +                    [("wtf",        ch) for ch in WTF_CHANNELS]

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
        elif group == "other":
            other_cards.append(card)
        elif group == "emigration":
            emigration_cards.append(card)
        else:
            wtf_cards.append(card)
        print(f"     ✓ {title}")
        time.sleep(1)  # небольшая пауза чтобы не спамить

    if not design_cards and not other_cards:
        print("Нет контента для дайджеста.")
        return

    print("▶ Собираю HTML...")
    html = build_html(design_cards, other_cards, emigration_cards, wtf_cards)

    print("▶ Деплою на Netlify...")
    page_url = deploy_to_github_pages(html, GITHUB_REPO, GITHUB_TOKEN)
    print(f"  ✓ {page_url}")

    print("▶ Отправляю в Telegram...")
    message = f"☀️ Дайджест готов\n{page_url}"
    asyncio.run(send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message))
    print("  ✓ Сообщение отправлено")
    print("✅ Готово!")


if __name__ == "__main__":
    main()
