import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import click
from Crypto.PublicKey import RSA
from jwcrypto import jwk

from angelia.api.helpers.vault import save_secret_to_vault
from angelia.encryption import JWE, base32_encode
from angelia.report import api_logger
from angelia.settings import settings


def _gen_rsa_keypair(priv_path: str, pub_path: str) -> None:
    key = RSA.generate(2048)
    Path(priv_path).write_bytes(key.export_key("PEM"))

    pub = key.public_key()
    Path(pub_path).write_bytes(pub.export_key("PEM"))


def _gen_vault_key_obj(
    channel_slug: str, priv: str, pub: str, mins_to_expire: int = 60 * 24, paths: bool = True
) -> tuple[str, dict]:
    pub_key = jwk.JWK()

    if paths:
        priv = os.path.abspath(priv)
        pub = os.path.abspath(pub)

        with open(pub, "rb") as f:
            pub_key_pem_raw = f.read()
            pub_key.import_from_pem(pub_key_pem_raw)
            pub_key_pem = pub_key_pem_raw.decode()

        with open(priv, "rb") as f:
            priv_key_pem = f.read().decode()

    else:
        pub_key.import_from_pem(pub.encode())
        pub_key_pem = pub
        priv_key_pem = priv

    jwe_kid = pub_key.thumbprint()

    azure_kid = f"jwe-{channel_slug.removeprefix('com.').replace('.', '-')}-{base32_encode(jwe_kid)}"
    expiry = datetime.now() + timedelta(minutes=mins_to_expire)
    value = {"public_key": pub_key_pem, "private_key": priv_key_pem, "expires_at": expiry.timestamp()}

    api_logger.info(
        "FOR TESTING PURPOSES OR LOCAL USE ONLY\nAzure secret name:"
        f"\n{azure_kid}\n\nValue:\n{json.dumps(value, indent=4)}\n\n"
    )
    return azure_kid, value


def manual_encrypt(data: dict, pub_key_path: str | None = None, kid: str | None = None) -> str:
    """
    A simplified, more user-friendly encryption function that allows providing a filepath to a public key.

    Can be used as a helper tool for manual testing with encryption.
    """

    if pub_key_path:
        pub_key_pem = Path(pub_key_path).read_text()

        token = JWE().encrypt(json.dumps(data), public_key_pem=pub_key_pem)
    elif kid:
        token = JWE().encrypt(json.dumps(data), kid=kid)
    else:
        raise ValueError("pub_key_path or kid required")

    return json.dumps(token)


@click.group()
def manage() -> None:
    pass


@manage.command()
def run_api_server() -> None:
    # To avoid requiring connections to rabbit + postgres for other commands
    from angelia.api.app import create_app

    app = create_app()
    try:
        import werkzeug.serving
    except ImportError:
        click.echo("Dev requirements must be installed to run the API this way.")
        sys.exit(-1)

    werkzeug.serving.run_simple(
        hostname=settings.DEV_HOST,
        port=settings.DEV_PORT,
        application=app,
        use_reloader=settings.RELOADER,
        use_debugger=settings.DEBUG,
    )


@manage.command()
def write_example_env() -> None:
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
    Path(".env").write_text(data)


@manage.command()
@click.option("--priv", default="rsa", help="path to save RSA private key", type=click.Path())
@click.option("--pub", default="rsa.pub", help="path to save RSA public key", type=click.Path())
def gen_rsa_keys(priv: str, pub: str) -> None:
    """
    Generate a pair of RSA keys of 2048 bit size.
    Optional path/filename can be provided to save each key.
    Default is rsa and rsa.pub for the private and public key respectively.
    """
    _gen_rsa_keypair(priv, pub)
    click.echo("Generated public/private RSA key pair")


@manage.command()
@click.argument("channel_slug")
@click.argument("private_key_path", type=click.Path(exists=True))
@click.argument("public_key_path", type=click.Path(exists=True))
@click.option("--expire", default=60 * 24, help="Minutes before the keys expire. Defaults to 60*24 (1 day).")
@click.option("--save", default=False, is_flag=True, help="Save to the vault")
def gen_key_store_obj(channel_slug: str, private_key_path: str, public_key_path: str, expire: int, save: bool) -> None:
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
    kid, key_obj = _gen_vault_key_obj(
        channel_slug=channel_slug, priv=private_key_path, pub=public_key_path, mins_to_expire=expire
    )

    if save:
        save_secret_to_vault(kid, json.dumps(key_obj))
        click.echo(f"Saved key object to vault with kid: '{kid}'")


if __name__ == "__main__":
    manage()
