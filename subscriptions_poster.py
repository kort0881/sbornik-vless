#!/usr/bin/env python3
import os
import sys
import requests
from datetime import datetime

# Флаги / окружение
DRY_RUN = os.environ.get("TELEGRAM_DRY_RUN", "0") == "1"

BOT_TOKEN_PUBLIC = os.environ.get("TELEGRAM_BOT_TOKEN_PUBLIC")
BOT_TOKEN_PRIVATE = os.environ.get("TELEGRAM_BOT_TOKEN")
PRIVATE_CHANNEL = os.environ.get("TELEGRAM_PRIVATE_CHANNEL")

# Публичный канал: numeric ID
PUBLIC_CHANNEL = -1002287416438

# Файл subscriptions в репо sbornik-vless
SUBSCRIPTIONS_URL = (
    "https://raw.githubusercontent.com/"
    "kort0881/sbornik-vless/refs/heads/main/subscriptions"
)

WARNING_TEXT = (
    "⚠️ Материал взят из открытых источников сети Интернет.\n"
    "Информация предоставляется в ознакомительных целях.\n"
    "Все данные получены легальными методами.\n\n"
)
CLIENTS = "Клиенты: v2rayNG · Clash · Hiddify · Shadowrocket\n"
TAGS = "#прокси #v2ray #vmess #vless #shadowsocks #vpn"


def load_subscriptions_raw():
    print(f"🌐 SUBSCRIPTIONS_URL = {SUBSCRIPTIONS_URL}")
    try:
        resp = requests.get(SUBSCRIPTIONS_URL, timeout=15)
        print(f"🔎 HTTP статус: {resp.status_code}")
        if resp.status_code != 200:
            print(f"⚠️ Не удалось получить subscriptions: HTTP {resp.status_code}")
            return ""
        text = resp.text
        print(f"🔎 len(resp.text) = {len(text)}")
        stripped = text.strip()
        print(f"🔎 len(stripped) = {len(stripped)}")
        if not stripped:
            print("⚠️ Файл subscriptions получен, но он пустой (после strip())")
        return stripped
    except Exception as e:
        print(f"❌ Ошибка загрузки subscriptions: {e}")
        return ""


def parse_subscriptions_blocks(subscriptions_text: str):
    blocks = {}
    current = None

    for line in subscriptions_text.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("===") and line.endswith("==="):
            name = line.strip("=").strip()
            proto = name.split()[0].upper()
            blocks.setdefault(proto, [])
            current = proto
            continue

        if current is None:
            continue

        if line.startswith("http"):
            blocks[current].append(line)

    return blocks


def build_keyboard(blocks, max_buttons=50):
    buttons = []
    flat = []

    order = ["VLESS", "VMESS", "TROJAN", "SS", "HYSTERIA", "HYSTERIA2", "HY2", "TUIC"]
    for proto in order:
        urls = blocks.get(proto, [])
        for idx, url in enumerate(urls, start=1):
            flat.append((proto, idx, url))

    for proto, idx, url in flat[:max_buttons]:
        text = f"📥 {proto} {idx:03d}"
        buttons.append({"text": text, "url": url})

    keyboard = []
    row = []
    for btn in buttons:
        row.append(btn)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    return keyboard


def build_private_text(blocks):
    order = ["VLESS", "VMESS", "TROJAN", "SS", "HYSTERIA", "HYSTERIA2", "HY2", "TUIC"]

    header = (
        "🔐 <b>Подписочные ссылки sbornik-vless</b>\n\n"
        f"📅 <code>{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</code>\n\n"
    )
    lines = [header]

    for proto in order:
        urls = blocks.get(proto, [])
        if not urls:
            continue
        lines.append(f"🔹 <b>{proto}</b> — {len(urls)} подписок")

    if len(lines) == 1:
        lines.append("Нет подписок.")

    lines.append("\nНиже — все подписки кнопками 👇")

    return "\n".join(lines)


def send_message_json(bot_token, chat_id, payload):
    if DRY_RUN:
        print(f"\n[DRY_RUN] sendMessage -> {chat_id}")
        print(payload)
        return True

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(url, json=payload, timeout=30)
    try:
        j = resp.json()
    except Exception:
        print(f"❌ Telegram response decode error: {resp.text[:300]}")
        return False

    if not j.get("ok"):
        print(f"❌ Telegram error: {j.get('description')}")
        return False
    return True


def main():
    if not BOT_TOKEN_PUBLIC:
        print("❌ TELEGRAM_BOT_TOKEN_PUBLIC не установлен")
        return 1
    if not BOT_TOKEN_PRIVATE:
        print("❌ TELEGRAM_BOT_TOKEN не установлен")
        return 1
    if not PRIVATE_CHANNEL:
        print("❌ TELEGRAM_PRIVATE_CHANNEL не установлен")
        return 1

    print("\n" + "=" * 70)
    print(" " * 20 + "📤 sbornik-vless SUBSCRIPTIONS POSTER")
    print("=" * 70 + "\n")

    subs_raw = load_subscriptions_raw()
    if not subs_raw:
        print("⚠️ subscriptions пустой или не удалось загрузить — продолжаем без ссылок")
        blocks = {}
        total_urls = 0
    else:
        blocks = parse_subscriptions_blocks(subs_raw)
        total_urls = sum(len(v) for v in blocks.values())

    print(f"📦 Всего ссылок в subscriptions: {total_urls}\n")

    # Одна клавиатура для обоих постов
    keyboard = build_keyboard(blocks, max_buttons=50)

    # ---------- ПУБЛИЧНЫЙ КАНАЛ ----------
    print("📢 Публичный канал:", PUBLIC_CHANNEL)

    public_text = (
        "🔥 <b>Подписочные ссылки sbornik-vless</b>\n\n"
        f"📅 <code>{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</code>\n\n"
        + WARNING_TEXT
        + CLIENTS
        + TAGS
    )

    payload_public = {
        "chat_id": PUBLIC_CHANNEL,
        "text": public_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if keyboard:
        # в паблик только первые 10 кнопок
        payload_public["reply_markup"] = {
            "inline_keyboard": build_keyboard(blocks, max_buttons=10)
        }

    ok_pub = send_message_json(BOT_TOKEN_PUBLIC, PUBLIC_CHANNEL, payload_public)
    if ok_pub:
        print("✅ Публичный пост отправлен")
    else:
        print("❌ Ошибка при отправке публичного поста")

    # ---------- ПРИВАТНЫЙ КАНАЛ ----------
    print("\n🔒 Приватный канал:", PRIVATE_CHANNEL)

    private_text = build_private_text(blocks)

    payload_private = {
        "chat_id": PRIVATE_CHANNEL,
        "text": private_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    if keyboard:
        payload_private["reply_markup"] = {"inline_keyboard": keyboard}

    ok_priv = send_message_json(BOT_TOKEN_PRIVATE, PRIVATE_CHANNEL, payload_private)
    if ok_priv:
        print("✅ Приватный пост отправлен")
    else:
        print("❌ Ошибка при отправке приватного поста")

    print("\n" + "=" * 70)
    print("✅ Скрипт завершил работу")
    print("=" * 70 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
