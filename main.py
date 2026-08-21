import json
import re
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request

# 1. 机房代码转中文地区
CF_COLO = {
    "HKG": "中国·香港", "TPE": "中国·台湾", "KHH": "中国·高雄",
    "NRT": "日本·东京", "KIX": "日本·大阪", "ICN": "韩国·首尔",
    "SIN": "新加坡", "BKK": "泰国·曼谷", "KUL": "马来西亚·吉隆坡",
    "SJC": "美国·圣何塞", "LAX": "美国·洛杉矶", "SEA": "美国·西雅图",
    "FRA": "德国·法兰克福", "LHR": "英国·伦敦", "CDG": "法国·巴黎"
}

# 忽略 SSL 证书校验（防止移动端证书报错引发闪退）
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def parse_region(colo):
    """自动识别地区"""
    if not colo:
        return "其它地区"
    code = str(colo).strip().upper()
    return CF_COLO.get(code, f"其它地区({code})")


def parse_ips(raw_text):
    """自定义 IP 清洗：自动补齐 :443 + 去重"""
    lines = re.split(r'[\r\n,\s]+', str(raw_text).strip())
    seen = set()
    ips = []
    for line in lines:
        item = line.strip()
        if not item:
            continue
        if ":" not in item:
            item = f"{item}:443"
        if item not in seen:
            seen.add(item)
            ips.append(item)
    return ips


def test_speed(ip_port):
    """测真实速度 (下载 256KB 测试包)"""
    try:
        proxy_handler = urllib.request.ProxyHandler({'http': f'http://{ip_port}', 'https': f'http://{ip_port}'})
        opener = urllib.request.build_opener(proxy_handler)
        
        speed_url = "https://speed.cloudflare.com/__down?bytes=262144"
        start_t = time.time()
        
        req = urllib.request.Request(speed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with opener.open(req, timeout=2.0) as resp:
            content = resp.read()
            duration = time.time() - start_t
            if duration > 0 and len(content) > 0:
                return round((len(content) / 1024) / duration, 1)
    except Exception:
        pass
    return 0.0


def check_one_ip(ip_port):
    """测真实探针与延迟（全量异常拦截，决不崩溃）"""
    try:
        url = f"https://check.proxyip.cmliussss.net/check?proxyip={ip_port}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=3.0, context=SSL_CTX) as response:
            if response.status != 200:
                return None
            
            latency = round((time.time() - start_time) * 1000, 1)
            data = json.loads(response.read().decode('utf-8'))
            
            # 网页探针校验失败直接剔除
            if not data.get("success"):
                return None
            
            real_latency = data.get("responseTime", latency)
            region = parse_region(data.get("colo", ""))
            speed = test_speed(ip_port)
            
            return {
                "ip": ip_port,
                "latency": real_latency,
                "region": region,
                "speed": speed
            }
    except Exception:
        return None


def run_scan(raw_ips_text, max_workers=3):
    """
    主运行入口
    max_workers=3：低并发，彻底解决移动端闪退
    """
    targets = parse_ips(raw_ips_text)
    if not targets:
        print("❌ 未识别到有效 IP")
        return []

    print(f"🔍 开始检测 {len(targets)} 个 IP...")
    results = []

    # 使用 Python 原生标准线程池，线程数设为 3 极其稳定
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(check_one_ip, ip) for ip in targets]
        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    results.append(res)
                    print(f"✅ {res['ip']:<21} | {res['region']:<10} | {res['latency']:>5}ms | {res['speed']:>6} KB/s")
            except Exception:
                pass

    # 按延迟升序排序
    results.sort(key=lambda x: x["latency"])

    # 打印便于一键复制的纯 IP 结果
    print("\n" + "="*45)
    print("📋 【检测完成 - 纯 IP 列表（直接长按复制）】")
    print("="*45)
    for item in results:
        print(item["ip"])

    return results


# ==================== 运行测试 ====================
if __name__ == "__main__":
    # 在此放入你的自定义 IP 文本（支持带端口/不带端口）
    custom_text = """
    103.21.244.13
    173.245.60.252:443
    188.114.106.185:2053
    """

    run_scan(custom_text)
