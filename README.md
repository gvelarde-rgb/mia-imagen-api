# MIA 93.7 — Imagen API + RSS Proxy

Servicio para automatizar la publicación de noticias de MIA 93.7 en Facebook.  
Réplica de la arquitectura de La Red 106.1 (`lared-imagen-api`).

## Endpoints

| Endpoint | Descripción |
|----------|-------------|
| `GET /` | Health check |
| `GET /rss-proxy` | RSS enriquecido con `media:content` (imágenes full-res) |
| `GET /generar-imagen?titulo=...&foto_url=...` | Genera imagen 1080x1350 con branding MIA |

## Flujo completo (Make.com)

```
RSS Trigger (/rss-proxy) → HTTP Download (generar-imagen) → Facebook Upload Photo → Facebook Create Comment
```

## Deploy en Render

1. Crear repo en GitHub (privado)
2. Push este código
3. En Render: New Web Service → conectar repo → Docker → Free plan
4. URL resultante: `https://mia-imagen-api.onrender.com`

## Configurar Make.com

1. Importar `make-blueprint.json` como nuevo escenario
2. Reemplazar placeholders:
   - `{{MIA_IMAGEN_API_URL}}` → URL de Render
   - `{{MIA_FB_PAGE_ID}}` → ID de la página de Facebook
   - `{{MIA_FB_CONNECTION_ID}}` → ID de conexión Facebook en Make.com
3. Conectar cuenta de Facebook con acceso a la página radiomia937
4. Configurar scheduling: cada 300s, roundtrips=1, sequential=true
5. Activar escenario

## Estructura

```
app.py              — Flask app principal
requirements.txt    — Dependencias Python
Dockerfile          — Para deploy en Render
render.yaml         — Configuración de Render
make-blueprint.json — Blueprint para Make.com (con placeholders)
```
