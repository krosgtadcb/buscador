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

@app.route('/buscar_en_internet', methods=['POST'])
def buscar_en_internet():
    """Busca una consulta en internet y añade resultados al índice"""
    data = request.json
    query = data.get('query', '')
    user_agent_key = data.get('user_agent', 'chrome')
    
    if not query:
        return jsonify({'error': 'Consulta vacía'}), 400
    
    # Obtener user agent
    user_agent = USER_AGENTS.get(user_agent_key, USER_AGENTS['chrome'])
    
    try:
        # Buscar en Google
        search_url = f"https://www.google.com/search?q={query}"
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
            crawler = WebCrawler(max_pages=5)
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

@app.route('/proxy')
def proxy():
    """Sirve como proxy para cargar páginas web dentro del iframe"""
    url = request.args.get('url', '')
    user_agent_key = request.args.get('ua', 'chrome')
    
    if not url:
        return "URL no especificada", 400
    
    try:
        user_agent = USER_AGENTS.get(user_agent_key, USER_AGENTS['chrome'])
        headers = {'User-Agent': user_agent}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        # Modificar los enlaces para que pasen por el proxy
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Modificar enlaces para que se abran en el mismo iframe
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('http'):
                link['href'] = f"/proxy?url={href}&ua={user_agent_key}"
                link['target'] = "_parent"
        
        # Añadir barra superior para navegación
        nav_bar = soup.new_tag('div')
        nav_bar['style'] = 'position: fixed; top: 0; left: 0; right: 0; background: #1a73e8; color: white; padding: 10px; z-index: 9999; display: flex; gap: 10px; align-items: center;'
        nav_bar.string = f'🌐 Navegando: {url[:100]}... '
        
        back_button = soup.new_tag('button')
        back_button['onclick'] = 'window.history.back()'
        back_button['style'] = 'background: white; color: #1a73e8; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;'
        back_button.string = '← Volver'
        
        nav_bar.append(back_button)
        
        # Añadir al body
        if soup.body:
            soup.body.insert(0, nav_bar)
            # Añadir padding-top para no tapar contenido
            soup.body['style'] = 'padding-top: 50px;'
        
        return str(soup)
        
    except Exception as e:
        return f"Error al cargar la página: {str(e)}", 500

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
                # Extraer tiempo
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
