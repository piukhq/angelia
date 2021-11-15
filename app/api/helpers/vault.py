import json
from copy import deepcopy
from enum import Enum
from typing import Optional

import falcon

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError

import settings
from app.report import api_logger

loaded = False
_local_vault_store = {}


class VaultError(Exception):
    """Exception raised for errors in the input."""

    def __init__(self, message: Optional[str] = None) -> None:
        self.message = message

    def __str__(self) -> str:
        return f"Vault Error: {self.message}"


class AESKeyNames(str, Enum):
    AES_KEY = "AES_KEY"
    LOCAL_AES_KEY = "LOCAL_AES_KEY"


def set_local_vault_secret(secret_store: str, values: dict):
    _local_vault_store[secret_store] = deepcopy(values)


def get_aes_key(key_type: str):
    try:
        return _local_vault_store["aes-keys"][key_type]
    except KeyError as e:
        err_msg = f"{e} not found in aes-keys: ({_local_vault_store['aes-keys']})."
        api_logger.exception(err_msg)
        raise VaultError(err_msg)


def get_current_token_secret() -> (str, str):
    try:
        current_key = _local_vault_store["api2-access-secrets"]["current_key"]
    except KeyError:
        load_secrets("api2-access-secrets", allow_reload=True)
        try:
            current_key = _local_vault_store["api2-access-secrets"]["current_key"]
        except KeyError:
            raise falcon.HTTPInternalServerError
    return current_key, get_access_token_secret(current_key)


def get_access_token_secret(key: str) -> str:
    """
    Tries to find key in dict obtained from vault. If not will reload the keys from the vault
    in case they have been rotated.
    :param key: key from token used to look up key
    :return: key value (the secret) or empty string
    """
    if key == "current_key":
        # make sure for security we can't use the key value stored in current_key
        # which can be hacked from the token
        raise falcon.HTTPUnauthorized(title="illegal KID", code="INVALID_TOKEN")

    try:
        return _local_vault_store["api2-access-secrets"][key]
    except KeyError:
        load_secrets("api2-access-secrets", allow_reload=True)
        try:
            return _local_vault_store["api2-access-secrets"][key]
        except KeyError:
            return ""


def get_secret_via_local_store(local_secrets_name: str, path: str) -> dict:
    global _local_vault_store
    tries = 2
    secrets_record = {}
    while tries:
        secrets_record = _local_vault_store.get(local_secrets_name)
        if secrets_record:
            tries = 0
        elif tries > 1:
            # if cannot be found then try to load it as it might be a new vault entry
            to_load = {local_secrets_name: path}
            load_secret_from_store(to_load, was_loaded=False, allow_reload=True)
            tries -= 1
        else:
            return {}
    return secrets_record


def dynamic_get_b2b_token_secret(kid: str) -> dict:
    """
    Gets a B2B token secret which cannot be determined at code start. It must be loaded from the vault and cached when
    our B2B customer first uses it. In this use case the customer notifies us of a public key they intend to use
    and we pre-add it to the vault.  They may periodically do this to roll over token public keys and we erase old ones
    after they are no longer used.

    The kid consists of the customer name - secret id eg lloyds-secret1.  The first part before the "-" must always be
    lloyds to ensure that their channel is selected and if a url is defined the token may be auto added to the vault.

    :param kid: kid sent in a b2b token
    :param reread_secs: how many seconds to re-read a secret from cache
    :param path: path to secret
    :return: a dict representing the secret
    """
    global _local_vault_store

    config = settings.VAULT_CONFIG
    pre_fix_kid, post_fix_kid = kid.split("-", 1)
    if len(post_fix_kid) < 1 or len(pre_fix_kid) < 3:
        return {}
    b2b_secrets_path = f"{config['API2_B2B_SECRETS_BASE_PATH']}{pre_fix_kid}"
    local_secrets_name = f"b2b_channel_secrets_{pre_fix_kid}"

    local_secrets_for_kid = get_secret_via_local_store(local_secrets_name, b2b_secrets_path)
    channel = local_secrets_for_kid.get("channel")
    get_external_secrets_url = local_secrets_for_kid.get("url")
    if not channel:
        return {}

    name = f"b2b_token_secrets_{kid}"
    path = f"{config['API2_B2B_TOKEN_KEYS_BASE_PATH']}{kid}"
    to_load = {name: path}
    tries = 2
    while tries:
        signing_secret_data = _local_vault_store.get(name)
        if signing_secret_data:
            return {"key": signing_secret_data["public_key"], "channel": channel}
        key_loaded = load_secret_from_store(to_load, was_loaded=False, allow_reload=True)
        if not key_loaded and get_external_secrets_url:
            pass
            # @todo add url read logic to get a secret and kid post fix (not full kid) from a b2b public key service
            # must ensure the correct key prefix is used if they
            # or we might just make a kid for the channel using a made up post fix and in the POST send a kid
            # and get back a new public secret.  This needs to be worked out with B@B cleints
        tries -= 1
    return {}


def load_secrets(load: str, allow_reload: bool = False) -> None:
    """
    Retrieves security credential values from channel and secret_keys storage vaults and stores them
    in  which are used as a cache.
    Secrets contained in _local_vault_store using the  "all_secrets" key map which maps the config
    path to an internal ref keys eg "aes-keys"

    The reference key is also used fro mapping in the local secrets file

    Example:

    "aes-keys": {
        "LOCAL_AES_KEY": "local aes key",
        "AES_KEY": "aes key"
    },
    "api2-access-secrets": {
        "current_key": "access-secret-2",
        "access-secret-1": "my_secret_1",
        "access-secret-2": "my_secret_2",
        "access-secret-3": "my_secret_3"
    }


    """
    global loaded
    global _local_vault_store
    config = settings.VAULT_CONFIG

    to_load = {}
    all_secrets = {
        "aes-keys": config["AES_KEYS_VAULT_PATH"],
        "api2-access-secrets": config["API2_ACCESS_SECRETS_PATH"],
    }
    if load == "all":
        to_load = all_secrets
    else:
        try:
            to_load[load] = all_secrets[load]
        except KeyError as e:
            err_msg = f"Cannot find secret to reload - Vault Exception {e}"
            api_logger.exception(err_msg)
            raise VaultError(err_msg) from e
    loaded = load_secret_from_store(to_load, loaded, allow_reload)


def load_secret_from_store(to_load, was_loaded, allow_reload) -> bool:
    config = settings.VAULT_CONFIG

    if was_loaded and not allow_reload:
        api_logger.info("Tried to load the vault secrets more than once, ignoring the request.")

    elif config.get("LOCAL_SECRETS"):
        api_logger.info(f"JWT bundle secrets - from local file {config['LOCAL_SECRETS_PATH']}")
        with open(config["LOCAL_SECRETS_PATH"]) as fp:
            loaded_secrets = json.load(fp)

        for secret_store, path in to_load.items():
            set_local_vault_secret(secret_store, loaded_secrets[secret_store])
        was_loaded = True

    else:

        credential = DefaultAzureCredential(exclude_environment_credential=True,
                                            exclude_shared_token_cache_credential=True,
                                            exclude_visual_studio_code_credential=True,
                                            exclude_interactive_browser_credential=True,
                                            )

        client = SecretClient(vault_url=config['VAULT_URL'], credential=credential)

        for secret_name, path in to_load.items():

            api_logger.info(f"Loading {secret_name} from vault at {config['VAULT_URL']}")

            _local_vault_store[secret_name] = client.get_secret(secret_name).value


        was_loaded = True

    return was_loaded
