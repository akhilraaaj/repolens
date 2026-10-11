FROM node:22-bookworm-slim AS analyzer
WORKDIR /analyzer
COPY apps/analyzer/package.json ./
RUN npm install
COPY apps/analyzer/parse.mjs ./

FROM python:3.12-slim-bookworm
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
RUN pip install --no-cache-dir uv==0.13.0
WORKDIR /srv/apps/api
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev
COPY apps/api /srv/apps/api
COPY --from=analyzer /analyzer /srv/apps/analyzer
ENV PATH="/srv/apps/api/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
