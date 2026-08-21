import json
import re
import ssl
import time
import urllib.request

# 地区代码映射
CF_COLO = {
    "HKG": "中国·香港", "TPE": "中国·台湾", "KHH": "中国·高雄",
    "NRT": "日本·东京", "KIX": "日本·大阪", "ICN": "韩国·首尔",
    "SIN": "新加坡", "BKK": "泰国·曼谷", "KUL": "马来西亚·吉隆坡",
    "SJC": "美国·圣何塞", "LAX": "美国·洛杉矶", "SEA": "美国·西雅图",
    "FRA": "德国·法兰克福", "LHR": "英国·伦敦", "CDG": "法国·巴黎"
}

# 忽略 SSL 验证（防止移动端证书报错引发闪退）
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def parse_region(colo):
    if not colo: return "其它地区"
    code = str(colo).strip().upper()
    return CF_COLO.get(code, f"其它地区({code})")

def parse_ips(text):
    """自动补充 :443 端口并去重"""
    lines = re.split(r'[\r\n,\s]+', str(text).strip())
    seen = set()
    ips = []
    for line in lines:
        item = line.strip()
        if not item: continue
        if ":" not in item: item = f"{item}:443"
        if item not in seen:
            seen.add(item)
            ips.append(item)
    return ips

def test_node(ip_port):
    """单线程绝对安全检测：验真 + 延迟 + 测速"""
    try:
        # 1. 探针验真与延迟
        check_url = f"https://check.proxyip.cmliussss.net/check?proxyip={ip_port}"
        req = urllib.request.Request(check_url, headers={'User-Agent': 'Mozilla/5.0'})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=2.5, context=ctx) as resp:
            if resp.status != 200: return None
            latency = round((time.time() - t0) * 1000, 1)
            data = json.loads(resp.read().decode('utf-8'))
            if not data.get("success"): return None
            region = parse_region(data.get("colo", ""))
            real_latency = data.get("responseTime", latency)

        # 2. 下载测速（小数据包防卡死）
        speed = 0.0
        try:
            proxy_h = urllib.request.ProxyHandler({'http': f'http://{ip_port}', 'https': f'http://{ip_port}'})
            opener = urllib.request.build_opener(proxy_h)
            s_req = urllib.request.Request("https://speed.cloudflare.com/__down?bytes=102400", headers={'User-Agent': 'Mozilla/5.0'})
            st = time.time()
            with opener.open(s_req, timeout=2.0) as s_resp:
                buf = s_resp.read()
                dur = time.time() - st
                if dur > 0 and len(buf) > 0:
                    speed = round((len(buf) / 1024) / dur, 1)
        except Exception:
            pass

        return {"ip": ip_port, "region": region, "latency": real_latency, "speed": speed}
    except Exception:
        return None

def main():
    try:
        # 在此处粘贴自定义 IP 文本
        raw_text = """
        103.21.244.13
        173.245.60.252:443
        188.114.106.185:2053
        """

        targets = parse_ips(raw_text)
        if not targets:
            print("未检测到有效 IP")
            return

        print(f"正在检测 {len(targets)} 个 IP...\n")
        results = []

        # 放弃一切多线程，采用纯单线程逐个检测，彻底消除 iOS 线程崩溃
        for ip in targets:
            res = test_node(ip)
            if res:
                results.append(res)
                print(f"✅ {res['ip']:<21} | {res['region']:<10} | 延迟:{res['latency']:>5}ms | 速度:{res['speed']:>6}KB/s")

        results.sort(key=lambda x: x["latency"])

        print("\n" + "=" * 40)
        print("【纯 IP 列表（直接长按全选复制）】")
        print("=" * 40)
        for item in results:
            print(item["ip"])

    except BaseException as e:
        print(f"捕获异常: {e}")

if __name__ == "__main__":
    main()
    
    # 核心解决点：iOS 上脚本运行完如果不挂起，App 会直接关闭退出（让你误以为是闪退）
    print("\n检测完成！已保持运行，请直接复制上方 IP。")
    while True:
        time.sleep(3600)
