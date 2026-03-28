#!/usr/bin/env python3
"""
main.py — пайплайн с многоуровневой проверкой качества БЕЗ xray

1. Запускает mirror.py (NO GEO) — сбор и дедуп по IP:PORT:SCHEME.
2. Читает githubmirror/clean/*.txt (по протоколам).
3. Многоуровневая проверка:
   - Валидация формата конфига
   - DNS-резолв (отсев несуществующих доменов)
   - TCP-пинг с измерением задержки
   - Повторная проверка нестабильных хостов
   - TLS handshake для HTTPS протоколов
   - Проверка на дубликаты по fingerprint
4. Пишет живые ключи в configs/final/{protocol}.txt с сортировкой по задержке.
5. Выводит детальную статистику.
"""

import os
import subprocess
import urllib.parse
import socket
import time
import ssl
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

# Настройки проверок
CONNECT_TIMEOUT = 3
DNS_TIMEOUT = 2
TLS_TIMEOUT = 4
MAX_WORKERS = 50
MIN_LATENCY_MS = 10      # минимальная разумная задержка
MAX_LATENCY_MS = 3000    # максимальная приемлемая задержка
RECHECK_THRESHOLD = 1500 # порог для повторной проверки


class ConfigValidator:
    """Валидатор конфигов с проверкой формата и извлечением параметров"""
    
    @staticmethod
    def validate_vless(uri: str) -> Optional[Dict]:
        """Проверка VLESS конфига"""
        try:
            parsed = urllib.parse.urlparse(uri)
            if not parsed.hostname:
                return None
            
            params = urllib.parse.parse_qs(parsed.query)
            
            # Проверка обязательных параметров
            if 'type' in params:
                network = params['type'][0]
                if network not in ['tcp', 'ws', 'grpc', 'http', 'quic']:
                    return None
            
            # Проверка security
            if 'security' in params:
                security = params['security'][0]
                if security not in ['none', 'tls', 'reality']:
                    return None
            
            return {
                'host': parsed.hostname,
                'port': parsed.port or 443,
                'uuid': parsed.username,
                'params': params
            }
        except Exception:
            return None
    
    @staticmethod
    def validate_vmess(uri: str) -> Optional[Dict]:
        """Проверка VMess конфига"""
        try:
            if not uri.startswith('vmess://'):
                return None
            
            encoded = uri[8:]
            decoded = base64.b64decode(encoded + '==').decode('utf-8')
            config = json.loads(decoded)
            
            # Проверка обязательных полей
            required = ['add', 'port', 'id']
            if not all(k in config for k in required):
                return None
            
            # Проверка UUID
            uuid = config.get('id', '')
            if len(uuid) not in [36, 32]:  # стандартный UUID или без дефисов
                return None
            
            return {
                'host': config['add'],
                'port': int(config['port']),
                'uuid': config['id'],
                'params': config
            }
        except Exception:
            return None
    
    @staticmethod
    def validate_trojan(uri: str) -> Optional[Dict]:
        """Проверка Trojan конфига"""
        try:
            parsed = urllib.parse.urlparse(uri)
            if not parsed.hostname or not parsed.username:
                return None
            
            # Проверка длины пароля (обычно 40+ символов)
            if len(parsed.username) < 8:
                return None
            
            return {
                'host': parsed.hostname,
                'port': parsed.port or 443,
                'password': parsed.username,
                'params': urllib.parse.parse_qs(parsed.query)
            }
        except Exception:
            return None
    
    @staticmethod
    def validate_shadowsocks(uri: str) -> Optional[Dict]:
        """Проверка Shadowsocks конфига"""
        try:
            parsed = urllib.parse.urlparse(uri)
            
            # ss://method:password@host:port
            if parsed.username:
                userinfo = parsed.username
                if ':' in userinfo:
                    method, password = userinfo.split(':', 1)
                else:
                    # base64 encoded
                    decoded = base64.b64decode(userinfo + '==').decode('utf-8')
                    method, password = decoded.split(':', 1)
                
                valid_methods = [
                    'aes-128-gcm', 'aes-256-gcm', 'chacha20-poly1305',
                    'chacha20-ietf-poly1305', '2022-blake3-aes-128-gcm',
                    '2022-blake3-aes-256-gcm'
                ]
                
                if method not in valid_methods:
                    return None
                
                return {
                    'host': parsed.hostname,
                    'port': parsed.port or 8388,
                    'method': method,
                    'password': password
                }
        except Exception:
            return None
        return None
    
    @staticmethod
    def validate_hysteria(uri: str) -> Optional[Dict]:
        """Проверка Hysteria конфига"""
        try:
            parsed = urllib.parse.urlparse(uri)
            if not parsed.hostname:
                return None
            
            params = urllib.parse.parse_qs(parsed.query)
            
            # Проверка наличия auth или пароля
            if 'auth' not in params and not parsed.username:
                return None
            
            return {
                'host': parsed.hostname,
                'port': parsed.port or 443,
                'params': params
            }
        except Exception:
            return None


