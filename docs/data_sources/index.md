# Data Sources

Data sources provide the underlying data for table definitions. They handle filtering, sorting, and pagination operations while abstracting away the specific data storage mechanism.

**Each table definition must specify a data source to fetch its data from.**

The list of available data sources includes:

  - [`DatabaseDataSource`](./database.md): Uses SQLAlchemy statements to fetch data from the database. This is the most common data source for production use.
  - [`ListDataSource`](./list.md): Uses an in-memory list of dictionaries. This is useful for small datasets or testing.
