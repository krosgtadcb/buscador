🌐 BUSCADOR WEB COMPLETO - FUNCIONALIDAD COMPLETA
📋 VISIÓN GENERAL

El sistema es un buscador web autónomo estilo Google que:

    Indexa páginas web automáticamente

    Nunca se detiene (modo infinito)

    Almacena todo en JSON

    Interfaz web moderna

    Sin APIs externas - 100% local

🏗️ ARQUITECTURA DEL SISTEMA
text

┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   CRAWLER       │────▶│   INDEXADOR     │────▶│   BUSCADOR      │
│   (rastreador)  │     │   (JSON)        │     │   (Flask)        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                        │
         ▼                       ▼                        ▼
    🌍 Web ∞              📁 data/index.json        🖥️ Templates/
                                                         style.css
