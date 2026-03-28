***
# sbornik-vless

Автоматический сборщик подписок для VLESS / VMESS / TROJAN / SS / Hysteria2 / Hysteria / HY2 / TUIC.  
Берём сырой зоопарк конфигов, быстро отстреливаем мёртвые, режем живых на аккуратные подписки и выкатываем их в Телеграм. Без ручного копипаста, без слёз, максимум легкого мата.

> “А можно то же самое, только автоматически?” — да, вот оно.

***

## Что это вообще такое

Этот репозиторий — **витрина подписок**, а не ещё один дамп ключей.

- За сбор и проверку конфигов отвечает репозиторий `vpn-vless-configs-russia` (там вся магия с mirror/checker). [github](https://github.com/kort0881/vpn-vless-configs-russia)
- Здесь происходит:
  - быстрая проверка и раскладка по протоколам (`main.py`);  
  - нарезка на подписочные файлы (`build_subscriptions.py`);  
  - сбор итогового файла `subscriptions`;  
  - подготовка постов с кнопками для Телеграма (`subscriptions_poster.py`).  

В результате ты получаешь не хаос из 40k ссылок, а нормальный набор подписок:

- `VLESS_00X`, `VMESS_00X`, `SS_00X` и т.д., максимум 1000 строк в каждой;  
- отдельные подписки под каждый протокол;  
- готовые raw‑ссылки, которые можно:
  - пихать прямо в клиента,  
  - постить в канал,  
  - скармливать своим скриптам.

***

## Как это работает под капотом

Пайплайн в GitHub Actions (`.github/workflows/sbornik-vless.yml`):

1. **Сбор и проверка**  

   ```yaml
   - name: Run sbornik main.py
     run: python main.py
   ```

   - тянем свежие конфиги (`mirror.py`),  
   - прогоняем быструю проверку (многопоточно, с агрессивными таймаутами),  
   - сохраняем отфильтрованные живые в:

   ```text
   configs/final/vless.txt
   configs/final/vmess.txt
   configs/final/trojan.txt
   configs/final/ss.txt
   configs/final/hysteria2.txt
   configs/final/hy2.txt
   configs/final/tuic.txt
   ```

2. **Нарезка на подписки**

   ```yaml
   - name: Build subscriptions file
     run: python build_subscriptions.py
   ```

   Что делает:

   - читает `configs/final/*.txt`;  
   - режет каждый протокол на чанки по 1000 строк;  
   - складывает их в `subs/`:

     ```text
     subs/vless_001.txt
     subs/vless_002.txt
     ...
     subs/vmess_001.txt
     ...
     ```

   - собирает файл `subscriptions` в формате:

     ```text
     === VLESS ===
     https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_001.txt
     https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_002.txt
     ...

     === VMESS ===
     https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vmess_001.txt
     ...
     ```

3. **Пост в Телеграм (с DRY‑RUN по умолчанию)**

   ```yaml
   - name: Post subscriptions to Telegram
     env:
       TELEGRAM_BOT_TOKEN_PUBLIC: ${{ secrets.TELEGRAM_BOT_TOKEN_PUBLIC }}
       TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
       TELEGRAM_PRIVATE_CHANNEL: ${{ secrets.TELEGRAM_PRIVATE_CHANNEL }}
       TELEGRAM_DRY_RUN: "1"
     run: python subscriptions_poster.py
   ```

   `subscriptions_poster.py`:

   - тянет `subscriptions` по raw‑URL;  
   - парсит блоки протоколов;  
   - собирает два поста:
     - публичный: заголовок, предупреждение, клиенты, теги + до 10 кнопок `📥 VLESS 001`, `📥 VMESS 001`, …;  
     - приватный: полный список всех ссылок по протоколам.  

   Пока `TELEGRAM_DRY_RUN="1"` — **ничего не улетает**, только печатается payload в логах.

4. **Коммит подписок обратно в репо**

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

   Это нужно, чтобы raw‑ссылки всегда указывали на свежие файлы, а не на воображаемый `subscriptions из прошлого`.

***

## Как этим пользоваться

### Как клиенту (юзеру)

Если ты не хочешь трогать код, а хочешь “просто VPN”:

1. Выбери нужный протокол:
   - VLESS, VMESS, TROJAN, SS, Hysteria2, HY2, TUIC.  
2. Возьми любую ссылку из блока `=== VLESS ===` (или другого) в `subscriptions`:
   - пример:  
     `https://raw.githubusercontent.com/kort0881/sbornik-vless/refs/heads/main/subs/vless_001.txt`  
3. Вставь её в свой клиент как URL подписки:
   - **Android**: v2rayNG / Hiddify / Nekobox.  
   - **iOS**: Shadowrocket / Streisand.  
   - **PC**: Clash / Hiddify / v2rayN.

Клиент дальше сам подтянет список узлов и покажет их как обычные конфиги.

### Как разработчику / администратору

Если хочешь крутить это у себя:

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

***

## Переменные окружения

Используются в `subscriptions_poster.py`:

- `TELEGRAM_BOT_TOKEN_PUBLIC` — токен бота для публичного канала.  
- `TELEGRAM_BOT_TOKEN` — токен бота для приватного канала/лога.  
- `TELEGRAM_PRIVATE_CHANNEL` — ID или @username приватного канала.  
- `TELEGRAM_DRY_RUN`:
  - `"1"` — **ничего не отправлять**, только печатать payload в лог;  
  - `"0"` — реально слать сообщения в Телеграм (на свой страх и риск).

***

## Часто задаваемые вопросы

**Q: Почему не все конфиги рабочие?**  
A: Потому что мы живём не в сказке. Скрипт отстреливает очевидных мёртвых, но интернет нестабилен, провайдеры злобные, а авторы серверов странные. [github](https://github.com/kort0881/vpn-vless-configs-russia/blob/main/post_2025-10-29_20-30.txt)

**Q: Можно ли поменять лимит 1000 строк на подписку?**  
A: Да, в `build_subscriptions.py` константа `CHUNK_SIZE`. Поменял → запустил → живёшь с последствиями.

**Q: А что если Телеграм всё это заблокирует?**  
A: Тогда это уже будет репозиторий “исторической реконструкции свободного интернета”.

***

## Дисклеймер

Проект предназначен **исключительно для образовательных и исследовательских целей**.  
Никаких гарантий, никаких обещаний, только логика, Python и крон.

Используя этот репозиторий, ты:

- подтверждаешь, что соблюдаешь законы своей юрисдикции,  
- не используешь его для всякой фигни,  
- понимаешь, что авторы не несут ответственности за твою сетевую карму.

---
