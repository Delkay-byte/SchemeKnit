# Future Domain Migration

Intended domain: `schemeknit.com`, not purchased and not active. Do not change
DNS, Render custom domains or production environment for it in this task.

## Central configuration

Frontend:

```env
NEXT_PUBLIC_SITE_URL=https://schemeknit.com
NEXT_PUBLIC_STAGING=false
NEXT_PUBLIC_API_URL=https://api.schemeknit.com
```

Backend:

```env
PUBLIC_WEB_URL=https://schemeknit.com
API_BASE_URL=https://api.schemeknit.com
CORS_ORIGINS=https://schemeknit.com
```

Verify the exact API hostname decision (apex path vs subdomain) before setting.

## Migration sequence

1. Purchase domain and configure DNS.
2. Provision TLS certificates.
3. Add the custom domain to Render frontend/backend.
4. Verify HTTPS and redirects.
5. Set staging to `NEXT_PUBLIC_STAGING=true`; never set it on production.
6. Update `NEXT_PUBLIC_SITE_URL` centrally.
7. Rebuild/restart frontend.
8. Update backend `CORS_ORIGINS`, `PUBLIC_WEB_URL`, `API_BASE_URL`.
9. Verify canonical URLs, sitemap, robots and Open Graph.
10. Submit the new sitemap in Search Console.
11. Keep redirects from any old host.
12. Do not enable HSTS preload until every relevant subdomain is HTTPS-ready.

No application-wide code change is required; only environment configuration and
deployment.
