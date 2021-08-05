from enum import Enum

import requests
from shared_config_storage.vault.secrets import VaultError, read_vault

from app.report import api_logger
from settings import AES_KEYS_VAULT_PATH, VAULT_TOKEN, VAULT_URL

loaded = False
_aes_keys = {}


class AESKeyNames(str, Enum):
    AES_KEY = "AES_KEY"
    LOCAL_AES_KEY = "LOCAL_AES_KEY"


def load_secrets():
    global loaded
    global _aes_keys

    if loaded:
        api_logger.info("Tried to load the vault secrets more than once, ignoring the request.")

    try:
        api_logger.info(f"Loading AES keys from vault at {VAULT_URL}")
        _aes_keys = read_vault(AES_KEYS_VAULT_PATH, VAULT_URL, VAULT_TOKEN)
    except requests.RequestException as e:
        err_msg = f"AES keys - Vault Exception {e}"
        api_logger.exception(err_msg)
        raise VaultError(err_msg) from e

    loaded = True


def get_aes_key(key_type: str):
    try:
        return _aes_keys[key_type]
    except KeyError as e:
        err_msg = f"{e} not found in _aes_keys: ({_aes_keys})."
        api_logger.exception(err_msg)
        raise VaultError(err_msg)
