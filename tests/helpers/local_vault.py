import json

from angelia.api.helpers.vault import set_local_vault_secret


def set_vault_cache(file_name: str | None = None, to_load: list | None = None) -> None:
    if to_load is None:
        to_load = ["aes-keys", "api2-access-secrets"]
    if file_name is None:
        file_name = "example_local_secrets.json"

    with open(file_name) as fp:
        loaded_secrets = json.load(fp)
    for secret_store in to_load:
        set_local_vault_secret(secret_store, loaded_secrets[secret_store])
