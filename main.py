#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPSelector Engine - 单文件全能优选工具
功能:
  1. 读取 IP:Port 列表 (文件/标准输入/参数)
  2. 高并发测速: TCP连接 + TLS握手 + HTTP真连 + 下载测速(可选)
  3. 离线识别: 运营商(ASN) + 国家/省/市 (需 GeoLite2 mmdb 文件)
  4. 智能评分 & 排序
  5. 导出: Clash / Sing-box / Shadowrocket / Surge / JSON / CSV
  6. 一键上传结果到 GitHub Release (gh cli)

依赖:
  pip install maxminddb-geolite2  # 可选, 自动下载 mmdb
  # 或手动放置 GeoLite2-City.mmdb / GeoLite2-ASN.mmdb 到 ./geoip/
  brew install gh  # 上传用

用法:
  python main.py -i ips.txt -o result.yaml --tls --http --geo --upload
  python main.py --scan 192.168.1.0/24 --ports 443,8443,2053,2083,2087,2096 --tls --geo
  cat ips.txt | python main.py --stdin --tls --http -o clash.yaml
"""
import asyncio, socket, ssl, time, json, csv, sys, os, re, argparse, subprocess, ipaddress, random, gzip, shutil
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ========================= 配置常量 =========================
CONCURRENCY = 500          # 并发协程数
TCP_TIMEOUT = 3.0          # TCP 连接超时(s)
TLS_TIMEOUT = 5.0          # TLS 握手超时(s)
HTTP_TIMEOUT = 8.0         # HTTP 请求超时(s)
DOWNLOAD_TIMEOUT = 10.0    # 下载测速超时(s)
DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=1048576"  # 1MB 测速文件
DOWNLOAD_SIZE = 1_048_576
SCORE_WEIGHT = {"tcp": 0.3, "tls": 0.3, "http": 0.2, "dl": 0.2}  # 评分权重
MAX_LATENCY_MS = 2000      # 超过视为失败

GEO_DIR = Path(__file__).parent / "geoip"
CITY_DB = GEO_DIR / "GeoLite2-City.mmdb"
ASN_DB  = GEO_DIR / "GeoLite2-ASN.mmdb"
MMDB_URLS = {
    "GeoLite2-City.mmdb": "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-City.mmdb",
    "GeoLite2-ASN.mmdb":  "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-ASN.mmdb",
}

# ========================= 数据模型 =========================
@dataclass
class ProbeResult:
    ip: str
    port: int
    tcp_ms: Optional[int] = None
    tls_ms: Optional[int] = None
    http_ms: Optional[int] = None
    dl_mbps: Optional[float] = None
    sni: Optional[str] = None
    cert_expire: Optional[str] = None
    cert_issuer: Optional[str] = None
    country: str = ""
    region: str = ""
    city: str = ""
    isp: str = ""
    asn: str = ""
    score: float = 0.0
    error: str = ""

    @property
    def addr(self) -> str: return f"{self.ip}:{self.port}"
    def to_dict(self) -> dict: return asdict(self)

# ========================= 工具函数 =========================
def log(msg: str, level="INFO"):
    print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}", file=sys.stderr)

def ensure_geoip():
    """自动下载 mmdb 到 ./geoip/"""
    GEO_DIR.mkdir(exist_ok=True)
    for fname, url in MMDB_URLS.items():
        fpath = GEO_DIR / fname
        if fpath.exists(): continue
        log(f"下载 GeoIP 数据库: {fname} ...")
        try:
            with urlopen(url, timeout=30) as r, open(fpath, "wb") as f:
                shutil.copyfileobj(r, f)
            log(f"完成: {fpath}")
        except Exception as e:
            log(f"下载失败 {fname}: {e}", "WARN")

def load_readers():
    """加载 mmdb reader (线程安全, 只读)"""
    try:
        import maxminddb
        city = maxminddb.open_database(str(CITY_DB)) if CITY_DB.exists() else None
        asn  = maxminddb.open_database(str(ASN_DB))  if ASN_DB.exists()  else None
        return city, asn
    except Exception as e:
        log(f"加载 mmdb 失败: {e}", "WARN")
        return None, None

CITY_READER, ASN_READER = load_readers()

def lookup_geo(ip: str) -> Tuple[str, str, str]:
    """返回 (country, region, city, isp, asn)"""
    c = r = ci = isp = asn = ""
    try:
        if CITY_READER:
            rec = CITY_READER.get(ip)
            if rec:
                c = rec.get("country", {}).get("names", {}).get("zh-CN") or rec.get("country", {}).get("iso_code", "")
                r = (rec.get("subdivisions", [{}])[0].get("names", {}).get("zh-CN") or "")
                ci = rec.get("city", {}).get("names", {}).get("zh-CN") or ""
        if ASN_READER:
            rec = ASN_READER.get(ip)
            if rec:
                asn = str(rec.get("autonomous_system_number", ""))
                isp = rec.get("autonomous_system_organization", "")
    except Exception: pass
    return c, r, ci, isp, asn

# ========================= 核心探测 =========================
async def tcp_ping(ip: str, port: int) -> Optional[float]:
    try:
        start = time.perf_counter()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=TCP_TIMEOUT)
        writer.close()
        await writer.wait_closed()
        return (time.perf_counter() - start) * 1000
    except Exception: return None

async def tls_handshake(ip: str, port: int, sni: str = "") -> Tuple[Optional[float], dict]:
    """返回 (延迟ms, 证书信息dict)"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        start = time.perf_counter()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=TLS_TIMEOUT)
        ssl_sock = ctx.wrap_socket(writer.get_extra_info("socket"),
                                   server_hostname=sni or ip,
                                   do_handshake_on_connect=False)
        # 手动握手以计时
        await asyncio.get_event_loop().run_in_executor(None, ssl_sock.do_handshake)
        latency = (time.perf_counter() - start) * 1000
        cert = ssl_sock.getpeercert()
        writer.close()
        await writer.wait_closed()
        info = {}
        if cert:
            info["expire"] = cert.get("notAfter", "")
            issuer = cert.get("issuer", [])
            info["issuer"] = " ".join([f"{k}={v}" for tup in issuer for k,v in tup])
        return latency, info
    except Exception: return None, {}

