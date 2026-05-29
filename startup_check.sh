#!/bin/bash
# ViralDNA Startup Analytics Check
# Run on machine startup: sends today's daily report if after 6 AM IST 
# and not yet sent. Also catches up weekly report on Sundays.

cd /home/jay/ViralDNA 2>/dev/null || exit 0

IST_HOUR=$(TZ='Asia/Kolkata' date +%H)
IST_DAY=$(TZ='Asia/Kolkata' date +%u)  # 1=Mon, 7=Sun
IST_DATE=$(TZ='Asia/Kolkata' date +%Y-%m-%d)

LOG="/home/jay/ViralDNA/analytics/startup_check.log"
echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] Startup check: IST=${IST_HOUR}h day=${IST_DAY} date=${IST_DATE}" >> "$LOG"

# --- DAILY REPORT ---
# Check snapshot file for today's date
LAST_SNAPSHOT=""
if [ -f "/home/jay/ViralDNA/analytics/metrics_history.json" ]; then
    LAST_SNAPSHOT=$(python3 -c "
import json
with open('/home/jay/ViralDNA/analytics/metrics_history.json') as f:
    d = json.load(f)
snaps = d.get('snapshots', [])
if snaps:
    print(snaps[-1].get('date', ''))
" 2>/dev/null)
fi

if [ "$IST_HOUR" -ge 6 ] && [ "$LAST_SNAPSHOT" != "$IST_DATE" ]; then
    echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] Running daily report..." >> "$LOG"
    python3 /home/jay/ViralDNA/send_analytics_report.py --mode daily >> "$LOG" 2>&1
    echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] Daily report done." >> "$LOG"
fi

# --- WEEKLY REPORT (Sunday) ---
WEEK_MARKER=$(TZ='Asia/Kolkata' date +%Y-W%V)
WEEKLY_SENT_FILE="/home/jay/ViralDNA/analytics/weekly_last_sent.txt"
LAST_WEEKLY=""
[ -f "$WEEKLY_SENT_FILE" ] && LAST_WEEKLY=$(cat "$WEEKLY_SENT_FILE")

if [ "$IST_DAY" -eq 7 ] && [ "$IST_HOUR" -ge 6 ] && [ "$LAST_WEEKLY" != "$WEEK_MARKER" ]; then
    echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] Running weekly report..." >> "$LOG"
    python3 /home/jay/ViralDNA/send_analytics_report.py --mode weekly >> "$LOG" 2>&1
    echo "$WEEK_MARKER" > "$WEEKLY_SENT_FILE"
    echo "[$(date -u '+%Y-%m-%d %H:%M UTC')] Weekly report done." >> "$LOG"
fi

# Keep log small
tail -100 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
