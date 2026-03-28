#!/usr/bin/env python3
"""
main.py — СУПЕР-БЫСТРЫЙ пайплайн с оптимизированной проверкой

Оптимизации:
- Убран TLS handshake (самая медленная операция)
- Кэширование DNS и failed hosts
- Батчинг по 1000 конфигов
- 150 параллельных потоков
- Fail-fast при первой ошибке
- Упрощённая валидация формата
- Предварительная фильтрация очевидно невалидных

Ожидаемое время: 2-4 минуты вместо 47 минут
"""

import os
import subprocess
import urllib.parse
import socket
import time
import base64
import json
import hashlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple, Optional, Dict, List

BASE_PATH = os.path.dirname(os.path.abspath(__file__))

GITHUBMIRROR_DIR = os.path.join(BASE_PATH, "githubmirror")
CLEAN_DIR = os.path.join(GITHUBMIRROR_DIR, "clean")

FINAL_DIR = os.path.join(BASE_PATH, "configs", "final")
REPORT_DIR = os.path.join(BASE_PATH, "reports")
os.makedirs(FINAL_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

PROTOCOLS = ["vless", "vmess", "trojan", "ss", "hysteria", "hysteria2", "hy2", "tuic"]

# Агрессивные настройки для максимальной скорости
CONNECT_TIMEOUT = 1.5    # Уменьшен с 3
DNS_TIMEOUT = 1          # Уменьшен с 2
MAX_WORKERS = 150        # Увеличен с 50
MAX_LATENCY_MS = 2500    # Увеличен для меньшей фильтрации
BATCH_SIZE = 1000        # Батчи для параллельной обработки

# Глобальные кэши для ускорения
DNS_CACHE = {}
DEAD_HOSTS = set()
VALID_HOSTS = {}


def run_mirror():
    """Запуск mirror.py"""
    mirror_path = os.path.join(BASE_PATH, "mirror.py")
    if not os.path.exists(mirror_path):
        raise FileNotFoundError(f"mirror.py не найден: {mirror_path}")

    print("🚀 Запуск mirror.py...")
    result = subprocess.run(
        ["python3", mirror_path],
        cwd=BASE_PATH,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("mirror.py failed")
    print("✅ mirror.py завершён\n")


def protocol_of(line: str) -> Optional[str]:
    """Быстрое определение протокола"""
    if line.startswith("vless://"):
        return "vless"
    elif line.startswith("vmess://"):
        return "vmess"
    elif line.startswith("trojan://"):
        return "trojan"
    elif line.startswith("ss://"):
        return "ss"
    elif line.startswith("hysteria2://") or line.startswith("hy2://"):
        return "hysteria2"
    elif line.startswith("hysteria://"):
        return "hysteria"
    elif line.startswith("tuic://"):
        return "tuic"
    return None


def extract_host_port(line: str) -> Tuple[Optional[str], Optional[int]]:
    """Быстрое извлечение host:port без полного парсинга"""
    try:
        # Убираем протокол
        after_protocol = line.split("://", 1)[1] if "://" in line else line
        
        # Для vmess - особый случай (base64)
        if line.startswith("vmess://"):
            try:
                decoded = base64.b64decode(after_protocol + "==").decode('utf-8', errors='ignore')
                data = json.loads(decoded)
                return data.get('add'), int(data.get('port', 443))
            except:
                return None, None
        
        # Для остальных - стандартный парсинг
        # Формат: user@host:port или host:port
        if '@' in after_protocol:
            after_protocol = after_protocol.split('@', 1)[1]
        
        # Убираем query string и fragment
        host_port = after_protocol.split('?')[0].split('#')[0]
        
        # Парсим host:port
        if ':' in host_port:
            parts = host_port.rsplit(':', 1)
            host = parts[0].strip('[]')  # Убираем квадратные скобки для IPv6
            try:
                port = int(parts[1].split('/')[0])  # На случай если есть путь
            except:
                port = 443
        else:
            host = host_port.strip('[]')
            port = 443
        
        return host if host else None, port
        
    except:
        return None, None


def quick_format_check(config: str, protocol: str) -> bool:
    """Быстрая проверка формата (без глубокого парсинга)"""
    try:
        # Минимальная длина
        if len(config) < 20:
            return False
        
        # Проверка наличия обязательных элементов
        if protocol == "vmess":
            if not config.startswith("vmess://"):
                return False
            try:
                encoded = config[8:]
                decoded = base64.b64decode(encoded + "==").decode('utf-8', errors='ignore')
                data = json.loads(decoded)
                return 'add' in data and 'port' in data
            except:
                return False
        
        elif protocol in ["vless", "trojan"]:
            # vless://UUID@host:port или trojan://password@host:port
            if '@' not in config:
                return False
            parts = config.split('@')
            return len(parts[0].split('://')[1]) > 8  # UUID или password минимум 8 символов
        
        elif protocol == "ss":
            # ss://base64 или ss://method:pass@host:port
            return '@' in config or len(config.split('://')[1]) > 10
        
        else:  # hysteria, hy2, tuic
            return '@' in config or '?' in config
            
    except:
        return False


def dns_resolve_fast(hostname: str) -> Optional[str]:
    """Сверхбыстрый DNS с кэшем и блэклистом"""
    # Проверка блэклиста
    if hostname in DEAD_HOSTS:
        return None
    
    # Проверка кэша
    if hostname in DNS_CACHE:
        return DNS_CACHE[hostname]
    
    try:
        socket.setdefaulttimeout(DNS_TIMEOUT)
        ip = socket.gethostbyname(hostname)
        DNS_CACHE[hostname] = ip
        return ip
    except:
        DEAD_HOSTS.add(hostname)
        return None


def tcp_check_ultra_fast(host: str, port: int) -> Tuple[bool, float]:
    """Ультрабыстрая TCP проверка"""
    # Проверка блэклиста
    host_key = f"{host}:{port}"
    if host_key in DEAD_HOSTS:
        return False, 9999
    
    # Проверка кэша валидных хостов
    if host_key in VALID_HOSTS:
        return True, VALID_HOSTS[host_key]
    
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        result = sock.connect_ex((host, port))
        latency_ms = (time.time() - start) * 1000
        sock.close()
        
        if result == 0 and latency_ms < MAX_LATENCY_MS:
            VALID_HOSTS[host_key] = latency_ms
            return True, latency_ms
        else:
            DEAD_HOSTS.add(host_key)
            return False, 9999
    except:
        DEAD_HOSTS.add(host_key)
        return False, 9999


def create_fingerprint(config: str) -> str:
    """Быстрый fingerprint"""
    try:
        host, port = extract_host_port(config)
        proto = protocol_of(config)
        key = f"{proto}:{host}:{port}"
        return hashlib.md5(key.encode()).hexdigest()[:12]
    except:
        return hashlib.md5(config.encode()).hexdigest()[:12]


def check_config_fast(config: str, protocol: str) -> Optional[Dict]:
    """Супер-быстрая проверка конфига (fail-fast)"""
    
    # 1. Быстрая проверка формата
    if not quick_format_check(config, protocol):
        return None
    
    # 2. Извлечение host:port
    host, port = extract_host_port(config)
    if not host or not port:
        return None
    
    # 3. DNS (с кэшем)
    if not dns_resolve_fast(host):
        return None
    
    # 4. TCP проверка
    tcp_ok, latency = tcp_check_ultra_fast(host, port)
    if not tcp_ok:
        return None
    
    return {
        'config': config,
        'protocol': protocol,
        'latency_ms': latency
    }


def process_batch(batch: List[Tuple[str, str]]) -> List[Dict]:
    """Обработка батча конфигов"""
    results = []
    seen_fps = set()
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {
            executor.submit(check_config_fast, cfg, proto): (cfg, proto)
            for cfg, proto in batch
        }
        
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    fp = create_fingerprint(result['config'])
                    if fp not in seen_fps:
                        seen_fps.add(fp)
                        results.append(result)
            except:
                pass
    
    return results


def load_from_clean() -> Tuple[List[Tuple[str, str]], Dict]:
    """Загрузка с предварительной фильтрацией"""
    configs = []
    per_proto_raw = defaultdict(int)

    if not os.path.isdir(CLEAN_DIR):
        raise FileNotFoundError(f"Папка {CLEAN_DIR} не найдена")

    for proto in PROTOCOLS:
        path = os.path.join(CLEAN_DIR, f"{proto}.txt")
        if not os.path.exists(path):
            continue
        
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if len(line) > 20 and "://" in line:  # Предварительная фильтрация
                    configs.append((line, proto))
                    per_proto_raw[proto] += 1

    return configs, per_proto_raw


def parallel_check_ultra_fast(configs: List[Tuple[str, str]]) -> Tuple[List[Dict], Dict]:
    """Ультрабыстрая параллельная проверка"""
    
    total = len(configs)
    print(f"🔍 Быстрая проверка {total} конфигов...")
    print(f"⚙️  Батчи по {BATCH_SIZE}, потоков: {MAX_WORKERS}")
    print(f"⚡ Таймауты: DNS={DNS_TIMEOUT}s, TCP={CONNECT_TIMEOUT}s (TLS отключен)\n")
    
    all_results = []
    per_proto = defaultdict(lambda: {'total': 0, 'passed': 0})
    
    # Подсчёт total по протоколам
    for _, proto in configs:
        per_proto[proto]['total'] += 1
    
    # Создание батчей
    batches = [configs[i:i + BATCH_SIZE] for i in range(0, len(configs), BATCH_SIZE)]
    
    # Параллельная обработка батчей
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_batch, batch): i 
            for i, batch in enumerate(batches)
        }
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            batch_idx = futures[future]
            
            try:
                results = future.result()
                all_results.extend(results)
                
                # Обновление статистики
                for r in results:
                    per_proto[r['protocol']]['passed'] += 1
                
                processed = min(completed * BATCH_SIZE, total)
                valid_count = len(all_results)
                print(f"  ✓ {processed:5d}/{total} | Валидных: {valid_count:5d} | "
                      f"DNS кэш: {len(DNS_CACHE)} | Dead: {len(DEAD_HOSTS)}")
                
            except Exception as e:
                print(f"  ⚠️  Ошибка батча {batch_idx}: {e}")
    
    stats = {
        'total': total,
        'passed': len(all_results),
        'dns_cache_size': len(DNS_CACHE),
        'dead_hosts': len(DEAD_HOSTS)
    }
    
    return all_results, stats, per_proto


