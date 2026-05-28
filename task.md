# MIA 93.7 - Imagen API Task

## BLOCKER: Siteground Captcha
Siteground's bot protection (`sgcaptcha`) blocks ALL requests from Render's outbound IP `74.220.48.235`.
This affects:
- `/rss-proxy` (can't fetch WP REST API or RSS feed)
- `/generar-imagen` (can't download photos from cms.mia937.com/wp-content/uploads/)

### Fix Required
User must whitelist IP `74.220.48.235` in **SiteTools → Security → Blocked IPs** (add as allowed).
Alternatively: SiteTools → Speed → Caching → uncheck "Block Bad Bots" or adjust SG Security settings.

## Status
- [x] App code complete and deployed on Render
- [x] /rss-proxy endpoint (builds RSS from WP REST API with media:content)
- [x] /generar-imagen endpoint (branded image generation)  
- [x] Debug endpoint added for troubleshooting
- [ ] **BLOCKED** - Production endpoints fail due to Siteground captcha
- [ ] Make.com blueprint needs updating (currently has placeholders)
- [ ] Make.com scenario creation
- [ ] FB page ID discovery for MIA
- [ ] End-to-end test

## Production URLs
- Service: https://mia-imagen-api.onrender.com
- Render service ID: srv-d8c5gebbc2fs738r3rgg
- Render outbound IP: 74.220.48.235

## Make.com
- Token: 13174307-5beb-4cdf-91a6-ed925fb03e0f
- Team: 12505, Region: us1.make.com
- Blueprint: /home/user/mia-imagen-api/make-blueprint.json
- FB page: radiomia937 (page_id TBD)
