# Running TradingAgents with Docker

Docker provides an isolated, reproducible environment for running TradingAgents.

## 🚀 Quick Start

### 1. Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed
- [Docker Compose](https://docs.docker.com/compose/install/) installed
- `.env` file configured (copy from `.env.example`)

### 2. Build and Run

```bash
# Build the container
docker-compose build

# Start TradingAgents web interface
docker-compose up

# Access at http://localhost:8000
```

That's it! The web interface will be available at http://localhost:8000

## 📦 What's Included

The Docker container includes:

- ✅ Python 3.11
- ✅ All TradingAgents dependencies
- ✅ Web interface (Chainlit)
- ✅ Portfolio management
- ✅ Backtesting framework
- ✅ Broker integrations (Alpaca)
- ✅ All data providers configured

## 🔧 Configuration

### Environment Variables

Create a `.env` file with your API keys:

```bash
# Copy example
cp .env.example .env

# Edit with your keys
nano .env
```

Required variables:
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - For LLM
- `ALPHA_VANTAGE_API_KEY` - For market data
- `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` - For paper trading (optional)

### Data Persistence

The following directories are mounted as volumes to persist data:

```yaml
volumes:
  - ./data:/app/data                    # Market data cache
  - ./eval_results:/app/eval_results    # Analysis results
  - ./portfolio_data:/app/portfolio_data # Portfolio state
```

## 🎯 Usage

### Web Interface (Default)

```bash
# Start web interface
docker-compose up

# Access at http://localhost:8000
```

### Run Python Scripts

```bash
# Run a specific script
docker-compose run tradingagents python examples/portfolio_example.py

# Run tests
docker-compose run tradingagents pytest tests/ -v

# Open Python shell
docker-compose run tradingagents python
```

### Interactive Shell

```bash
# Open bash in container
docker-compose run tradingagents bash

# Then run any commands
python examples/paper_trading_alpaca.py
pytest tests/
```

## 🔬 Optional Services

### Jupyter Notebook

For interactive analysis and development:

```bash
# Start with Jupyter
docker-compose --profile jupyter up

# Access Jupyter at http://localhost:8888
```

## 🛠️ Docker Commands Reference

### Building

```bash
# Build/rebuild images
docker-compose build

# Build without cache
docker-compose build --no-cache

# Build specific service
docker-compose build tradingagents
```

### Running

```bash
# Start in foreground
docker-compose up

# Start in background (detached)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

### Maintenance

```bash
# View running containers
docker-compose ps

# Restart services
docker-compose restart

# Remove stopped containers
docker-compose rm

# Prune unused images/volumes
docker system prune -a
```

## 🐛 Troubleshooting

### Port Already in Use

If port 8000 is already in use:

```yaml
# Edit docker-compose.yml
ports:
  - "8001:8000"  # Change 8000 to 8001 (or any free port)
```

### Permission Issues

If you encounter permission errors:

```bash
# Fix ownership of data directories
sudo chown -R $USER:$USER data/ eval_results/ portfolio_data/
```

### Container Won't Start

Check logs for errors:

```bash
docker-compose logs tradingagents
```

Common issues:
- Missing `.env` file
- Invalid API keys
- Port conflicts

### Out of Memory

Increase Docker memory limit:

- **Docker Desktop**: Settings → Resources → Memory → Increase limit
- **Linux**: Edit `/etc/docker/daemon.json`

### Clean Restart

Complete reset:

```bash
# Stop everything
docker-compose down -v

# Remove images
docker rmi tradingagents:latest

# Rebuild
docker-compose build --no-cache

# Start fresh
docker-compose up
```

## 📊 Production Deployment

### Security Considerations

1. **Never commit `.env`** - Already in `.gitignore`
2. **Use secrets management** - Docker secrets or vault
3. **Network security** - Use reverse proxy (nginx)
4. **Rate limiting** - Configure Chainlit auth
5. **HTTPS** - Use SSL certificates

### Example Production Setup

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  tradingagents:
    build: .
    restart: always
    env_file:
      - .env.prod
    environment:
      - CHAINLIT_AUTH_SECRET=${CHAINLIT_AUTH_SECRET}
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.tradingagents.rule=Host(`trading.yourdomain.com`)"
      - "traefik.http.routers.tradingagents.tls=true"
```

### Monitoring

Add monitoring with Prometheus/Grafana:

```yaml
# Add to docker-compose.yml
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
```

## 🌐 Cloud Deployment

### AWS ECS

```bash
# Build for AWS
docker build -t tradingagents:latest .

# Tag for ECR
docker tag tradingagents:latest YOUR_ECR_REPO/tradingagents:latest

# Push to ECR
docker push YOUR_ECR_REPO/tradingagents:latest
```

### Google Cloud Run

```bash
# Build for Cloud Run
gcloud builds submit --tag gcr.io/YOUR_PROJECT/tradingagents

# Deploy
gcloud run deploy tradingagents \
  --image gcr.io/YOUR_PROJECT/tradingagents \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

### Digital Ocean

```bash
# Use Docker Compose on droplet
doctl compute droplet create tradingagents \
  --image docker-20-04 \
  --size s-2vcpu-4gb \
  --region nyc1

# SSH and setup
ssh root@YOUR_DROPLET_IP
git clone YOUR_REPO
cd TradingAgents
docker-compose up -d
```

## 💡 Tips

1. **Development Mode**: Mount code as volume to see changes without rebuild
   ```yaml
   volumes:
     - ./tradingagents:/app/tradingagents
   ```

2. **Multiple Environments**: Use different compose files
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
   ```

3. **Resource Limits**: Prevent runaway containers
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '2'
         memory: 4G
   ```

4. **Health Checks**: Monitor container health
   ```yaml
   healthcheck:
     test: ["CMD", "curl", "-f", "http://localhost:8000"]
     interval: 30s
     timeout: 10s
     retries: 3
   ```

## 📚 Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [Chainlit Deployment](https://docs.chainlit.io/deployment/overview)
- [TradingAgents Docs](README.md)