def run_mirror():
    """Запуск mirror.py (NO GEO)."""
    mirror_path = os.path.join(BASE_PATH, "mirror.py")
    if not os.path.exists(mirror_path):
        raise FileNotFoundError(f"mirror.py не найден: {mirror_path}")

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
    print("✅ mirror.py завершён успешно\n")


def protocol_of(line: str) -> Optional[str]:
    """Определение протокола"""
    for p in PROTOCOLS:
        if line.startswith(p + "://"):
            return p
    return None


def extract_host_port(line: str) -> Tuple[Optional[str], Optional[int]]:
    """Извлечение host и port из URI"""
    try:
        u = urllib.parse.urlparse(line)
        host = u.hostname
        port = u.port
        if port is None:
            if u.scheme in PROTOCOLS:
                port = 443
        return host, port
    except Exception:
        return None, None


def create_fingerprint(config: str) -> str:
    """Создание fingerprint конфига для поиска дубликатов"""
    try:
        parsed = urllib.parse.urlparse(config)
        # Убираем изменяемые параметры (remarks, etc)
        key_parts = [
            parsed.scheme,
            parsed.hostname,
            str(parsed.port),
            parsed.username or '',
        ]
        return hashlib.md5('|'.join(key_parts).encode()).hexdigest()
    except Exception:
        return hashlib.md5(config.encode()).hexdigest()


def dns_resolve(hostname: str) -> Optional[str]:
    """DNS резолв с таймаутом"""
    try:
        socket.setdefaulttimeout(DNS_TIMEOUT)
        ip = socket.gethostbyname(hostname)
        return ip
    except (socket.gaierror, socket.timeout):
        return None


def tcp_ping_with_latency(host: str, port: int, timeout: float = CONNECT_TIMEOUT) -> Tuple[bool, float]:
    """TCP-пинг с измерением задержки в миллисекундах"""
    if not host or not port:
        return False, 9999
    
    try:
        start = time.time()
        with socket.create_connection((host, port), timeout=timeout):
            latency_ms = (time.time() - start) * 1000
            
            # Фильтрация аномально быстрых ответов (возможно локальные/ошибочные)
            if latency_ms < MIN_LATENCY_MS:
                return False, latency_ms
            
            return True, latency_ms
    except (socket.timeout, OSError, ConnectionRefusedError):
        return False, 9999


