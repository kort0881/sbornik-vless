#!/usr/bin/env python3
# Mirror.py — Оптимизированная версия с устойчивыми сетевыми запросами

import os
import shutil
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib.parse
import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Set, List, Tuple, Dict
import time

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(BASE_PATH, "githubmirror")
NEW_DIR = os.path.join(BASE_DIR, "new")
CLEAN_DIR = os.path.join(BASE_DIR, "clean")
NEW_BY_PROTO_DIR = os.path.join(NEW_DIR, "by_protocol")

PROTOCOLS = ["vless", "vmess", "trojan", "ss", "hysteria", "hysteria2", "hy2", "tuic"]
DRY_RUN = os.environ.get("MIRROR_DRY_RUN", "0") == "1"

# Настройки производительности
MAX_WORKERS = int(os.environ.get("MIRROR_MAX_WORKERS", "20"))
TIMEOUT = int(os.environ.get("MIRROR_TIMEOUT", "10"))
CHUNK_SIZE = 500

URLS_BASE = [
    "https://raw.githubusercontent.com/Airuop/archive/6aefdedc2cde21ff91bd14105393cda477c6ae21/donated/2309/230916_0501M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/6aefdedc2cde21ff91bd14105393cda477c6ae21/donated/2309/230923_2310M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/6aefdedc2cde21ff91bd14105393cda477c6ae21/donated/2310/231004_0310M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/6aefdedc2cde21ff91bd14105393cda477c6ae21/donated/2310/231009_1110M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/6aefdedc2cde21ff91bd14105393cda477c6ae21/donated/2311/231122_1510M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/6aefdedc2cde21ff91bd14105393cda477c6ae21/donated/2312/231213_1710M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/6aefdedc2cde21ff91bd14105393cda477c6ae21/donated/2312/231218_0311M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/6aefdedc2cde21ff91bd14105393cda477c6ae21/donated/2312/231223_1411M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/6aefdedc2cde21ff91bd14105393cda477c6ae21/donated/2401/240109_1712M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/6aefdedc2cde21ff91bd14105393cda477c6ae21/update/2310/231005_0503.txt",
    "https://raw.githubusercontent.com/Airuop/archive/a3a7ed0bcf661d1d503b0005812df1fdc7c6f4b0/donated/2310/231003_2310M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/a3a7ed0bcf661d1d503b0005812df1fdc7c6f4b0/donated/2310/231004_2210M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/a3a7ed0bcf661d1d503b0005812df1fdc7c6f4b0/donated/2310/231013_0508M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/a3a7ed0bcf661d1d503b0005812df1fdc7c6f4b0/donated/2310/231018_2211M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/a3a7ed0bcf661d1d503b0005812df1fdc7c6f4b0/donated/2310/231026_0711M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/a3a7ed0bcf661d1d503b0005812df1fdc7c6f4b0/donated/2310/231029_0710M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/a3a7ed0bcf661d1d503b0005812df1fdc7c6f4b0/donated/2311/231106_0910M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/a3a7ed0bcf661d1d503b0005812df1fdc7c6f4b0/donated/2401/240111_2111M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/a3a7ed0bcf661d1d503b0005812df1fdc7c6f4b0/donated/2401/240124_0210M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/c3954c9c5155b9c9726f46ef520ae22e29c6ebf1/selected/2311/231113_1936S.txt",
    "https://raw.githubusercontent.com/Airuop/archive/c3954c9c5155b9c9726f46ef520ae22e29c6ebf1/selected/2311/231127_1045S.txt",
    "https://raw.githubusercontent.com/Airuop/archive/f020a942e86d0a0f8e5b1abe53d6348e27b54103/donated/2312/231202_0011M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/f020a942e86d0a0f8e5b1abe53d6348e27b54103/donated/2312/231231_0710M.txt",
    "https://raw.githubusercontent.com/Airuop/archive/f020a942e86d0a0f8e5b1abe53d6348e27b54103/update/2310/231005_0503.txt",
    "https://raw.githubusercontent.com/Airuop/archive/f020a942e86d0a0f8e5b1abe53d6348e27b54103/update/2310/231005_0701.txt",
    "https://raw.githubusercontent.com/Airuop/cross/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/AmirHDevo/temp2/7f15e7ddb311a6f8c5ab338bd1af0e1f2136a84b/configs.txt",
    "https://raw.githubusercontent.com/andytjh/v2ray/0b6e7d606a51a1772e943aa1073f22551ed0f127/07-19v.txt",
    "https://raw.githubusercontent.com/Argh94/V2RayAutoConfig/refs/heads/main/configs/Hysteria2.txt",
    "https://raw.githubusercontent.com/Argh94/V2RayAutoConfig/refs/heads/main/configs/Vless.txt",
    "https://raw.githubusercontent.com/Ashkan-m/v2ray/a4c9dcdb41aa71477aabb2588c241c27228163ba/Sub.txt",
    "https://raw.githubusercontent.com/AzadNetCH/Clash/refs/heads/main/AzadNet.txt",
    "https://raw.githubusercontent.com/Barabama/FreeNodes/4b1deddc866bb4b5e925cac9cd16db5782b59c27/nodes/yudou66.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Configs/ced94ddfff48276ec365b40227561f36b1b64bc8/Sub5.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Configs/main/Splitted-By-Protocol/vless.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Configs/main/Sub1.txt",
    "https://raw.githubusercontent.com/chxxyz2004/zd/17fca23b73c46b5dd73e9be49b14d219b5e5f836/sub/2401/240110.txt",
    "https://raw.githubusercontent.com/coldwater-10/Vpnclashfa/e7b9b6a2cfb01ce1d94018977eecc06ea0d731dc/raw/tuic%20%26%20hy2.txt",
    "https://raw.githubusercontent.com/Crusader-Strike/AKBConf/e092ca19c23eae315e59facf829be930bf08229a/AKBConfigs.txt",
    "https://raw.githubusercontent.com/deepinor/v2ray_luck/702642c1867e6e5cdf871d91255510c945c40b35/node.txt",
    "https://raw.githubusercontent.com/dimzon/scaling-sniffle/7f5f4f1c31d96015218da9ead3d07405f3471e46/by-country/EE.txt",
    "https://raw.githubusercontent.com/ellondoa/tele-providers-collector/cf1744ead53efd54bc31b16fa16b3eff9ee24498/script/raw/protocols/hysteria.txt",
    "https://raw.githubusercontent.com/Ennzo0/V2ray/e5bf5c5f54a1d8aad71975ccd8e988a3042920b7/all.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/raw/main/Splitted-By-Protocol/trojan.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/raw/main/Splitted-By-Protocol/vmess.txt",
    "https://raw.githubusercontent.com/fakmoth/vmess_tg/main/v2",
    "https://raw.githubusercontent.com/Fido6/FreeNodes/57221e59caddde55ffdda21d491ae952cd608049/nodes/halekj.txt",
    "https://raw.githubusercontent.com/Fido6/FreeNodes/57221e59caddde55ffdda21d491ae952cd608049/nodes/kkzui.txt",
    "https://raw.githubusercontent.com/Fido6/FreeNodes/57221e59caddde55ffdda21d491ae952cd608049/nodes/wenode.txt",
    "https://raw.githubusercontent.com/free18/jd/da18c454eb4ed09466c41ebd24cc6ae214a33e88/07-20t.txt",
    "https://raw.githubusercontent.com/free18/jd/da18c454eb4ed09466c41ebd24cc6ae214a33e88/07-21f.txt",
    "https://raw.githubusercontent.com/free18/jd/da18c454eb4ed09466c41ebd24cc6ae214a33e88/07-24p.txt",
    "https://raw.githubusercontent.com/freev2rayconfig/V2RAY_SUB/3e6a7786a1601ee3723e8d043ae79e70dbdfd9a8/v2rayconfigs.txt",
    "https://raw.githubusercontent.com/hameed-maleki/TVC/89a4522969c57dcc22458cae9898426e5c4f2679/lite/config.txt",
    "https://raw.githubusercontent.com/HDYOU/porxy/a580704fd54db8e7180629d8163d2a8f6158d0dc/data/no_code_proxy.txt",
    "https://raw.githubusercontent.com/hfarahani/vv/63f6ae6c3f6bdb572c4d5836d72bac9ebf6ea9a4/co.txt",
    "https://raw.githubusercontent.com/hkpc/Autoproxy/6cf946ddfc677a29062007e4b47d70674474baa7/sub/2401/240110.txt",
    "https://raw.githubusercontent.com/hkpc/V2ray-Configs/7d9aa0dabf947af180a7dd6302818ed37950531a/Sub1.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/Vless-Reality-White-Lists-Rus-Cable.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
    "https://raw.githubusercontent.com/Kwinshadow/TelegramV2rayCollector/raw/refs/heads/main/sublinks/mix.txt",
    "https://raw.githubusercontent.com/lagzian/SS-Collector/main/mix_clash.yaml",
    "https://raw.githubusercontent.com/LalatinaHub/Mineral/raw/refs/heads/master/result/nodes",
    "https://raw.githubusercontent.com/liketolivefree/kobabi/195a773fa0ef0525ce6595b47ef9af5f838f2356/sub.txt",
    "https://raw.githubusercontent.com/liufung/v2ray-1/5dc697ea84893c770b59c5e2c94d4efda772d94a/Sub.txt",
    "https://raw.githubusercontent.com/LonUp/NodeList/7b27813bfebb55f4abc982335fa9f14268f2d456/V2RAY/046.txt",
    "https://raw.githubusercontent.com/M-Mashreghi/free-config-collector/main/Splitted-By-Protocol/ssr.txt",
    "https://raw.githubusercontent.com/M450ud/PrList/fc8a69e79d70fdbf955f3ca29a60566051599041/dsl.txt",
    "https://raw.githubusercontent.com/M450ud/PrList/fc8a69e79d70fdbf955f3ca29a60566051599041/prx.txt",
    "https://raw.githubusercontent.com/mahdi-marjani/v2ray-server-regex/f41d1a3cf896b2f1a3af1f508af36ca4361ac983/output.txt",
    "https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/Eternity",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_list.json",
    "https://raw.githubusercontent.com/Mahdi0024/ProxyCollector/master/sub/proxies.txt",
    "https://raw.githubusercontent.com/mehran1404/Sub_Link/refs/heads/main/V2RAY-Sub.txt",
    "https://raw.githubusercontent.com/mheidari98/.proxy/refs/heads/main/all",
    "https://raw.githubusercontent.com/mheidari98/.proxy/refs/heads/main/vless",
    "https://raw.githubusercontent.com/MhdiTaheri/V2rayCollector/raw/refs/heads/main/sub/mix",
    "https://raw.githubusercontent.com/MhdiTaheri/V2rayCollector_Py/412f5977c513649827f187ab2385fe725f9f6164/sub/United%20States/config.txt",
    "https://raw.githubusercontent.com/MhdiTaheri/V2rayCollector_Py/raw/refs/heads/main/sub/Mix/mix.txt",
    "https://raw.githubusercontent.com/miladtahanian/multi-proxy-config-fetcher/refs/heads/main/configs/proxy_configs.txt",
    "https://raw.githubusercontent.com/miladtahanian/V2RayCFGDumper/refs/heads/main/config.txt",
    "https://raw.githubusercontent.com/moeinkey/key/b1e8ce539e8328ade2aa79211750f35ce15afe15/new.txt",
    "https://raw.githubusercontent.com/mohamadfg-dev/telegram-v2ray-configs-collector/refs/heads/main/category/vless.txt",
    "https://raw.githubusercontent.com/Mosifree/-FREE2CONFIG/refs/heads/main/Reality",
    "https://raw.githubusercontent.com/MrMohebi/xray-proxy-grabber-telegram/master/collected-proxies/row-url/actives.txt",
    "https://raw.githubusercontent.com/MrMohebi/xray-proxy-grabber-telegram/master/collected-proxies/row-url/all.txt",
    "https://raw.githubusercontent.com/mrvcoder/V2rayCollector/d5e2e4c2774e527521838841a821cdf9359b4854/ss_iran.txt",
    "https://raw.githubusercontent.com/ndsphonemy/proxy-sub/f05f42764ced69b9591875fe786dfe230f0ed266/hys-tuic.txt",
    "https://raw.githubusercontent.com/ndsphonemy/proxy-sub/f8011c8975b97a6be74db81c05f4046f7cf2a804/lt-sub.txt",
    "https://raw.githubusercontent.com/ndsphonemy/proxy-sub/main/speed.txt",
    "https://raw.githubusercontent.com/NiREvil/vless/575cbe54417021787f11fd6618f3c299e2904f25/sub/catnip.txt",
    "https://raw.githubusercontent.com/NiREvil/vless/main/sub/SSTime",
    "https://raw.githubusercontent.com/op30mmd/things/909b38024ba14d69dc0f95c238f63bc6e930a00f/eut.txt",
    "https://raw.githubusercontent.com/OpenCNLink/freevpn/3cfcff048bfdd1493ccffa52ecf30ce7f9fc6b28/src/list/vmess.txt",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/refs/heads/main/sub",
    "https://raw.githubusercontent.com/rasoulnorouzi/rasoulnorouzi.github.io/26fb7c851f0cafea9e8b1e545c0baa2ce96780a6/sources/files/rey.txt",
    "https://raw.githubusercontent.com/RaymondHarris971/ssrsub/master/9a075bdee5.txt",
    "https://raw.githubusercontent.com/resasanian/Mirza/1e45095b374a6e8d3861f1c88f78d51ef59bf61d/mirza-all.txt",
    "https://raw.githubusercontent.com/ResistalProxy/V2Ray/e927ffb37f732edea84f81d1eca555f6b29784c1/server.txt",
    "https://raw.githubusercontent.com/rb360full/V2Ray-Configs/8111c190def6b6714982369cfb1685434eff11cf/Reza-ClashConfig.txt",
    "https://raw.githubusercontent.com/rb360full/V2Ray-Configs/8111c190def6b6714982369cfb1685434eff11cf/Reza-configs.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt",
    "https://raw.githubusercontent.com/sajad-sajadi/V2ray-Collector/raw/main/output/protocols/vmess.txt",
    "https://raw.githubusercontent.com/Sajad-meow/free-vmess/0a2bf5319c9bec099ebbaa5e0d9bbc8414116880/vp.txt",
    "https://raw.githubusercontent.com/sakha1370/OpenRay/raw/refs/heads/main/output/all_valid_proxies.txt",
    "https://raw.githubusercontent.com/sami-soft/v2rayN_proxy/447a8383ec54f243cbeee05196a9093cf60a2eb/new2.txt",
    "https://raw.githubusercontent.com/satrom/V2SSR/master/SSR/Sub.txt",
    "https://raw.githubusercontent.com/satrom/V2SSR/master/V2RAY/Sub.txt",
    "https://raw.githubusercontent.com/Saviorhoss/V2ray2/dbb72f8ab0c06fd5bf98d639789b07c818770ee3/hysteria.txt",
    "https://raw.githubusercontent.com/Saviorhoss/V2ray2/dbb72f8ab0c06fd5bf98d639789b07c818770ee3/ss.txt",
    "https://raw.githubusercontent.com/sevcator/5ubscrpt10n/main/protocols/vl.txt",
    "https://raw.githubusercontent.com/shabane/kamaji/75e841a6c9735a4e8d1840cc6c2d95a80b89673b/hub/vmess.txt",
    "https://raw.githubusercontent.com/shabane/kamaji/master/hub/merged.txt",
    "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/splitted/subscribe",
    "https://raw.githubusercontent.com/STR97/STRUGOV/refs/heads/main/STR.BYPASS",
    "https://raw.githubusercontent.com/sunshinehome/zidong/b4a61de307b189c6585a72642d737b0833d8d31e/%E4%BB%A3%E7%90%86%E6%B1%A0%E9%93%BE%E6%8E%A501.txt",
    "https://raw.githubusercontent.com/sunshinehome/zidong/b4a61de307b189c6585a72642d737b0833d8d31e/%E6%88%91%E7%94%A8%E7%9A%84%E4%BB%93%E5%BA%93.txt",
    "https://raw.githubusercontent.com/sunshinehome/zidong/b4a61de307b189c6585a72642d737b0833d8d31e/%E7%A7%91%E5%AD%A6%E4%B8%8A%E7%BD%91%E7%9A%84%E6%96%B9%E6%B3%95.txt",
    "https://raw.githubusercontent.com/Tazan1230/NoMoreWalls/db6e37cf0b8d5674e02085d371289a71c720a8d1/list_raw.txt",
    "https://raw.githubusercontent.com/tristan-deng/v2rayNodesSelected/ba42c865f6f963b8ea1c980207b826c0502eb063/MyNodes.txt",
    "https://raw.githubusercontent.com/V2RayRoot/V2RayConfig/refs/heads/main/Config/vless.txt",
    "https://raw.githubusercontent.com/v2clash/Autoproxy/a81f840ab2364124133572ec94e4b81fb0d4e58d/sub/2401/240104.txt",
    "https://raw.githubusercontent.com/v2clash/V2ray-Configs/31f493c584d0c7b56350f4a34d80c53ad82bcc18/Sub9.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/57e88e0b2dec9f04a3eb11b4a57a1a4fc0416c9b/sub/2311/231108.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2310/231031.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2311/231106.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2311/231111.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2311/231116.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2311/231123.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2311/231124.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2312/231216.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2312/231218.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2312/231219.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2401/240109.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2401/240110.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2401/240122.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2401/240123.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2401/240124.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/799bcf41567dff8a3cfea7ab8c2bbbadeffe32ea/sub/2402/240202.txt",
    "https://raw.githubusercontent.com/w1770946466/Auto_proxy/main/Long_term_subscription_num",
    "https://raw.githubusercontent.com/wuqb2i4f/xray-config-toolkit/main/output/base64/mix-uri",
    "https://raw.githubusercontent.com/wudongdefeng/free/914cea8410a6712d45ba8feb88ac2626db2ada0a/nodes/nodefree.txt",
    "https://raw.githubusercontent.com/wudongdefeng/free/914cea8410a6712d45ba8feb88ac2626db2ada0a/nodes/yudou66.txt",
    "https://raw.githubusercontent.com/xiaozhu2007/xiaozhu2007/61a755a044dbaeea678bc2d1e20f21a21c6d7170/docs/fxxk.txt",
    "https://raw.githubusercontent.com/YasserDivaR/pr0xy/refs/heads/main/ShadowSocks2021.txt",
    "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/normal/mix",
    "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/normal/vless",
    "https://raw.githubusercontent.com/yebekhe/TVC/0f745f92bf381e505f1245abbc7c145b19b11503/config.txt",
    "https://raw.githubusercontent.com/yebekhe/TVC/9fac69239c69327fb7a61f5a8d79d107133889e1/lite/config.txt",
    "https://raw.githubusercontent.com/yebekhe/V2Hub/main/merged",
    "https://raw.githubusercontent.com/yebekhe/V2Hub/main/Split/Normal/shadowsocks",
    "https://raw.githubusercontent.com/yitong2333/proxy-minging/refs/heads/main/v2ray.txt",
    "https://raw.githubusercontent.com/youfoundamin/V2rayCollector/main/mixed_iran.txt",
    "https://raw.githubusercontent.com/yyyr-otz/tele-providers-collector/019cb3e07ee52fddbc7caa54fc670c6b9bae6539/sub/proxies.txt",
    "https://raw.githubusercontent.com/yyyr-otz/tele-providers-collector/b7a74ee98bcf02c5a507d688a1bed3aa9f7f4ed1/script/raw/protocols/mixed.txt",
    "https://raw.githubusercontent.com/abbasdvd3/abbasdvd10/73ec60de7a6c6aa6df4c14b511c1da60686891ca/ppo.txt",
    "https://raw.githubusercontent.com/acymz/AutoVPN/refs/heads/main/data/V2.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/EternityBase",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/EternityAir.txt"
]

