FROM ghcr.io/binkhq/python:3.11-pipenv

WORKDIR /app
ADD . .
RUN pipenv install --deploy --system --ignore-pipfile

ENV PROMETHEUS_MULTIPROC_DIR=/dev/shm
ENTRYPOINT [ "linkerd-await", "--" ]
CMD [ "gunicorn", "--error-logfile=-", "--access-logfile=-", \
    "--bind=0.0.0.0:9000", "--bind=0.0.0.0:9100", "main:app", \
    "--logger-class=app.report.CustomGunicornLogger"]
