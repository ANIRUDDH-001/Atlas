# Handoff: Dashboard → Deployment

## Dashboard Service in Docker Compose
The dashboard is served by the `dashboard` nginx service.

Dockerfile: none needed — use `nginx:alpine` base image.
Volume mount: `./dashboard:/usr/share/nginx/html:ro`
Port: `3000:80`

## nginx Configuration
The default nginx config serves static files.
Add a custom `nginx.conf` only if proxy headers are needed.

## README Note Required
Add this line to README.md under "Accessing the system":
```
Dashboard (live): http://localhost:3000
```

## API CORS Check
Confirm `app/main.py` CORS includes `http://localhost:3000`.
If not, add it before deployment review.

## Part E Submission Note
In README.md, under "Live Dashboard", write:
> "The dashboard connects to the API via SSE and updates visitor
> count in real time as events are ingested. Accessible at
> http://localhost:3000 after `docker compose up`."
