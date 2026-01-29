#!/bin/bash
set -euo pipefail

LOG_FILE="${HOME}/.hekate/logs/cleanup.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

cleanup_stale_agent_heartbeats() {
    local count=0
    while IFS= read -r key; do
        if [[ -n "$key" ]]; then
            ttl=$(redis-cli TTL "$key" 2>/dev/null || echo "-2")
            if [[ "$ttl" == "-1" ]]; then
                redis-cli DEL "$key" >/dev/null 2>&1
                ((count++))
            fi
        fi
    done < <(redis-cli --scan --pattern "agent:*:heartbeat" 2>/dev/null)

    if [[ $count -gt 0 ]]; then
        log "Cleaned $count stale agent heartbeats"
    fi
}

cleanup_orphaned_task_claims() {
    local count=0
    while IFS= read -r key; do
        if [[ -n "$key" && "$key" =~ task:.*:claimed ]]; then
            claimed=$(redis-cli GET "$key" 2>/dev/null || echo "false")
            task_id=$(echo "$key" | cut -d: -f2)

            if [[ "$claimed" == "true" ]]; then
                agent_key=$(redis-cli --scan --pattern "agent:*:task_id" 2>/dev/null | \
                    xargs -I {} sh -c 'redis-cli HGET "$1" "$2" 2>/dev/null | grep -q "$3" && echo "$1"' _ {} {} "$task_id" || true)

                if [[ -z "$agent_key" ]]; then
                    redis-cli SET "$key" "false" >/dev/null 2>&1
                    redis-cli SET "task:${task_id}:status" "pending" >/dev/null 2>&1
                    ((count++))
                fi
            fi
        fi
    done < <(redis-cli --scan --pattern "task:*:claimed" 2>/dev/null)

    if [[ $count -gt 0 ]]; then
        log "Released $count orphaned task claims"
    fi
}

cleanup_expired_verification_prefetch() {
    local count=0
    while IFS= read -r key; do
        if [[ -n "$key" && "$key" =~ verify:prefetch: ]]; then
            ttl=$(redis-cli TTL "$key" 2>/dev/null || echo "-2")
            if [[ "$ttl" -lt 0 ]]; then
                redis-cli DEL "$key" >/dev/null 2>&1
                ((count++))
            fi
        fi
    done < <(redis-cli --scan --pattern "verify:prefetch:*" 2>/dev/null)

    if [[ $count -gt 0 ]]; then
        log "Cleaned $count expired verification prefetch entries"
    fi
}

cleanup_old_metrics() {
    local count=0
    while IFS= read -r key; do
        if [[ -n "$key" && "$key" =~ metrics: ]]; then
            ttl=$(redis-cli TTL "$key" 2>/dev/null || echo "-2")
            if [[ "$ttl" -lt 0 ]]; then
                redis-cli DEL "$key" >/dev/null 2>&1
                ((count++))
            fi
        fi
    done < <(redis-cli --scan --pattern "metrics:*" 2>/dev/null)

    if [[ $count -gt 0 ]]; then
        log "Cleaned $count old metrics entries"
    fi
}

cleanup_old_alerts() {
    local count=0
    while IFS= read -r key; do
        if [[ -n "$key" && "$key" =~ alerts: ]]; then
            ttl=$(redis-cli TTL "$key" 2>/dev/null || echo "-2")
            if [[ "$ttl" -lt 0 ]]; then
                redis-cli DEL "$key" >/dev/null 2>&1
                ((count++))
            fi
        fi
    done < <(redis-cli --scan --pattern "alerts:*" 2>/dev/null)

    if [[ $count -gt 0 ]]; then
        log "Cleaned $count old alert entries"
    fi
}

cleanup_old_vectors() {
    local count=0
    count=$(python3 -c "
import chromadb
from pathlib import Path
import time

client = chromadb.PersistentClient(path=str(Path.home() / '.hekate/memory'))
collection = client.get_or_create_collection('sessions')

cutoff = int(time.time()) - 7200  # 2 hours
results = collection.get(include=['metadatas', 'ids'])

to_delete = []
for meta, id in zip(results['metadatas'], results['ids']):
    if meta.get('timestamp', 0) < cutoff:
        to_delete.append(id)

if to_delete:
    collection.delete(ids=to_delete)
    print(len(to_delete))
" 2>/dev/null || echo "0")

    if [[ $count -gt 0 ]]; then
        log "Cleaned $count old vector entries"
    fi
}

main() {
    log "Starting Redis cleanup..."

    cleanup_stale_agent_heartbeats
    cleanup_orphaned_task_claims
    cleanup_expired_verification_prefetch
    cleanup_old_metrics
    cleanup_old_alerts
    cleanup_old_vectors

    log "Redis cleanup complete"
}

main "$@"
