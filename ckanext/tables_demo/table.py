import ckanext.tables.shared as t
from ckanext.tables_demo.utils import generate_mock_data

DATA = generate_mock_data(1000)


class PeopleTable(t.TableDefinition):
    """Demo table definition for the people table."""

    def __init__(self):
        super().__init__(
            name="people",
            data_source=t.ListDataSource(data=DATA),
            columns=[
                t.ColumnDefinition(field="id", width=70),
                t.ColumnDefinition(field="name"),
                t.ColumnDefinition(field="surname", title="Last Name"),
                t.ColumnDefinition(field="email"),
                t.ColumnDefinition(
                    field="created",
                    formatters=[(t.formatters.DateFormatter, {"date_format": "%d %B %Y"})],
                ),
            ],
            row_actions=[
                t.RowActionDefinition(
                    action="remove_user",
                    label="Remove User",
                    icon="fa fa-trash",
                    callback=self.remove_user,
                    with_confirmation=True,
                ),
            ],
            bulk_actions=[
                t.BulkActionDefinition(
                    action="remove_user",
                    label="Remove Selected Users",
                    icon="fa fa-trash",
                    callback=self.remove_users,
                ),
            ],
            table_actions=[
                t.TableActionDefinition(
                    action="remove_all_users",
                    label="Remove All Users",
                    icon="fa fa-trash",
                    callback=self.remove_all_users,
                ),
                t.TableActionDefinition(
                    action="recreate_users",
                    label="Recreate Users",
                    icon="fa fa-refresh",
                    callback=self.recreate_users,
                ),
            ],
            exporters=t.ALL_EXPORTERS,
        )

    def remove_user(self, row: t.Row) -> t.ActionHandlerResult:
        """Callback to remove a user from the data source."""
        DATA[:] = [r for r in DATA if r["id"] != row["id"]]
        return t.ActionHandlerResult(success=True, message="User removed.")

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
        DATA[:] = generate_mock_data(1000)
        return t.ActionHandlerResult(success=True, message="Users recreated.")
