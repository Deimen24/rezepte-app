#!/usr/bin/env bash
#
# backup.sh        daily at BACKUP_HOUR: pg_dump and media tar to /backups
# backup.sh now    once, then exit

set -Eeuo pipefail

BACKUP_DIR=/backups
MEDIA_ROOT=/data
MEDIA_NAME=media
KEEP_DAYS=${BACKUP_KEEP_DAYS:-14}
HOUR=${BACKUP_HOUR:-3}
DB_WAIT_TRIES=30

export PGHOST=${PGHOST:-db}
export PGUSER=${PGUSER:-rezepte}
export PGDATABASE=${PGDATABASE:-rezepte}

log()
{
	printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

check_config()
{
	case "$HOUR" in
	[0-9]|1[0-9]|2[0-3])
		;;
	*)
		log "BACKUP_HOUR must be 0-23, got '$HOUR'"
		exit 1
		;;
	esac
	case "$KEEP_DAYS" in
	''|*[!0-9]*)
		log "BACKUP_KEEP_DAYS must be a number, got '$KEEP_DAYS'"
		exit 1
		;;
	esac
}

seconds_until_next_run()
{
	local now next

	now=$(date +%s)
	next=$(date -d "$(printf '%02d:00' "$HOUR")" +%s)
	if [ "$next" -le "$now" ]; then
		next=$(date -d "tomorrow $(printf '%02d:00' "$HOUR")" +%s)
	fi
	echo $((next - now))
}

wait_for_db()
{
	local i

	for ((i = 0; i < DB_WAIT_TRIES; i++)); do
		if pg_isready -q; then
			return 0
		fi
		sleep 2
	done
	log "database at $PGHOST not reachable, giving up"
	return 1
}

file_size()
{
	du -h "$1" | cut -f1
}

dump_db()
{
	local stamp=$1 file

	file="$BACKUP_DIR/db-$stamp.dump"
	pg_dump -Fc --file "$file.part"
	mv "$file.part" "$file"
	log "database dumped to $file ($(file_size "$file"))"
}

media_is_empty()
{
	[ -z "$(ls -A "$MEDIA_ROOT/$MEDIA_NAME" 2>/dev/null)" ]
}

archive_media()
{
	local stamp=$1 file

	file="$BACKUP_DIR/media-$stamp.tar.gz"
	if media_is_empty; then
		log "media directory empty, no archive written"
		return 0
	fi
	tar -czf "$file.part" -C "$MEDIA_ROOT" "$MEDIA_NAME"
	mv "$file.part" "$file"
	log "media archived to $file ($(file_size "$file"))"
}

prune_old()
{
	local f

	while IFS= read -r f; do
		rm -f "$f"
		log "deleted old backup $f"
	done < <(find "$BACKUP_DIR" -maxdepth 1 -type f \
		\( -name 'db-*.dump' -o -name 'media-*.tar.gz' \) \
		-mtime +"$KEEP_DAYS")
}

run_backup()
{
	local stamp

	stamp=$(date +%Y%m%d-%H%M%S)
	mkdir -p "$BACKUP_DIR"
	rm -f "$BACKUP_DIR"/*.part
	wait_for_db
	dump_db "$stamp"
	archive_media "$stamp"
	prune_old
	log "backup $stamp finished"
}

run_loop()
{
	local secs

	log "backup loop started: daily at $HOUR:00 ($(date +%Z))," \
		"keeping $KEEP_DAYS days"
	while true; do
		secs=$(seconds_until_next_run)
		log "next backup in $secs s"
		sleep "$secs"
		run_backup
	done
}

main()
{
	trap 'log "backup failed: $BASH_COMMAND"' ERR
	check_config
	if [ "${1:-}" = now ]; then
		run_backup
		exit 0
	fi
	run_loop
}

main "$@"
