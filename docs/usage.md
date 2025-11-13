# Basic usage

Here you can find complete usage instructions for the Tables extension. The process is fairly simple and involves only several steps:

1. Defining a table
2. Creating a view to display the table

We're going to use a **demo** table definition called `PeopleTable` for demonstration purposes.

It's a working example located in a separate extension and can be enabled alongside the tables extension. Just add `tables_demo` to your `ckan.plugins` configuration.

The demo table uses all the features of the tables extension, including data sources, formatters, all action types, and exporters. A minimal example could be much simpler, but this one demonstrates the full power of the extension.

## Defining a Table

First, create a table definition by inheriting from `TableDefinition`.

We will use the `ListDataSource` with a mock data for demonstration purposes, but in a real-world scenario, you might want to use `DatabaseDataSource` or create a custom data source. Read more about data sources [here](data_sources/index.md).

In general, `ListDataSource` is suitable for small datasets or testing, while `DatabaseDataSource` is recommended for production use with larger datasets.

If you're interested in how we're generating the mock data, check out the `generate_mock_data` function below:

::: tables_demo.utils.generate_mock_data
    options:
      show_source: true

---

Below is the full code of the `PeopleTable` definition:

```python
--8<-- "ckanext/tables_demo/table.py"
```

### Using Formatters

The tables extension provides several built-in formatters to change the way data is rendered in the table cells. You can apply one or more formatters to a column by specifying them in the `formatters` attribute of `ColumnDefinition`.

For example, from the above `PeopleTable`, we are using the `datetime` formatter to format the `created` field. So this `2024-02-25T11:10:00Z` value will be displayed as `2024-02-25`.

```py
ColumnDefinition(
    field="created",
    formatters=[(formatters.DateFormatter, {"date_format": "%Y-%m-%d"})],
    sortable=True
),
```

### Using Exporters

The tables extension also provides several built-in exporters to export the table data in different formats. You can specify the exporters to be used in the `exporters` attribute of the `TableDefinition`.

In the above `PeopleTable`, we are using all the available exporters by specifying `t.ALL_EXPORTERS`. You can also specify individual exporters if you want to limit the available export options.

```py
exporters=[
    t.exporters.CSVExporter,
    t.exporters.TSVExporter,
],
```

Obviously, you can write your own custom exporters as well. See the [exporters](exporters/index.md) documentation for more information.

### Using Actions

The tables extension allows you to define actions that can be performed on individual rows or on multiple selected rows. You can define these actions in the `row_actions`, `table_actions` and `bulk_actions` attributes of the `TableDefinition`.

Basically, it's just a matter of defining the action and providing a **callback function** that will be called when the action is **triggered**.

Read more about actions in the [actions](entities/actions.md) documentation.

## Creating a View

Once your table is defined, you can create a view to display it using the `GenericTableView`:

```python
--8<-- "ckanext/tables_demo/views.py"
```

As you can see, this view does not require any custom code to render the table. The `GenericTableView` takes care of everything.

## Results

After completing the above steps, you can navigate to `/admin/people` in your CKAN instance to see the rendered table.

!["Rendered Table Example"](image/usage_result.png)

## Next Steps

- Learn about [Data Sources](data_sources/index.md) for different data backends
- Explore [Built-In](formatters/built-in.md) and [Custom Formatters](formatters/custom.md) to enhance table presentation.
- Explore [Actions](entities/actions.md) to add interactivity to your tables.
- Explore [Exporters](exporters/index.md) to provide data export functionality.
