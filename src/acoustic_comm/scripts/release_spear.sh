#!/usr/bin/env bash
set -e

# ============================================================
# Sound mapping: control frame ID → wav filename
# Add new entries here to support more sounds.
# ============================================================
declare -A SOUND_MAP=(
    [0x01]="fast_release_spear.wav"
    [0x02]="place.wav"
    [0x03]="r2_climb_r1.wav"
    [0x04]="grid_1_4.wav"
    [0x05]="grid_2_5.wav"
    [0x06]="grid_3_6.wav"
    [0x07]="fast_enter_merlin.wav"
)

# ============================================================

WAV_DIR="/home/r1/acoustic/src/acoustic_comm/generated_wavs"
LOG_FILE="/home/r1/acoustic/log/release_spear.log"

log() {
    local msg="$1"
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[$ts] $msg" | tee -a "$LOG_FILE"
}

usage() {
    echo "Usage: $0 <frame_id>"
    echo "  frame_id: control frame identifier"
    echo ""
    echo "Available frame IDs:"
    for id in "${!SOUND_MAP[@]}"; do
        printf "  %-8s → %s\n" "$id" "${SOUND_MAP[$id]}"
    done
    exit 1
}

# --- argument check ---
FRAME_ID="${1:-}"
if [ -z "$FRAME_ID" ]; then
    usage
fi

# --- lookup ---
WAV="${SOUND_MAP[$FRAME_ID]}"
if [ -z "$WAV" ]; then
    log "[release_spear] ERROR: unknown frame ID: $FRAME_ID"
    usage
fi

WAV_PATH="$WAV_DIR/$WAV"
if [ ! -f "$WAV_PATH" ]; then
    log "[release_spear] ERROR: wav not found: $WAV_PATH"
    exit 1
fi

log "[release_spear] frame=$FRAME_ID → $WAV"
aplay "$WAV_PATH"
log "[release_spear] done"
