# Milvus Quick Setup Guide

## 🚀 Fast Deployment

### Step 1: Prepare Your Instance

1. **Install Docker and Docker Compose** on your deployment instance:
   ```bash
   # Ubuntu/Debian
   curl -fsSL https://get.docker.com -o get-docker.sh
   sh get-docker.sh
   sudo usermod -aG docker $USER
   
   # Install Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

2. **Install Node.js and PM2** (Recommended for production):
   ```bash
   # Install Node.js
   curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
   sudo apt-get install -y nodejs
   
   # Install PM2 globally
   sudo npm install -g pm2
   ```

2. **Configure Firewall** to allow traffic on your Milvus port (default: 19530):
   ```bash
   # Ubuntu/Debian (UFW)
   sudo ufw allow 19530/tcp
   
   # Or configure your cloud provider's security group/firewall rules
   ```

### Step 2: Deploy Milvus

#### Option A: Manual Deployment

```bash
# Copy files to your instance
scp -r milvus/* user@your-instance:~/milvus/

# SSH into instance
ssh user@your-instance
cd ~/milvus

# Create environment file
cp env.template .env

# Edit .env with your public port
nano .env  # Set MILVUS_PORT to your instance's public port

# Setup PM2 (recommended for production)
chmod +x pm2-setup.sh
./pm2-setup.sh
# Follow instructions to enable PM2 on system startup

# Deploy with PM2 (recommended)
chmod +x pm2-start.sh pm2-stop.sh pm2-restart.sh
./pm2-start.sh

# OR deploy directly with Docker Compose
chmod +x deploy.sh stop.sh health-check.sh
./deploy.sh
```

#### Option B: CI/CD Deployment (Recommended)

1. **Configure GitHub Secrets**:
   - Go to your repository → Settings → Secrets and variables → Actions
   - Add the following secrets:
     - `DEPLOY_HOST`: Your instance IP or domain
     - `DEPLOY_USER`: SSH username
     - `SSH_PRIVATE_KEY`: Your private SSH key
     - `MILVUS_PORT`: (Optional) Your public port (defaults to 19530)

2. **Trigger Deployment**:
   - Push changes to `production` or `testing` branch
   - Or manually trigger via GitHub Actions → Deploy Milvus → Run workflow

### Step 3: Verify Deployment

```bash
# On your instance
cd ~/milvus
./health-check.sh

# Or test from your local machine
python milvus/test-connection.py your-instance-ip 19530
```

### Step 4: Configure Clients

Update your backend and ingestion services to use the Milvus instance:

**Backend `.env`:**
```env
MILVUS_HOST=your-instance-public-ip-or-domain
MILVUS_PORT=19530
MILVUS_COLLECTION=legal_documents
```

**Ingestion `.env`:**
```env
MILVUS_HOST=your-instance-public-ip-or-domain
MILVUS_PORT=19530
MILVUS_COLLECTION=legal_documents
```

## 🔧 Common Configuration

### Change Port

1. Update `MILVUS_PORT` in `.env` file
2. Update port mapping in `docker-compose.yml` (if needed)
3. Restart: `./stop.sh && ./deploy.sh`

### View Logs

**With PM2:**
```bash
pm2 logs milvus-docker
pm2 logs milvus-docker --lines 100  # Last 100 lines
```

**With Docker Compose:**
```bash
docker-compose logs -f standalone
```

### Stop Services

**With PM2:**
```bash
./pm2-stop.sh
```

**With Docker Compose:**
```bash
./stop.sh
```

### Restart Services

**With PM2:**
```bash
./pm2-restart.sh
# Or
pm2 restart milvus-docker
```

**With Docker Compose:**
```bash
./stop.sh
./deploy.sh
```

### PM2 Management

```bash
# View status
pm2 status

# Monitor resources
pm2 monit

# Save process list (for auto-start on reboot)
pm2 save

# View logs
pm2 logs milvus-docker
```

## 🔒 Security Checklist

- [ ] Firewall configured to only allow necessary ports
- [ ] SSH key-based authentication enabled
- [ ] Milvus authentication enabled (for production)
- [ ] Regular backups configured
- [ ] Monitoring and alerting set up

## 📞 Troubleshooting

**Connection refused?**
- Check firewall rules
- Verify port is correct in `.env`
- Check if Milvus is running: `docker-compose ps`

**Services not starting?**
- Check logs: `docker-compose logs`
- Verify Docker is running: `docker ps`
- Check disk space: `df -h`

**Health check failing?**
- Wait a few minutes for services to fully start
- Check individual service logs
- Verify all dependencies are healthy

For more details, see [README.md](./README.md)