CONFIG_SOURCES_FILE = os.path.join(BASE_PATH, "config_sources.json")


def create_session() -> requests.Session:
    """Создаёт сессию с повторными попытками и connection pooling (устойчиво к временным DNS/сетевым сбоям)."""
    session = requests.Session()
    retry = Retry(
        total=5,                # больше попыток
        connect=5,
        read=5,
        backoff_factor=0.8,     # экспоненциальный backoff: 0.8, 1.6, 3.2, ...
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=100, pool_maxsize=100)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    # Явный заголовок user-agent — иногда помогает при редких блокировках
    session.headers.update({"User-Agent": "githubmirror/1.0 (+https://github.com/igareck)"})
    return session


def load_all_urls() -> List[str]:
    """Загружает все URL из базового списка и config_sources.json."""
    urls = set(URLS_BASE)
    if os.path.exists(CONFIG_SOURCES_FILE):
        try:
            with open(CONFIG_SOURCES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                urls.update(u.strip() for u in data if isinstance(u, str) and u.strip())
        except Exception as e:
            print(f"⚠️ Ошибка чтения config_sources.json: {e}")
    return sorted(urls)


def clean_start():
    """Очищает и создаёт директории."""
    if DRY_RUN:
        print("⚙️ MIRROR_DRY_RUN=1 — файловая система не изменяется")
        return
    if os.path.exists(BASE_DIR):
        shutil.rmtree(BASE_DIR)
    os.makedirs(NEW_DIR, exist_ok=True)
    os.makedirs(CLEAN_DIR, exist_ok=True)
    os.makedirs(NEW_BY_PROTO_DIR, exist_ok=True)


def protocol_of(line: str) -> str:
    """Определяет протокол из строки."""
    for p in PROTOCOLS:
        if line.startswith(p + "://"):
            return p
    return None


def extract_host_port_scheme(line: str) -> Tuple[str, int, str]:
    """Извлекает хост, порт и схему из URL."""
    try:
        u = urllib.parse.urlparse(line)
        return u.hostname, u.port or 443, u.scheme
    except Exception:
        return None, None, None


def decode_content(content: str) -> str:
    """Пытается декодировать base64, если это необходимо."""
    if "://" not in content:
        try:
            return base64.b64decode(content + "==").decode("utf-8", errors="ignore")
        except Exception:
            pass
    return content


def fetch_url(session: requests.Session, url: str, index: int, total: int) -> Tuple[int, Set[str]]:
    """Загружает один URL и возвращает найденные конфиги, с локальными retry на случай DNS/сетевых сбоев."""
    keys: Set[str] = set()
    max_local_retries = 3
    for attempt in range(1, max_local_retries + 1):
        try:
            r = session.get(url, timeout=TIMEOUT)
            if r.status_code != 200:
                print(f"{index}/{total} ❌ HTTP {r.status_code}: {url[:80]}")
                return 0, keys

            content = decode_content(r.text.strip())
            for line in content.splitlines():
                line = line.strip()
                if protocol_of(line):
                    keys.add(line)

            print(f"{index}/{total} ✅ {len(keys)} конфигов")
            return len(keys), keys

        except requests.Timeout:
            print(f"{index}/{total} ⏱️ Timeout (попытка {attempt}/{max_local_retries}): {url[:80]}")
        except requests.ConnectionError as e:
            # В т.ч. socket.gaierror [Errno -3] Temporary failure in name resolution
            print(f"{index}/{total} 🌐 ConnectionError (попытка {attempt}/{max_local_retries}): {url[:80]} — {e}")
        except Exception as e:
            print(f"{index}/{total} ⚠️ {type(e).__name__} (попытка {attempt}/{max_local_retries}): {url[:80]} — {e}")
            break

        if attempt < max_local_retries:
            sleep_sec = 1.5 * attempt
            time.sleep(sleep_sec)

    return 0, keys


def write_chunks_by_protocol(base_dir: str, protocol: str, items: List[str], chunk_size: int = 500):
    """Записывает конфиги по чанкам."""
    if DRY_RUN:
        return

    proto_dir = os.path.join(base_dir, protocol)
    os.makedirs(proto_dir, exist_ok=True)

    for start in range(0, len(items), chunk_size):
        part = items[start:start + chunk_size]
        part_num = start // chunk_size + 1
        with open(os.path.join(proto_dir, f"{protocol}_{part_num:03d}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(part))


def main():
    start_time = time.time()
    clean_start()

    urls = load_all_urls()
    print(f"🚀 Начало сбора из {len(urls)} источников")
    print(f"⚙️ Параллельных потоков: {MAX_WORKERS}, таймаут: {TIMEOUT}с\n")

    all_keys: Set[str] = set()
    session = create_session()

    # Параллельная загрузка
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(fetch_url, session, url, i, len(urls)): url
            for i, url in enumerate(urls, 1)
        }

        for future in as_completed(futures):
            try:
                count, keys = future.result()
                all_keys.update(keys)
            except Exception as e:
                print(f"⚠️ Ошибка в потоке: {e}")

    all_keys_list = sorted(all_keys)

    # Запись всех конфигов
    if not DRY_RUN:
        with open(os.path.join(NEW_DIR, "all_new.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(all_keys_list))

    # Группировка по протоколам (без geo-фильтров)
    raw_buckets: Dict[str, List[str]] = {p: [] for p in PROTOCOLS}
    for line in all_keys_list:
        p = protocol_of(line)
        if p:
            raw_buckets[p].append(line)

    for p, items in raw_buckets.items():
        if items:
            write_chunks_by_protocol(NEW_BY_PROTO_DIR, p, items, CHUNK_SIZE)

    # Дедупликация по IP:PORT:SCHEME
    seen_ip = set()
    clean_keys: List[str] = []

    for line in all_keys_list:
        host, port, scheme = extract_host_port_scheme(line)
        if not host:
            continue
        key = (host, port, scheme)
        if key not in seen_ip:
            seen_ip.add(key)
            clean_keys.append(line)

    # Запись чистых файлов
    if not DRY_RUN:
        for p in PROTOCOLS:
            items = [k for k in clean_keys if protocol_of(k) == p]
            if items:
                with open(os.path.join(CLEAN_DIR, f"{p}.txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(items))

    elapsed = time.time() - start_time

    print(f"\n✅ ГОТОВО за {elapsed:.1f}с!")
    print(f"   📥 Всего конфигов: {len(all_keys_list)}")
    print(f"   🔗 Уникальных IP:PORT:SCHEME: {len(clean_keys)}")
    if elapsed > 0:
        print(f"   ⚡ Скорость: {len(urls)/elapsed:.1f} источников/сек\n")

    print("📊 Статистика по протоколам:")
    for p in PROTOCOLS:
        count = len([k for k in clean_keys if protocol_of(k) == p])
        if count > 0:
            print(f"   {p:12s}: {count:6d}")


if __name__ == "__main__":
    main()












































































