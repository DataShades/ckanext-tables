from __future__ import annotations

from ckan import model
from ckan.plugins import toolkit as tk

from ckanext.tables import types


def get_formatters() -> dict[str, types.Formatter]:
    return {
        "date": date,
        "user_link": user_link,
        "bool": bool,
        "list": list,
        "none_as_empty": none_as_empty,
        "trim_string": trim_string,
        "actions": actions,
        "json_display": json_display,
    }


def date(
    value: types.Value,
    options: types.Options,
    column: types.ColumnDefinition,
    row: types.Row,
    table: types.TableDefinition,
) -> types.FormatterResult:
    """Format a datetime string."""
    date_format: str = options.get("date_format", "%d/%m/%Y - %H:%M")

    return tk.h.render_datetime(value, date_format=date_format)


def user_link(
    value: types.Value,
    options: types.Options,
    column: types.ColumnDefinition,
    row: types.Row,
    table: types.TableDefinition,
) -> types.FormatterResult:
    """Generate a link to the user profile page with an avatar.

    It's a custom implementation of the linked_user
    function, where we replace an actual user avatar with a placeholder.

    Fetching an avatar requires an additional user_show call, and it's too
    expensive to do it for every user in the list. So we use a placeholder

    Args:
        value: user ID
        options: options for the renderer
        column: column definition
        row: row data
        table: table definition

    Options:
        - `maxlength` (int) - maximum length of the user name. **Default** is `20`
        - `avatar` (int) - size of the avatar. **Default** is `20`

    Returns:
        User link with an avatar placeholder
    """
    if not value:
        return ""

    user = model.User.get(value)

    if not user:
        return value

    maxlength = options.get("maxlength") or 20
    avatar = options.get("maxlength") or 20

    display_name = user.display_name

    if maxlength and len(user.display_name) > maxlength:
        display_name = display_name[:maxlength] + "..."

    return tk.h.literal(
        "{icon} {link}".format(
            icon=tk.h.snippet(
                "user/snippets/placeholder.html", size=avatar, user_name=display_name
            ),
            link=tk.h.link_to(display_name, tk.h.url_for("user.read", id=user.name)),
        )
    )


def bool(
    value: types.Value,
    options: types.Options,
    column: types.ColumnDefinition,
    row: types.Row,
    table: types.TableDefinition,
) -> types.FormatterResult:
    """Render a boolean as 'Yes' or 'No'."""
    return "Yes" if value else "No"


def list(
    value: types.Value,
    options: types.Options,
    column: types.ColumnDefinition,
    row: types.Row,
    table: types.TableDefinition,
) -> types.FormatterResult:
    """Render a list as a comma-separated string."""
    return ", ".join(value)


def none_as_empty(
    value: types.Value,
    options: types.Options,
    column: types.ColumnDefinition,
    row: types.Row,
    table: types.TableDefinition,
) -> types.FormatterResult:
    """Render `None` as an empty string."""
    return value if value is not None else ""


def trim_string(
    value: types.Value,
    options: types.Options,
    column: types.ColumnDefinition,
    row: types.Row,
    table: types.TableDefinition,
) -> types.FormatterResult:
    """Trim string to a certain length.

    Options:
        - `max_length` (int) - maximum length of the string. **Default** is `79`
        - `add_ellipsis` (bool) - add ellipsis to the end of the string.
                **Default** is `True`
    """
    if not value:
        return ""

    max_length: int = options.get("max_length", 79)
    trimmed_value: str = value[:max_length]

    if tk.asbool(options.get("add_ellipsis", True)):
        trimmed_value += "..."

    return trimmed_value


def actions(
    value: types.Value,
    options: types.Options,
    column: types.ColumnDefinition,
    row: types.Row,
    table: types.TableDefinition,
) -> types.FormatterResult:
    """Render actions for the table row.

    Options:
        - `template` (str) - template to render the actions.
    """
    template = options.get("template", "tables/formatters/actions.html")

    return tk.literal(
        tk.render(
            template,
            extra_vars={"table": table, "column": column, "row": row},
        )
    )


def json_display(
    value: types.Value,
    options: types.Options,
    column: types.ColumnDefinition,
    row: types.Row,
    table: types.TableDefinition,
) -> types.FormatterResult:
    """Render a JSON object as a string."""
    return tk.literal(
        tk.render(
            "ap_cron/formatters/json.html",
            extra_vars={"value": value},
        )
    )