def write_final_fast(results: List[Dict]):
    """Быстрая запись результатов"""
    buckets = defaultdict(list)
    
    for r in results:
        buckets[r['protocol']].append(r)
    
    for proto, items in buckets.items():
        # Сортировка по задержке
        items_sorted = sorted(items, key=lambda x: x['latency_ms'])
        
        out_path = os.path.join(FINAL_DIR, f"{proto}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            for item in items_sorted:
                f.write(f"{item['config']}\n")
        
        avg_lat = sum(i['latency_ms'] for i in items) / len(items)
        print(f"💾 {proto:12s}: {len(items):5d} конфигов (avg {avg_lat:4.0f}ms) → {out_path}")


def save_fast_report(stats: Dict, per_proto: Dict, elapsed: float):
    """Быстрый отчёт"""
    report_path = os.path.join(REPORT_DIR, "fast_report.txt")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("FAST QUALITY CHECK REPORT\n")
        f.write("=" * 60 + "\n\n")
        
        f.write(f"Processing time: {elapsed:.1f}s ({elapsed/60:.1f} min)\n")
        f.write(f"Speed: {stats['total']/elapsed:.1f} configs/sec\n\n")
        
        f.write("STATISTICS:\n")
        f.write(f"  Total:         {stats['total']}\n")
        f.write(f"  Passed:        {stats['passed']} ({stats['passed']/stats['total']*100:.1f}%)\n")
        f.write(f"  DNS cache:     {stats['dns_cache_size']} hosts\n")
        f.write(f"  Dead hosts:    {stats['dead_hosts']}\n\n")
        
        f.write("PER-PROTOCOL:\n")
        for proto in PROTOCOLS:
            if per_proto[proto]['total'] > 0:
                p = per_proto[proto]
                rate = p['passed'] / p['total'] * 100 if p['total'] > 0 else 0
                f.write(f"  {proto:12s}: {p['passed']:5d}/{p['total']:5d} ({rate:5.1f}%)\n")
    
    print(f"\n📄 Отчёт: {report_path}")


def main():
    start_ts = time.time()

    # 1. Запуск mirror.py
    run_mirror()

    # 2. Загрузка
    configs, per_proto_raw = load_from_clean()
    print(f"📥 Загружено: {len(configs)} конфигов")
    print("\n📋 По протоколам:")
    for p in PROTOCOLS:
        if per_proto_raw[p]:
            print(f"   {p:12s}: {per_proto_raw[p]:6d}")

    # 3. Быстрая проверка
    print()
    results, stats, per_proto = parallel_check_ultra_fast(configs)

    # 4. Запись
    print()
    write_final_fast(results)

    # 5. Отчёт
    elapsed = time.time() - start_ts
    save_fast_report(stats, per_proto, elapsed)

    # 6. Финальная статистика
    print("\n" + "=" * 60)
    print("✅ ПАЙПЛАЙН ЗАВЕРШЁН")
    print("=" * 60)
    print(f"\n📊 РЕЗУЛЬТАТЫ:")
    print(f"   Всего:              {stats['total']}")
    print(f"   ✅ Прошли проверку:  {stats['passed']} ({stats['passed']/stats['total']*100:.1f}%)")
    print(f"   📡 DNS кэш:          {stats['dns_cache_size']} хостов")
    print(f"   ❌ Мёртвых хостов:   {stats['dead_hosts']}")

    print(f"\n📈 ПО ПРОТОКОЛАМ:")
    for p in PROTOCOLS:
        if per_proto[p]['total'] > 0:
            pt = per_proto[p]
            rate = pt['passed'] / pt['total'] * 100
            print(f"   {p:12s}: {pt['passed']:5d}/{pt['total']:5d} ({rate:5.1f}%)")

    print(f"\n⏱️  Время: {elapsed:.1f}s ({elapsed/60:.1f} мин)")
    print(f"⚡ Скорость: {stats['total']/elapsed:.1f} конфигов/сек")
    
    # Оценка ускорения
    old_time = 47 * 60  # 47 минут в секундах
    speedup = old_time / elapsed
    print(f"🚀 Ускорение: {speedup:.1f}x по сравнению со старой версией")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
