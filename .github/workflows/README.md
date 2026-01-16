# CI/CD Deployment

Unified deployment workflow for all services: Milvus, Backend, and Ingestion.

## Usage

### Automatic Deployment
- Push to  `testing` branch
- Automatically deploys changed services
- `production` is not yet configured Yet to recevie creds from client

### Manual Deployment
1. Go to Actions → Deploy Services
2. Click "Run workflow"
3. Select service: `all`, `milvus`, `backend`, or `ingestion`

## Services

### Milvus
- Managed with PM2
- Runs Docker Compose
- Port: 19530 (configurable)

### Backend
- FastAPI application
- Managed with PM2
- Port: 8000
- Requires virtual environment

### Ingestion
- Python pipeline
- Managed with PM2
- Requires virtual environment

## Required Secrets

- `DEPLOY_HOST` - Server IP/domain
- `DEPLOY_USER` - SSH username
- `SSH_PRIVATE_KEY` - SSH private key

## PM2 Commands (on server)

```bash
pm2 status              # View all services
pm2 logs milvus         # Milvus logs
pm2 logs backend        # Backend logs
pm2 logs ingestion      # Ingestion logs
pm2 restart <name>      # Restart service
pm2 stop <name>         # Stop service
pm2 delete <name>       # Remove service
```
