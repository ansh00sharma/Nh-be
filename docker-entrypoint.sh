#!/bin/sh

set -e

echo "========================================="
echo "Running Django migrations"
echo "========================================="

python manage.py migrate --noinput

echo "Migrations completed successfully."

echo "========================================="
echo "Starting backend server"
echo "========================================="

exec "$@"