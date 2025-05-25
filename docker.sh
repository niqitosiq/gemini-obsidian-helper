#!/bin/bash

# Make the script executable
chmod +x docker.sh

# Function to display help
show_help() {
  echo "Usage: ./docker.sh [command]"
  echo "Commands:"
  echo "  build       - Build Docker images"
  echo "  up          - Start containers"
  echo "  down        - Stop and remove containers"
  echo "  restart     - Restart containers"
  echo "  logs        - Show logs from containers"
  echo "  ps          - List running containers"
  echo "  help        - Show this help message"
}

# Process command
case "$1" in
  build)
    docker-compose build
    ;;
  up)
    docker-compose up -d
    ;;
  down)
    docker-compose down
    ;;
  restart)
    docker-compose restart
    ;;
  logs)
    docker-compose logs -f
    ;;
  ps)
    docker-compose ps
    ;;
  help|*)
    show_help
    ;;
esac 