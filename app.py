from flask import Flask, render_template, request, jsonify, redirect, url_for
from crawler import WebCrawler, CrawlerManager
from indexador import Indexador
import threading
import time
import requests
from datetime import datetime
import urllib.parse
import re

app = Flask(__name__)
indexador = Indexador()
crawler_manager = CrawlerManager()
active_crawler = None

crawler_status = {
    'running': False,
    'pages_crawled': 0,
    'domains_discovered': 0,
    'queue_size': 0,
    'current_url': '',
    'start_time': None,
    'crawler_type': 'inactivo'
}

# Configuración de User Agents
USER_AGENTS = {
    'chrome': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'firefox': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'safari': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'edge': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
    'iphone': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
    'android': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    'bot': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
}

@app.context_processor
def utility_processor():
    """Añade funciones útiles a todas las plantillas"""
    return dict(now=datetime.now())

@app.route('/')
def index():
    stats = indexador.obtener_estadisticas()
    return render_template('index.html', stats=stats, user_agents=USER_AGENTS)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    user_agent = request.args.get('ua', 'chrome')
    
    if not query:
        return redirect(url_for('index'))
    
    # Buscar en índice local
    resultados, total = indexador.buscar(query, page)
    total_paginas = (total + 9) // 10 if total > 0 else 0
    
    return render_template('resultados.html', 
                         query=query,
                         resultados=resultados,
                         total=total,
                         page=page,
                         total_paginas=total_paginas,
                         user_agent=user_agent)

