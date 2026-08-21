import asyncio
import gc
import re
import time
from typing import Dict, List, Optional
import aiohttp

# Cloudflare Colo 机房代码映射表
CF_COLO_MAP = {
    "HKG": "中国·香港", "TPE": "中国·台湾", "KHH": "中国·高雄",
    "NRT": "日本·东京", "KIX": "日本·大阪", "ICN": "韩国·首尔",
    "SIN": "新加坡", "BKK": "泰国·曼谷", "KUL": "马来西亚·吉隆坡",
    "SJC": "美国·圣何塞", "LAX": "美国·洛杉矶", "SEA": "美国·西雅图",
    "ORD": "美国·芝加哥", "JFK": "美国·纽约", "IAD": "美国·华盛顿",
    "FRA": "德国·法兰克福", "LHR": "英国·伦敦", "CDG": "法国·巴黎",
    "AMS": "荷兰·阿姆斯特丹", "SYD": "澳大利亚·悉尼", "MEL": "澳大利亚·墨尔本"
}

class IOSProxyScanner:
    def __init__(self, check_api: str = "https://check.proxyip.cmliussss.net/check", max_concurrency: int = 10):
        self.check_api = check_api
        # iOS Socket句柄限制极严格，并发数降至 10~12，绝对不闪退
        self.max_concurrency = max_concurrency  
        self.speed_url = "https://speed.cloudflare.com/__down?bytes=524288"

    def parse_region(self, colo: str) -> str:
        code = colo.strip().upper()
        return CF_COLO_MAP.get(code, f"其它地区 ({code})" if code else "其它地区")

    def parse_custom_ips(self, raw_text: str) -> List[str]:
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

    async def _check_single_ip(self, session: aiohttp.ClientSession, ip_port: str) -> Optional[Dict]:
        """单节点检测，增加全局全量异常拦截，防底层崩溃"""
        res = {
            "ip_port": ip_port,
            "valid": False,
            "latency": 0.0,
            "region": "其它地区",
            "speed": 0.0
        }

        # 1. 探针验真
        try:
            check_url = f"{self.check_api}?proxyip={ip_port}"
            start_t = time.perf_counter()
            async with session.get(check_url, timeout=aiohttp.ClientTimeout(total=3.5)) as resp:
                rtt = round((time.perf_counter() - start_t) * 1000, 1)
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success") is True:
                        res["valid"] = True
                        res["latency"] = data.get("responseTime", rtt)
                        res["region"] = self.parse_region(data.get("colo", ""))
                    else:
                        return None
                else:
                    return None
        except Exception:
            return None

        # 2. 真实代理下载测速
        if res["valid"]:
            try:
                proxy_url = f"http://{ip_port}"
                s_time = time.perf_counter()
                async with session.get(
                    self.speed_url,
                    proxy=proxy_url,
                    ssl=False,
                    timeout=aiohttp.ClientTimeout(total=2.5)
                ) as speed_resp:
                    if speed_resp.status == 200:
                        downloaded = 0
                        async for chunk in speed_resp.content.iter_chunked(4096):
                            downloaded += len(chunk)
                        duration = time.perf_counter() - s_time
                        if duration > 0:
                            res["speed"] = round((downloaded / 1024) / duration, 1)
            except Exception:
                res["speed"] = 0.0

        return res

    async def _worker(self, queue: asyncio.Queue, session: aiohttp.ClientSession, results: list):
        """Worker 动态队列消费者，按需取任务，零额外内存开销"""
        while not queue.empty():
            try:
                ip_port = await queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            res = await self._check_single_ip(session, ip_port)
            if res and res["valid"]:
                results.append(res)

            queue.task_done()
            # 必须让出 CPU 时间片，防止 iOS Watchdog 认定 App 卡死而强制杀进程
            await asyncio.sleep(0.01)

    async def run_scan(self, raw_custom_text: str, is_custom_mode: bool = True, default_list: List[str] = None) -> List[Dict]:
        targets = self.parse_custom_ips(raw_custom_text) if is_custom_mode else (default_list or [])
        if not targets:
            return []

        # 使用队列存储任务，避免万级数据一次性生成对象挤爆系统内存
        queue = asyncio.Queue()
        for ip in targets:
            queue.put_nowait(ip)

        results = []

        # 配置专门针对移动端 iOS 优化过的 TCP 连接池
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrency,
            force_close=True,            # 每次请求完强制释放 Socket 句柄，防 iOS 句柄超限
            enable_cleanup_closed=True,  # 自动清理已关闭的 socket
            ssl=False
        )

        async with aiohttp.ClientSession(connector=connector) as session:
            # 仅创建固定数量（例如 10 个）的常驻 Worker 协程
            workers = [
                asyncio.create_task(self._worker(queue, session, results))
                for _ in range(min(self.max_concurrency, len(targets)))
            ]
            
            await asyncio.gather(*workers, return_exceptions=True)

        # 手动触发 GC，防止 iOS 内存占用递增
        gc.collect()

        # 按延迟升序排序
        results.sort(key=lambda x: (x["latency"], -x["speed"]))
        return results


# ==================== main.py 入口示例 ====================
if __name__ == "__main__":
    user_input = """
    103.21.244.13
    173.245.60.252:443
    188.114.106.185:2053
    """

    # max_concurrency 建议保持在 10，移动端非常稳定且不闪退
    scanner = IOSProxyScanner(max_concurrency=10)
    
    # 运行检测
    valid_nodes = asyncio.run(scanner.run_scan(user_input, is_custom_mode=True))

    for node in valid_nodes:
        print(f"IP: {node['ip_port']:<20} | 地区: {node['region']:<10} | 延迟: {node['latency']:>5} ms | 速度: {node['speed']:>6} KB/s")
