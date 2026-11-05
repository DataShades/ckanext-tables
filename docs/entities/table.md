# Table Definition

The table definition holds the configuration for a table, including its columns, data source, and other options.

Below you can check the available attributes of the `TableDefinition` class and their descriptions. Also, a full code is provided at the end of this document for reference.

!!! warning
    Only one table can be rendered per page. The frontend controls (filters, columns, refresh, fullscreen, etc.) are wired up by global element id, so a second table on the same page would fight the first one over the same controls.

::: tables.table.TableDefinition
    options:
      show_source: true

## Toolbar

!!! tip
    The `ArticlesTable` of the demo plugin (`tables_demo`, at `/tables-demo/dashboard`) shows
    every option of this section, the empty state and the inline row actions together.

The toolbar above the table renders the Filters, Columns, Refresh, total count and Fullscreen
controls by default. Turn off the ones a table doesn't need with the `show_*` attributes, and
add a search input and quick filter selects for a simpler toolbar:

```python
import ckanext.tables.shared as t


class SubscriptionsTable(t.TableDefinition):
    def __init__(self, ajax_url: str | None = None):
        super().__init__(
            name="subscriptions",
            data_source=t.ListDataSource(data=get_rows()),
            ajax_url=ajax_url,
            columns=[...],
            # A row matches when any of the fields contains the query, case-insensitively
            search_fields=["title", "theme"],
            search_placeholder="Search dataset name or theme",
            # Each quick filter is a select filtering one field by the chosen value
            quick_filters=[
                t.QuickFilterDefinition(
                    field="theme",
                    options=[("economy", "Economy"), ("health", "Health")],
                    placeholder="All themes",
                ),
            ],
            show_filters=False,
            show_columns=False,
            show_refresh=False,
            show_fullscreen=False,
            show_total_count=False,
        )
```

The search query and the quick filter values are kept in the page URL, like the filters and the
page number. The search requires a data source implementing `search()`: `ListDataSource`,
`DatabaseDataSource` and the resource data sources do, `DataStoreDataSource` doesn't.

For many options, turn a quick filter into a searchable select with `attrs`, e.g.
`attrs={"data-module": "my-searchable-select"}`. The table reads the `change` event of the
`<select>`, which widgets like Tom Select fire on a choice. When the table sets the value itself
(restoring it from the URL, or clearing the filters), it fires a bubbling
`tables:quick-filter:sync` event on the `<select>` for the widget to show the new value.

With `ListDataSource`, a list cell (e.g. tags) matches the `=` and `like` filters when any of its
items does, and the `!=` filter when none of its items equals the value.

## Empty state

By default an empty table shows its `placeholder` inside the table. Set `empty_state_template`
to show a template instead of the whole table (the toolbar stays). The template decides what
to show for an empty search and for a table without data:

```html
<div class="my-empty-state">
    <div data-empty-state="filtered">
        <p>{{ _("Nothing matches your search.") }}</p>
        <button type="button" data-table-clear-filters>{{ _("Clear search") }}</button>
    </div>

    <div data-empty-state="empty">
        <p>{{ _("Nothing here yet.") }}</p>
    </div>
</div>
```

The `data-table-clear-filters` element clears the search, the quick filters, the Filters modal
filters and the column header filters.

## Pagination

`page_size_label` changes the label of the page size select, and `pagination_counter="range"`
shows the counter as "1 – 10 of 120" instead of "Showing 1-10 of 120 rows".

::: tables.table.QuickFilterDefinition
    options:
      show_root_heading: true
      show_source: true
