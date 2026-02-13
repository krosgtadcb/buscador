from flask import Flask, render_template, request, jsonify, redirect, url_for
from crawler import WebCrawler, CrawlerManager
from indexador import Indexador
import threading
import time
import requests
from datetime import datetime
import socket
import subprocess
import platform
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
    'bot': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'custom': ''  # Para user agent personalizado
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
    
    # Primero buscar en índice local
    resultados, total = indexador.buscar(query, page)
    
    # Si no hay resultados, buscar en internet
    buscar_en_internet = request.args.get('search_web', 'false') == 'true'
    
    return render_template('resultados.html', 
                         query=query,
                         resultados=resultados,
                         total=total,
                         page=page,
                         total_paginas=(total + 9) // 10,
                         buscar_en_internet=buscar_en_internet,
                         user_agent=user_agent)

@app.route('/abrir_url', methods=['POST'])
def abrir_url():
    """Abre una URL directamente en el iframe y la añade al crawler"""
    data = request.json
    url = data.get('url', '').strip()
    user_agent_key = data.get('user_agent', 'chrome')
    indexar = data.get('indexar', True)  # Por defecto, indexar la página
    
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
            # Si se solicita indexar, añadir al crawler
            if indexar:
                def indexar_url_task():
                    crawler = WebCrawler(max_pages=1, user_agent_key=user_agent_key)
                    resultado = crawler.crawl_page(url)
                    if resultado['success'] and resultado['page_info']:
                        indexador.agregar_paginas({url: resultado['page_info']})
                
                thread = threading.Thread(target=indexar_url_task)
                thread.daemon = True
                thread.start()
            
            return jsonify({
                'success': True,
                'url': url,
                'status_code': response.status_code,
                'message': 'URL válida, abriendo...',
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
        
        # Hacer la petición
        response = requests.get(url, headers=headers, timeout=10, stream=True)
        
        # Determinar el tipo de contenido
        content_type = response.headers.get('Content-Type', '').lower()
        
        # Si es un recurso estático (CSS, JS, imagen, etc.), devolverlo directamente
        if 'text/html' not in content_type:
            # Devolver el contenido directamente con los headers correctos
            excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
            headers = [(name, value) for (name, value) in response.raw.headers.items()
                      if name.lower() not in excluded_headers]
            
            response_content = response.content
            return (response_content, response.status_code, headers)
        
        # Es HTML, procesarlo
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        base_url = '/'.join(url.split('/')[:3])  # http://dominio.com
        
        # Función para hacer URLs absolutas
        def make_absolute(src, base):
            if src.startswith('http'):
                return src
            elif src.startswith('//'):
                return 'https:' + src
            elif src.startswith('/'):
                return base + src
            else:
                # URL relativa
                if url.endswith('/'):
                    return url + src
                else:
                    return '/'.join(url.split('/')[:-1]) + '/' + src
        
        # PROCESAR CSS - Modificar URLs dentro de los archivos CSS
        for link in soup.find_all('link', rel='stylesheet'):
            if link.get('href'):
                original_href = link['href']
                absolute_href = make_absolute(original_href, base_url)
                # Cambiar a nuestro proxy para CSS
                link['href'] = f"/proxy_recurso?url={urllib.parse.quote(absolute_href)}&ua={user_agent_key}"
        
        # PROCESAR JAVASCRIPT
        for script in soup.find_all('script', src=True):
            if script.get('src'):
                original_src = script['src']
                absolute_src = make_absolute(original_src, base_url)
                # Cambiar a nuestro proxy para JS
                script['src'] = f"/proxy_recurso?url={urllib.parse.quote(absolute_src)}&ua={user_agent_key}"
        
        # PROCESAR IMÁGENES
        for img in soup.find_all('img', src=True):
            if img.get('src'):
                original_src = img['src']
                absolute_src = make_absolute(original_src, base_url)
                img['src'] = f"/proxy_recurso?url={urllib.parse.quote(absolute_src)}&ua={user_agent_key}"
        
        # PROCESAR ENLACES (a href)
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('http') or href.startswith('//') or href.startswith('/'):
                absolute_href = make_absolute(href, base_url)
                link['href'] = f"/proxy?url={urllib.parse.quote(absolute_href)}&ua={user_agent_key}"
                link['target'] = "_parent"
        
        # Añadir meta tag para viewport y otros
        meta_viewport = soup.new_tag('meta')
        meta_viewport['name'] = 'viewport'
        meta_viewport['content'] = 'width=device-width, initial-scale=1.0'
        if soup.head:
            soup.head.insert(0, meta_viewport)
        
        # Añadir barra superior para navegación
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
        
        # Botón volver
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
        
        # URL actual
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
        
        # Selector User Agent
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
        
        # Botón indexar
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
        
        # Añadir al body
        if soup.body:
            soup.body.insert(0, nav_bar)
            # Añadir padding-top y estilos base
            if soup.body.get('style'):
                soup.body['style'] += '; padding-top: 70px !important; margin: 0 !important;'
            else:
                soup.body['style'] = 'padding-top: 70px !important; margin: 0 !important;'
        
        # Añadir script para manejar eventos
        script_tag = soup.new_tag('script')
        script_tag.string = '''
            // Prevenir que los enlaces se abran en nueva pestaña
            document.addEventListener('click', function(e) {
                const link = e.target.closest('a');
                if (link && link.target === '_blank') {
                    e.preventDefault();
                    if (link.href) {
                        window.parent.location.href = '/proxy?url=' + encodeURIComponent(link.href) + '&ua=' + document.querySelector('select').value;
                    }
                }
            });
            
            // Adaptar iframes
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
        
        # Hacer la petición
        response = requests.get(url, headers=headers, timeout=10, stream=True)
        
        # Devolver el contenido con los headers correctos
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in response.raw.headers.items()
                  if name.lower() not in excluded_headers]
        
        response_content = response.content
        return (response_content, response.status_code, headers)
        
    except Exception as e:
        return f"Error cargando recurso: {str(e)}", 500

@app.route('/buscar_en_internet', methods=['POST'])
def buscar_en_internet():
    """Busca una consulta en internet y añade resultados al índice"""
    data = request.json
    query = data.get('query', '')
    user_agent_key = data.get('user_agent', 'chrome')
    
    if not query:
        return jsonify({'error': 'Consulta vacía'}), 400
    
    user_agent = USER_AGENTS.get(user_agent_key, USER_AGENTS['chrome'])
    
    try:
        # Buscar en Google
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        headers = {'User-Agent': user_agent}
        
        response = requests.get(search_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extraer resultados de Google
            resultados = []
            for result in soup.select('div.g'):
                title_elem = result.select_one('h3')
                link_elem = result.select_one('a')
                desc_elem = result.select_one('div.VwiC3b')
                
                if title_elem and link_elem:
                    title = title_elem.text
                    url = link_elem.get('href', '')
                    if url.startswith('/url?q='):
                        url = url.split('/url?q=')[1].split('&')[0]
                    
                    description = desc_elem.text if desc_elem else ''
                    
                    resultados.append({
                        'title': title,
                        'url': url,
                        'description': description
                    })
            
            # Crawlear las primeras 5 URLs encontradas
            crawler = WebCrawler(max_pages=5, user_agent_key=user_agent_key)
            paginas_indexadas = {}
            
            for resultado in resultados[:5]:
                try:
                    page_result = crawler.crawl_page(resultado['url'])
                    if page_result['success'] and page_result['page_info']:
                        paginas_indexadas[resultado['url']] = page_result['page_info']
                except:
                    continue
            
            # Añadir al índice
            if paginas_indexadas:
                indexador.agregar_paginas(paginas_indexadas)
            
            return jsonify({
                'success': True,
                'resultados': resultados[:10],
                'indexadas': len(paginas_indexadas)
            })
        
        return jsonify({'error': 'No se pudo buscar en internet'}), 500
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ping', methods=['POST'])
def ping_test():
    """Realiza test de ping a un dominio"""
    data = request.json
    url = data.get('url', '')
    
    try:
        # Extraer dominio
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc or url
        
        # Hacer ping
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '4', domain]
        
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        
        # Procesar resultados
        lines = result.stdout.split('\n')
        ping_results = []
        
        for line in lines:
            if 'time=' in line.lower() or 'tiempo=' in line.lower():
                import re
                time_match = re.search(r'time[=<]\s*(\d+(?:\.\d+)?)', line.lower())
                if time_match:
                    ping_results.append(float(time_match.group(1)))
        
        if ping_results:
            avg_ping = sum(ping_results) / len(ping_results)
            min_ping = min(ping_results)
            max_ping = max(ping_results)
            
            return jsonify({
                'success': True,
                'domain': domain,
                'avg': round(avg_ping, 2),
                'min': round(min_ping, 2),
                'max': round(max_ping, 2),
                'packets': len(ping_results),
                'raw': result.stdout
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No se pudo medir la latencia',
                'raw': result.stdout
            })
            
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout en el ping'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin')
def admin():
    stats = indexador.obtener_estadisticas()
    paginas_recientes = indexador.obtener_paginas_recientes(20)
    domains = indexador.obtener_domains()
    
    # Actualizar estado
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
        """INICIA EL CRAWLER INFINITO"""
        
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
