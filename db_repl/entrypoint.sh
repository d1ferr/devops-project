#!/bin/bash
set -e
until PGPASSWORD=$POSTGRES_PASSWORD pg_isready -h "$MASTER_HOST" -p 5432 -U postgres; do
    echo "Ожидание Master ($MASTER_HOST)..."
    sleep 2
done
echo "Master доступен. Выполняю pg_basebackup..."
rm -rf /var/lib/postgresql/data/*
PGPASSWORD="$REPL_PASSWORD" pg_basebackup \
    -R -h "$MASTER_HOST" -U "$REPL_USER" \
    -D /var/lib/postgresql/data -P --wal-method=stream
chown -R postgres:postgres /var/lib/postgresql/data
chmod 700 /var/lib/postgresql/data
echo "Запускаю PostgreSQL в режиме Standby..."
exec gosu postgres postgres
