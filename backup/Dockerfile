# Backup container: pg_dump 17 (matches the db image) plus tar.
FROM postgres:17.11

# tzdata so that BACKUP_HOUR is interpreted in the configured TZ.
RUN apt-get update \
	&& apt-get install -y --no-install-recommends tzdata \
	&& rm -rf /var/lib/apt/lists/*

COPY backup.sh /usr/local/bin/backup.sh
RUN chmod 0755 /usr/local/bin/backup.sh

ENTRYPOINT ["/usr/local/bin/backup.sh"]
