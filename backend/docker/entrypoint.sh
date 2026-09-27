#!/bin/sh

echo "Attente de PostgreSQL..."

while ! python -c "import psycopg2; psycopg2.connect(host='db', port='5432', dbname='barakagive', user='postgres', password='postgres')" 2>/dev/null; do
  echo "PostgreSQL pas encore prêt..."
  sleep 2
done

python manage.py migrate

python manage.py runserver 0.0.0.0:8000 --noreload