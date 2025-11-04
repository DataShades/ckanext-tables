from typing import Any

import ckanext.tables.shared as tables


def generate_mock_data(num_records: int) -> list[dict[str, Any]]:
    """Generate mock data for the people table."""
    from faker import Faker

    fake = Faker()

    return [
        {
            "id": i,
            "name": fake.first_name(),
            "surname": fake.last_name(),
            "email": fake.email(),
            "created": fake.date_time_this_decade().isoformat(),
        }
        for i in range(1, num_records + 1)
    ]


data = generate_mock_data(1000)


class PeopleTable(tables.TableDefinition):
    """Demo table definition for the people table."""

    def __init__(self):
        super().__init__(
            name="people",
            data_source=tables.ListDataSource(data=data),
            columns=[
                tables.ColumnDefinition(field="id"),
                tables.ColumnDefinition(field="name"),
                tables.ColumnDefinition(field="surname", title="Last Name"),
                tables.ColumnDefinition(field="email"),
                tables.ColumnDefinition(
                    field="created",
                    formatters=[(tables.formatters.DateFormatter, {"date_format": "%d %B %Y"})],
                ),
            ],
            row_actions=[
                tables.RowActionDefinition(
                    action="remove_user",
                    label="Remove User",
                    icon="fa fa-trash",
                    callback=self.remove_user,
                    with_confirmation=True,
                ),
            ],
            bulk_actions=[
                tables.BulkActionDefinition(
                    action="remove_user",
                    label="Remove Selected Users",
                    icon="fa fa-trash",
                    callback=self.remove_user,
                ),
            ],
            table_actions=[
                tables.TableActionDefinition(
                    action="remove_all_users",
                    label="Remove All Users",
                    icon="fa fa-trash",
                    callback=self.remove_all_users,
                ),
                tables.TableActionDefinition(
                    action="recreate_users",
                    label="Recreate Users",
                    icon="fa fa-refresh",
                    callback=self.recreate_users,
                ),
            ],
            exporters=[
                tables.exporters.CSVExporter,
                tables.exporters.TSVExporter,
                tables.exporters.JSONExporter,
                tables.exporters.XLSXExporter,
                tables.exporters.HTMLExporter,
                tables.exporters.YAMLExporter,
                tables.exporters.NDJSONExporter,
            ],
        )

    def remove_user(self, row: tables.Row) -> tables.ActionHandlerResult:
        """Callback to remove a user from the data source."""
        global data  # noqa: PLW0603
        data = [r for r in data if r["id"] != row["id"]]
        return tables.ActionHandlerResult(success=True, message="User removed.")

    def remove_all_users(self) -> tables.ActionHandlerResult:
        """Callback to remove all users from the data source."""
        global data  # noqa: PLW0603
        data = []
        return tables.ActionHandlerResult(success=True, message="All users removed.")

    def recreate_users(self) -> tables.ActionHandlerResult:
        """Callback to recreate the mock users."""
        global data  # noqa: PLW0603
        data = generate_mock_data(1000)
        return tables.ActionHandlerResult(success=True, message="Users recreated.")
