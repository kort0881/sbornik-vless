#!/usr/bin/env python3
"""
main.py — пайплайн для нового репо/канала БЕЗ гео-фильтров

1. Запускает mirror.py (NO GEO) — сбор и дедуп по IP:PORT:SCHEME.
2. Читает githubmirror/clean/*.txt (по протоколам).
3. Делает TCP-пинг хостов, отсекает мёртвые.
4. Пишет живые ключи в configs/final/{protocol}.txt.
5. Выводит статистику.
"""

import os
import subprocess
import urllib.parse
import socket
import time
from collections import defaultdict

BASE_PATH = os.path.dirname(os.path.abspath(__file__))

GITHUBMIRROR_DIR = os.path.join(BASE_PATH, "githubmirror")
CLEAN_DIR = os.path.join(GITHUBMIRROR_DIR, "clean")

FINAL_DIR = os.path.join(BASE_PATH, "configs", "final")
os.makedirs(FINAL_DIR, exist_ok=True)

PROTOCOLS = ["vless", "vmess", "trojan", "ss", "hysteria", "hysteria2", "hy2", "tuic"]

CONNECT_TIMEOUT = 3  # секунды


def run_mirror():
    """Запуск mirror.py (NO GEO)."""
    mirror_path = os.path.join(BASE_PATH, "mirror.py")
    if not os.path.exists(mirror_path):
        raise FileNotFoundError(f"mirror.py не найден по пути: {mirror_path}")

    print("🚀 Запуск mirror.py (NO GEO, дедуп по IP:PORT:SCHEME)...")
    result = subprocess.run(
        ["python3", mirror_path],
        cwd=BASE_PATH,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("❌ mirror.py завершился с ошибкой")
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("mirror.py failed")
    print("✅ mirror.py завершён успешно")
    print(result.stdout)


def protocol_of(line: str):
    for p in PROTOCOLS:
        if line.startswith(p + "://"):
            return p
    return None


def extract_host_port(line: str):
    """Парсим host и port из URI."""
    try:
        u = urllib.parse.urlparse(line)
        host = u.hostname
        port = u.port
        if port is None:
            if u.scheme in ("vless", "vmess", "trojan", "hysteria", "hysteria2", "hy2", "tuic", "ss"):
                port = 443
        return host, port
    except Exception:
        return None, None


def tcp_ping(host: str, port: int, timeout: float = CONNECT_TIMEOUT) -> bool:
    """TCP-connect пинг."""
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def load_from_clean():
    """
    Читаем все файлы из githubmirror/clean/*.txt.
    Возвращаем список строк и статистику по протоколам (до пинга).
    """
    all_lines = []
    per_proto_raw = defaultdict(int)

    if not os.path.isdir(CLEAN_DIR):
        raise FileNotFoundError(f"Папка {CLEAN_DIR} не найдена. mirror.py отработал?")

    for p in PROTOCOLS:
        path = os.path.join(CLEAN_DIR, f"{p}.txt")
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if "://" in l]
        all_lines.extend(lines)
        per_proto_raw[p] += len(lines)

    return all_lines, per_proto_raw


def validate_and_ping(lines):
    """
    Пинг-чек:
    - отбрасываем строки без протокола/хоста,
    - TCP-connect к host:port,
    - собираем статистику.
    """
    alive = []
    dead = []

    stats = {
        "total": len(lines),
        "alive": 0,
        "dead": 0,
    }
    per_proto = defaultdict(lambda: {"total": 0, "alive": 0, "dead": 0})

    print(f"🔍 Пинг-чек {len(lines)} ключей...")

    for idx, line in enumerate(lines, 1):
        p = protocol_of(line)
        if not p:
            continue

        per_proto[p]["total"] += 1

        host, port = extract_host_port(line)
        if not host or not port:
            dead.append(line)
            stats["dead"] += 1
            per_proto[p]["dead"] += 1
        else:
            ok = tcp_ping(host, port)
            if ok:
                alive.append(line)
                stats["alive"] += 1
                per_proto[p]["alive"] += 1
            else:
                dead.append(line)
                stats["dead"] += 1
                per_proto[p]["dead"] += 1

        if idx % 100 == 0:
            print(f"  {idx}/{len(lines)} обработано...")

    return alive, dead, stats, per_proto


def write_final(alive_keys):
    """Пишем финальные файлы configs/final/{protocol}.txt."""
    buckets = defaultdict(list)
    for line in alive_keys:
        p = protocol_of(line)
        if p:
            buckets[p].append(line)

    for p, items in buckets.items():
        out_path = os.path.join(FINAL_DIR, f"{p}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(set(items))))
        print(f"💾 {p}: записано {len(items)} живых ключей в {out_path}")


def main():
    start_ts = time.time()

    # 1. mirror.py без GEO
    run_mirror()

    # 2. Читаем githubmirror/clean/*.txt
    all_lines, per_proto_raw = load_from_clean()
    print(f"📥 После mirror.py (clean/*): {len(all_lines)} строк")
    print("   По протоколам до пинга:")
    for p in PROTOCOLS:
        if per_proto_raw[p]:
            print(f"   {p}: {per_proto_raw[p]}")

    # 3. Пинг-чек
    alive, dead, stats, per_proto = validate_and_ping(all_lines)

    # 4. Запись итогов
    write_final(alive)

    # 5. Статистика
    print("\n✅ ПАЙПЛАЙН ГОТОВ")
    print(f"   Всего (clean/*): {stats['total']}")
    print(f"   Живых:           {stats['alive']}")
    print(f"   Мёртвых:         {stats['dead']}")

    print("\n📊 По протоколам после пинга:")
    for p in PROTOCOLS:
        if per_proto[p]["total"] == 0:
            continue
        print(
            f"   {p}: total={per_proto[p]['total']}, "
            f"alive={per_proto[p]['alive']}, dead={per_proto[p]['dead']}"
        )

    print(f"\n⏱ Время работы: {time.time() - start_ts:.1f} сек")


if __name__ == "__main__":
    main()
