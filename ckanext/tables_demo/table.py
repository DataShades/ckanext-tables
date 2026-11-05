from typing import Any

from sqlalchemy import select

from ckan import model

import ckanext.tables.shared as t
from ckanext.tables_demo.utils import (
    ARTICLE_STATUSES,
    ARTICLE_TAGS,
    generate_mock_articles,
    generate_mock_data,
    generate_mock_products,
)

DATA = generate_mock_data(10000)
PRODUCTS_DATA = generate_mock_products(10000)
ARTICLES_DATA = generate_mock_articles(250)


class PeopleTable(t.TableDefinition):
    """Demo table definition for the people table."""

    def __init__(self, ajax_url: str | None = None):
        super().__init__(
            name="people",
            data_source=t.ListDataSource(data=DATA),
            ajax_url=ajax_url,
            columns=[
                t.ColumnDefinition(field="id", title="ID", width=90),
                t.ColumnDefinition(field="name"),
                t.ColumnDefinition(field="surname", title="Last Name"),
                t.ColumnDefinition(field="email"),
                t.ColumnDefinition(field="sysadmin", formatters=[(t.formatters.BooleanFormatter, {})]),
                t.ColumnDefinition(
                    field="created",
                    formatters=[(t.formatters.DateFormatter, {"date_format": "%d %B %Y"})],
                ),
            ],
            row_actions=[
                t.RowActionDefinition(
                    action="make_sysadmin",
                    label="Promote to Sysadmin",
                    icon="fa fa-user-graduate",
                    callback=self.promote_to_sysadmin,
                    with_confirmation=True,
                ),
                t.RowActionDefinition(
                    action="remove_user",
                    label="Remove User",
                    icon="fa fa-trash",
                    attrs={"class": "text-danger"},
                    callback=self.remove_user,
                    with_confirmation=True,
                ),
            ],
            bulk_actions=[
                t.BulkActionDefinition(
                    action="remove_user",
                    label="Remove Selected Users",
                    icon="fa fa-trash",
                    attrs={"class": "text-danger"},
                    callback=self.remove_users,
                ),
            ],
            table_actions=[
                t.TableActionDefinition(
                    action="recreate_users",
                    label="Recreate Users",
                    icon="fa fa-refresh",
                    callback=self.recreate_users,
                ),
                t.TableActionDefinition(
                    action="remove_all_users",
                    label="Remove All Users",
                    icon="fa fa-trash",
                    attrs={"class": "text-danger"},
                    callback=self.remove_all_users,
                ),
            ],
            exporters=t.ALL_EXPORTERS,
        )

    def remove_user(self, row: t.Row) -> t.ActionHandlerResult:
        """Callback to remove a user from the data source."""
        DATA[:] = [r for r in DATA if r["id"] != row["id"]]
        return t.ActionHandlerResult(success=True, message="User removed.")

    def promote_to_sysadmin(self, row: t.Row) -> t.ActionHandlerResult:
        user_data = next((r for r in DATA if r["id"] == row["id"]), None)
        user_data["sysadmin"] = True  # type: ignore
        return t.ActionHandlerResult(success=True, message="User has been promoted.")

    def remove_users(self, rows: list[t.Row]) -> t.ActionHandlerResult:
        """Callback to remove a user from the data source."""
        ids_to_remove = {row["id"] for row in rows}
        DATA[:] = [r for r in DATA if r["id"] not in ids_to_remove]
        return t.ActionHandlerResult(success=True, message="Users removed.")

    def remove_all_users(self) -> t.ActionHandlerResult:
        """Callback to remove all users from the data source."""
        DATA.clear()
        return t.ActionHandlerResult(success=True, message="All users removed.")

    def recreate_users(self) -> t.ActionHandlerResult:
        """Callback to recreate the mock users."""
        DATA[:] = generate_mock_data(10000)
        return t.ActionHandlerResult(success=True, message="Users recreated.")


