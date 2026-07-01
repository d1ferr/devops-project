FROM postgres:15
COPY init.sql /docker-entrypoint-initdb.d/
COPY postgresql.conf /etc/postgresql/custom.conf
COPY pg_hba_custom.conf /etc/postgresql/pg_hba_custom.conf
CMD ["postgres", "-c", "config_file=/etc/postgresql/custom.conf", "-c", "hba_file=/etc/postgresql/pg_hba_custom.conf"]
