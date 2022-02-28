import os
import sys

import click

from app.api.app import create_app
from app.encryption import gen_rsa_keypair


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
@click.argument('private_key_path')
@click.argument('public_key_path')
def gen_rsa_keys(private_key_path, public_key_path):
    gen_rsa_keypair(private_key_path, public_key_path)
    print("Generated public/private RSA key pair")


# @manage.command()
# @click.argument('private_key_path')
# @click.argument('public_key_path')
# def gen_vault_key_obj(private_key_path, public_key_path):
#     gen_rsa_keypair(private_key_path, public_key_path)
#     print("Generated public/private RSA key pair")
#
#
# @manage.command()
# @click.argument('data')
# @click.argument('kid')
# def jwe_encrypt(data, kid):
#     gen_rsa_keypair(private_key_path, public_key_path)
#     print("Generated public/private RSA key pair")


manage.add_command(run_api_server)
manage.add_command(write_example_env)
manage.add_command(gen_rsa_keys)

if __name__ == "__main__":
    manage()