async def http_probe(ip: str, port: int, sni: str = "", use_https: bool = True) -> Optional[float]:
    """发送 HEAD 请求测真连延迟"""
    scheme = "https" if use_https else "http"
    url = f"{scheme}://{ip}:{port}"
    headers = {"User-Agent": "IPSelector/1.0", "Connection": "close"}
    if sni: headers["Host"] = sni
    try:
        start = time.perf_counter()
        req = Request(url, method="HEAD", headers=headers)
        # 自定义 SSL 上下文跳过验证
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urlopen(req, timeout=HTTP_TIMEOUT, context=ctx) as resp:
            _ = resp.read(0)
        return (time.perf_counter() - start) * 1000
    except Exception: return None

async def download_speed(ip: str, port: int, sni: str = "") -> Optional[float]:
    """下载 1MB 测速, 返回 Mbps"""
    url = f"https://{ip}:{port}{DOWNLOAD_URL.split('cloudflare.com')[1]}"
    headers = {"User-Agent": "IPSelector/1.0", "Range": f"bytes=0-{DOWNLOAD_SIZE-1}"}
    if sni: headers["Host"] = sni
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    try:
        start = time.perf_counter()
        req = Request(url, headers=headers)
        with urlopen(req, timeout=DOWNLOAD_TIMEOUT, context=ctx) as resp:
            data = resp.read()
        elapsed = time.perf_counter() - start
        if elapsed > 0 and len(data) > 0:
            return (len(data) * 8 / elapsed) / 1_000_000  # Mbps
    except Exception: return None

# ========================= 单 IP 全流程 =========================
async def probe_one(ip: str, port: int, sni: str, sem: asyncio.Semaphore,
                    do_tls: bool, do_http: bool, do_dl: bool) -> ProbeResult:
    async with sem:
        res = ProbeResult(ip=ip, port=port, sni=sni)
        country, region, city, isp, asn = lookup_geo(ip)
        res.country, res.region, res.city, res.isp, res.asn = country, region, city, isp, asn

        # 1. TCP
        tcp = await tcp_ping(ip, port)
        if tcp is None or tcp > MAX_LATENCY_MS:
            res.error = "TCP超时/失败"; return res
        res.tcp_ms = int(tcp)

        # 2. TLS
        if do_tls:
            tls_lat, cert_info = await tls_handshake(ip, port, sni)
            if tls_lat and tls_lat <= MAX_LATENCY_MS:
                res.tls_ms = int(tls_lat)
                res.cert_expire = cert_info.get("expire", "")
                res.cert_issuer = cert_info.get("issuer", "")
            else:
                res.error = "TLS失败"; return res

        # 3. HTTP
        if do_http:
            http_lat = await http_probe(ip, port, sni, use_https=bool(do_tls))
            if http_lat and http_lat <= MAX_LATENCY_MS:
                res.http_ms = int(http_lat)
            else:
                res.error = "HTTP失败"; return res

        # 4. 下载测速 (可选, 耗时)
        if do_dl and res.http_ms:
            dl = await download_speed(ip, port, sni)
            if dl: res.dl_mbps = round(dl, 2)

        # 5. 评分 (越低越好)
        penalties = []
        if res.tcp_ms: penalties.append(res.tcp_ms * SCORE_WEIGHT["tcp"])
        if res.tls_ms: penalties.append(res.tls_ms * SCORE_WEIGHT["tls"])
        if res.http_ms: penalties.append(res.http_ms * SCORE_WEIGHT["http"])
        if res.dl_mbps: penalties.append((1000 / res.dl_mbps) * SCORE_WEIGHT["dl"])  # 速度越快惩罚越小
        res.score = sum(penalties) if penalties else 99999
