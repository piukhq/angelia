import falcon


def _force_str(s, encoding='utf-8', errors='strict'):
    if issubclass(type(s), str):
        return s

    if isinstance(s, bytes):
        s = str(s, encoding, errors)
    else:
        s = str(s)

    return s


def _get_error_details(data):
    if isinstance(data, list):
        ret = [_get_error_details(item) for item in data]
        return ret
    elif isinstance(data, dict):
        ret = {
            key: _get_error_details(value)
            for key, value in data.items()
        }
        return ret

    return _force_str(data)


class AuthenticationError(falcon.HTTPUnauthorized):
    pass


class ValidationError(falcon.HTTPBadRequest):

    def __init__(self, description=None, headers=None, **kwargs):
        super().__init__(
            title="Validation Error",
            description=description,
            headers=headers,
            **kwargs
        )

    def to_dict(self, obj_type=dict):
        """
        Override to_dict so a ValidationError raised with non-hashable objects for the description
        (E.g voluptuous.MultipleInvalid) is handled and converted to strings.
        """
        obj = obj_type()

        obj['title'] = self.title

        if self.description is not None:
            obj['description'] = _get_error_details(self.description)

        if self.code is not None:
            obj['code'] = self.code

        if self.link is not None:
            obj['link'] = self.link

        return obj
