#!/usr/bin/env python3
import os

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
FINAL_DIR = os.path.join(BASE_PATH, "configs", "final")

PROTOCOLS = [
    ("VLESS", "vless"),
    ("VMESS", "vmess"),
    ("TROJAN", "trojan"),
    ("SS", "ss"),
    ("HYSTERIA", "hysteria"),
    ("HYSTERIA2", "hysteria2"),
    ("HY2", "hy2"),
    ("TUIC", "tuic"),
]

CHUNK_SIZE = 1000

def split_to_chunks(src_path, prefix, chunk_size=CHUNK_SIZE):
    print(f"🔎 Читаем {src_path}")
    if not os.path.exists(src_path):
        print(f"  ❌ Файл не найден: {src_path}")
        return []

    with open(src_path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    print(f"  📄 Найдено строк: {len(lines)}")
    if not lines:
        print(f"  ⚠️ Файл пустой: {src_path}")
        return []

    urls = []
    for i in range(0, len(lines), chunk_size):
        chunk = lines[i:i + chunk_size]
        idx = i // chunk_size + 1
        filename = f"{prefix}_{idx:03d}.txt"
        full_path = os.path.join(BASE_PATH, filename)
        print(f"  💾 Пишем {len(chunk)} строк в {full_path}")
        with open(full_path, "w", encoding="utf-8") as out:
            out.write("\n".join(chunk) + "\n")

        raw_url = (
            "https://raw.githubusercontent.com/"
            "kort0881/sbornik-vless/refs/heads/main/"
            + filename
        )
        urls.append(raw_url)

    print(f"  ✅ Сгенерировано ссылок: {len(urls)}")
    return urls


def main():
    print("=" * 60)
    print(f"🚀 Запуск генератора подписок")
    print("=" * 60)
    print(f"📁 BASE_PATH = {BASE_PATH}")
    print(f"📁 FINAL_DIR = {FINAL_DIR}")
    
    # Проверка существования директории
    if not os.path.exists(FINAL_DIR):
        print(f"\n❌ ОШИБКА: Директория {FINAL_DIR} не существует!")
        print(f"\n📂 Содержимое BASE_PATH:")
        for item in os.listdir(BASE_PATH):
            print(f"   - {item}")
        return
    
    print(f"\n📂 Содержимое FINAL_DIR:")
    final_files = os.listdir(FINAL_DIR)
    if not final_files:
        print("   ⚠️ Директория пустая!")
    for item in final_files:
        full_path = os.path.join(FINAL_DIR, item)
        size = os.path.getsize(full_path)
        print(f"   - {item} ({size} байт)")
    
    print("\n" + "=" * 60)
    subs_lines = []
    total_configs = 0

    for header, proto in PROTOCOLS:
        src = os.path.join(FINAL_DIR, f"{proto}.txt")
        urls = split_to_chunks(src, proto.lower())
        if urls:
            print(f"✅ {header}: {len(urls)} подписок")
            subs_lines.append(f"=== {header} ===")
            subs_lines.extend(urls)
            subs_lines.append("")
            total_configs += len(urls)
        else:
            print(f"⚠️ {header}: нет данных\n")

    print("=" * 60)
    subs_path = os.path.join(BASE_PATH, "subscriptions")

    if not subs_lines:
        open(subs_path, "w").close()
        print("❌ Нет данных для subscriptions, создан пустой файл")
        print("\n💡 РЕШЕНИЕ:")
        print("   1. Убедитесь, что файлы в configs/final/ содержат конфигурации")
        print("   2. Проверьте права доступа к файлам")
        print("   3. Запустите скрипт сбора конфигураций перед этим")
        return

    with open(subs_path, "w", encoding="utf-8") as f:
        f.write("\n".join(subs_lines).strip() + "\n")

    print(f"✅ Обновлён {subs_path}")
    print(f"📏 Размер: {os.path.getsize(subs_path)} байт")
    print(f"📊 Всего подписок: {total_configs}")
    print("=" * 60)


if __name__ == "__main__":
    main()
