#!/bin/bash
echo "Deploying Amazon Pet Arbitrage Scout..."
mkdir -p data/cookies data/temp data/output logs
if [ ! -f .env ]; then cp .env.example .env; fi
docker-compose up -d
echo "✓ Deployed: http://localhost:8000/docs"
