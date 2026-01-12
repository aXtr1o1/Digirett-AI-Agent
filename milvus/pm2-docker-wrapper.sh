#!/bin/bash
cd "$(dirname "$0")"
[ -f .env ] && export $(cat .env | grep -v '^#' | xargs)
docker-compose up || docker compose up
