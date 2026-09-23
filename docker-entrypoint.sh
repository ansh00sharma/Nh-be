#!/bin/sh

set -e

echo "========================================="
echo "Running Django migrations"
echo "========================================="

python manage.py migrate --noinput

echo "Migrations completed successfully."

echo "========================================="
echo "Starting Celery worker"
echo "========================================="

celery -A config.celery:app worker \
    --loglevel=info \
    --beat \
    --pidfile= &

echo "========================================="
echo "Starting backend server"
echo "========================================="

exec "$@"