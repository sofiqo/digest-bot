# Digest Bot — пошаговая настройка

## Что делает бот
Каждый день в 10:00 читает посты из Telegram-каналов через RSS,
фильтрует рекламу через Claude, собирает HTML-страницу, деплоит на Netlify
и присылает тебе ссылку в Telegram.

---

## Шаг 1 — Узнай свой Telegram Chat ID

1. Напиши боту @userinfobot в Telegram
2. Он пришлёт твой числовой ID (например `123456789`)
3. Это и есть `TELEGRAM_CHAT_ID`

---

## Шаг 2 — Создай сайт на Netlify

1. Зарегистрируйся на netlify.com
2. Нажми **Add new site → Deploy manually**
3. Перетащи любой пустой файл index.html (создай файл с текстом "hello")
4. После создания сайта зайди в **Site settings** и скопируй **Site ID**
5. Зайди в **User settings → Applications → Personal access tokens → New access token**
6. Скопируй токен — это `NETLIFY_TOKEN`

---

## Шаг 3 — Задеплой на Railway

1. Зарегистрируйся на railway.app
2. Нажми **New Project → Deploy from GitHub repo**
   (или **Empty project → Add service → GitHub repo**)
3. Залей папку с файлами в GitHub (можно создать приватный репозиторий)
4. В Railway зайди в **Variables** и добавь:

| Переменная | Значение |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен от BotFather |
| `TELEGRAM_CHAT_ID` | твой числовой ID из шага 1 |
| `ANTHROPIC_API_KEY` | ключ от platform.claude.ai |
| `NETLIFY_SITE_ID` | ID сайта из шага 2 |
| `NETLIFY_TOKEN` | токен Netlify из шага 2 |

5. Railway сам прочитает `railway.toml` и запустит скрипт каждый день в 9:00 UTC (= 10:00 Берлин/Варшава/Москва зимой, 11:00 летом)

---

## Шаг 4 — Проверь локально (опционально)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export ANTHROPIC_API_KEY="..."
export NETLIFY_SITE_ID="..."
export NETLIFY_TOKEN="..."
python digest.py
```

Результат появится в папке `output/index.html` — можно открыть в браузере.

---

## Часовой пояс

`cronSchedule = "0 9 * * *"` — это 9:00 UTC.
- Зима (CET): UTC+1 → приходит в 10:00
- Лето (CEST): UTC+2 → приходит в 11:00

Если хочешь строго 10:00 летом — измени на `"0 8 * * *"`.
