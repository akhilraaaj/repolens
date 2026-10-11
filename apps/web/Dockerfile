FROM oven/bun:1.3.2
WORKDIR /app
COPY apps/web/package.json apps/web/bun.lock ./
RUN bun install --frozen-lockfile
COPY apps/web .
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN bun run build
EXPOSE 3000
CMD ["bun", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
