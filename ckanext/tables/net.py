"""Guarded HTTP(S) fetch helpers.

A resource's ``url`` and a resource view's ``file_url`` override are set by
dataset editors, not sysadmins, yet they are fetched by the CKAN server
process (see :mod:`ckanext.tables.data_sources`). Handing such a URL
straight to ``requests``/``pandas``/``fsspec`` without guards lets an editor
make the server:

* reach internal-only services and cloud metadata endpoints — SSRF, e.g.
  ``http://169.254.169.254/latest/meta-data/...`` or ``http://localhost:6379``;
* hang a worker indefinitely (no timeout);
* exhaust memory/disk on an unbounded or hostile response body.

:func:`fetch_remote_file` guards against all three: it resolves the hostname
and rejects private/loopback/link-local/reserved/multicast addresses
*before* connecting, applies connect/read timeouts, follows a bounded number
of redirects (re-validating the target on every hop), and enforces a maximum
response size while streaming the body to a temporary file.

Note:
    Hostname resolution happens immediately before each connection, not at
    connection time, so this does not fully defend against DNS rebinding
    (a DNS record that resolves to a public address during the check and to
    a private one moments later). Closing that gap requires pinning the
    connection to the address that was validated, which is out of scope
    here — the guards above stop the straightforward attack of pointing a
    resource/view URL directly at an internal or metadata address.
"""

from __future__ import annotations

import contextlib
import ipaddress
import logging
import os
import socket
import tempfile
from collections.abc import Iterator
from urllib.parse import urljoin, urlparse

import requests

from ckanext.tables.config import get_fetch_connect_timeout, get_fetch_max_bytes, get_fetch_read_timeout

log = logging.getLogger(__name__)

_ALLOWED_SCHEMES = ("http", "https")
_MAX_REDIRECTS = 5
_CHUNK_SIZE = 64 * 1024


class RemoteFetchError(OSError):
    """A remote URL could not be fetched safely.

    Subclasses :class:`OSError` so it is caught by the same ``except
    (OSError, ...)`` clauses the data sources already use for I/O failures.
    """


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def _validate_url(url: str) -> None:
    """Raise :class:`RemoteFetchError` unless *url* is safe to fetch.

    Requires an http(s) scheme with a hostname, and rejects the request if
    *any* address the hostname resolves to is private, loopback, link-local,
    reserved, multicast, or unspecified.
    """
    parsed = urlparse(url)

    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        raise RemoteFetchError(f"Unsupported or unsafe URL: {url!r}. Only http(s) URLs are allowed.")

    try:
        addrinfo = socket.getaddrinfo(parsed.hostname, None)
    except OSError as e:
        raise RemoteFetchError(f"Could not resolve host {parsed.hostname!r}: {e}") from e

    for *_, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])

        if _is_disallowed_ip(ip):
            raise RemoteFetchError(
                f"Refusing to fetch {url!r}: host {parsed.hostname!r} resolves to a non-public address ({ip})"
            )


@contextlib.contextmanager
def fetch_remote_file(url: str) -> Iterator[str]:
    """Download *url* to a local temporary file and yield its path.

    The file is removed when the context exits. Raises
    :class:`RemoteFetchError` if the URL (or any redirect target) is unsafe,
    unreachable within the configured timeouts, or the response exceeds the
    configured size limit.
    """
    connect_timeout = get_fetch_connect_timeout()
    read_timeout = get_fetch_read_timeout()
    max_bytes = get_fetch_max_bytes()

    current_url = url
    response: requests.Response | None = None

    try:
        for _ in range(_MAX_REDIRECTS + 1):
            _validate_url(current_url)

            response = requests.get(
                current_url,
                stream=True,
                timeout=(connect_timeout, read_timeout),
                allow_redirects=False,
            )

            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                response.close()

                if not location:
                    raise RemoteFetchError(f"Redirect from {current_url!r} had no Location header")

                current_url = urljoin(current_url, location)
                continue

            break
        else:
            raise RemoteFetchError(f"Too many redirects while fetching {url!r}")

        response.raise_for_status()

        content_length = response.headers.get("Content-Length")
        if content_length is not None and int(content_length) > max_bytes:
            raise RemoteFetchError(
                f"Refusing to fetch {url!r}: response is {content_length} bytes, limit is {max_bytes}"
            )

        fd, tmp_path = tempfile.mkstemp(prefix="ckanext-tables-")

        try:
            downloaded = 0

            with os.fdopen(fd, "wb") as tmp_file:
                for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
                    downloaded += len(chunk)

                    if downloaded > max_bytes:
                        raise RemoteFetchError(
                            f"Refusing to fetch {url!r}: response exceeded the {max_bytes}-byte limit"
                        )

                    tmp_file.write(chunk)

            yield tmp_path
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.remove(tmp_path)
    finally:
        if response is not None:
            response.close()
