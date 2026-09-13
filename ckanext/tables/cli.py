from __future__ import annotations

import click

from ckanext.tables.cache import get_cache_backend

__all__ = ["tables"]


@click.group()
def tables():
    """ckanext-tables CLI commands."""


@tables.command("clean-cache")
def clean_cache():
    """Delete expired cache entries left on disk by the configured cache backend.

    Only meaningful for the file-based backends (parquet/feather): an
    entry whose TTL has passed but that is never read again would otherwise
    keep its file on disk indefinitely. The Redis backend already expires and
    removes its own keys, so this is a no-op there. Safe to run periodically
    from a cron job.
    """
    removed = get_cache_backend().clean_expired()

    if removed:
        click.secho(f"Removed {removed} expired cache file(s).", fg="green")
    else:
        click.echo("No expired cache entries found.")
