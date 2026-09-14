from __future__ import annotations

import os
import time

import click

from ckanext.tables.cache import get_cache_backend
from ckanext.tables.config import get_export_dir, get_export_job_ttl

__all__ = ["tables"]


@click.group()
def tables():
    """ckanext-tables CLI commands."""


@tables.command("clean-cache")
def clean_cache():
    """Delete expired cache entries left on disk by the configured cache backend.

    An entry whose TTL has passed but that is never read again would
    otherwise keep its file on disk indefinitely. Row-count/generation
    entries in Redis aren't affected by this command — they already expire
    and remove themselves via their own TTL. Safe to run periodically from
    a cron job.
    """
    removed = get_cache_backend().clean_expired()

    if removed:
        click.secho(f"Removed {removed} expired cache file(s).", fg="green")
    else:
        click.echo("No expired cache entries found.")


@tables.command("clean-exports")
def clean_exports():
    """Delete background-export files older than ckanext.tables.export.job_ttl.

    A background export (HTML/PDF/XLSX) writes its finished file to disk once,
    for the download endpoint to serve — nothing else ever deletes it on its
    own, so a job nobody downloads (or already did) would otherwise keep its
    file on disk indefinitely. Safe to run periodically from a cron job, the
    same way as clean-cache.
    """
    export_dir = get_export_dir()

    if not export_dir:
        click.echo("No export directory is configured or usable — nothing to clean.")
        return

    cutoff = time.time() - get_export_job_ttl()
    removed = 0

    for entry in os.scandir(export_dir):
        if not entry.is_file():
            continue

        try:
            if entry.stat().st_mtime < cutoff:
                os.remove(entry.path)
                removed += 1
        except OSError:
            continue

    if removed:
        click.secho(f"Removed {removed} expired export file(s).", fg="green")
    else:
        click.echo("No expired export files found.")
