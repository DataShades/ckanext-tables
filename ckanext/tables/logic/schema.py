from __future__ import annotations

from ckan import types
from ckan.logic.schema import validator_args


@validator_args
def get_preview_schema(
    ignore_empty: types.Validator,
    unicode_safe: types.Validator,
    url_validator: types.Validator,
) -> types.Schema:
    return {
        "file_url": [ignore_empty, unicode_safe, url_validator],
    }