@app.route('/abrir_url', methods=['POST'])
def abrir_url():
    """Abre una URL directamente en el iframe y la añade al crawler"""
    data = request.json
    url = data.get('url', '').strip()
    user_agent_key = data.get('user_agent', 'chrome')
    indexar = data.get('indexar', True)
    
    if not url:
        return jsonify({'error': 'URL no válida'}), 400
    
    if not url.startswith('http'):
        url = 'https://' + url
    
    try:
        # Verificar que la URL es accesible
        user_agent = USER_AGENTS.get(user_agent_key, USER_AGENTS['chrome'])
        headers = {'User-Agent': user_agent}
        
        response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
        
        if response.status_code < 400:
            # Si se solicita indexar y no está ya indexada
            if indexar and not indexador.url_esta_indexada(url):
                def indexar_url_task():
                    crawler = WebCrawler(max_pages=1, user_agent_key=user_agent_key)
                    resultado = crawler.crawl_page(url, force_refresh=True)
                    if resultado['success'] and resultado['page_info']:
                        indexador.agregar_paginas({url: resultado['page_info']})
                
                thread = threading.Thread(target=indexar_url_task)
                thread.daemon = True
                thread.start()
                mensaje_indexado = " (añadiendo al índice...)"
            else:
                mensaje_indexado = " (ya estaba en el índice)" if indexador.url_esta_indexada(url) else ""
            
            return jsonify({
                'success': True,
                'url': url,
                'status_code': response.status_code,
                'message': f'URL válida, abriendo...{mensaje_indexado}',
                'indexada': indexar
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Error HTTP {response.status_code}',
                'url': url
            }), 400
            
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'No se pudo conectar a la URL'}), 400
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Timeout al conectar'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/buscar_en_internet', methods=['POST'])
def buscar_en_internet():
    """Busca una consulta en internet y añade resultados al índice - CORREGIDO"""
    data = request.json
    query = data.get('query', '')
    user_agent_key = data.get('user_agent', 'chrome')
    
    if not query:
        return jsonify({'error': 'Consulta vacía'}), 400
    
    user_agent = USER_AGENTS.get(user_agent_key, USER_AGENTS['chrome'])
    
    try:
        # Usar múltiples motores de búsqueda para mayor probabilidad de éxito
        resultados_totales = []
        
        # 1. Intentar con Google
        try:
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=es"
            headers = {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
                'Cache-Control': 'no-cache'
            }
            
            response = requests.get(search_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Google actual - múltiples selectores para adaptarse a cambios
                selectores = [
                    'div.g',
                    'div.yuRUbf',
                    'div.tF2Cxc',
                    'div[jsname="UWckNb"]'
                ]
                
                for selector in selectores:
                    resultados = soup.select(selector)
                    if resultados:
                        break
                
                for result in resultados[:10]:
                    # Título
                    title_elem = (result.select_one('h3') or 
                                 result.select_one('a > h3') or
                                 result.select_one('div[role="heading"]'))
                    
                    # Enlace
                    link_elem = result.select_one('a[href]')
                    
                    # Descripción
                    desc_elem = (result.select_one('div.VwiC3b') or 
                                result.select_one('div.IsZvec') or
                                result.select_one('div[style*="color:#4d5156"]'))
                    
                    if title_elem and link_elem:
                        title = title_elem.get_text().strip()
                        url = link_elem.get('href', '')
                        
                        # Extraer URL real de Google
                        if url.startswith('/url?q='):
                            url = url.split('/url?q=')[1].split('&')[0]
                        elif url.startswith('http'):
                            pass
                        else:
                            continue
                        
                        description = desc_elem.get_text().strip() if desc_elem else ''
                        
                        if url.startswith('http'):
                            resultados_totales.append({
                                'title': title,
                                'url': url,
                                'description': description[:200],
                                'source': 'Google'
                            })
        except Exception as e:
            print(f"Error con Google: {e}")
        
        # 2. Si Google falla, intentar con DuckDuckGo
        if len(resultados_totales) < 3:
            try:
                ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
                response = requests.get(ddg_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    for result in soup.select('.result')[:10]:
                        title_elem = result.select_one('.result__a')
                        link_elem = result.select_one('.result__url')
                        desc_elem = result.select_one('.result__snippet')
                        
                        if title_elem and link_elem:
                            title = title_elem.get_text().strip()
                            url = link_elem.get('href', '')
                            description = desc_elem.get_text().strip() if desc_elem else ''
                            
                            if url.startswith('http'):
                                resultados_totales.append({
                                    'title': title,
                                    'url': url,
                                    'description': description[:200],
                                    'source': 'DuckDuckGo'
                                })
            except Exception as e:
                print(f"Error con DuckDuckGo: {e}")
        
        # 3. Si aún no hay resultados, intentar con Bing
        if len(resultados_totales) < 3:
            try:
                bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
                response = requests.get(bing_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    for result in soup.select('.b_algo')[:10]:
                        title_elem = result.select_one('h2 a')
                        desc_elem = result.select_one('.b_caption p')
                        
                        if title_elem:
                            title = title_elem.get_text().strip()
                            url = title_elem.get('href', '')
                            description = desc_elem.get_text().strip() if desc_elem else ''
                            
                            if url.startswith('http'):
                                resultados_totales.append({
                                    'title': title,
                                    'url': url,
                                    'description': description[:200],
                                    'source': 'Bing'
                                })
            except Exception as e:
                print(f"Error con Bing: {e}")
        
        # Eliminar duplicados por URL
        urls_vistas = set()
        resultados_unicos = []
        for r in resultados_totales:
            if r['url'] not in urls_vistas:
                urls_vistas.add(r['url'])
                resultados_unicos.append(r)
        
        if not resultados_unicos:
            return jsonify({
                'success': False,
                'error': 'No se encontraron resultados en ningún buscador',
                'resultados': [],
                'indexadas': 0
            })
        
        # Crawlear las primeras 5 URLs encontradas (solo las que no están ya indexadas)
        crawler = WebCrawler(max_pages=5, user_agent_key=user_agent_key)
        paginas_indexadas = {}
        indexadas_count = 0
        
        for resultado in resultados_unicos[:5]:
            url = resultado['url']
            if not indexador.url_esta_indexada(url):
                try:
                    print(f"Indexando: {url}")
                    page_result = crawler.crawl_page(url, force_refresh=True)
                    if page_result['success'] and page_result['page_info']:
                        paginas_indexadas[url] = page_result['page_info']
                        indexadas_count += 1
                        print(f"✓ Indexada: {url}")
                except Exception as e:
                    print(f"Error indexando {url}: {e}")
            else:
                print(f"Ya indexada: {url}")
        
        # Añadir al índice
        if paginas_indexadas:
            indexador.agregar_paginas(paginas_indexadas)
        
        return jsonify({
            'success': True,
            'resultados': resultados_unicos[:10],
            'indexadas': indexadas_count
        })
        
    except Exception as e:
        print(f"Error general en búsqueda: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/proxy')
def proxy():
    """Sirve como proxy para cargar páginas web dentro del iframe - CON CSS Y JS"""
    url = request.args.get('url', '')
    user_agent_key = request.args.get('ua', 'chrome')
    
    if not url:
        return "URL no especificada", 400
    
    try:
        user_agent = USER_AGENTS.get(user_agent_key, USER_AGENTS['chrome'])
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        response = requests.get(url, headers=headers, timeout=10, stream=True)
        
        content_type = response.headers.get('Content-Type', '').lower()
        
        if 'text/html' not in content_type:
            excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
            headers = [(name, value) for (name, value) in response.raw.headers.items()
                      if name.lower() not in excluded_headers]
            response_content = response.content
            return (response_content, response.status_code, headers)
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        base_url = '/'.join(url.split('/')[:3])
        
        def make_absolute(src, base):
            if src.startswith('http'):
                return src
            elif src.startswith('//'):
                return 'https:' + src
            elif src.startswith('/'):
                return base + src
            else:
                if url.endswith('/'):
                    return url + src
                else:
                    return '/'.join(url.split('/')[:-1]) + '/' + src
        
        for link in soup.find_all('link', rel='stylesheet'):
            if link.get('href'):
                original_href = link['href']
                absolute_href = make_absolute(original_href, base_url)
                link['href'] = f"/proxy_recurso?url={urllib.parse.quote(absolute_href)}&ua={user_agent_key}"
        
        for script in soup.find_all('script', src=True):
            if script.get('src'):
                original_src = script['src']
                absolute_src = make_absolute(original_src, base_url)
                script['src'] = f"/proxy_recurso?url={urllib.parse.quote(absolute_src)}&ua={user_agent_key}"
        
        for img in soup.find_all('img', src=True):
            if img.get('src'):
                original_src = img['src']
                absolute_src = make_absolute(original_src, base_url)
                img['src'] = f"/proxy_recurso?url={urllib.parse.quote(absolute_src)}&ua={user_agent_key}"
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('http') or href.startswith('//') or href.startswith('/'):
                absolute_href = make_absolute(href, base_url)
                link['href'] = f"/proxy?url={urllib.parse.quote(absolute_href)}&ua={user_agent_key}"
                link['target'] = "_parent"
        
        meta_viewport = soup.new_tag('meta')
        meta_viewport['name'] = 'viewport'
        meta_viewport['content'] = 'width=device-width, initial-scale=1.0'
        if soup.head:
            soup.head.insert(0, meta_viewport)
        
        nav_bar = soup.new_tag('div')
        nav_bar['style'] = '''
            position: fixed; 
            top: 0; 
            left: 0; 
            right: 0; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; 
            padding: 12px; 
            z-index: 999999; 
            display: flex; 
            gap: 10px; 
            align-items: center; 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        '''
        
        back_button = soup.new_tag('button')
        back_button['onclick'] = 'parent.cerrarIframe()'
        back_button['style'] = '''
            background: white; 
            color: #667eea; 
            border: none; 
            padding: 8px 20px; 
            border-radius: 20px; 
            cursor: pointer; 
            font-weight: 600;
            font-size: 14px;
            transition: all 0.3s;
        '''
        back_button['onmouseover'] = "this.style.transform='scale(1.05)'"
        back_button['onmouseout'] = "this.style.transform='scale(1)'"
        back_button.string = '← Volver'
        nav_bar.append(back_button)
        
        url_span = soup.new_tag('span')
        url_span['style'] = '''
            flex: 1; 
            margin: 0 10px; 
            font-size: 13px; 
            overflow: hidden; 
            text-overflow: ellipsis; 
            white-space: nowrap;
            background: rgba(255,255,255,0.2);
            padding: 6px 12px;
            border-radius: 20px;
        '''
        url_span.string = url
        nav_bar.append(url_span)
        
        ua_select = soup.new_tag('select')
        ua_select['onchange'] = f"parent.cambiarUA(this.value, '{url}')"
        ua_select['style'] = '''
            background: white; 
            color: #667eea; 
            border: none; 
            padding: 6px 12px; 
            border-radius: 20px; 
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
        '''
        
        ua_options = [
            ('chrome', 'Chrome'),
            ('firefox', 'Firefox'),
            ('safari', 'Safari'),
            ('iphone', 'iPhone'),
            ('android', 'Android'),
            ('bot', 'Googlebot')
        ]
        
        for value, text in ua_options:
            option = soup.new_tag('option', value=value)
            if value == user_agent_key:
                option['selected'] = 'selected'
            option.string = text
            ua_select.append(option)
        
        nav_bar.append(ua_select)
        
        indexar_button = soup.new_tag('button')
        indexar_button['onclick'] = f"parent.indexarURL('{url}')"
        indexar_button['style'] = '''
            background: #34a853; 
            color: white; 
            border: none; 
            padding: 8px 20px; 
            border-radius: 20px; 
            cursor: pointer; 
            font-weight: 600;
            font-size: 14px;
            margin-left: 5px;
            transition: all 0.3s;
        '''
        indexar_button['onmouseover'] = "this.style.background='#2d8e47'"
        indexar_button['onmouseout'] = "this.style.background='#34a853'"
        indexar_button.string = '📥 Indexar'
        nav_bar.append(indexar_button)
        
        if soup.body:
            soup.body.insert(0, nav_bar)
            if soup.body.get('style'):
                soup.body['style'] += '; padding-top: 70px !important; margin: 0 !important;'
            else:
                soup.body['style'] = 'padding-top: 70px !important; margin: 0 !important;'
        
        script_tag = soup.new_tag('script')
        script_tag.string = '''
            document.addEventListener('click', function(e) {
                const link = e.target.closest('a');
                if (link && link.target === '_blank') {
                    e.preventDefault();
                    if (link.href) {
                        window.parent.location.href = '/proxy?url=' + encodeURIComponent(link.href) + '&ua=' + document.querySelector('select').value;
                    }
                }
            });
            
            window.addEventListener('load', function() {
                const iframes = document.querySelectorAll('iframe');
                iframes.forEach(iframe => {
                    iframe.style.maxWidth = '100%';
                });
            });
        '''
        if soup.body:
            soup.body.append(script_tag)
        
        return str(soup)
        
    except Exception as e:
        return f"""
        <html>
        <head>
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    margin: 0; 
                    padding: 0;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .error-container {{ 
                    max-width: 600px; 
                    margin: 20px; 
                    background: white; 
                    border-radius: 16px; 
                    padding: 40px; 
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3); 
                }}
                h1 {{ 
                    color: #d93025; 
                    font-size: 24px;
                    margin-bottom: 20px;
                }}
                p {{ 
                    color: #5f6368;
                    line-height: 1.6;
                    margin-bottom: 10px;
                }}
                .url {{ 
                    background: #f8f9fa;
                    padding: 12px;
                    border-radius: 8px;
                    font-family: monospace;
                    word-break: break-all;
                    margin: 20px 0;
                }}
                button {{ 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white; 
                    border: none; 
                    padding: 12px 30px; 
                    border-radius: 25px; 
                    cursor: pointer; 
                    font-size: 16px;
                    font-weight: 600;
                    transition: all 0.3s;
                }}
                button:hover {{
                    transform: scale(1.05);
                    box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
                }}
            </style>
        </head>
        <body>
            <div class="error-container">
                <h1>❌ Error al cargar la página</h1>
                <p><strong>URL:</strong></p>
                <div class="url">{url}</div>
                <p><strong>Error:</strong> {str(e)}</p>
                <button onclick="parent.cerrarIframe()">Volver al buscador</button>
            </div>
        </body>
        </html>
        """, 500

@app.route('/proxy_recurso')
def proxy_recurso():
    """Proxy para recursos estáticos (CSS, JS, imágenes, etc.)"""
    url = request.args.get('url', '')
    user_agent_key = request.args.get('ua', 'chrome')
    
    if not url:
        return "URL no especificada", 400
    
    try:
        user_agent = USER_AGENTS.get(user_agent_key, USER_AGENTS['chrome'])
        headers = {'User-Agent': user_agent}
        
        response = requests.get(url, headers=headers, timeout=10, stream=True)
        
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in response.raw.headers.items()
                  if name.lower() not in excluded_headers]
        
        response_content = response.content
        return (response_content, response.status_code, headers)
        
    except Exception as e:
        return f"Error cargando recurso: {str(e)}", 500

@app.route('/admin')
def admin():
    stats = indexador.obtener_estadisticas()
    paginas_recientes = indexador.obtener_paginas_recientes(20)
    domains = indexador.obtener_domains()
    
    global active_crawler, crawler_status
    if active_crawler:
        status = active_crawler.get_status()
        crawler_status['running'] = status['running']
        crawler_status['pages_crawled'] = status['pages_crawled']
        crawler_status['domains_discovered'] = status['domains_discovered']
        crawler_status['queue_size'] = status['queue_size']
        crawler_status['crawler_type'] = 'infinito'
    
    return render_template('admin.html', 
                         stats=stats, 
                         paginas_recientes=paginas_recientes,
                         domains=domains,
                         crawler_status=crawler_status,
                         user_agents=USER_AGENTS)

@app.route('/crawl', methods=['POST'])
def crawl():
    global active_crawler, crawler_status
    
    action = request.form.get('action', '')
    user_agent_key = request.form.get('user_agent', 'chrome')
    
    if action == 'start_infinite':
        def indexador_callback(paginas):
            indexador.agregar_paginas(paginas)
        
        active_crawler = crawler_manager.start_crawler(indexador_callback, user_agent_key)
        
        crawler_status['running'] = True
        crawler_status['start_time'] = time.time()
        crawler_status['crawler_type'] = 'infinito'
        crawler_status['user_agent'] = user_agent_key
        
        return jsonify({
            'message': '🚀 CRAWLER INFINITO INICIADO',
            'description': 'El crawler nunca se detendrá - Va de web en web automáticamente'
        })
    
    elif action == 'start_specific':
        url = request.form.get('url', '').strip()
        max_pages = int(request.form.get('max_pages', 100))
        
        if not url:
            return jsonify({'error': 'URL no válida'}), 400
        
        if not url.startswith('http'):
            url = 'https://' + url
        
        def specific_crawl_task():
            global crawler_status
            crawler_status['running'] = True
            crawler_status['start_time'] = time.time()
            crawler_status['crawler_type'] = 'específico'
            crawler_status['user_agent'] = user_agent_key
            
            crawler = WebCrawler(user_agent_key=user_agent_key)
            
            def crawl_limited():
                crawler.crawling_active = True
                crawler.url_queue.put(url)
                pages = 0
                
                while crawler.crawling_active and pages < max_pages:
                    try:
                        current_url = crawler.url_queue.get(timeout=5)
                        if current_url in crawler.visited:
                            continue
                        
                        result = crawler.crawl_page(current_url)
                        if result['success'] and result['page_info']:
                            page_info = result['page_info']
                            crawler.index[current_url] = page_info
                            indexador.agregar_paginas({current_url: page_info})
                            pages += 1
                            crawler_status['pages_crawled'] = pages
                            crawler_status['current_url'] = current_url
                            
                            for link in result['links']:
                                if link not in crawler.visited:
                                    crawler.url_queue.put(link)
                        
                        crawler.url_queue.task_done()
                    except:
                        break
                
                crawler_status['running'] = False
            
            crawl_limited()
        
        thread = threading.Thread(target=specific_crawl_task)
        thread.daemon = True
        thread.start()
        
        return jsonify({'message': 'Rastreo específico iniciado', 'url': url})
    
    elif action == 'stop':
        if active_crawler:
            active_crawler.stop_crawl()
            crawler_status['running'] = False
            return jsonify({'message': 'Crawler detenido'})
        return jsonify({'message': 'No hay crawler activo'})
    
    elif action == 'status':
        if active_crawler:
            status = active_crawler.get_status()
            return jsonify(status)
        return jsonify(crawler_status)
    
    return jsonify({'error': 'Acción no válida'}), 400

@app.route('/clear', methods=['POST'])
def clear():
    indexador.limpiar_index()
    return jsonify({'message': 'Índice limpiado'})

@app.route('/stats')
def stats():
    return jsonify(indexador.obtener_estadisticas())

@app.route('/cache_stats')
def cache_stats():
    """Obtiene estadísticas del caché"""
    global active_crawler
    if active_crawler:
        stats = active_crawler.obtener_estadisticas_cache()
        return jsonify(stats)
    return jsonify({'error': 'No hay crawler activo'}), 404

@app.route('/limpiar_cache', methods=['POST'])
def limpiar_cache():
    """Limpia el caché manualmente"""
    global active_crawler
    data = request.json
    max_days = data.get('max_days', 30)
    
    if active_crawler:
        active_crawler.limpiar_cache_expirado(max_days)
        return jsonify({'success': True, 'message': f'Caché limpiado (más de {max_days} días)'})
    return jsonify({'error': 'No hay crawler activo'}), 404

@app.route('/forzar_actualizacion', methods=['POST'])
def forzar_actualizacion():
    """Fuerza la actualización de una URL específica"""
    data = request.json
    url = data.get('url', '')
    
    if not url:
        return jsonify({'error': 'URL no especificada'}), 400
    
    global active_crawler
    if active_crawler:
        active_crawler.eliminar_del_cache(url)
        
        def refresh_task():
            time.sleep(1)
            active_crawler.crawl_page(url, force_refresh=True)
        
        thread = threading.Thread(target=refresh_task)
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': f'Actualización forzada para {url}'})
    return jsonify({'error': 'No hay crawler activo'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
