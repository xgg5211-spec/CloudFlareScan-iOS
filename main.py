import asyncio
import re
import time
from typing import Dict, List
import aiohttp

# 1. Cloudflare Colo (机房代码) -> 真实地区对照映射表（解决“显示其它地区”问题）
CF_COLO_MAP = {
    "HKG": "中国·香港", "TPE": "中国·台湾", "KHH": "中国·高雄",
    "NRT": "日本·东京", "KIX": "日本·大阪", "ICN": "韩国·首尔",
    "SIN": "新加坡", "BKK": "泰国·曼谷", "KUL": "马来西亚·吉隆坡",
    "SJC": "美国·圣何塞", "LAX": "美国·洛杉矶", "SEA": "美国·西雅图",
    "ORD": "美国·芝加哥", "JFK": "美国·纽约", "IAD": "美国·华盛顿",
    "FRA": "德国·法兰克福", "LHR": "英国·伦敦", "CDG": "法国·巴黎",
    "AMS": "荷兰·阿姆斯特丹", "SYD": "澳大利亚·悉尼", "MEL": "澳大利亚·墨尔本"
}

class CyberScannerEngine:
    def __init__(self, check_api: str = "https://check.proxyip.cmliussss.net/check", concurrency: int = 32):
        self.check_api = check_api  # 对齐网页端 Worker 内置 /check 探针接口
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.speed_test_url = "https://speed.cloudflare.com/__down?bytes=524288"  # 512KB 真实流量测速包

    def parse_custom_ips(self, raw_input: str) -> List[str]:
        """
        【自定义 IP 解析优化】
        - 自动提取文本中的 IPv4/IPv6 地址与端口
        - 若用户未输入端口，自动补全默认 443 端口
        - 自动去重、去除空行
        """
        lines = re.split(r'[\r\n,\s]+', raw_input.strip())
        valid_targets = []
        seen = set()

        for item in lines:
            item = item.strip()
            if not item:
                continue
            
            # 端口自动补全逻辑
            if ":" not in item:
                item = f"{item}:443"
            
            if item not in seen:
                seen.add(item)
                valid_targets.append(item)
                
        return valid_targets

    async def check_single_proxy(self, session: aiohttp.ClientSession, ip_port: str) -> Dict:
        """
        单节点深度检测（完全对齐 check.proxyip.cmliussss.net 网页端逻辑）
        """
        async with self.semaphore:
            result = {
                "ip_port": ip_port,
                "valid": False,
                "latency_ms": 0,
                "region": "未知地区",
                "speed_kbps": 0.0,
                "error": None
            }

            try:
                # 步骤 A: 调用网页端同款 API 进行 ProxyIP 协议探针验真
                check_url = f"{self.check_api}?proxyip={ip_port}"
                start_t = time.perf_counter()
                
                async with session.get(check_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    rtt = round((time.perf_counter() - start_t) * 1000, 1)
                    if resp.status == 200:
                        data = await resp.json()
                        # 校验网页 API 返回的 success 标记
                        if data.get("success") is True:
                            result["valid"] = True
                            result["latency_ms"] = data.get("responseTime", rtt)
                            
                            # 提取 Colo 节点代号并映射为中文地理位置
                            colo = data.get("colo", "").upper()
                            result["region"] = CF_COLO_MAP.get(colo, f"其他地区 ({colo})" if colo else "其他地区")
                        else:
                            result["error"] = "ProxyIP 验真失败 (握手拒绝/无法透传)"
                    else:
                        result["error"] = f"Check API 状态码 HTTP {resp.status}"

            except asyncio.TimeoutError:
                result["error"] = "检测超时"
            except Exception as e:
                result["error"] = str(e)

            # 步骤 B: 仅对真实有效的节点进行【真实下载吞吐测速】
            if result["valid"]:
                try:
                    proxy_url = f"http://{ip_port}"
                    s_time = time.perf_counter()
                    
                    async with session.get(
                        self.speed_test_url, 
                        proxy=proxy_url, 
                        ssl=False, 
                        timeout=aiohttp.ClientTimeout(total=3)
                    ) as speed_resp:
                        downloaded_bytes = 0
                        async for chunk in speed_resp.content.iter_chunked(1024 * 8):
                            downloaded_bytes += len(chunk)
                        
                        duration = time.perf_counter() - s_time
                        if duration > 0 and downloaded_bytes > 0:
                            result["speed_kbps"] = round((downloaded_bytes / 1024) / duration, 1)
                except Exception:
                    result["speed_kbps"] = 0.0  # 测速异常不影响节点有效性

            return result

    async def run_scan(self, raw_custom_input: str, is_custom_mode: bool = True) -> Dict:
        """
        主控入口
        :param raw_custom_input: 用户在“自定义输入框”粘贴的字符串
        :param is_custom_mode: True 代表开启【自定义 IP 独立检测开关】，完全切断默认网段
        """
        if is_custom_mode:
            targets = self.parse_custom_ips(raw_custom_input)
            source_desc = f"自定义上传列表 ({len(targets)} 个)"
        else:
            # 默认官方网段库逻辑
            targets = ["103.21.244.13:443", "173.245.60.252:443"] 
            source_desc = "官方 IPv4 网段"

        if not targets:
            return {"status": "error", "message": "未识别到有效的待测 IP 目标！"}

        async with aiohttp.ClientSession() as session:
            tasks = [self.check_single_proxy(session, ip) for ip in targets]
            raw_results = await asyncio.gather(*tasks)

        valid_nodes = [r for r in raw_results if r["valid"]]
        failed_nodes = [r for r in raw_results if not r["valid"]]

        # 按“真实延迟升序”与“速度降序”综合排序
        valid_nodes.sort(key=lambda x: (x["latency_ms"], -x["speed_kbps"]))

        return {
            "source": source_desc,
            "total": len(targets),
            "valid_count": len(valid_nodes),
            "failed_count": len(failed_nodes),
            "valid_nodes": valid_nodes
        }

# ==========================================
# 测试运行
# ==========================================
if __name__ == "__main__":
    scanner = CyberScannerEngine()

    # 模拟用户在 App 自定义框输入的 IP 文本
    user_custom_input = """
    103.21.244.13:443
    173.245.60.252:443
    188.114.106.185:2053
    104.17.157.170
    """

    print(">>> 开启【自定义 IP 深度检测开关】，开始检测...")
    res = asyncio.run(scanner.run_scan(raw_custom_input=user_custom_input, is_custom_mode=True))

    print(f"\n[检测概览] 来源: {res['source']} | 总数: {res['total']} | 有效: {res['valid_count']} | 失败: {res['failed_count']}")
    print("-" * 65)
    print(f"{'IP:Port':<22} | {'识别地区':<12} | {'真实延迟':<8} | {'真实速度'}")
    print("-" * 65)
    for node in res["valid_nodes"]:
        print(f"{node['ip_port']:<22} | {node['region']:<12} | {node['latency_ms']:>5} ms | {node['speed_kbps']:>7} KB/s")
