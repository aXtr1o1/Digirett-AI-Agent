# Milvus Setup

Simple Milvus deployment with PM2 and CI/CD.

## Quick Start

### 1. Setup Environment
```bash
cp env.template .env
# Edit .env and set MILVUS_PORT to your public port
```

### 2. Start with PM2
```bash
mkdir -p logs data/etcd data/minio data/milvus
chmod +x pm2-docker-wrapper.sh
pm2 start ecosystem.config.js
pm2 save
```

### 3. PM2 Commands
```bash
pm2 status          # Check status
pm2 logs milvus     # View logs
pm2 restart milvus  # Restart
pm2 stop milvus     # Stop
pm2 delete milvus   # Stop and remove
```

### 4. Stop Everything
```bash
pm2 delete milvus
docker-compose down
```

## CI/CD

The GitHub Actions workflow automatically:
- Installs PM2 if needed
- Deploys Milvus on push to `production` or `testing` branches
- Manages the service with PM2

**Required Secrets:**
- `DEPLOY_HOST` - Your server IP/domain
- `DEPLOY_USER` - SSH username
- `SSH_PRIVATE_KEY` - SSH private key

## Configuration

Edit `.env`:
```env
MILVUS_PORT=19530  # Your public port
```

## Files

- `docker-compose.yml` - Milvus services
- `ecosystem.config.js` - PM2 config
- `pm2-docker-wrapper.sh` - Docker Compose wrapper for PM2
- `env.template` - Environment template