def tls_handshake_check(host: str, port: int) -> bool:
    """Проверка TLS handshake для протоколов с шифрованием"""
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        with socket.create_connection((host, port), timeout=TLS_TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                return True
    except Exception:
        return False


def validate_config_format(line: str, protocol: str) -> bool:
    """Валидация формата конфига"""
    validator = ConfigValidator()
    
    validators = {
        'vless': validator.validate_vless,
        'vmess': validator.validate_vmess,
        'trojan': validator.validate_trojan,
        'ss': validator.validate_shadowsocks,
        'hysteria': validator.validate_hysteria,
        'hysteria2': validator.validate_hysteria,
        'hy2': validator.validate_hysteria,
        'tuic': validator.validate_hysteria,  # Упрощённая проверка
    }
    
    validate_func = validators.get(protocol)
    if not validate_func:
        return True  # Если нет валидатора, пропускаем
    
    result = validate_func(line)
    return result is not None


def check_config_quality(config: str, protocol: str) -> Dict:
    """Комплексная проверка качества одного конфига"""
    result = {
        'config': config,
        'protocol': protocol,
        'valid': False,
        'latency_ms': 9999,
        'checks': {
            'format': False,
            'dns': False,
            'tcp': False,
            'tls': False
        }
    }
    
    # 1. Проверка формата
    if not validate_config_format(config, protocol):
        return result
    result['checks']['format'] = True
    
    # 2. Извлечение host:port
    host, port = extract_host_port(config)
    if not host or not port:
        return result
    
    # 3. DNS резолв
    ip = dns_resolve(host)
    if not ip:
        return result
    result['checks']['dns'] = True
    
    # 4. TCP пинг с задержкой
    tcp_ok, latency = tcp_ping_with_latency(host, port)
    if not tcp_ok:
        return result
    result['checks']['tcp'] = True
    result['latency_ms'] = latency
    
    # 5. TLS handshake для протоколов с шифрованием
    if protocol in ['vless', 'vmess', 'trojan']:
        if not tls_handshake_check(host, port):
            # TLS не обязателен для всех конфигов, но его наличие — плюс
            pass
        else:
            result['checks']['tls'] = True
    
    # 6. Проверка приемлемой задержки
    if latency > MAX_LATENCY_MS:
        return result
    
    result['valid'] = True
    return result


def load_from_clean() -> Tuple[List[str], Dict]:
    """Чтение из githubmirror/clean/*.txt"""
    all_lines = []
    per_proto_raw = defaultdict(int)

    if not os.path.isdir(CLEAN_DIR):
        raise FileNotFoundError(f"Папка {CLEAN_DIR} не найдена")

    for p in PROTOCOLS:
        path = os.path.join(CLEAN_DIR, f"{p}.txt")
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if "://" in l]
        all_lines.extend(lines)
        per_proto_raw[p] += len(lines)

    return all_lines, per_proto_raw


def parallel_quality_check(configs: List[str]) -> Tuple[List[Dict], Dict]:
    """Параллельная проверка качества конфигов"""
    results = []
    stats = {
        'total': len(configs),
        'format_valid': 0,
        'dns_resolved': 0,
        'tcp_alive': 0,
        'tls_ok': 0,
        'quality_passed': 0,
        'duplicates_removed': 0
    }
    
    per_proto = defaultdict(lambda: {
        'total': 0,
        'format_valid': 0,
        'dns_resolved': 0,
        'tcp_alive': 0,
        'tls_ok': 0,
        'quality_passed': 0
    })
    
    print(f"🔍 Многоуровневая проверка {len(configs)} конфигов...")
    print(f"⚙️  Потоков: {MAX_WORKERS}, таймауты: DNS={DNS_TIMEOUT}s, TCP={CONNECT_TIMEOUT}s, TLS={TLS_TIMEOUT}s\n")
    
    seen_fingerprints = set()
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for config in configs:
            proto = protocol_of(config)
            if not proto:
                continue
            per_proto[proto]['total'] += 1
            future = executor.submit(check_config_quality, config, proto)
            futures[future] = (config, proto)
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            if completed % 100 == 0:
                print(f"  ✓ Проверено {completed}/{len(futures)}...")
            
            try:
                result = future.result()
                config, proto = futures[future]
                
                # Статистика по этапам
                if result['checks']['format']:
                    stats['format_valid'] += 1
                    per_proto[proto]['format_valid'] += 1
                
                if result['checks']['dns']:
                    stats['dns_resolved'] += 1
                    per_proto[proto]['dns_resolved'] += 1
                
                if result['checks']['tcp']:
                    stats['tcp_alive'] += 1
                    per_proto[proto]['tcp_alive'] += 1
                
                if result['checks']['tls']:
                    stats['tls_ok'] += 1
                    per_proto[proto]['tls_ok'] += 1
                
                if result['valid']:
                    # Проверка на дубликаты
                    fp = create_fingerprint(config)
                    if fp in seen_fingerprints:
                        stats['duplicates_removed'] += 1
                        continue
                    seen_fingerprints.add(fp)
                    
                    stats['quality_passed'] += 1
                    per_proto[proto]['quality_passed'] += 1
                    results.append(result)
                    
            except Exception as e:
                print(f"  ⚠️  Ошибка при проверке: {e}")
    
    return results, stats, per_proto