class ProductsTable(t.TableDefinition):
    """Demo table definition for the products table."""

    def __init__(self, ajax_url: str | None = None):
        super().__init__(
            name="products",
            data_source=t.ListDataSource(data=PRODUCTS_DATA),
            ajax_url=ajax_url,
            columns=[
                t.ColumnDefinition(field="id", title="ID", width=90),
                t.ColumnDefinition(field="name", title="Product"),
                t.ColumnDefinition(field="category"),
                t.ColumnDefinition(field="price"),
                t.ColumnDefinition(
                    field="in_stock",
                    title="In Stock",
                    formatters=[(t.formatters.BooleanFormatter, {})],
                ),
                t.ColumnDefinition(field="supplier"),
            ],
            table_actions=[
                t.TableActionDefinition(
                    action="recreate_products",
                    label="Recreate Products",
                    icon="fa fa-refresh",
                    callback=self.recreate_products,
                ),
            ],
            exporters=t.ALL_EXPORTERS,
        )

    def recreate_products(self) -> t.ActionHandlerResult:
        """Callback to recreate the mock products."""
        PRODUCTS_DATA[:] = generate_mock_products(10000)
        return t.ActionHandlerResult(success=True, message="Products recreated.")


class PackagesTable(t.TableDefinition):
    """Demo table definition backed by a real database query (CKAN's package table).

    Unlike ``PeopleTable``/``ProductsTable``, which use ``ListDataSource`` over
    in-memory mock data, this one uses ``DatabaseDataSource`` to demonstrate
    filtering/sorting/pagination pushed down to SQL against a real table.
    """

    def __init__(self, ajax_url: str | None = None):
        stmt = select(
            model.Package.name,
            model.Package.title,
            model.Package.type,
            model.Package.state,
            model.Package.private,
            model.Package.creator_user_id,
            model.Package.metadata_created,
            model.Package.metadata_modified,
        )

        super().__init__(
            name="packages",
            data_source=t.DatabaseDataSource(stmt),
            ajax_url=ajax_url,
            columns=[
                t.ColumnDefinition(field="name"),
                t.ColumnDefinition(field="title"),
                t.ColumnDefinition(field="type"),
                t.ColumnDefinition(field="state"),
                t.ColumnDefinition(field="private", formatters=[(t.formatters.BooleanFormatter, {})]),
                t.ColumnDefinition(
                    field="creator_user_id",
                    title="Creator",
                    formatters=[(t.formatters.UserLinkFormatter, {})],
                    tabulator_formatter="html",
                ),
                t.ColumnDefinition(
                    field="metadata_modified",
                    title="Last Modified",
                    formatters=[(t.formatters.DateFormatter, {"date_format": "%d %B %Y"})],
                ),
            ],
            exporters=t.ALL_EXPORTERS,
        )


