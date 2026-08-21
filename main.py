import asyncio
import re
import time
from typing import Dict, List, Optional
import aiohttp

# Cloudflare Colo 代码转中文地区映射表（解决“其它地区”问题）
CF_COLO_MAP = {
    "HKG": "中国·香港", "TPE": "中国·台湾", "KHH": "中国·高雄",
    "NRT": "日本·东京", "KIX": "日本·大阪", "ICN": "韩国·首尔",
    "SIN": "新加坡", "BKK": "泰国·曼谷", "KUL": "马来西亚·吉隆坡",
    "SJC": "美国·圣何塞", "LAX": "美国·洛杉矶", "SEA": "美国·西雅图",
    "ORD": "美国·芝加哥", "JFK": "美国·纽约", "IAD": "美国·华盛顿",
    "FRA": "德国·法兰克福", "LHR": "英国·伦敦", "CDG": "法国·巴黎",
    "AMS": "荷兰·阿姆斯特丹", "SYD": "澳大利亚·悉尼", "MEL": "澳大利亚·墨尔本"
}

class ProxyScanner:
    def __init__(self, check_api: str = "https://check.proxyip.cmliussss.net/check", max_concurrency: int = 20):
        self.check_api = check_api
        self.max_concurrency = max_concurrency  # 并发上限控制在 20，防止手机爆内存闪退
        self.speed_url = "https://speed.cloudflare.com/__down?bytes=524288"  # 512KB 测试包

    def parse_region(self, colo: str) -> str:
        """解析 Colo 机房代码为中文地区"""
        code = colo.strip().upper()
        return CF_COLO_MAP.get(code, f"其它地区 ({code})" if code else "其它地区")

    def parse_custom_ips(self, raw_text: str) -> List[str]:
        """提取自定义文本中的 IP，自动补充 :443 端口并去重"""
        lines = re.split(r'[\r\n,\s]+', raw_text.strip())
        seen = set()
        result = []

        for line in lines:
            item = line.strip()
            if not item:
                continue
            if ":" not in item:
                item = f"{item}:443"
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    async def check_single_ip(self, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, ip_port: str) -> Optional[Dict]:
        """单 IP 深度探针验真与测速"""
        async with semaphore:
            res = {
                "ip_port": ip_port,
                "valid": False,
                "latency": 0.0,
                "region": "其它地区",
                "speed": 0.0
            }

            # 1. 调用网页端同款 API 进行代理探针校验
            check_url = f"{self.check_api}?proxyip={ip_port}"
            start_t = time.perf_counter()

            try:
                async with session.get(check_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    rtt = round((time.perf_counter() - start_t) * 1000, 1)
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success") is True:
                            res["valid"] = True
                            res["latency"] = data.get("responseTime", rtt)
                            colo = data.get("colo", "")
                            res["region"] = self.parse_region(colo)
                        else:
                            return None
                    else:
                        return None
            except Exception:
                return None

            # 2. 仅对网页端确认有效的节点进行 512KB 真实 HTTP 代理下载测速
            if res["valid"]:
                try:
                    proxy_url = f"http://{ip_port}"
                    s_time = time.perf_counter()
                    async with session.get(
                        self.speed_url,
                        proxy=proxy_url,
                        ssl=False,
                        timeout=aiohttp.ClientTimeout(total=3)
                    ) as speed_resp:
                        if speed_resp.status == 200:
                            downloaded = 0
                            async for chunk in speed_resp.content.iter_chunked(1024 * 8):
                                downloaded += len(chunk)
                            duration = time.perf_counter() - s_time
                            if duration > 0:
                                res["speed"] = round((downloaded / 1024) / duration, 1)
                except Exception:
                    res["speed"] = 0.0

            return res

    async def run_scan(self, raw_custom_text: str, is_custom_mode: bool = True, default_list: List[str] = None) -> List[Dict]:
        """检测主入口"""
        if default_list is None:
            default_list = []

        targets = self.parse_custom_ips(raw_custom_text) if is_custom_mode else default_list
        if not targets:
            return []

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async with aiohttp.ClientSession() as session:
            tasks = [self.check_single_ip(session, semaphore, ip) for ip in targets]
            results = await asyncio.gather(*tasks)

        # 过滤无效节点，并按延迟升序、速度降序排序
        valid_nodes = [r for r in results if r and r["valid"]]
        valid_nodes.sort(key=lambda x: (x["latency"], -x["speed"]))
        return valid_nodes


# ==================== main.py 运行示例 ====================
if __name__ == "__main__":
    # 模拟输入框接收到的自定义文本
    user_input = """
    103.21.244.13
    173.245.60.252:443
    188.114.106.185:2053
    """

    scanner = ProxyScanner(max_concurrency=20)
    print("开始深度检测...")

    nodes = asyncio.run(scanner.run_scan(user_input, is_custom_mode=True))

    print(f"\n检测完成，有效节点数: {len(nodes)}")
    for item in nodes:
        print(f"IP: {item['ip_port']:<20} | 地区: {item['region']:<10} | 延迟: {item['latency']:>5} ms | 速度: {item['speed']:>6} KB/s")
