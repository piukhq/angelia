from settings import AES_KEYS
# We will need to import these keys from Azure, not directly from settings, but we need Azure Vault set up correctly.


def get_aes_key(key_type: str):
    try:
        return AES_KEYS[key_type]
    except KeyError as e:
        err_msg = f"{e} not found in _aes_keys: ({AES_KEYS})."
        # log error
        # raise error
