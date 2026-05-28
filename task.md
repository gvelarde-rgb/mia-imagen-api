# MIA 93.7 RSS → Facebook Automation

## Status: Almost Complete ✅

### Completed
- [x] Flask API deployed on Render (`mia-imagen-api.onrender.com`)
- [x] `/rss-proxy` — builds RSS with `media:content` from WP REST API
- [x] `/generar-imagen` — 1080x1350 branded images with MIA purple brackets + logo
- [x] SiteGround captcha solver — SHA-1 proof-of-work, caches session
- [x] Make.com scenario created (ID: 4757025) — `MIA 93.7 RSS a Facebook`
- [x] Scheduling: 300s interval, roundtrips=1, sequential=true
- [x] No category filter (all categories published)
- [x] FB page ID found: `773069582830640` (facebook.com/mia937)

### Pending (requires user action)
- [ ] **Create Facebook connection in Make.com** for MIA page (radiomia937 / mia937)
  - Go to https://us1.make.com/12505/connections
  - Add new Facebook Pages connection for MIA's page
  - Update scenario modules 5 and 3 with the new connection ID
- [ ] **Activate scenario** in Make.com after FB connection is set
- [ ] **Test end-to-end** — run scenario once manually to verify

### Production URLs
- Health: https://mia-imagen-api.onrender.com/
- RSS Proxy: https://mia-imagen-api.onrender.com/rss-proxy
- Image Gen: https://mia-imagen-api.onrender.com/generar-imagen?titulo=...&foto_url=...
- Make Scenario: https://us1.make.com/4757025/scenario/edit
- GitHub: https://github.com/gvelarde-rgb/mia-imagen-api

### Key IDs
- Render service: srv-d8c5gebbc2fs738r3rgg
- Make scenario: 4757025
- FB page ID: 773069582830640
- Current FB connection (placeholder): 1316211 (La Red's — needs to be changed to MIA's)
