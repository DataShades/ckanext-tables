from __future__ import annotations

from typing import Any

import ckan.plugins.toolkit as tk
from ckan import types


@tk.auth_allow_anonymous_access
def tables_check_table_access(context: types.Context, data_dict: dict[str, Any]):
    table_class = tk.h.tables_get_table(data_dict["table_name"])

    try:
        table_class.check_access(context)
    except tk.NotAuthorized:
        return {"success": False}

    return {"success": True}
