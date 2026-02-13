import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
import time
import random
import re
import threading
from queue import Queue
from datetime import datetime

class WebCrawler:
    def __init__(self, max_pages=500, timeout=5, user_agent_key='chrome'):
        self.user_agent_key = user_agent_key
        self.user_agents = {
            'chrome': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'firefox': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'safari': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'edge': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
            'iphone': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
            'android': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'bot': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
        }
        
        self.url_queue = Queue()
        self.visited = set()
        self.index = {}
        self.new_domains = set()
        
        self.timeout = timeout
        self.max_retries = 3
        self.crawling_active = False
        self.pages_crawled = 0
        self.domains_crawled = set()
        
        # Session con user agent seleccionado
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.user_agents.get(user_agent_key, self.user_agents['chrome']),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Semillas iniciales (igual que antes)
        self.seed_urls = [ ... ]  # Misma lista de 80+ URLs
        
        self.blocked_domains = [ ... ]  # Misma lista
        self.blocked_extensions = [ ... ]  # Misma lista
        self.blocked_patterns = [ ... ]  # Misma lista
    
    def crawl_page(self, url):
        """Rastrea una página individual con el user agent seleccionado"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    page_info = self.extract_info(url, soup)
                    
                    if page_info:
                        links = self.extract_links(soup, url)
                        
                        return {
                            'success': True,
                            'page_info': page_info,
                            'links': links,
                            'soup': soup
                        }
                
                break
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    return {'success': False, 'error': str(e)}
                time.sleep(1)
        
        return {'success': False, 'error': 'Failed after retries'}
    
    def start_infinite_crawl(self, indexador_callback=None):
        """INICIA EL RASTREO INFINITO con el user agent seleccionado"""
        self.crawling_active = True
        self.pages_crawled = 0
        start_time = time.time()
        
        print("=" * 80)
        print(f"🚀 CRAWLER INFINITO INICIADO - User Agent: {self.user_agent_key}")
        print("=" * 80)
        
        # Añadir semillas
        for seed in self.seed_urls:
            if self.is_valid_url(seed):
                self.url_queue.put(seed)
        
        while self.crawling_active:
            try:
                url = self.url_queue.get(timeout=5)
                
                if url in self.visited:
                    continue
                
                self.visited.add(url)
                result = self.crawl_page(url)
                
                if result['success'] and result['page_info']:
                    page_info = result['page_info']
                    self.index[url] = page_info
                    self.pages_crawled += 1
                    
                    domain = page_info['domain']
                    self.domains_crawled.add(domain)
                    
                    if indexador_callback and page_info:
                        indexador_callback({url: page_info})
                    
                    # Añadir nuevos enlaces
                    for link in result['links']:
                        if link not in self.visited:
                            self.url_queue.put(link)
                
                self.url_queue.task_done()
                time.sleep(random.uniform(0.3, 1.0))
                
            except Exception as e:
                continue
        
        print(f"✅ Crawler finalizado - Total páginas: {self.pages_crawled}")
    
    def stop_crawl(self):
        self.crawling_active = False
    
    def get_status(self):
        return {
            'running': self.crawling_active,
            'pages_crawled': self.pages_crawled,
            'domains_discovered': len(self.domains_crawled),
            'queue_size': self.url_queue.qsize(),
            'unique_urls': len(self.visited),
            'index_size': len(self.index),
            'user_agent': self.user_agent_key
        }

class CrawlerManager:
    def __init__(self):
        self.crawlers = []
        self.active_crawlers = 0
    
    def start_crawler(self, indexador_callback=None, user_agent_key='chrome'):
        crawler = WebCrawler(user_agent_key=user_agent_key)
        self.crawlers.append(crawler)
        self.active_crawlers += 1
        
        thread = threading.Thread(target=crawler.start_infinite_crawl, 
                                 args=(indexador_callback,))
        thread.daemon = True
        thread.start()
        
        return crawler
    
    def stop_all(self):
        for crawler in self.crawlers:
            crawler.stop_crawl()
        self.active_crawlers = 0
