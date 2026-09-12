from __future__ import annotations

# pyright: reportImportCycles=false
# table.py imports `formatters` for real; the TYPE_CHECKING-only import below
# is what pyright flags as a "cycle" — it walks TYPE_CHECKING blocks too, even
# though this never creates a real circular import at runtime.
import abc
import datetime
import uuid
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from ckan import model
from ckan.plugins import toolkit as tk

from ckanext.tables import types

if TYPE_CHECKING:
    from ckanext.tables import table


class BaseFormatter(abc.ABC):
    """Abstract base class for all formatters."""

    def __init__(
        self,
        column: table.ColumnDefinition,
        row: types.Row,
        initial_row: types.Row,
        table: table.TableDefinition,
    ):
        self.column = column
        self.row = row
        self.initial_row = initial_row
        self.table = table

    @abc.abstractmethod
    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        raise NotImplementedError


class DateFormatter(BaseFormatter):
    """Formats a datetime object into a more readable date.

    Options:
        - `date_format` (str): The strftime format for the output.
          Defaults to "%d/%m/%Y - %H:%M".
    """

    def format(self, value: datetime.datetime, options: types.Options) -> types.FormatterResult:
        date_format = options.get("date_format", "%d/%m/%Y - %H:%M")
        return tk.h.render_datetime(value, date_format=date_format)


class URLFormatter(BaseFormatter):
    """Generates a clickable link for a URL.

    Options:
        - `target` (str): The target attribute for the link. Defaults to "_blank".

    Only ``http``/``https`` values are turned into a link. Anything else
    (e.g. a ``javascript:`` URI, or a value with no scheme at all) is
    rendered as plain, escaped text instead — cell values can come from
    untrusted data, and letting an arbitrary scheme or unescaped markup
    through here would let one row inject a link or script for everyone
    who views the table.
    """

    _ALLOWED_SCHEMES = ("http", "https")

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        if not value:
            return ""

        url = str(value)

        if urlparse(url).scheme not in self._ALLOWED_SCHEMES:
            return tk.literal("{}").format(url)

        target = options.get("target", "_blank")

        return tk.literal('<a href="{}" target="{}">{}</a>').format(url, target, url)


class UserLinkFormatter(BaseFormatter):
    """Generates a link to a user's profile with a placeholder avatar.

    This is a custom, performant implementation that avoids expensive
    `user_show` calls for every row by using a placeholder.
    The `value` for this formatter should be a user ID.

    Each distinct user id is looked up at most once per table render — the
    lookup is memoised on the table instance — rather than re-querying a user
    id that recurs across many rows on the same page (e.g. a "created by"
    column where a handful of users own most of the rows).

    Options:
        - `maxlength` (int): Maximum length of the user's display name. Defaults to 20.
        - `avatar` (int): The size of the avatar placeholder in pixels. Defaults to 20.
    """

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        if not value:
            return ""
        user = self._get_user(value)
        if not user:
            return str(value)

        maxlength = options.get("maxlength", 20)
        avatar_size = options.get("avatar", 20)

        display_name = user.display_name
        if len(display_name) > maxlength:
            display_name = f"{display_name[:maxlength]}..."

        icon = tk.h.snippet("user/snippets/placeholder.html", size=avatar_size, user_name=display_name)
        link = tk.h.link_to(display_name, tk.h.url_for("user.read", id=user.name))
        return tk.h.literal(f"{icon} {link}")

    def _get_user(self, user_id: str) -> model.User | None:
        cache = self.table.get_formatter_cache("user_link_users")

        if user_id not in cache:
            cache[user_id] = model.User.get(user_id)

        return cache[user_id]


class BooleanFormatter(BaseFormatter):
    """Renders a boolean value as 'Yes' or 'No'."""

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        return "Yes" if value else "No"


class ListFormatter(BaseFormatter):
    """Renders a list as a comma-separated string."""

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        if not isinstance(value, list):
            return ""
        return ", ".join(map(str, value))


class NoneAsEmptyFormatter(BaseFormatter):
    """Renders a `None` value as an empty string."""

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        return value if value is not None else ""


class TrimStringFormatter(BaseFormatter):
    """Trims a string to a specified maximum length.

    Options:
        - `max_length` (int): The maximum length of the string. Defaults to 79.
        - `add_ellipsis` (bool): Whether to add "..." if the string is trimmed.
          Defaults to True.
    """

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        if not isinstance(value, str):
            return ""

        max_length = options.get("max_length", 79)
        add_ellipsis = tk.asbool(options.get("add_ellipsis", True))

        if len(value) > max_length:
            trimmed = value[:max_length]
            return f"{trimmed}..." if add_ellipsis else trimmed

        return value


class ActionsFormatter(BaseFormatter):
    """Renders a template snippet to display row-level actions.

    Options:
        - `template` (str): The path to the template to render.
          Defaults to `tables/formatters/actions.html`.
    """

    _DEFAULT_TEMPLATE = "tables/formatters/actions.html"

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        template = options.get("template", self._DEFAULT_TEMPLATE)

        if template != self._DEFAULT_TEMPLATE:
            # A custom template might legitimately render differently per row
            # (e.g. reference `row`), so it's never cached — only the bundled
            # default, which renders the same markup regardless of row, is.
            return self._render(template)

        cache = self.table.get_formatter_cache("actions_formatter")

        if self.column.field not in cache:
            cache[self.column.field] = self._render(template)

        return cache[self.column.field]

    def _render(self, template: str) -> types.FormatterResult:
        return tk.literal(
            tk.render(
                template,
                extra_vars={
                    "table": self.table,
                    "column": self.column,
                    "row": self.row,
                },
            )
        )


class JsonDisplayFormatter(BaseFormatter):
    """Renders a JSON object using a template snippet for display.

    Must be combined with `tabulator_formatter="html"` in the ColumnDefinition
    to ensure proper HTML rendering in the frontend.
    """

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        return tk.literal(tk.render("tables/formatters/json.html", extra_vars={"value": value}))


class TextBoldFormatter(BaseFormatter):
    """Renders text in bold."""

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        if not value:
            return ""
        return tk.literal("<strong>{}</strong>").format(value)


class DialogModalFormatter(BaseFormatter):
    """Renders a link that opens a dialog modal with detailed information.

    Options:
        - `template` (str): The path to the template to render inside the modal.
          Defaults to `tables/formatters/dialog_modal.html`.
        - `modal_title` (str): The title of the modal dialog.
          Defaults to "Details".
        - `max_length` (int): The maximum length of the preview text before
          truncation. Defaults to 100.
    """

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        if not value:
            return ""

        template = options.get("template", "tables/formatters/dialog_modal.html")
        max_length = options.get("max_length", 100)
        modal_title = options.get("modal_title", "Details")

        return tk.literal(
            tk.render(
                template,
                extra_vars={
                    "value": value,
                    "table": self.table,
                    "column": self.column,
                    "row": self.row,
                    "modal_title": modal_title,
                    "max_length": max_length,
                    "modal_id": f"modal-{uuid.uuid4().hex}",
                },
            )
        )
