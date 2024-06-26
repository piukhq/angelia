from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any

import falcon

if TYPE_CHECKING:
    from typing import TypeVar

    ResType = TypeVar("ResType")


def filter_field(default_fields: list) -> "Callable[..., Callable[..., ResType]]":
    def decorator(func: "Callable[..., ResType]") -> "Callable[..., ResType]":
        @wraps(func)
        def wrapper(obj: object, req: falcon.Request, *args: Any, **kwargs: Any) -> "ResType":
            filter_params_string = req.params.get("fields")
            if not filter_params_string:
                filter_params = default_fields
            else:
                provided_filter_params = [x.strip() for x in filter_params_string.split(",")]
                filter_params = list(set(default_fields).intersection(set(provided_filter_params)))

            return func(obj, req, *args, filter_params=filter_params, **kwargs)

        return wrapper

    return decorator


def hide_fields(obj: dict, fields: set) -> dict:
    for field in fields:
        key, *rest = field.split(".", maxsplit=1)
        try:
            if rest:
                many = isinstance(obj[key], list)
                if many:
                    [hide_fields(d, rest) for d in obj[key]]
                else:
                    hide_fields(obj[key], rest)
            else:
                obj[field] = "[REDACTED]"
        except KeyError:
            pass
        except TypeError:
            break
    return obj
