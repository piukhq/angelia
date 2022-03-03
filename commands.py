import json
import os
import sys

import click

from app.api.app import create_app
from app.api.helpers.vault import save_secret_to_vault
from app.encryption import gen_rsa_keypair, gen_vault_key_obj


@click.group()
def manage():
    pass


@manage.command()
def run_api_server():
    app = create_app()
    try:
        import werkzeug.serving
    except ImportError:
        print("Dev requirements must be installed to run the API this way.")
        sys.exit(-1)

    in_debugger = bool(os.getenv("DEBUGGING"))

    werkzeug.serving.run_simple(
        hostname="localhost",
        port=6502,
        application=app,
        use_reloader=not in_debugger,
        use_debugger=True,
    )


@manage.command()
def write_example_env():
    data = """
LOG_LEVEL=DEBUG
LOCAL_SECRETS=True
POSTGRES_READ_DSN=postgresql://postgres@127.0.0.1:5432/hermes
POSTGRES_WRITE_DSN=postgresql://postgres@127.0.0.1:5432/hermes
RABBIT_PASSWORD=guest
RABBIT_USER=guest
RABBIT_HOST=127.0.0.1
RABBIT_PORT=5672
HERMES_URL=http://127.0.0.1:8000
METRICS_SIDECAR_DOMAIN=localhost
METRICS_PORT=4000
PERFORMANCE_METRICS=1
VAULT_URL=https://bink-uksouth-dev-com.vault.azure.net/

"""
    f = open(".env", "w")
    f.write(data)
    f.close()


@manage.command()
@click.option("--priv", default="rsa", help="path to save RSA private key", type=click.Path(exists=True))
@click.option("--pub", default="rsa.pub", help="path to save RSA public key", type=click.Path(exists=True))
def gen_rsa_keys(priv, pub):
    """
    Generate a pair of RSA keys of 2048 bit size.
    Optional path/filename can be provided to save each key.
    Default is rsa and rsa.pub for the private and public key respectively.
    """
    gen_rsa_keypair(priv, pub)
    print("Generated public/private RSA key pair")


@manage.command()
@click.argument("channel_slug")
@click.argument("private_key_path", type=click.Path(exists=True))
@click.argument("public_key_path", type=click.Path(exists=True))
@click.option("--expire", default=60 * 24, help="Minutes before the keys expire. Defaults to 60*24 (1 day).")
@click.option("--save", default=False, is_flag=True, help="Save to the vault")
def gen_key_store_obj(channel_slug, private_key_path, public_key_path, expire, save):
    """
    Generate a key object, in the correct formatting to be stored in the key vault, and the secret name that
    it should be stored under.

    The key object will contain the private and public key, as well as the time of expiry for these keys.
    This command requires the CHANNEL_SLUG of the relevant channel e.g "com.bink.wallet",
    the PRIVATE_KEY_PATH, which is a path to the locally stored private key,
    and the PUBLIC_KEY_PATH, which is a path to the locally stored public key.

    It is possible to save to the vault using the --save option.
    Saving the same key for the same channel will overwrite the existing key object in the vault with a new version.
    This can be useful for updating the expiry date for an existing key object.
    """
    kid, key_obj = gen_vault_key_obj(
        channel_slug=channel_slug, priv=private_key_path, pub=public_key_path, mins_to_expire=expire
    )

    if save:
        save_secret_to_vault(kid, json.dumps(key_obj))
        print(f"Saved key object to vault with kid: '{kid}'")


if __name__ == "__main__":
    manage()
