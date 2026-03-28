#!/usr/bin/env python3
"""subscriptions_poster.py — Создание subscription файлов"""

import os
import base64
from collections import defaultdict

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
FINAL_DIR = os.path.join(BASE_PATH, "configs", "final")
SUB_DIR = os.path.join(BASE_PATH, "subscriptions")
BASE64_DIR = os.path.join(SUB_DIR, "base64")
PLAIN_DIR = os.path.join(SUB_DIR, "plain")

PROTOCOLS = ["vless", "vmess", "trojan", "ss", "hysteria", "hysteria2", "hy2", "tuic"]


def load_configs():
    configs = defaultdict(list)
    
    if not os.path.isdir(FINAL_DIR):
        print(f"❌ {FINAL_DIR} не найдена")
        return configs
    
    for proto in PROTOCOLS:
        path = os.path.join(FINAL_DIR, f"{proto}.txt")
        if os.path.exists(path):
            with open(path, "r") as f:
                lines = [l.strip() for l in f if l.strip()]
            configs[proto] = lines
            print(f"📥 {proto:12s}: {len(lines):5d} конфигов")
    
    return configs


def write_subscription(proto: str, configs: list):
    if not configs:
        return
    
    os.makedirs(PLAIN_DIR, exist_ok=True)
    os.makedirs(BASE64_DIR, exist_ok=True)
    
    # Plain
    plain_path = os.path.join(PLAIN_DIR, proto)
    with open(plain_path, "w") as f:
        f.write("\n".join(configs))
    
    # Base64
    content = "\n".join(configs)
    encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    
    base64_path = os.path.join(BASE64_DIR, proto)
    with open(base64_path, "w") as f:
        f.write(encoded)
    
    print(f"✅ {proto:12s}: {plain_path}")


def write_mix(all_configs: dict):
    mixed = []
    for proto in PROTOCOLS:
        mixed.extend(all_configs.get(proto, []))
    
    if not mixed:
        return
    
    # Plain
    plain_path = os.path.join(PLAIN_DIR, "mix")
    with open(plain_path, "w") as f:
        f.write("\n".join(mixed))
    
    # Base64
    encoded = base64.b64encode("\n".join(mixed).encode('utf-8')).decode('utf-8')
    base64_path = os.path.join(BASE64_DIR, "mix")
    with open(base64_path, "w") as f:
        f.write(encoded)
    
    print(f"\n✅ MIX ({len(mixed)} configs)")


def main():
    print("="*70)
    print("📤 SUBSCRIPTIONS POSTER")
    print("="*70 + "\n")
    
    configs = load_configs()
    
    if not any(configs.values()):
        print(f"\n❌ Нет конфигов в {FINAL_DIR}")
        return 1
    
    print(f"\n📊 Всего: {sum(len(v) for v in configs.values())}\n")
    
    for proto in PROTOCOLS:
        if configs[proto]:
            write_subscription(proto, configs[proto])
    
    write_mix(configs)
    
    print("\n" + "="*70)
    print("✅ Subscriptions созданы!")
    print("="*70)
    
    return 0


if __name__ == "__main__":
    exit(main())
