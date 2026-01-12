module.exports = {
  apps: [{
    name: 'milvus',
    script: './pm2-docker-wrapper.sh',
    interpreter: 'bash',
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    error_file: './logs/pm2-error.log',
    out_file: './logs/pm2-out.log',
    log_file: './logs/pm2-combined.log',
    time: true
  }]
};
