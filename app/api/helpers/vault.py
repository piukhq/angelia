import json
from enum import Enum

import falcon
import requests
from shared_config_storage.vault.secrets import VaultError, read_vault

import settings
from app.report import api_logger

loaded = False
_local_vault_store = {}


class AESKeyNames(str, Enum):
    AES_KEY = "AES_KEY"
    LOCAL_AES_KEY = "LOCAL_AES_KEY"


def get_aes_key(key_type: str):
    try:
        return _local_vault_store["aes_keys"][key_type]
    except KeyError as e:
        err_msg = f"{e} not found in aes_keys: ({_local_vault_store['aes_keys']})."
        api_logger.exception(err_msg)
        raise VaultError(err_msg)


def get_access_token_secret(key):
    """
    Tries to find key in dict obtained from vault. If not will reload the keys from the vault
    in case they have been rotated.
    :param key: key from token used to look up key
    :return: key value (the secret) or False
    """
    if key == "current_key":
        # make sure for security we can't use the key value stored in current_key
        # which can be hacked from the token
        raise falcon.HTTPUnauthorized(title="illegal KID", code="INVALID_TOKEN")

    try:
        return _local_vault_store["access_token_secrets"][key]
    except KeyError:
        load_secrets("access_token_secrets", allow_reload=True)
        try:
            return _local_vault_store["access_token_secrets"][key]
        except KeyError:
            return False


def load_secrets(load, allow_reload=False):
    """
    Retrieves security credential values from channel and secret_keys storage vaults and stores them
    in  which are used as a cache.
    Secrets contained in _local_vault_store using the  "all_secrets" key map which maps the config
    path to an internal ref keys eg "aes_keys"

    The reference key is also used fro mapping in the local secrets file

    Example:

    "aes_keys": {
        "LOCAL_AES_KEY": "local aes key",
        "AES_KEY": "aes key"
    },
    "access_token_secrets": {
        "current_key": "access-secret-2",
        "access-secret-1": "my_secret_1",
        "access-secret-2": "my_secret_2",
        "access-secret-3": "my_secret_3"
    }


    """
    global loaded
    global _local_vault_store

    to_load = {}
    all_secrets = {"aes_keys": "AES_KEYS_VAULT_PATH", "access_token_secrets": "API2_ACCESS_SECRETS_PATH"}
    if load == "all":
        to_load = all_secrets
    else:
        try:
            to_load[load] = all_secrets[load]
        except KeyError as e:
            err_msg = f"Cannot find secret to reload - Vault Exception {e}"
            api_logger.exception(err_msg)
            raise VaultError(err_msg) from e

    config = settings.VAULT_CONFIG
    if loaded and not allow_reload:
        api_logger.info("Tried to load the vault secrets more than once, ignoring the request.")

    elif config.get("LOCAL_SECRETS"):
        api_logger.info(f"JWT bundle secrets - from local file {config['LOCAL_SECRETS_PATH']}")
        with open(config["LOCAL_SECRETS_PATH"]) as fp:
            loaded_secrets = json.load(fp)

        for secret_store, path in to_load.items():
            _local_vault_store[secret_store] = loaded_secrets[secret_store]
        loaded = True

    else:
        for secret_store, path in to_load.items():
            try:
                api_logger.info(f"Loading {secret_store} from vault at {config['VAULT_URL']}")
                _local_vault_store["secret_store"] = read_vault(path, config["VAULT_URL"], config["VAULT_TOKEN"])
            except requests.RequestException as e:
                err_msg = f"{secret_store} error:  {path} - Vault Exception {e}"
                api_logger.exception(err_msg)
                raise VaultError(err_msg) from e

        loaded = True
