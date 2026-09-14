# Generic Views

The [`ckanext.tables.generics`](https://github.com/DataShades/ckanext-tables/tree/master/ckanext/tables/generics.py) module provides a ready-to-use view class that can render tables without writing custom view code.

## GenericTableView

The `GenericTableView` is a Flask `MethodView` that automatically renders any registered table definition.

### Basic Usage

```python
--8 < --"ckanext/tables_demo/views.py"
```

### Constructor Parameters

- **`table`** (`type[TableDefinition]`, required): The table definition class to be rendered.
- **`breadcrumb_label`** (`str`, optional): Label shown in breadcrumbs. The template renders it
  as-is, so pass an already-translated string (e.g. the result of your own `tk._(...)` call).
  Defaults to a translated "Table".
- **`page_title`** (`str`, optional): Page title shown in the browser/header. Also rendered as-is
  — translate it yourself before passing it in. Defaults to empty string.

### Access Control

The `GenericTableView` delegates access control to the table definition's `check_access()` method. Make sure your table definitions implement proper authorization:

```python
class PeopleTable(TableDefinition):
    ...

    @classmethod
    def check_access(cls, context: Context) -> None:
        """Only allow sysadmins to view this table."""
        tk.check_access("sysadmin", context)
```

`GenericTableView` always calls `check_access()` with a bare `{}` — no `model`, `user`, or `session` pre-populated. Routing the check through `tk.check_access(...)`, as above, fills those in for you; reading the context directly (e.g. `context["user"]`) will not work.

### HTTP Response Contract

`GenericTableView` and the resource-view AJAX endpoint (`ResourceViewHandler`, used by the *Tables View* resource view) share the same GET/POST dispatch logic. The two request types follow different conventions:

**GET** — used for the full-page render, AJAX data fetches, and exports — uses real HTTP status codes for anything that stops the request before a table is rendered or data returned:

| Status | When |
| --- | --- |
| `200` | Full-page render; AJAX data (including a genuinely empty result set — that's a successful response, not a failure); a successful export stream. |
| `400` | Non-AJAX GET on an endpoint that only serves AJAX (the base `_render_full_page`; `GenericTableView` overrides this to render the full page instead). |
| `403` | `check_access()` (or, for a resource view, `resource_show`/`resource_view_show`) denies the request. |
| `404` | Unknown exporter name, or (resource views only) the resource/resource view doesn't exist or doesn't belong to this dataset. |
| `413` | Export would exceed `ckanext.tables.export.max_rows`. |
| `501` | A requested exporter's optional dependency isn't installed. |
| `502` | The data source itself failed (`DataSourceError`) — for AJAX data, or while resolving a resource view's table. |

**POST** — table/row/bulk actions and cache refresh — always returns `200` with a fixed JSON envelope, regardless of whether the action succeeded, doesn't exist, or raised:

```json
{"success": false, "error": "...", "message": null, "redirect": null}
```

This is deliberate: an action's outcome is a business result for the caller to branch on (see [`ActionHandlerResult`](entities/actions.md)), not a transport failure, so an unrecognised action name and a handler that raises look the same to the client as any other `success: false` — a JSON body it can always parse, rather than a bare non-2xx response it would have to special-case. `403` is still used for the resource-view refresh's own authorization check (`resource_update`), since that happens before an action is dispatched. The one exception to the always-200 rule is `ResourceViewHandler.post` failing to resolve the table at all (`DataSourceError`) — that still returns `502`, wrapped in the same `{"success": false, "error": ...}` shape, since no action ever got to run.
