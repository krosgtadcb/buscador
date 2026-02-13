from flask import Flask, render_template, request, jsonify, redirect, url_for
from crawler import WebCrawler, CrawlerManager
from indexador import Indexador
import threading
import time
from datetime import datetime

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

@app.context_processor
def utility_processor():
    """Añade funciones útiles a todas las plantillas"""
    return dict(now=datetime.now())

@app.route('/')
def index():
    stats = indexador.obtener_estadisticas()
    return render_template('index.html', stats=stats)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    
    if not query:
        return redirect(url_for('index'))
    
    resultados, total = indexador.buscar(query, page)
    total_paginas = (total + 9) // 10
    
    return render_template('resultados.html', 
                         query=query,
                         resultados=resultados,
                         total=total,
                         page=page,
                         total_paginas=total_paginas)

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
                         crawler_status=crawler_status)

@app.route('/crawl', methods=['POST'])
def crawl():
    global active_crawler, crawler_status
    
    action = request.form.get('action', '')
    
    if action == 'start_infinite':
        """INICIA EL CRAWLER INFINITO - NUNCA SE DETIENE"""
        
        def indexador_callback(paginas):
            """Callback para guardar páginas en tiempo real"""
            indexador.agregar_paginas(paginas)
        
        # Iniciar crawler infinito
        active_crawler = crawler_manager.start_crawler(indexador_callback)
        
        crawler_status['running'] = True
        crawler_status['start_time'] = time.time()
        crawler_status['crawler_type'] = 'infinito'
        
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
            
            crawler = WebCrawler()
            
            # Versión específica con límite
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
                        if result['success']:
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