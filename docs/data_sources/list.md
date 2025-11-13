# ListDataSource

The `ListDataSource` works with Python lists of dictionaries. It is useful for small datasets, testing, demos, or when working with preloaded data.

## Basic Usage

```python
from ckanext.tables.shared import ListDataSource

# Sample data
users_data = [
    {"id": 1, "name": "alice", "email": "alice@example.com", "age": 30},
    {"id": 2, "name": "bob", "email": "bob@example.com", "age": 25},
    {"id": 3, "name": "charlie", "email": "charlie@example.com", "age": 35},
]

data_source = ListDataSource(users_data)
```

## Definition

::: tables.data_sources.ListDataSource
    options:
      show_source: true
      show_bases: false

## Best Practices

  - Suitable for small amout of data
  - Consider caching expensive data preparation