class ArticlesTable(t.TableDefinition):
    """Demo table with a compact toolbar: a search, quick filters and an empty state.

    Shows the options for tables that don't need the full set of controls:

    - ``search_fields``: one search input over the title, author and tags.
    - ``quick_filters``: selects filtering one field each; ``tags`` is a list
      cell, matched when any of its items equals the chosen tag.
    - ``show_*``: the Filters, Columns, Refresh, Fullscreen and total count
      controls are hidden.
    - ``row_actions_display="inline"`` and ``row_actions_position="start"``: one
      icon button per action, in the first column. "Publish" is disabled for
      published articles.
    - ``empty_state_template``: shown instead of an empty table, with a clear
      search button. "Remove All Articles" shows its other part, for no data.
    - ``page_size_label`` and ``pagination_counter="range"``: "Articles per
      page" and "1 – 10 of 250".
    - ``width_grow``: the title takes three times the free width of a column.
    """

    def __init__(self, ajax_url: str | None = None):
        super().__init__(
            name="articles",
            data_source=t.ListDataSource(data=ARTICLES_DATA),
            ajax_url=ajax_url,
            columns=[
                t.ColumnDefinition(field="title", filterable=False, min_width=200, width_grow=3),
                t.ColumnDefinition(field="author", filterable=False),
                t.ColumnDefinition(field="status", filterable=False),
                t.ColumnDefinition(
                    field="tags",
                    filterable=False,
                    sortable=False,
                    formatters=[(t.formatters.ListFormatter, {})],
                ),
                t.ColumnDefinition(
                    field="pinned",
                    filterable=False,
                    formatters=[(t.formatters.BooleanFormatter, {})],
                ),
                t.ColumnDefinition(
                    field="updated",
                    filterable=False,
                    formatters=[(t.formatters.DateFormatter, {"date_format": "%b %d, %Y"})],
                ),
            ],
            row_actions=[
                t.RowActionDefinition(
                    action="toggle_pin",
                    label="Pin / Unpin",
                    icon="fa fa-thumbtack",
                    callback=self.toggle_pin,
                ),
                t.RowActionDefinition(
                    action="publish",
                    label="Publish",
                    icon="fa fa-paper-plane",
                    callback=self.publish,
                    disabled=lambda row: "Already published" if row["status"] == "published" else None,
                ),
                t.RowActionDefinition(
                    action="remove_article",
                    label="Remove",
                    icon="fa fa-trash",
                    attrs={"class": "text-danger", "data-confirm-message": "Remove this article?"},
                    callback=self.remove_article,
                    with_confirmation=True,
                ),
            ],
            row_actions_display="inline",
            row_actions_position="start",
            table_actions=[
                t.TableActionDefinition(
                    action="remove_all_articles",
                    label="Remove All Articles",
                    icon="fa fa-trash",
                    attrs={"class": "text-danger"},
                    callback=self.remove_all_articles,
                ),
                t.TableActionDefinition(
                    action="recreate_articles",
                    label="Recreate Articles",
                    icon="fa fa-refresh",
                    callback=self.recreate_articles,
                    with_confirmation=False,
                ),
            ],
            search_fields=["title", "author", "tags"],
            search_placeholder="Search title, author or tag",
            quick_filters=[
                t.QuickFilterDefinition(
                    field="status",
                    options=[(status, status.title()) for status in ARTICLE_STATUSES],
                    placeholder="All statuses",
                ),
                t.QuickFilterDefinition(
                    field="tags",
                    options=[(tag, tag.title()) for tag in ARTICLE_TAGS],
                    placeholder="All tags",
                ),
            ],
            empty_state_template="tables_demo/snippets/articles_empty.html",
            page_size_label="Articles per page",
            pagination_counter="range",
            show_filters=False,
            show_columns=False,
            show_refresh=False,
            show_fullscreen=False,
            show_total_count=False,
        )

    def _find(self, row: t.Row) -> dict[str, Any] | None:
        return next((r for r in ARTICLES_DATA if r["id"] == row["id"]), None)

    def toggle_pin(self, row: t.Row) -> t.ActionHandlerResult:
        article = self._find(row)
        if article is None:
            return t.ActionHandlerResult(success=False, error="Article not found.")

        article["pinned"] = not article["pinned"]
        return t.ActionHandlerResult(success=True, message="Article pinned." if article["pinned"] else "Article unpinned.")

    def publish(self, row: t.Row) -> t.ActionHandlerResult:
        article = self._find(row)
        if article is None:
            return t.ActionHandlerResult(success=False, error="Article not found.")

        article["status"] = "published"
        return t.ActionHandlerResult(success=True, message="Article published.")

    def remove_article(self, row: t.Row) -> t.ActionHandlerResult:
        ARTICLES_DATA[:] = [r for r in ARTICLES_DATA if r["id"] != row["id"]]
        return t.ActionHandlerResult(success=True, message="Article removed.")

    def remove_all_articles(self) -> t.ActionHandlerResult:
        ARTICLES_DATA.clear()
        return t.ActionHandlerResult(success=True, message="All articles removed.")

    def recreate_articles(self) -> t.ActionHandlerResult:
        ARTICLES_DATA[:] = generate_mock_articles(250)
        return t.ActionHandlerResult(success=True, message="Articles recreated.")
