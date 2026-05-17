#!/usr/bin/env bash
set -e

cd /home/r1/acoustic/src/acoustic_comm

WAV="generated_wavs/fast_release_spear.wav"
LOG_FILE="/home/r1/acoustic/log/release_spear.log"

log() {
    local msg="$1"
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$ts] $msg" | tee -a "$LOG_FILE"
}

if [ ! -f "$WAV" ]; then
    log "[release_spear] ERROR: wav not found: $WAV"
    exit 1
fi

log "[release_spear] playing $WAV"
aplay "$WAV"
log "[release_spear] done"
