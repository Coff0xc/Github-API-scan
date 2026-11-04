# Docker Deployment Guide

## Quick Start

### 1. Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+

### 2. Configuration

Create `config_local.py`:

```python
GITHUB_TOKENS = [
    "ghp_your_token_here",
]

PROXY_URL = ""  # Optional: "http://127.0.0.1:7890"
```

Or use environment variables in `.env`:

```bash
GITHUB_TOKENS=ghp_token1,ghp_token2
PROXY_URL=http://127.0.0.1:7890
```

### 3. Run with Docker Compose

```bash
# Start both scanner and dashboard
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

Access dashboard at: **http://localhost:5000**

---

## Manual Docker Commands

### Build Image

```bash
docker build -t api-key-scanner .
```

### Run Scanner Only

```bash
docker run -d \
  --name scanner \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config_local.py:/app/config_local.py:ro \
  -e GITHUB_TOKENS="ghp_your_token" \
  api-key-scanner
```

### Run Dashboard Only

```bash
docker run -d \
  --name dashboard \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  api-key-scanner \
  python web_dashboard.py
```

---

## Architecture

```
┌─────────────────────────────────────┐
│     Docker Compose Network          │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │   Scanner    │  │  Dashboard  │ │
│  │ (main_v2.2)  │  │ (Flask:5000)│ │
│  └──────┬───────┘  └──────┬──────┘ │
│         │                 │         │
│         └─────────┬───────┘         │
│                   │                 │
│            ┌──────▼──────┐          │
│            │  ./data/    │          │
│            │ leaked_keys.db         │
│            └─────────────┘          │
└─────────────────────────────────────┘
```

---

## Volume Mounts

- `./data:/app/data` - Database and output files
- `./config_local.py:/app/config_local.py` - Configuration (read-only)

---

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `GITHUB_TOKENS` | Comma-separated tokens | - | Yes |
| `PROXY_URL` | HTTP proxy URL | - | No |
| `DB_PATH` | Database file path | `/app/data/leaked_keys.db` | No |

---

## Common Tasks

### View Scanner Logs

```bash
docker-compose logs -f scanner
```

### View Dashboard Logs

```bash
docker-compose logs -f dashboard
```

### Restart Services

```bash
docker-compose restart
```

### Update to Latest Code

```bash
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Backup Database

```bash
docker cp scanner:/app/data/leaked_keys.db ./backup.db
```

### Access Container Shell

```bash
docker exec -it scanner bash
```

---

## Production Deployment

### Using Docker Swarm

```bash
docker stack deploy -c docker-compose.yml api-scanner
```

### Using Kubernetes

Create deployment YAML (example):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-scanner
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api-scanner
  template:
    metadata:
      labels:
        app: api-scanner
    spec:
      containers:
      - name: scanner
        image: api-key-scanner:latest
        volumeMounts:
        - name: data
          mountPath: /app/data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: scanner-data-pvc
```

---

## Security Best Practices

1. **Never commit config_local.py**
   - Added to `.gitignore` by default
   - Mount as read-only volume

2. **Use secrets management**
   - Docker secrets (Swarm)
   - Kubernetes secrets
   - HashiCorp Vault

3. **Network isolation**
   - Use Docker networks
   - Firewall rules
   - VPN access only

4. **Regular updates**
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

---

## Troubleshooting

### Container won't start

Check logs:
```bash
docker-compose logs scanner
```

### Database permission errors

Fix permissions:
```bash
chmod 777 data/
```

### Dashboard can't connect

Check network:
```bash
docker network inspect api-scanner-network
```

### Out of disk space

Clean up:
```bash
docker system prune -a
```

---

## Resource Limits

Add to `docker-compose.yml`:

```yaml
services:
  scanner:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

---

## Multi-Architecture Support

Build for multiple platforms:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t api-key-scanner:latest \
  --push .
```

---

## Health Checks

Add to Dockerfile:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import sqlite3; sqlite3.connect('/app/data/leaked_keys.db')" || exit 1
```

---

**Status:** ✅ Production ready  
**Tested on:** Docker 24.0+, Compose 2.20+  
**Last Updated:** 2026-07-29
