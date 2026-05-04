# sbornik-vless

**Автоматический сборщик и публикатор подписок** для протоколов VLESS, VMESS, TROJAN, SS, Hysteria2, Hysteria, HY2, TUIC.

Система выполняет следующие задачи: агрегация исходных конфигураций, фильтрация нерабочих узлов, формирование структурированных подписочных файлов и их публикация в Telegram. Процесс полностью автоматизирован, не требует ручного вмешательства.

> Автоматизированное решение для поддержания актуальных подписок VPN.

---

## Назначение репозитория

Данный репозиторий является **витриной готовых подписок**, а не хранилищем «сырых» ключей.

- Сбор и проверка конфигураций выполняются в репозитории [`vpn-vless-configs-russia`](https://github.com/kort0881/vpn-vless-configs-russia) (механизмы зеркалирования и валидации).
- В текущем репозитории реализованы:
  - быстрая проверка и сортировка по протоколам (`main.py`);
  - разбиение на подписочные файлы (`build_subscriptions.py`);
  - формирование итогового файла `subscriptions`;
  - подготовка сообщений с кнопками для Telegram (`subscriptions_poster.py`).

Результат — упорядоченный набор подписок:

- `VLESS_00X`, `VMESS_00X`, `SS_00X` и т.д. (не более 1000 строк на файл);
- отдельные подписки для каждого протокола;
- прямые RAW-ссылки, пригодные для использования в клиентах, публикации в каналах или интеграции с другими скриптами.

---

## Принцип работы

Используется GitHub Actions (конфигурация `.github/workflows/sbornik-vless.yml`). Пайплайн состоит из следующих этапов:

### 1. Сбор и проверка

```yaml
- name: Run sbornik main.py
  run: python main.py
```

- Загрузка актуальных конфигураций (`mirror.py`).
- Многопоточная проверка работоспособности с агрессивными таймаутами.
- Сохранение валидных конфигураций в директорию:

```
configs/final/vless.txt
configs/final/vmess.txt
configs/final/trojan.txt
configs/final/ss.txt
configs/final/hysteria2.txt
configs/final/hy2.txt
configs/final/tuic.txt
```

### 2. Формирование подписочных файлов

```yaml
- name: Build subscriptions file
  run: python build_subscriptions.py
```

- Чтение файлов из `configs/final/*.txt`.
- Разбиение каждого протокола на части (по умолчанию 1000 строк на файл).
- Сохранение результатов в `subs/`:

```
subs/vless_001.txt
subs/vless_002.txt
...
subs/vmess_001.txt
...
```

- Создание итогового файла `subscriptions` в формате:

```text
=== VLESS ===
https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_001.txt
https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_002.txt
...

=== VMESS ===
https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vmess_001.txt
...
```

### 3. Публикация в Telegram (режим DRY-RUN по умолчанию)

```yaml
- name: Post subscriptions to Telegram
  env:
    TELEGRAM_BOT_TOKEN_PUBLIC: ${{ secrets.TELEGRAM_BOT_TOKEN_PUBLIC }}
    TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
    TELEGRAM_PRIVATE_CHANNEL: ${{ secrets.TELEGRAM_PRIVATE_CHANNEL }}
    TELEGRAM_DRY_RUN: "1"
  run: python subscriptions_poster.py
```

Скрипт `subscriptions_poster.py`:

- Загружает файл `subscriptions` по RAW-ссылке.
- Разбирает блоки протоколов.
- Формирует два сообщения:
  - **Публичное**: заголовок, предупреждение, список клиентов, теги и до 10 кнопок вида `📥 VLESS 001`, `📥 VMESS 001` и т.д.
  - **Приватное**: полный перечень ссылок по протоколам.

Пока `TELEGRAM_DRY_RUN="1"` фактической отправки не происходит — полезная нагрузка выводится только в логи.

### 4. Фиксация изменений в репозитории

```yaml
- name: Commit subscriptions and chunks
  if: success()
  run: |
    git config user.name "github-actions"
    git config user.email "github-actions@users.noreply.github.com"
    git add subscriptions subs/*.txt || true
    if git diff --cached --quiet; then
      echo "No changes to commit"
    else
      git commit -m "Update subscriptions and chunks"
      git push
    fi
```

Это гарантирует, что RAW-ссылки всегда указывают на актуальные файлы.

---

## Использование

### Для конечных пользователей

1. Выберите протокол: VLESS, VMESS, TROJAN, SS, Hysteria2, HY2, TUIC.
2. Возьмите любую ссылку из соответствующего блока файла `subscriptions` (например, `=== VLESS ===`).
   - Пример: `https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_001.txt`
3. Вставьте ссылку в клиент как URL подписки:
   - **Android**: v2rayNG, Hiddify, Nekobox.
   - **iOS**: Shadowrocket, Streisand.
   - **ПК**: Clash, Hiddify, v2rayN.

Клиент автоматически загрузит список узлов и представит их в виде обычных конфигураций.

### Для разработчиков и администраторов

Локальный запуск:

```bash
git clone https://github.com/kort0881/sbornik-vless.git
cd sbornik-vless
python -m venv .venv
source .venv/bin/activate  # или .venv\Scripts\activate на Windows
pip install requests
python main.py
python build_subscriptions.py
python subscriptions_poster.py  # TELEGRAM_DRY_RUN=1 по умолчанию
```

---

## Переменные окружения

Используются в `subscriptions_poster.py`:

- `TELEGRAM_BOT_TOKEN_PUBLIC` — токен бота для публичного канала.
- `TELEGRAM_BOT_TOKEN` — токен бота для приватного канала/лога.
- `TELEGRAM_PRIVATE_CHANNEL` — идентификатор или `@username` приватного канала.
- `TELEGRAM_DRY_RUN`:
  - `"1"` — отправка отключена (только вывод в лог);
  - `"0"` — реальная отправка сообщений в Telegram.

---

## Часто задаваемые вопросы

**Вопрос:** Почему не все конфигурации являются рабочими?  
**Ответ:** Используемые алгоритмы отсеивают заведомо нерабочие узлы, однако качество соединения может варьироваться в зависимости от сетевых условий, политики провайдеров и стабильности серверов. Источник конфигураций доступен [здесь](https://github.com/kort0881/vpn-vless-configs-russia/blob/main/post_2025-10-29_20-30.txt).

**Вопрос:** Можно ли изменить лимит в 1000 строк на подписку?  
**Ответ:** Да, в `build_subscriptions.py` определена константа `CHUNK_SIZE`. Измените значение и выполните скрипт заново.

**Вопрос:** Что произойдёт, если Telegram заблокирует публикации?  
**Ответ:** В этом случае репозиторий останется архивом подписок, а возможность публикации в Telegram будет утрачена.

---

## Правовая информация

Проект предоставлен **исключительно в образовательных и исследовательских целях**. Авторы не дают никаких гарантий, явных или подразумеваемых.

Используя данный репозиторий, вы подтверждаете, что:

- соблюдаете действующее законодательство вашей юрисдикции;
- не применяете материалы для противоправных действий;
- принимаете на себя всю ответственность за последствия использования предоставленных данных.

Авторы не несут ответственности за любые убытки, возникшие в результате использования данного программного обеспечения или полученных подписок.
