module.exports = {
  apps: [{
    name: 'backend',
    script: './venv/bin/uvicorn',
    args: 'main:app --host 0.0.0.0 --port 8000',
    interpreter: 'none',
    autorestart: true,
    watch: false,
    max_memory_restart: '500M',
    env: {
      NODE_ENV: 'production'
    },
    error_file: './logs/pm2-error.log',
    out_file: './logs/pm2-out.log',
    log_file: './logs/pm2-combined.log',
    time: true
  }]
};
