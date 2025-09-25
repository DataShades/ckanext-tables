# DatabaseDataSource

The `DatabaseDataSource` uses SQLAlchemy statements to fetch data from the database. This is the most common data source for production use.

## Basic Usage

```python
from sqlalchemy import select

from ckan import model

from ckanext.tables.shared import DatabaseDataSource


data_source = DatabaseDataSource(
    stmt=select(
        model.User.id,
        model.User.email,
        model.User.name,
        model.User.state,
    ).order_by(model.User.created.desc()),
    model=model.User,
)
```

## Definition

::: tables.data_sources.DatabaseDataSource
    options:
      show_source: true
      show_bases: false


## Best Practices

  - Use selective queries
  - Add database indexes for commonly filtered/sorted columns

```python
# Good: Select only needed columns
stmt = select(model.User.id, model.User.name, model.User.email)

# Avoid: Selecting everything
stmt = select(model.User)
```
