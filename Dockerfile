# pgdocket: the worker and CLI in one small image.
#   docker build -t pgdocket .
#   docker run --rm -e DATABASE_URL=... -e TYPESAFE_API_KEY=... pgdocket worker
FROM python:3.12-slim
WORKDIR /src
COPY pyproject.toml LICENSE ./
COPY pgdocket ./pgdocket
RUN pip install --no-cache-dir . && rm -rf /src
WORKDIR /
USER nobody
ENTRYPOINT ["pgdocket"]
CMD ["worker"]