def recheck_slow_configs(results: List[Dict]) -> List[Dict]:
    """Повторная проверка конфигов с высокой задержкой"""
    slow_configs = [r for r in results if r['latency_ms'] > RECHECK_THRESHOLD]
    
    if not slow_configs:
        return results
    
    print(f"\n🔄 Повторная проверка {len(slow_configs)} конфигов с высокой задержкой...")
    
    rechecked = []
    for result in slow_configs:
        host, port = extract_host_port(result['config'])
        if not host or not port:
            continue
        
        # Делаем 3 проверки и берём минимальную задержку
        latencies = []
        for _ in range(3):
            ok, lat = tcp_ping_with_latency(host, port)
            if ok:
                latencies.append(lat)
            time.sleep(0.1)
        
        if latencies:
            result['latency_ms'] = min(latencies)
            if result['latency_ms'] <= MAX_LATENCY_MS:
                rechecked.append(result)
    
    # Объединяем с быстрыми конфигами
    fast_configs = [r for r in results if r['latency_ms'] <= RECHECK_THRESHOLD]
    all_results = fast_configs + rechecked
    
    print(f"  ✓ После перепроверки осталось {len(all_results)} из {len(results)}")
    
    return all_results


def write_final(results: List[Dict]):
    """Запись финальных файлов с сортировкой по задержке"""
    buckets = defaultdict(list)
    
    for result in results:
        proto = result['protocol']
        buckets[proto].append(result)
    
    for proto, items in buckets.items():
        # Сортировка по задержке (лучшие первыми)
        items_sorted = sorted(items, key=lambda x: x['latency_ms'])
        
        # Основной файл
        out_path = os.path.join(FINAL_DIR, f"{proto}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            for item in items_sorted:
                f.write(f"{item['config']}\n")
        
        # Файл с метаданными (задержка, проверки)
        meta_path = os.path.join(REPORT_DIR, f"{proto}_quality.txt")
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(f"# Quality Report for {proto.upper()}\n")
            f.write(f"# Total configs: {len(items)}\n")
            f.write(f"# Avg latency: {sum(i['latency_ms'] for i in items)/len(items):.1f}ms\n\n")
            
            for item in items_sorted:
                checks = item['checks']
                f.write(f"Latency: {item['latency_ms']:.0f}ms | "
                       f"Format:{checks['format']} DNS:{checks['dns']} "
                       f"TCP:{checks['tcp']} TLS:{checks['tls']}\n")
                f.write(f"{item['config']}\n\n")
        
        print(f"💾 {proto}: {len(items)} конфигов → {out_path}")
        print(f"   📊 Отчёт: {meta_path}")


def save_detailed_report(stats: Dict, per_proto: Dict):
    """Сохранение детального отчёта"""
    report_path = os.path.join(REPORT_DIR, "quality_report.txt")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("QUALITY CHECK DETAILED REPORT\n")
        f.write("=" * 60 + "\n\n")
        
        f.write("OVERALL STATISTICS:\n")
        f.write(f"  Total configs checked:    {stats['total']}\n")
        f.write(f"  Format validation passed: {stats['format_valid']} ({stats['format_valid']/stats['total']*100:.1f}%)\n")
        f.write(f"  DNS resolved:             {stats['dns_resolved']} ({stats['dns_resolved']/stats['total']*100:.1f}%)\n")
        f.write(f"  TCP connection success:   {stats['tcp_alive']} ({stats['tcp_alive']/stats['total']*100:.1f}%)\n")
        f.write(f"  TLS handshake success:    {stats['tls_ok']} ({stats['tls_ok']/stats['total']*100:.1f}%)\n")
        f.write(f"  Quality passed:           {stats['quality_passed']} ({stats['quality_passed']/stats['total']*100:.1f}%)\n")
        f.write(f"  Duplicates removed:       {stats['duplicates_removed']}\n\n")
        
        f.write("PER-PROTOCOL STATISTICS:\n")
        for proto in PROTOCOLS:
            if per_proto[proto]['total'] == 0:
                continue
            p = per_proto[proto]
            f.write(f"\n  {proto.upper()}:\n")
            f.write(f"    Total:        {p['total']}\n")
            f.write(f"    Format OK:    {p['format_valid']} ({p['format_valid']/p['total']*100:.1f}%)\n")
            f.write(f"    DNS OK:       {p['dns_resolved']} ({p['dns_resolved']/p['total']*100:.1f}%)\n")
            f.write(f"    TCP OK:       {p['tcp_alive']} ({p['tcp_alive']/p['total']*100:.1f}%)\n")
            f.write(f"    TLS OK:       {p['tls_ok']} ({p['tls_ok']/p['total']*100:.1f}%)\n")
            f.write(f"    Quality OK:   {p['quality_passed']} ({p['quality_passed']/p['total']*100:.1f}%)\n")
    
    print(f"\n📄 Детальный отчёт: {report_path}")


def main():
    start_ts = time.time()

    # 1. Запуск mirror.py
    run_mirror()

    # 2. Чтение из clean/*
    all_lines, per_proto_raw = load_from_clean()
    print(f"📥 После mirror.py (clean/*): {len(all_lines)} конфигов")
    print("\n📋 По протоколам (до проверки):")
    for p in PROTOCOLS:
        if per_proto_raw[p]:
            print(f"   {p:12s}: {per_proto_raw[p]:6d}")

    # 3. Многоуровневая проверка качества
    print()
    results, stats, per_proto = parallel_quality_check(all_lines)

    # 4. Повторная проверка медленных
    results = recheck_slow_configs(results)

    # 5. Запись финальных файлов
    print()
    write_final(results)

    # 6. Сохранение отчёта
    save_detailed_report(stats, per_proto)

    # 7. Финальная статистика
    print("\n" + "=" * 60)
    print("✅ ПАЙПЛАЙН ЗАВЕРШЁН")
    print("=" * 60)
    print(f"\n📊 ОБЩАЯ СТАТИСТИКА:")
    print(f"   Всего проверено:          {stats['total']}")
    print(f"   ✓ Валидный формат:        {stats['format_valid']} ({stats['format_valid']/stats['total']*100:.1f}%)")
    print(f"   ✓ DNS резолв:             {stats['dns_resolved']} ({stats['dns_resolved']/stats['total']*100:.1f}%)")
    print(f"   ✓ TCP соединение:         {stats['tcp_alive']} ({stats['tcp_alive']/stats['total']*100:.1f}%)")
    print(f"   ✓ TLS handshake:          {stats['tls_ok']} ({stats['tls_ok']/stats['total']*100:.1f}%)")
    print(f"   ✅ Прошли все проверки:   {stats['quality_passed']} ({stats['quality_passed']/stats['total']*100:.1f}%)")
    print(f"   🗑️  Удалено дубликатов:    {stats['duplicates_removed']}")

    print(f"\n📈 ПО ПРОТОКОЛАМ:")
    for p in PROTOCOLS:
        if per_proto[p]['total'] == 0:
            continue
        pt = per_proto[p]
        print(f"\n   {p.upper()}:")
        print(f"      Всего:     {pt['total']:5d}")
        print(f"      Формат:    {pt['format_valid']:5d} ({pt['format_valid']/pt['total']*100:5.1f}%)")
        print(f"      DNS:       {pt['dns_resolved']:5d} ({pt['dns_resolved']/pt['total']*100:5.1f}%)")
        print(f"      TCP:       {pt['tcp_alive']:5d} ({pt['tcp_alive']/pt['total']*100:5.1f}%)")
        print(f"      TLS:       {pt['tls_ok']:5d} ({pt['tls_ok']/pt['total']*100:5.1f}%)")
        print(f"      Качество:  {pt['quality_passed']:5d} ({pt['quality_passed']/pt['total']*100:5.1f}%)")

    elapsed = time.time() - start_ts
    print(f"\n⏱️  Общее время работы: {elapsed:.1f} сек ({elapsed/60:.1f} мин)")
    print(f"⚡ Скорость проверки: {stats['total']/elapsed:.1f} конфигов/сек")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
