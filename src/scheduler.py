from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler


def run_daily(timezone: str, hour: int, minute: int, job):
    scheduler = BlockingScheduler(timezone=timezone)
    scheduler.add_job(job, "cron", hour=hour, minute=minute)
    scheduler.start()
