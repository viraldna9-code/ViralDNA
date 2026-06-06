# CRON_REGISTRY.md — Source of Truth for All Cron Jobs

This file is the authoritative list of ALL expected Hermes cron jobs.
After ANY Hermes update/migration, diff this list against `hermes cron list`
and restore any missing jobs immediately.

## Active Jobs (as of 2026-06-06)

| Job Name | ID | Schedule | Status | Purpose |
|---|---|---|---|---|
| VDNA Morning Publish | ab423cd38769 | 30 1 * * * (9AM IST) | PAUSED (manual) | Runs morning publish pipeline |
| VDNA Evening Publish | 47ccc5ce2210 | 30 11 * * * (7PM IST) | PAUSED (manual) | Runs evening publish pipeline |
| Channel Health Monitor | efd6e4eb155b | every 2h | ACTIVE | channel_health.py + Telegram alert on issues |
| Daily Analytics Report | 13c9202a18e4 | 30 0 * * * (6AM IST) | ACTIVE | scripts/daily_report.py → Telegram |
| Weekly Analytics Report | 5ab128cdde49 | 30 0 * * 0 (Sun 6AM) | ACTIVE | scripts/daily_report.py --mode weekly → Telegram |

## Job Details

### Channel Health Monitor
- Script: `/home/jay/ViralDNA/channel_health.py`
- Delivery: `telegram:8659664950`
- Alert: Only on actionable change (no routine "all clear")
- Active window: 6AM-11PM IST (script handles this internally)

### Daily Analytics Report
- Script: `/home/jay/ViralDNA/scripts/daily_report.py`
- Delivery: `telegram:8659664950`
- Schedule: `30 0 * * *` = 6AM IST

### Weekly Analytics Report
- Script: `/home/jay/ViralDNA/scripts/daily_report.py --mode weekly`
- Delivery: `telegram:8659664950`
- Schedule: `30 0 * * 0` = Sunday 6AM IST

## Maintenance Rules

1. **After every Hermes update**: Run `hermes cron list` and compare against this file
2. **Never delete registry**: Even paused jobs should remain listed
3. **Document changes**: Any job added/removed/changed = update this file
4. **Job IDs change on recreation**: Update this file with new IDs if jobs are recreated
