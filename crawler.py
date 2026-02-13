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
import hashlib
import os
import json

class WebCrawler:
    def __init__(self, max_pages=500, timeout=10, user_agent_key='chrome', cache_dir='cache'):
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
        
        # CONFIGURACIÓN DE CACHÉ
        self.cache_dir = cache_dir
        self.cache_metadata_file = os.path.join(cache_dir, 'cache_metadata.json')
        self.cache_metadata = self.cargar_metadata_cache()
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Crear directorio de caché si no existe
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        
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
        
        # Semillas iniciales
        self.seed_urls = [
            'https://es.wikipedia.org/wiki/Portada',
            'https://en.wikipedia.org/wiki/Main_Page',
            'https://news.ycombinator.com',
            'https://github.com/explore',
            'https://stackoverflow.com',
            'https://www.python.org',
            'https://www.w3.org',
            'https://developer.mozilla.org',
            'https://www.nature.com',
            'https://arxiv.org',
            'https://www.nasa.gov',
            'https://www.bbc.com/news',
            'https://www.reuters.com',
            'https://www.metmuseum.org',
            'https://www.nationalgeographic.com',
            'https://www.khanacademy.org',
            'https://www.coursera.org',
            'https://ocw.mit.edu',
            'https://www.un.org',
            'https://www.who.int',
            'https://www.gutenberg.org',
            'https://archive.org',
            'https://www.harvard.edu',
            'https://www.stanford.edu',
            'https://www.ox.ac.uk',
            'https://www.mit.edu',
            'https://www.usa.gov',
            'https://www.data.gov',
            'https://www.nih.gov'
        ]
        
        # Dominios bloqueados
        self.blocked_domains = [
            'youtube.com', 'youtu.be', 'facebook.com', 'instagram.com', 
            'tiktok.com', 'twitch.tv', 'pinterest.com', 'flickr.com', 
            'imgur.com', 'amazon.com', 'ebay.com', 'aliexpress.com',
            'walmart.com', 'netflix.com', 'spotify.com', 'deviantart.com',
            'vimeo.com', 'dailymotion.com', 'tumblr.com', 'snapchat.com',
            'whatsapp.com', 'telegram.org', 'discord.com'
        ]
        
        # Extensiones de archivo a ignorar
        self.blocked_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp',
            '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
            '.exe', '.msi', '.bin', '.dmg', '.iso', '.img'
        ]
        
        # Patrones de URL a ignorar
        self.blocked_patterns = [
            r'login', r'signup', r'register', r'password', r'auth',
            r'cart', r'checkout', r'payment', r'order', r'invoice',
            r'logout', r'session', r'forgot', r'recover',
            r'captcha', r'bot', r'spider', r'crawler',
            r'\.git', r'\.svn', r'\.hg', r'\.bzr',
            r'wp-admin', r'wp-login', r'administrator',
            r'phpmyadmin', r'mysql', r'phpPgAdmin',
            r'calendar', r'events', r'print', r'pdf',
            r'#', r'mailto:', r'tel:', r'javascript:'
        ]
    
    def cargar_metadata_cache(self):
        """Carga los metadatos del caché desde el archivo JSON"""
        if os.path.exists(self.cache_metadata_file):
            try:
                with open(self.cache_metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {'urls': {}, 'stats': {'total_cached': 0, 'total_size': 0}}
        return {'urls': {}, 'stats': {'total_cached': 0, 'total_size': 0}}
    
    def guardar_metadata_cache(self):
        """Guarda los metadatos del caché en el archivo JSON"""
        try:
            # Calcular tamaño total del caché
            total_size = 0
            for url_data in self.cache_metadata['urls'].values():
                total_size += url_data.get('size', 0)
            
            self.cache_metadata['stats'] = {
                'total_cached': len(self.cache_metadata['urls']),
                'total_size': total_size,
                'cache_hits': getattr(self, 'cache_hits', 0),
                'cache_misses': getattr(self, 'cache_misses', 0)
            }
            
            with open(self.cache_metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error guardando metadatos de caché: {e}")
    
    def generar_cache_key(self, url):
        """Genera una clave única para la URL (hash)"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def obtener_del_cache(self, url):
        """Obtiene una página del caché si existe y no ha expirado"""
        cache_key = self.generar_cache_key(url)
        
        if cache_key in self.cache_metadata['urls']:
            metadata = self.cache_metadata['urls'][cache_key]
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.html")
            
            if os.path.exists(cache_file):
                # Verificar si el caché ha expirado (30 días por defecto)
                cached_time = datetime.fromisoformat(metadata['cached_date'])
                now = datetime.now()
                days_diff = (now - cached_time).days
                
                # Si tiene menos de 30 días, usar caché
                if days_diff < 30:
                    try:
                        with open(cache_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        self.cache_hits += 1
                        return {
                            'content': content,
                            'metadata': metadata,
                            'from_cache': True
                        }
                    except:
                        pass
                else:
                    # Caché expirado, eliminar
                    self.eliminar_del_cache(url)
        
        self.cache_misses += 1
        return None
    
    def guardar_en_cache(self, url, content, headers=None):
        """Guarda una página en el caché"""
        cache_key = self.generar_cache_key(url)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.html")
        
        try:
            # Guardar contenido HTML
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Calcular tamaño
            size = os.path.getsize(cache_file)
            
            # Guardar metadatos
            self.cache_metadata['urls'][cache_key] = {
                'url': url,
                'cached_date': datetime.now().isoformat(),
                'last_accessed': datetime.now().isoformat(),
                'headers': headers if headers else {},
                'size': size,
                'etag': headers.get('etag', '') if headers else '',
                'last_modified': headers.get('last-modified', '') if headers else ''
            }
            
            self.guardar_metadata_cache()
            return True
            
        except Exception as e:
            print(f"Error guardando en caché {url}: {e}")
            return False
    
    def eliminar_del_cache(self, url):
        """Elimina una URL específica del caché"""
        cache_key = self.generar_cache_key(url)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.html")
        
        if cache_key in self.cache_metadata['urls']:
            del self.cache_metadata['urls'][cache_key]
            
        if os.path.exists(cache_file):
            os.remove(cache_file)
        
        self.guardar_metadata_cache()
    
    def limpiar_cache_expirado(self, max_days=30):
        """Limpia del caché las URLs más antiguas que max_days"""
        now = datetime.now()
        urls_a_eliminar = []
        
        for cache_key, metadata in self.cache_metadata['urls'].items():
            cached_date = datetime.fromisoformat(metadata['cached_date'])
            days_diff = (now - cached_date).days
            
            if days_diff > max_days:
                urls_a_eliminar.append(cache_key)
        
        for cache_key in urls_a_eliminar:
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.html")
            if cache_key in self.cache_metadata['urls']:
                del self.cache_metadata['urls'][cache_key]
            if os.path.exists(cache_file):
                os.remove(cache_file)
        
        if urls_a_eliminar:
            self.guardar_metadata_cache()
            print(f"🧹 Limpiados {len(urls_a_eliminar)} elementos del caché (más de {max_days} días)")
    
    def obtener_estadisticas_cache(self):
        """Obtiene estadísticas del caché"""
        return {
            'total_cached': self.cache_metadata['stats'].get('total_cached', 0),
            'total_size_mb': round(self.cache_metadata['stats'].get('total_size', 0) / (1024 * 1024), 2),
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_ratio': round(self.cache_hits / (self.cache_hits + self.cache_misses) * 100, 2) if (self.cache_hits + self.cache_misses) > 0 else 0
        }
    
    def is_valid_url(self, url):
        """Verifica si la URL es válida para rastrear"""
        try:
            parsed = urlparse(url)
            
            if parsed.scheme not in ['http', 'https']:
                return False
                
            if len(url) > 800:
                return False
                
            if '#' in url:
                return False
                
            domain = parsed.netloc.lower()
            
            for blocked in self.blocked_domains:
                if blocked in domain:
                    return False
            
            path = parsed.path.lower()
            for ext in self.blocked_extensions:
                if path.endswith(ext):
                    return False
            
            for pattern in self.blocked_patterns:
                if re.search(pattern, path, re.IGNORECASE):
                    return False
            
            return True
        except:
            return False
    
    def extract_links(self, soup, base_url):
        """Extrae todos los enlaces válidos de una página"""
        links = set()
        domain = urlparse(base_url).netloc
        
        for link in soup.find_all('a', href=True):
            href = link['href'].strip()
            
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
                
            try:
                full_url = urljoin(base_url, href)
                
                if self.is_valid_url(full_url):
                    links.add(full_url)
                    
                    link_domain = urlparse(full_url).netloc
                    if link_domain and link_domain != domain:
                        if link_domain not in self.domains_crawled:
                            self.new_domains.add(full_url)
                            
            except:
                continue
                
        return links
    
    def extract_info(self, url, soup):
        """Extrae información relevante de la página"""
        try:
            title = soup.title.string if soup.title else "Sin título"
            title = ' '.join(title.split())[:150]
            
            meta_desc = (soup.find('meta', attrs={'name': 'description'}) or 
                        soup.find('meta', attrs={'property': 'og:description'}) or
                        soup.find('meta', attrs={'name': 'twitter:description'}))
            description = meta_desc['content'] if meta_desc else ""
            description = description[:300]
            
            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            meta_keywords = meta_keywords['content'] if meta_keywords else ""
            
            for script in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                script.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            text = ' '.join(text.split())[:2000]
            
            words = (title + " " + description + " " + meta_keywords + " " + text[:1000]).lower().split()
            stop_words = {'el','la','los','las','un','una','unos','unas','y','e','o','u',
                         'de','del','a','en','con','por','para','que','es','son','fue',
                         'era','como','mas','pero','si','no','the','a','an','and','or',
                         'of','to','in','on','at','this','that','with','from','by','for'}
            
            word_freq = {}
            for word in words[:500]:
                if len(word) > 3 and word not in stop_words and word.isalnum():
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            keywords = [k[0] for k in sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20]]
            
            return {
                'title': title,
                'url': url,
                'domain': urlparse(url).netloc,
                'description': description,
                'keywords': keywords,
                'text_snippet': text[:500] + '...' if len(text) > 500 else text,
                'crawled_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'from_cache': False
            }
        except Exception as e:
            return None
    
    def crawl_page(self, url, force_refresh=False):
        """Rastrea una página individual - AHORA CON CACHÉ"""
        
        # Si no es forzar actualización, intentar obtener del caché
        if not force_refresh:
            cached = self.obtener_del_cache(url)
            if cached:
                print(f"📦 CACHE HIT: {url[:80]}...")
                soup = BeautifulSoup(cached['content'], 'html.parser')
                page_info = self.extract_info(url, soup)
                if page_info:
                    page_info['from_cache'] = True
                    page_info['cached_date'] = cached['metadata']['cached_date']
                    links = self.extract_links(soup, url)
                    
                    return {
                        'success': True,
                        'page_info': page_info,
                        'links': links,
                        'soup': soup,
                        'from_cache': True
                    }
        
        for attempt in range(self.max_retries):
            try:
                print(f"🌐 FETCHING: {url[:80]}...")
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    page_info = self.extract_info(url, soup)
                    
                    if page_info:
                        links = self.extract_links(soup, url)
                        
                        # GUARDAR EN CACHÉ
                        self.guardar_en_cache(url, response.text, dict(response.headers))
                        
                        return {
                            'success': True,
                            'page_info': page_info,
                            'links': links,
                            'soup': soup,
                            'from_cache': False
                        }
                
                break
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    return {'success': False, 'error': str(e)}
                time.sleep(1)
        
        return {'success': False, 'error': 'Failed after retries'}
    
    def start_infinite_crawl(self, indexador_callback=None):
        """INICIA EL RASTREO INFINITO con caché"""
        self.crawling_active = True
        self.pages_crawled = 0
        start_time = time.time()
        
        # Limpiar caché expirado al iniciar
        self.limpiar_cache_expirado()
        
        print("=" * 80)
        print(f"🚀 CRAWLER INFINITO INICIADO - User Agent: {self.user_agent_key}")
        print(f"📦 CACHÉ ACTIVADO - Directorio: {self.cache_dir}")
        print("=" * 80)
        
        # Añadir semillas
        for seed in self.seed_urls:
            if self.is_valid_url(seed):
                self.url_queue.put(seed)
        
        last_stats_time = time.time()
        
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
                
                # Mostrar estadísticas cada 30 segundos
                if time.time() - last_stats_time > 30:
                    cache_stats = self.obtener_estadisticas_cache()
                    elapsed = time.time() - start_time
                    print(f"\n📊 ESTADÍSTICAS CACHÉ:")
                    print(f"  📦 En caché: {cache_stats['total_cached']} páginas")
                    print(f"  💾 Tamaño: {cache_stats['total_size_mb']} MB")
                    print(f"  🎯 Hit ratio: {cache_stats['hit_ratio']}%")
                    print(f"  ⚡ Páginas/minuto: {self.pages_crawled / (elapsed/60):.1f}")
                    last_stats_time = time.time()
                
                time.sleep(random.uniform(0.3, 1.0))
                
            except Exception as e:
                continue
        
        print(f"✅ Crawler finalizado - Total páginas: {self.pages_crawled}")
    
    def stop_crawl(self):
        self.crawling_active = False
    
    def get_status(self):
        cache_stats = self.obtener_estadisticas_cache()
        return {
            'running': self.crawling_active,
            'pages_crawled': self.pages_crawled,
            'domains_discovered': len(self.domains_crawled),
            'queue_size': self.url_queue.qsize(),
            'unique_urls': len(self.visited),
            'index_size': len(self.index),
            'user_agent': self.user_agent_key,
            'cache': cache_stats
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
