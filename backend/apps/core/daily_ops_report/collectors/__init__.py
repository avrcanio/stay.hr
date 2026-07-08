"""Registered daily ops report collectors."""

from __future__ import annotations

from apps.core.daily_ops_report.collectors.celery_workers import CeleryWorkersCollector
from apps.core.daily_ops_report.collectors.db import DbCollector
from apps.core.daily_ops_report.collectors.disk import DiskCollector
from apps.core.daily_ops_report.collectors.docker_signals import DockerSignalsCollector
from apps.core.daily_ops_report.collectors.gunicorn import GunicornCollector
from apps.core.daily_ops_report.collectors.overbooking import OverbookingCollector

COLLECTORS = [
    GunicornCollector(),
    DbCollector(),
    DiskCollector(),
    CeleryWorkersCollector(),
    OverbookingCollector(),
    DockerSignalsCollector(),
]
