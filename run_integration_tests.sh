#!/bin/bash
# Run integration tests in Docker container
# This script builds the test container and runs all integration tests
# against the streams-prefetcher container in the same Docker network.

set -e

echo "🔨 Building test runner container..."
cd /opt/docker/apps/streams-prefetcher

# Use custom .dockerignore for test build (allows tests/ directory)
cp .dockerignore .dockerignore.bak
cp .dockerignore.test .dockerignore

# Build test container directly with docker build
docker build -f Dockerfile.test -t streams-prefetcher-tests:latest .

# Restore original .dockerignore
mv .dockerignore.bak .dockerignore

echo ""
echo "🧪 Running integration tests..."
echo "   Target: http://streams-prefetcher:5000"
echo "   Network: aio_default"
echo ""

# Run tests in the same network as streams-prefetcher
# --rm: Remove container when done
# --network: Connect to same network as streams-prefetcher
# -e: Set environment variable for container-to-container communication
docker run --rm \
  --network aio_default \
  -e STREAMS_PREFETCHER_HOST=streams-prefetcher:5000 \
  streams-prefetcher-tests:latest

echo ""
echo "✅ Integration tests complete!"
