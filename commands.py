import os
import sys

import click

from app.api.app import create_app


@click.group()
def manage():
    pass


@manage.command()
def run_api_server():
    app = create_app()
    try:
        import werkzeug.serving
    except ImportError:
        print(f"Dev requirements must be installed to run the API this way.")
        sys.exit(-1)

    in_debugger = bool(os.getenv("DEBUGGING"))

    werkzeug.serving.run_simple(
        hostname="localhost",
        port=6502,
        application=app,
        use_reloader=not in_debugger,
        use_debugger=True,
    )


# @manage.command()
# def create_messaging_db():
#     click.echo('Creating Messaging Collections')
#     DB().set_up_database()


@manage.command()
def write_example_env():
    data = """
LOG_LEVEL=DEBUG
JWT_SECRET=gYxqfNqh8eTKHDpsY25nYqk7gmXD6fXinLoWc9zwIa6EosCGKvPA2jJLnMPnnQB4
INTERNAL_SERVICE_JWT_SECRET=ZDLKkvm4zoiRZa4m3QmtSKm00s3yqlZCPTd7KWkXsJN13ePnBb
ORGANISATION_ID=Loyalty Angels
POSTGRES_READ_HOST=127.0.0.1
POSTGRES_READ_PORT=5432
POSTGRES_WRITE_HOST=127.0.0.1
POSTGRES_WRITE_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASS=
POSTGRES_DB=hermes
RABBIT_PASSWORD=guest
RABBIT_USER=guest
RABBIT_HOST=127.0.0.1
RABBIT_PORT=5672
HERMES_URL=http://127.0.0.1:8000
METRICS_SIDECAR_DOMAIN=localhost
METRICS_PORT=4000
PERFORMANCE_METRICS=1
"""
    f = open(".env", "w")
    f.write(data)
    f.close()


manage.add_command(run_api_server)
manage.add_command(write_example_env)

if __name__ == "__main__":
    manage()
