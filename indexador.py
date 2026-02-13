import json
import os
from datetime import datetime
from collections import defaultdict

class Indexador:
    def __init__(self, json_path='data/index.json'):
        self.json_path = json_path
        self.index_data = self.cargar_index()
    
    def cargar_index(self):
        """Carga el índice desde JSON"""
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return self.crear_estructura_base()
        return self.crear_estructura_base()
    
    def crear_estructura_base(self):
        """Crea la estructura base del índice"""
        return {
            'paginas': [],
            'keywords': {},
            'domains': {},
            'stats': {
                'total_paginas': 0,
                'total_keywords': 0,
                'total_domains': 0,
                'last_update': None,
                'created': datetime.now().isoformat()
            }
        }
    
    def guardar_index(self):
        """Guarda el índice en JSON"""
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        
        # Actualizar estadísticas
        self.index_data['stats']['total_paginas'] = len(self.index_data['paginas'])
        self.index_data['stats']['total_keywords'] = len(self.index_data['keywords'])
        self.index_data['stats']['total_domains'] = len(self.index_data['domains'])
        self.index_data['stats']['last_update'] = datetime.now().isoformat()
        
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(self.index_data, f, ensure_ascii=False, indent=2)
    
    def agregar_paginas(self, nuevas_paginas):
        """Agrega nuevas páginas al índice"""
        urls_existentes = {p['url'] for p in self.index_data['paginas']}
        added = 0
        
        for url, info in nuevas_paginas.items():
            if url not in urls_existentes:
                self.index_data['paginas'].append(info)
                added += 1
                
                # Actualizar dominios
                domain = info['domain']
                if domain not in self.index_data['domains']:
                    self.index_data['domains'][domain] = {
                        'urls': [],
                        'pages_count': 0,
                        'last_crawled': info['crawled_date']
                    }
                self.index_data['domains'][domain]['urls'].append(url)
                self.index_data['domains'][domain]['pages_count'] += 1
                self.index_data['domains'][domain]['last_crawled'] = info['crawled_date']
                
                # Actualizar keywords
                for keyword in info['keywords']:
                    if keyword not in self.index_data['keywords']:
                        self.index_data['keywords'][keyword] = []
                    if url not in self.index_data['keywords'][keyword]:
                        self.index_data['keywords'][keyword].append(url)
        
        if added > 0:
            self.guardar_index()
        
        return added
    
    def buscar(self, query, page=1, per_page=10):
        """Busca páginas por palabras clave"""
        palabras = query.lower().split()
        puntajes = defaultdict(float)
        
        if not palabras:
            return [], 0
        
        for palabra in palabras:
            if palabra in self.index_data['keywords']:
                for url in self.index_data['keywords'][palabra]:
                    puntajes[url] += 1
        
        urls_ordenadas = sorted(puntajes.keys(), key=lambda x: puntajes[x], reverse=True)
        
        total_resultados = len(urls_ordenadas)
        start = (page - 1) * per_page
        end = start + per_page
        urls_pagina = urls_ordenadas[start:end]
        
        resultados = []
        for url in urls_pagina:
            for pagina in self.index_data['paginas']:
                if pagina['url'] == url:
                    resultados.append({
                        'title': pagina['title'],
                        'url': pagina['url'],
                        'description': pagina.get('description', pagina['text_snippet'][:160]),
                        'domain': pagina['domain'],
                        'relevance': puntajes[url],
                        'from_cache': pagina.get('from_cache', False),
                        'cached_date': pagina.get('cached_date', pagina['crawled_date'])
                    })
                    break
        
        return resultados, total_resultados
    
    def obtener_estadisticas(self):
        """Obtiene estadísticas del índice"""
        return self.index_data['stats']
    
    def limpiar_index(self):
        """Limpia todo el índice"""
        self.index_data = self.crear_estructura_base()
        self.guardar_index()
    
    def obtener_paginas_recientes(self, limit=20):
        """Obtiene las páginas más recientes"""
        paginas = self.index_data['paginas'][-limit:]
        return reversed(paginas)
    
    def obtener_domains(self):
        """Obtiene todos los dominios indexados"""
        return self.index_data['domains']
    
    def url_esta_indexada(self, url):
        """Verifica si una URL ya está indexada"""
        for pagina in self.index_data['paginas']:
            if pagina['url'] == url:
                return True
        return False
