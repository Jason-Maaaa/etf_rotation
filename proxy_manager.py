# -*- coding: utf-8 -*-
"""
轻量级动态代理池管理器
支持从多个免费代理源爬取、异步验证并维护有效代理池
"""

import asyncio
import aiohttp
import requests
from typing import List, Dict, Optional, Tuple
from collections import deque
import threading
import time
import random
import logging
import re
from urllib.parse import urlparse

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ProxyManager:
    """代理池管理器"""
    
    def __init__(self, 
                 min_proxies: int = 5,
                 max_proxies: int = 50,
                 verify_timeout: int = 5,
                 verify_url: str = "http://finance.sina.com.cn",
                 refresh_interval: int = 300):
        """
        初始化代理管理器
        
        Args:
            min_proxies: 最小代理数量，低于此值会触发刷新
            max_proxies: 最大代理数量
            verify_timeout: 验证超时时间（秒）
            verify_url: 验证代理时使用的测试URL
            refresh_interval: 自动刷新间隔（秒）
        """
        self.min_proxies = min_proxies
        self.max_proxies = max_proxies
        self.verify_timeout = verify_timeout
        self.verify_url = verify_url
        self.refresh_interval = refresh_interval
        
        # 线程安全的代理池（使用deque + 锁）
        self._proxy_pool: deque = deque()
        self._lock = threading.RLock()
        
        # 无效代理集合（避免重复验证）
        self._invalid_proxies: set = set()
        self._invalid_lock = threading.RLock()
        
        # 代理源配置
        self.proxy_sources = [
            self._fetch_kuaidaili,
            self._fetch_89ip,
            self._fetch_proxylistplus,
        ]
        
        # 后台刷新线程
        self._refresh_thread: Optional[threading.Thread] = None
        self._running = False
        
    def _fetch_kuaidaili(self) -> List[Dict[str, str]]:
        """从快代理爬取代理IP"""
        proxies = []
        try:
            # 使用快代理的API接口（如果可用）
            # 注意：免费代理源可能不稳定，这里提供备用方案
            url = "https://www.kuaidaili.com/free/inha/1/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            }
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                # 简单文本解析（如果页面格式是 IP:PORT）
                ip_port_pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{2,5})'
                matches = re.findall(ip_port_pattern, resp.text)
                for ip, port in matches:
                    proxies.append({
                        'http': f'http://{ip}:{port}',
                        'https': f'http://{ip}:{port}'
                    })
                if proxies:
                    logger.info(f"快代理源: 获取到 {len(proxies)} 个代理")
        except Exception as e:
            logger.debug(f"快代理源获取失败: {e}")
        return proxies
    
    def _fetch_89ip(self) -> List[Dict[str, str]]:
        """从89ip爬取代理IP"""
        proxies = []
        try:
            url = "https://api.89ip.cn/tqdl.html?api=1&num=100&port=&address=&isp="
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                # 解析文本格式的代理列表
                lines = resp.text.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if ':' in line:
                        parts = line.split(':')
                        if len(parts) == 2:
                            ip, port = parts[0].strip(), parts[1].strip()
                            if ip and port:
                                proxies.append({
                                    'http': f'http://{ip}:{port}',
                                    'https': f'http://{ip}:{port}'
                                })
                logger.info(f"89ip源: 获取到 {len(proxies)} 个代理")
        except Exception as e:
            logger.warning(f"89ip源获取失败: {e}")
        return proxies
    
    def _fetch_proxylistplus(self) -> List[Dict[str, str]]:
        """从ProxyListPlus爬取代理IP"""
        proxies = []
        try:
            # 尝试多个可能的API端点
            urls = [
                "https://www.proxylistplus.com/api/proxy?format=json",
                "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt"
            ]
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            for url in urls:
                try:
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        # 尝试解析JSON
                        try:
                            data = resp.json()
                            if isinstance(data, list):
                                for item in data:
                                    if isinstance(item, dict):
                                        ip = item.get('ip') or item.get('IP')
                                        port = item.get('port') or item.get('Port')
                                        if ip and port:
                                            proxies.append({
                                                'http': f'http://{ip}:{port}',
                                                'https': f'http://{ip}:{port}'
                                            })
                        except:
                            # 如果不是JSON，尝试文本格式解析
                            ip_port_pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{2,5})'
                            matches = re.findall(ip_port_pattern, resp.text)
                            for ip, port in matches:
                                proxies.append({
                                    'http': f'http://{ip}:{port}',
                                    'https': f'http://{ip}:{port}'
                                })
                        if proxies:
                            logger.info(f"ProxyListPlus源: 获取到 {len(proxies)} 个代理")
                            break
                except:
                    continue
        except Exception as e:
            logger.debug(f"ProxyListPlus源获取失败: {e}")
        return proxies
    
    async def _verify_proxy(self, session: aiohttp.ClientSession, proxy: Dict[str, str]) -> Optional[Tuple[Dict[str, str], float]]:
        """
        异步验证单个代理（适配器模式：只要通了就行）
        
        Returns:
            (proxy_dict, latency) 如果有效，否则 None
        """
        proxy_url = proxy.get('http')
        if not proxy_url:
            return None
        
        # 优化点 1：使用 HTTP 而非 HTTPS 提高兼容性
        # 优化点 2：放宽超时到 8 秒
        test_url = "http://www.baidu.com"
        
        try:
            start_time = time.time()
            async with session.get(
                test_url,
                proxy=proxy_url,
                timeout=aiohttp.ClientTimeout(total=8),  # 增加超时
                allow_redirects=True
            ) as resp:
                if resp.status == 200:
                    latency = time.time() - start_time
                    # 只要通了就行，免费代理不求快，只求能动
                    return (proxy, latency)
        except Exception as e:
            # logger.debug(f"验证失败: {proxy_url} - {e}")
            pass
        return None
    
    async def _verify_proxies_batch(self, proxies: List[Dict[str, str]]) -> List[Tuple[Dict[str, str], float]]:
        """批量异步验证代理"""
        valid_proxies = []
        
        async with aiohttp.ClientSession() as session:
            tasks = [self._verify_proxy(session, proxy) for proxy in proxies]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, tuple) and result[0] is not None:
                    valid_proxies.append(result)
        
        # 按延迟排序
        valid_proxies.sort(key=lambda x: x[1])
        return valid_proxies
    
    def _fetch_all_proxies(self) -> List[Dict[str, str]]:
        """从所有源获取代理"""
        all_proxies = []
        for source_func in self.proxy_sources:
            try:
                proxies = source_func()
                all_proxies.extend(proxies)
            except Exception as e:
                logger.warning(f"代理源 {source_func.__name__} 失败: {e}")
        
        # 去重
        seen = set()
        unique_proxies = []
        for proxy in all_proxies:
            proxy_key = proxy.get('http', '')
            if proxy_key and proxy_key not in seen:
                seen.add(proxy_key)
                unique_proxies.append(proxy)
        
        logger.info(f"从所有源共获取 {len(unique_proxies)} 个唯一代理")
        return unique_proxies
    
    def refresh_proxy_pool(self):
        """刷新代理池（同步方法，可在后台线程调用）"""
        logger.info("开始刷新代理池...")
        
        # 获取所有代理
        all_proxies = self._fetch_all_proxies()
        
        if not all_proxies:
            logger.warning("未获取到任何代理，尝试使用备用方案")
            return
        
        # 过滤掉已知无效的代理
        with self._invalid_lock:
            filtered_proxies = [
                p for p in all_proxies 
                if p.get('http', '') not in self._invalid_proxies
            ]
        
        if not filtered_proxies:
            logger.warning("所有代理都在无效列表中，清空无效列表后重试")
            with self._invalid_lock:
                self._invalid_proxies.clear()
            filtered_proxies = all_proxies
        
        # 异步验证
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            valid_proxies = loop.run_until_complete(
                self._verify_proxies_batch(filtered_proxies)
            )
        finally:
            loop.close()
        
        # 更新代理池
        with self._lock:
            # 保留部分旧代理（避免全部替换）
            old_proxies = list(self._proxy_pool)
            self._proxy_pool.clear()
            
            # 添加新验证的代理
            for proxy, latency in valid_proxies[:self.max_proxies]:
                self._proxy_pool.append(proxy)
            
            # 如果新代理不够，保留部分旧代理
            if len(self._proxy_pool) < self.min_proxies and old_proxies:
                keep_count = min(len(old_proxies), self.min_proxies - len(self._proxy_pool))
                self._proxy_pool.extend(old_proxies[:keep_count])
            
            logger.info(f"代理池已更新: 当前有效代理 {len(self._proxy_pool)} 个")
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """
        获取一个随机有效代理（适配器模式：支持直连保底）
        
        Returns:
            代理字典，格式: {'http': 'http://ip:port', 'https': 'http://ip:port'}
            如果没有可用代理，返回 None（允许直连模式）
        """
        with self._lock:
            # 如果池子空了，触发异步刷新，但本次请求返回 None (即直连)
            if len(self._proxy_pool) == 0:
                # 避免频繁触发刷新，可以加个简单的频率限制
                logger.warning("代理池为空，尝试直连模式运行...")
                # 这里可以异步启动刷新，不阻塞当前请求
                return None
            
            # 随机选择
            proxy = random.choice(list(self._proxy_pool))
            return proxy
    
    def mark_proxy_invalid(self, proxy: Dict[str, str]):
        """标记代理为无效"""
        proxy_key = proxy.get('http', '')
        if proxy_key:
            with self._invalid_lock:
                self._invalid_proxies.add(proxy_key)
            
            # 从池中移除
            with self._lock:
                try:
                    self._proxy_pool.remove(proxy)
                    logger.info(f"已移除无效代理: {proxy_key}")
                except ValueError:
                    pass
    
    def _background_refresh(self):
        """后台自动刷新线程"""
        while self._running:
            time.sleep(self.refresh_interval)
            if self._running:
                try:
                    with self._lock:
                        current_count = len(self._proxy_pool)
                    
                    if current_count < self.min_proxies:
                        logger.info(f"代理数量不足 ({current_count} < {self.min_proxies})，触发刷新")
                        self.refresh_proxy_pool()
                except Exception as e:
                    logger.error(f"后台刷新失败: {e}")
    
    def start_background_refresh(self):
        """启动后台自动刷新"""
        if self._refresh_thread is None or not self._refresh_thread.is_alive():
            self._running = True
            self._refresh_thread = threading.Thread(
                target=self._background_refresh,
                daemon=True,
                name="ProxyRefreshThread"
            )
            self._refresh_thread.start()
            logger.info("后台代理刷新线程已启动")
    
    def stop_background_refresh(self):
        """停止后台自动刷新"""
        self._running = False
        if self._refresh_thread and self._refresh_thread.is_alive():
            self._refresh_thread.join(timeout=2)
        logger.info("后台代理刷新线程已停止")
    
    def get_pool_size(self) -> int:
        """获取当前代理池大小"""
        with self._lock:
            return len(self._proxy_pool)


# 全局单例
_global_proxy_manager: Optional[ProxyManager] = None
_manager_lock = threading.Lock()


def get_proxy_manager() -> ProxyManager:
    """获取全局代理管理器单例"""
    global _global_proxy_manager
    if _global_proxy_manager is None:
        with _manager_lock:
            if _global_proxy_manager is None:
                # 调大 verify_timeout 到 10
                _global_proxy_manager = ProxyManager(verify_timeout=10)
                # 初始化时立即刷新一次
                _global_proxy_manager.refresh_proxy_pool()
                # 启动后台刷新
                _global_proxy_manager.start_background_refresh()
    return _global_proxy_manager
