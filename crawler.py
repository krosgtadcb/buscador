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
    def __init__(self):
        # Colas y conjuntos para el rastreo infinito
        self.url_queue = Queue()
        self.visited = set()
        self.index = {}
        self.new_domains = set()
        
        # Configuración
        self.timeout = 5
        self.max_retries = 3
        self.crawling_active = False
        self.pages_crawled = 0
        self.domains_crawled = set()
        
        # Session para mantener conexiones
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # SEMILLAS INICIALES - Puntos de partida diversos
        self.seed_urls = [
            # Enciclopedias y conocimiento general
            'https://es.wikipedia.org/wiki/Portada',
            'https://en.wikipedia.org/wiki/Main_Page',
            'https://www.britannica.com',
            'https://www.wikidata.org',
            
            # Tecnología y programación
            'https://news.ycombinator.com',
            'https://github.com/explore',
            'https://stackoverflow.com',
            'https://dev.to',
            'https://medium.com',
            'https://www.python.org',
            'https://www.w3.org',
            'https://developer.mozilla.org',
            'https://www.tutorialspoint.com',
            'https://www.geeksforgeeks.org',
            
            # Ciencia e investigación
            'https://www.nature.com',
            'https://www.science.org',
            'https://arxiv.org',
            'https://www.researchgate.net',
            'https://scholar.google.com',
            'https://www.nasa.gov',
            
            # Noticias y actualidad
            'https://www.bbc.com/news',
            'https://www.reuters.com',
            'https://apnews.com',
            'https://www.euronews.com',
            'https://www.aljazeera.com',
            
            # Cultura y arte
            'https://www.metmuseum.org',
            'https://www.britishmuseum.org',
            'https://www.smithsonianmag.com',
            'https://www.nationalgeographic.com',
            'https://www.imdb.com',
            
            # Educación
            'https://www.khanacademy.org',
            'https://www.coursera.org',
            'https://www.edx.org',
            'https://ocw.mit.edu',
            'https://www.open.edu',
            
            # Organizaciones internacionales
            'https://www.un.org',
            'https://www.who.int',
            'https://www.worldbank.org',
            'https://www.imf.org',
            'https://www.oecd.org',
            
            # Bibliotecas digitales
            'https://www.gutenberg.org',
            'https://archive.org',
            'https://www.europeana.eu',
            'https://www.digitalcommonwealth.org',
            
            # Blogs y publicaciones
            'https://www.wired.com',
            'https://www.technologyreview.com',
            'https://arstechnica.com',
            'https://www.theverge.com',
            'https://www.engadget.com',
            'https://www.zdnet.com',
            
            # Universidades
            'https://www.harvard.edu',
            'https://www.stanford.edu',
            'https://www.ox.ac.uk',
            'https://www.cam.ac.uk',
            'https://www.mit.edu',
            'https://www.berkeley.edu',
            
            # Organismos gubernamentales (.gov)
            'https://www.usa.gov',
            'https://www.data.gov',
            'https://science.gov',
            'https://www.nih.gov',
            'https://www.nasa.gov',
            
            # Revistas científicas
            'https://www.pnas.org',
            'https://www.cell.com',
            'https://www.thelancet.com',
            'https://www.scientificamerican.com',
            'https://www.newscientist.com',
            
            # Proyectos open source
            'https://sourceforge.net',
            'https://gitlab.com/explore',
            'https://bitbucket.org',
            'https://www.apache.org',
            'https://www.gnu.org',
            'https://www.kernel.org',
            
            # Documentación técnica
            'https://readthedocs.org',
            'https://docs.python.org',
            'https://docs.docker.com',
            'https://kubernetes.io/docs',
            'https://docs.aws.amazon.com',
            
            # Foros y comunidades
            'https://www.reddit.com',
            'https://discourse.org',
            'https://community.sap.com',
            'https://community.oracle.com',
            
            # Múseos y galerías
            'https://www.louvre.fr',
            'https://www.moma.org',
            'https://www.tate.org.uk',
            'https://www.getty.edu',
            'https://www.rijksmuseum.nl',
            
            # Historia y patrimonio
            'https://www.unesco.org',
            'https://whc.unesco.org',
            'https://www.nationalarchives.gov.uk',
            'https://www.archives.gov',
            
            # Economía y finanzas
            'https://www.economist.com',
            'https://www.bloomberg.com',
            'https://www.ft.com',
            'https://www.wsj.com',
            'https://www.forbes.com',
            
            # Salud y medicina
            'https://www.mayoclinic.org',
            'https://www.webmd.com',
            'https://medlineplus.gov',
            'https://www.cdc.gov',
            'https://www.fda.gov'
        ]
        
        # Dominios bloqueados (redes sociales, streaming, etc)
        self.blocked_domains = [
            'youtube.com', 'youtu.be', 'facebook.com', 'instagram.com', 
            'tiktok.com', 'twitch.tv', 'pinterest.com', 'flickr.com', 
            'imgur.com', 'amazon.com', 'ebay.com', 'aliexpress.com',
            'walmart.com', 'netflix.com', 'spotify.com', 'deviantart.com',
            'vimeo.com', 'dailymotion.com', 'tumblr.com', 'snapchat.com',
            'whatsapp.com', 'telegram.org', 'discord.com', 'reddit.com/r/gifs',
            'reddit.com/r/funny', 'reddit.com/r/pics', '9gag.com'
        ]
        
        # Extensiones de archivo a ignorar
        self.blocked_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp',
            '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
            '.exe', '.msi', '.bin', '.dmg', '.iso', '.img',
            '.css', '.js', '.json', '.xml', '.rss', '.atom',
            '.ico', '.woff', '.woff2', '.ttf', '.eot'
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
    
    def is_valid_url(self, url):
        """Verifica si la URL es válida para rastrear"""
        try:
            parsed = urlparse(url)
            
            # Solo HTTP/HTTPS
            if parsed.scheme not in ['http', 'https']:
                return False
                
            # Longitud máxima
            if len(url) > 800:
                return False
                
            # Sin fragmentos
            if '#' in url:
                return False
                
            domain = parsed.netloc.lower()
            
            # Evitar dominios bloqueados
            for blocked in self.blocked_domains:
                if blocked in domain:
                    return False
            
            # Evitar extensiones bloqueadas
            path = parsed.path.lower()
            for ext in self.blocked_extensions:
                if path.endswith(ext):
                    return False
            
            # Evitar patrones bloqueados
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
                    
                    # Descubrir nuevos dominios
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
            # Título
            title = soup.title.string if soup.title else "Sin título"
            title = ' '.join(title.split())[:150]
            
            # Descripción
            meta_desc = (soup.find('meta', attrs={'name': 'description'}) or 
                        soup.find('meta', attrs={'property': 'og:description'}) or
                        soup.find('meta', attrs={'name': 'twitter:description'}))
            description = meta_desc['content'] if meta_desc else ""
            description = description[:300]
            
            # Keywords
            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            meta_keywords = meta_keywords['content'] if meta_keywords else ""
            
            # Texto principal
            for script in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                script.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            text = ' '.join(text.split())[:2000]
            
            # Extraer keywords del texto
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
                'content_length': len(response.text) if 'response' in locals() else 0
            }
        except Exception as e:
            return None
    
    def crawl_page(self, url):
        """Rastrea una página individual"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extraer información
                    page_info = self.extract_info(url, soup)
                    
                    if page_info:
                        # Extraer enlaces
                        links = self.extract_links(soup, url)
                        
                        return {
                            'success': True,
                            'page_info': page_info,
                            'links': links,
                            'soup': soup
                        }
                
                break
                
            except requests.exceptions.Timeout:
                if attempt == self.max_retries - 1:
                    return {'success': False, 'error': 'Timeout'}
                time.sleep(1)
            except requests.exceptions.ConnectionError:
                if attempt == self.max_retries - 1:
                    return {'success': False, 'error': 'Connection error'}
                time.sleep(2)
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        return {'success': False, 'error': 'Failed after retries'}
    
    def start_infinite_crawl(self, indexador_callback=None):
        """
        INICIA EL RASTREO INFINITO - NUNCA SE DETIENE
        Va de web en web automáticamente, descubriendo nuevas páginas constantemente
        """
        self.crawling_active = True
        self.pages_crawled = 0
        start_time = time.time()
        
        print("=" * 80)
        print("🚀 CRAWLER INFINITO INICIADO")
        print("=" * 80)
        print(f"📚 Semillas iniciales: {len(self.seed_urls)}")
        print(f"🌐 Modo: Sin parar | Auto-descubrimiento activado")
        print("=" * 80)
        
        # Añadir todas las semillas a la cola
        for seed in self.seed_urls:
            if self.is_valid_url(seed):
                self.url_queue.put(seed)
        
        # BUCLE INFINITO - NUNCA TERMINA
        while self.crawling_active:
            try:
                # Obtener URL de la cola
                url = self.url_queue.get(timeout=5)
                
                # Saltar si ya fue visitada
                if url in self.visited:
                    continue
                
                # Marcar como visitada
                self.visited.add(url)
                
                # Rastrear página
                result = self.crawl_page(url)
                
                if result['success']:
                    # Guardar página
                    page_info = result['page_info']
                    self.index[url] = page_info
                    self.pages_crawled += 1
                    
                    # Registrar dominio
                    domain = page_info['domain']
                    self.domains_crawled.add(domain)
                    
                    # Enviar a indexador si existe callback
                    if indexador_callback and page_info:
                        indexador_callback({url: page_info})
                    
                    # AÑADIR NUEVOS ENLACES A LA COLA
                    # Esto es lo que hace que el crawler sea infinito
                    links_added = 0
                    for link in result['links']:
                        if link not in self.visited:
                            self.url_queue.put(link)
                            links_added += 1
                    
                    # AÑADIR NUEVOS DOMINIOS DESCUBIERTOS
                    # Esto expande el crawler a nuevos sitios web
                    domains_added = 0
                    new_domains_to_remove = set()
                    for new_domain_url in self.new_domains:
                        if new_domain_url not in self.visited:
                            self.url_queue.put(new_domain_url)
                            new_domains_to_remove.add(new_domain_url)
                            domains_added += 1
                    
                    self.new_domains -= new_domains_to_remove
                    
                    # Mostrar progreso
                    if self.pages_crawled % 10 == 0:
                        queue_size = self.url_queue.qsize()
                        elapsed = time.time() - start_time
                        pages_per_sec = self.pages_crawled / elapsed if elapsed > 0 else 0
                        
                        print(f"\n{'='*60}")
                        print(f"📊 ESTADO DEL CRAWLER INFINITO")
                        print(f"{'='*60}")
                        print(f"📄 Páginas indexadas: {self.pages_crawled}")
                        print(f"🌍 Dominios descubiertos: {len(self.domains_crawled)}")
                        print(f"⏳ URLs en cola: {queue_size}")
                        print(f"⚡ Velocidad: {pages_per_sec:.2f} páginas/segundo")
                        print(f"🔗 Nuevos enlaces encontrados: {links_added}")
                        print(f"✨ Nuevos dominios añadidos: {domains_added}")
                        print(f"{'='*60}")
                    
                    # Pequeña pausa para no saturar servidores
                    time.sleep(random.uniform(0.3, 1.0))
                
                self.url_queue.task_done()
                
            except KeyboardInterrupt:
                print("\n⏹️ Crawler detenido por el usuario")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                continue
        
        print(f"\n✅ Crawler finalizado - Total páginas: {self.pages_crawled}")
    
    def stop_crawl(self):
        """Detiene el rastreo infinito"""
        self.crawling_active = False
        print("⏹️ Deteniendo crawler...")
    
    def get_status(self):
        """Obtiene el estado actual del crawler"""
        return {
            'running': self.crawling_active,
            'pages_crawled': self.pages_crawled,
            'domains_discovered': len(self.domains_crawled),
            'queue_size': self.url_queue.qsize() if hasattr(self.url_queue, 'qsize') else 0,
            'unique_urls': len(self.visited),
            'index_size': len(self.index)
        }

# CrawlerManager para manejar múltiples instancias
class CrawlerManager:
    def __init__(self):
        self.crawlers = []
        self.active_crawlers = 0
    
    def start_crawler(self, indexador_callback=None):
        """Inicia una nueva instancia del crawler infinito"""
        crawler = WebCrawler()
        self.crawlers.append(crawler)
        self.active_crawlers += 1
        
        thread = threading.Thread(target=crawler.start_infinite_crawl, 
                                 args=(indexador_callback,))
        thread.daemon = True
        thread.start()
        
        return crawler
    
    def stop_all(self):
        """Detiene todos los crawlers activos"""
        for crawler in self.crawlers:
            crawler.stop_crawl()
        self.active_crawlers = 0