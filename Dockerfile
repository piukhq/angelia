FROM ghcr.io/binkhq/python:3.9

WORKDIR /app
ADD . .
RUN pipenv install --deploy --system --ignore-pipfile

ENV PROMETHEUS_MULTIPROC_DIR=/dev/shm
CMD [ "gunicorn", "--workers=2", "--threads=2", "--error-logfile=-", "--access-logfile=-", \
    "--bind=0.0.0.0:9000", "--bind=0.0.0.0:9100", "app.api.app:create_app()" ]