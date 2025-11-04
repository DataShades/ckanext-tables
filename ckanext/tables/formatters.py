from __future__ import annotations

import abc
import datetime
import uuid

from ckan import model
from ckan.plugins import toolkit as tk

from ckanext.tables import table, types


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


class UserLinkFormatter(BaseFormatter):
    """Generates a link to a user's profile with a placeholder avatar.

    This is a custom, performant implementation that avoids expensive
    `user_show` calls for every row by using a placeholder.
    The `value` for this formatter should be a user ID.

    Options:
        - `maxlength` (int): Maximum length of the user's display name. Defaults to 20.
        - `avatar` (int): The size of the avatar placeholder in pixels. Defaults to 20.
    """

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        if not value:
            return ""
        user = model.User.get(value)
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

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        template = options.get("template", "tables/formatters/actions.html")
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
        return tk.literal(f"<strong>{value}</strong>")


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
