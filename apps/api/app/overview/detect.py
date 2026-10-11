"""Deterministic facts about a snapshot: stack, languages, entry points, folder roles.

Everything here reads stored text as data. Manifests are parsed as JSON and
scripts are split into tokens; nothing from the repository is executed.
"""

import json
import posixpath
import re
from collections import Counter
from dataclasses import dataclass

# package name -> (display name, category). Prefix entries end with "/".
PACKAGES: dict[str, tuple[str, str]] = {
    "next": ("Next.js", "framework"),
    "nuxt": ("Nuxt", "framework"),
    "@sveltejs/kit": ("SvelteKit", "framework"),
    "@angular/core": ("Angular", "framework"),
    "astro": ("Astro", "framework"),
    "@remix-run/react": ("Remix", "framework"),
    "react-native": ("React Native", "framework"),
    "expo": ("Expo", "framework"),
    "electron": ("Electron", "framework"),
    "react": ("React", "ui"),
    "vue": ("Vue", "ui"),
    "svelte": ("Svelte", "ui"),
    "solid-js": ("Solid", "ui"),
    "preact": ("Preact", "ui"),
    "@mui/material": ("Material UI", "ui"),
    "@chakra-ui/react": ("Chakra UI", "ui"),
    "@material-tailwind/react": ("Material Tailwind", "ui"),
    "antd": ("Ant Design", "ui"),
    "@radix-ui/": ("Radix UI", "ui"),
    "framer-motion": ("Framer Motion", "ui"),
    "motion": ("Motion", "ui"),
    "chart.js": ("Chart.js", "ui"),
    "recharts": ("Recharts", "ui"),
    "d3": ("D3", "ui"),
    "three": ("three.js", "ui"),
    "react-router-dom": ("React Router", "routing"),
    "react-router": ("React Router", "routing"),
    "@tanstack/react-router": ("TanStack Router", "routing"),
    "vue-router": ("Vue Router", "routing"),
    "redux": ("Redux", "state"),
    "@reduxjs/toolkit": ("Redux Toolkit", "state"),
    "zustand": ("Zustand", "state"),
    "jotai": ("Jotai", "state"),
    "mobx": ("MobX", "state"),
    "pinia": ("Pinia", "state"),
    "@tanstack/react-query": ("TanStack Query", "data"),
    "swr": ("SWR", "data"),
    "axios": ("Axios", "data"),
    "@apollo/client": ("Apollo Client", "data"),
    "@trpc/client": ("tRPC", "data"),
    "express": ("Express", "server"),
    "fastify": ("Fastify", "server"),
    "koa": ("Koa", "server"),
    "hono": ("Hono", "server"),
    "@nestjs/core": ("NestJS", "server"),
    "@trpc/server": ("tRPC", "server"),
    "@apollo/server": ("Apollo Server", "server"),
    "graphql": ("GraphQL", "server"),
    "socket.io": ("Socket.IO", "server"),
    "prisma": ("Prisma", "database"),
    "@prisma/client": ("Prisma", "database"),
    "drizzle-orm": ("Drizzle", "database"),
    "mongoose": ("Mongoose", "database"),
    "typeorm": ("TypeORM", "database"),
    "sequelize": ("Sequelize", "database"),
    "pg": ("PostgreSQL client", "database"),
    "mysql2": ("MySQL client", "database"),
    "ioredis": ("Redis client", "database"),
    "redis": ("Redis client", "database"),
    "firebase": ("Firebase", "platform"),
    "firebase-admin": ("Firebase", "platform"),
    "@supabase/supabase-js": ("Supabase", "platform"),
    "tailwindcss": ("Tailwind CSS", "styling"),
    "styled-components": ("styled-components", "styling"),
    "@emotion/react": ("Emotion", "styling"),
    "sass": ("Sass", "styling"),
    "typescript": ("TypeScript", "language"),
    "vite": ("Vite", "build"),
    "webpack": ("webpack", "build"),
    "esbuild": ("esbuild", "build"),
    "rollup": ("Rollup", "build"),
    "tsup": ("tsup", "build"),
    "turbo": ("Turborepo", "build"),
    "nx": ("Nx", "build"),
    "jest": ("Jest", "testing"),
    "vitest": ("Vitest", "testing"),
    "mocha": ("Mocha", "testing"),
    "@playwright/test": ("Playwright", "testing"),
    "cypress": ("Cypress", "testing"),
    "@testing-library/react": ("Testing Library", "testing"),
    "eslint": ("ESLint", "tooling"),
    "prettier": ("Prettier", "tooling"),
    "@biomejs/biome": ("Biome", "tooling"),
    "@storybook/react": ("Storybook", "tooling"),
    "zod": ("Zod", "validation"),
    "yup": ("Yup", "validation"),
    "openai": ("OpenAI SDK", "ai"),
    "@anthropic-ai/sdk": ("Anthropic SDK", "ai"),
    "ai": ("Vercel AI SDK", "ai"),
    "@langchain/core": ("LangChain", "ai"),
    "langchain": ("LangChain", "ai"),
}

# file name -> (display name, category), matched at depth 0 or 1.
MARKER_FILES: dict[str, tuple[str, str]] = {
    "tsconfig.json": ("TypeScript", "language"),
    "pyproject.toml": ("Python", "language"),
    "requirements.txt": ("Python", "language"),
    "setup.py": ("Python", "language"),
    "go.mod": ("Go", "language"),
    "Cargo.toml": ("Rust", "language"),
    "Gemfile": ("Ruby", "language"),
    "pom.xml": ("Java", "language"),
    "build.gradle": ("Java or Kotlin", "language"),
    "Dockerfile": ("Docker", "tooling"),
    "docker-compose.yml": ("Docker Compose", "tooling"),
    "docker-compose.yaml": ("Docker Compose", "tooling"),
    "compose.yaml": ("Docker Compose", "tooling"),
    "vercel.json": ("Vercel", "platform"),
    "netlify.toml": ("Netlify", "platform"),
}

# Within a category, foundational entries come first in the catalogs above.
CATALOG_ORDER: dict[str, int] = {}
for _name, _ in [*PACKAGES.values(), *MARKER_FILES.values()]:
    CATALOG_ORDER.setdefault(_name, len(CATALOG_ORDER))

CATEGORY_ORDER = [
    "framework",
    "language",
    "ui",
    "routing",
    "state",
    "data",
    "server",
    "database",
    "platform",
    "styling",
    "ai",
    "validation",
    "build",
    "testing",
    "tooling",
]

LANGUAGES: dict[str, str] = {
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".py": "Python",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cs": "C#",
    ".php": "PHP",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".css": "CSS",
    ".scss": "SCSS",
    ".html": "HTML",
    ".md": "Markdown",
    ".mdx": "Markdown",
    ".json": "JSON",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".sql": "SQL",
    ".sh": "Shell",
}

NON_CODE = {"JSON", "YAML", "Markdown"}
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb", "Cargo.lock", "poetry.lock", "uv.lock"}

CODE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
BUILD_FOLDERS = ("dist/", "build/", "lib/", "out/", "esm/", "cjs/")
MAX_SCRIPTS = 40
MAX_ENTRY_POINTS = 8
MAX_ROUTES = 6
MAX_FOLDERS = 16
MAX_TEXT = 300

FOLDER_ROLES: dict[str, str] = {
    "src": "Source root",
    "source": "Source root",
    "components": "UI components",
    "ui": "UI components",
    "widgets": "UI components",
    "pages": "Pages and routes",
    "routes": "Pages and routes",
    "views": "Pages and routes",
    "screens": "Pages and routes",
    "app": "Application routes and shell",
    "layouts": "Page layouts",
    "api": "HTTP handlers",
    "server": "Server code",
    "controllers": "HTTP handlers",
    "handlers": "HTTP handlers",
    "middleware": "Request middleware",
    "services": "Services and business logic",
    "core": "Core logic",
    "domain": "Domain logic",
    "lib": "Shared library code",
    "libs": "Shared library code",
    "utils": "Shared utilities",
    "util": "Shared utilities",
    "helpers": "Shared utilities",
    "common": "Shared code",
    "shared": "Shared code",
    "hooks": "React hooks",
    "context": "React context providers",
    "contexts": "React context providers",
    "providers": "Context providers",
    "store": "State management",
    "stores": "State management",
    "state": "State management",
    "redux": "State management",
    "slices": "State management",
    "models": "Data models",
    "schemas": "Data schemas",
    "types": "Type definitions",
    "interfaces": "Type definitions",
    "db": "Database access",
    "database": "Database access",
    "migrations": "Database migrations",
    "prisma": "Database schema",
    "config": "Configuration",
    "configs": "Configuration",
    "constants": "Constants",
    "scripts": "Build and maintenance scripts",
    "bin": "Command-line executables",
    "cli": "Command-line interface",
    "test": "Tests",
    "tests": "Tests",
    "__tests__": "Tests",
    "spec": "Tests",
    "e2e": "End-to-end tests",
    "docs": "Documentation",
    "examples": "Examples",
    "example": "Examples",
    "public": "Static assets",
    "static": "Static assets",
    "assets": "Static assets",
    "icons": "Icons and graphics",
    "images": "Static assets",
    "styles": "Styles",
    "css": "Styles",
    "i18n": "Translations",
    "locales": "Translations",
    ".github": "CI and repository settings",
}
NESTED_ROOTS = {"src", "source", "lib", "app"}
WORKSPACE_ROOTS = {"apps", "packages", "services", "libs", "modules", "plugins"}


@dataclass(frozen=True)
class Manifest:
    path: str
    data: dict

    @property
    def directory(self) -> str:
        return posixpath.dirname(self.path)


def parse_manifest(path: str, content: str | None) -> Manifest | None:
    if not content:
        return None
    try:
        data = json.loads(content)
    except ValueError:
        return None
    return Manifest(path=path, data=data) if isinstance(data, dict) else None


def detect_stack(manifests: list[Manifest], paths: list[str]) -> list[dict]:
    """Known packages from dependencies, plus marker files such as go.mod or Dockerfile."""

    found: dict[str, dict] = {}
    for manifest in manifests:
        for field in ("dependencies", "devDependencies", "peerDependencies"):
            dependencies = manifest.data.get(field)
            if not isinstance(dependencies, dict):
                continue
            for package, version in dependencies.items():
                match = _known_package(str(package))
                if match is None:
                    continue
                name, category = match
                if name in found:
                    continue
                found[name] = {
                    "name": name,
                    "category": category,
                    "package": str(package),
                    "version": str(version)[:40] if isinstance(version, str) else None,
                    "evidence": manifest.path,
                    "dev": field == "devDependencies",
                }
    for path in paths:
        if path.count("/") > 1:
            continue
        marker = MARKER_FILES.get(posixpath.basename(path))
        if marker is None and path.startswith(".github/workflows/"):
            marker = ("GitHub Actions", "tooling")
        if marker is None or marker[0] in found:
            continue
        found[marker[0]] = {
            "name": marker[0],
            "category": marker[1],
            "package": None,
            "version": None,
            "evidence": path,
            "dev": False,
        }
    return sorted(
        found.values(),
        key=lambda item: (CATEGORY_ORDER.index(item["category"]), item["dev"], CATALOG_ORDER.get(item["name"], len(CATALOG_ORDER))),
    )


def _known_package(package: str) -> tuple[str, str] | None:
    if package in PACKAGES:
        return PACKAGES[package]
    for prefix, value in PACKAGES.items():
        if prefix.endswith("/") and package.startswith(prefix):
            return value
    return None


def language_breakdown(files: list[tuple[str, int]]) -> list[dict]:
    """Bytes and file counts per programming or markup language, largest first.

    Data and prose (JSON, YAML, Markdown) and lockfiles are left out so a large
    package-lock.json does not drown the source.
    """

    sizes: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    for path, size in files:
        language = LANGUAGES.get(posixpath.splitext(path)[1].lower())
        if language is None or language in NON_CODE or posixpath.basename(path) in LOCKFILES:
            continue
        sizes[language] += size
        counts[language] += 1
    total = sum(sizes.values()) or 1
    return [
        {"language": language, "files": counts[language], "bytes": size, "share": round(size / total, 4)}
        for language, size in sizes.most_common(8)
    ]


def detect_entry_points(
    manifests: list[Manifest],
    paths: list[str],
    html_pages: dict[str, str],
    stack_names: set[str],
) -> list[dict]:
    """Where execution or reading starts, each with the evidence that says so."""

    known = set(paths)
    entries: dict[str, dict] = {}

    def add(path: str | None, kind: str, reason: str, evidence: str | None) -> None:
        if path is not None and path not in entries:
            entries[path] = {"path": path, "kind": kind, "reason": reason, "evidence": evidence}

    for manifest in sorted(manifests, key=lambda item: item.path.count("/")):
        data = manifest.data
        for field in ("main", "module", "browser", "source"):
            value = data.get(field)
            if isinstance(value, str):
                add(_resolve(manifest.directory, value, known), "package", f'The "{field}" field of {manifest.path}.', manifest.path)
        binaries = data.get("bin")
        if isinstance(binaries, str):
            add(_resolve(manifest.directory, binaries, known), "bin", f"The command-line executable in {manifest.path}.", manifest.path)
        elif isinstance(binaries, dict):
            for command, value in list(binaries.items())[:4]:
                if isinstance(value, str):
                    add(_resolve(manifest.directory, value, known), "bin", f'The "{command}" command in {manifest.path}.', manifest.path)
        for value in _export_targets(data.get("exports")):
            add(_resolve(manifest.directory, value, known), "package", f"Exported by {manifest.path}.", manifest.path)

    for html_path, content in html_pages.items():
        directory = posixpath.dirname(html_path)
        for source in re.findall(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", content, flags=re.IGNORECASE)[:4]:
            if "://" in source or source.startswith("//"):
                continue
            base = "" if source.startswith("/") else directory
            add(_resolve(base, source.lstrip("/"), known), "html", f"Loaded by a script tag in {html_path}.", html_path)

    for manifest in manifests:
        scripts = manifest.data.get("scripts")
        if not isinstance(scripts, dict):
            continue
        for name, command in list(scripts.items())[:MAX_SCRIPTS]:
            if not isinstance(command, str):
                continue
            for token in re.split(r"[\s;&|()]+", command):
                token = token.strip("'\"")
                if not token or token.startswith("-") or "=" in token or "$" in token:
                    continue
                if not (token.endswith(CODE_EXTENSIONS) or token.endswith(".py")):
                    continue
                add(_resolve(manifest.directory, token, known), "script", f'Run by the "{name}" script in {manifest.path}.', manifest.path)

    if "Next.js" in stack_names:
        routes = sorted(
            (path for path in paths if re.search(r"(^|/)(src/)?app/(.+/)?(layout|page|route)\.(t|j)sx?$", path)),
            key=lambda path: (path.count("/"), not path.endswith(("layout.tsx", "layout.jsx", "layout.ts", "layout.js")), path),
        )
        pages = sorted(
            (path for path in paths if re.search(r"(^|/)(src/)?pages/.+\.(t|j)sx?$", path)),
            key=lambda path: (path.count("/"), path),
        )
        for path in (routes + pages)[:MAX_ROUTES]:
            add(path, "route", "A Next.js route file; the framework loads it by its location.", None)

    for directory in [""] + sorted({manifest.directory for manifest in manifests if manifest.directory}):
        for stem in ("src/main", "src/index", "main", "index", "src/server", "server", "src/app", "app", "src/cli", "cli"):
            for extension in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
                candidate = posixpath.join(directory, stem + extension)
                if candidate in known:
                    add(candidate, "convention", "A conventional entry file name.", None)
        for name in ("main.py", "app.py", "manage.py", "__main__.py"):
            candidate = posixpath.join(directory, name)
            if candidate in known:
                add(candidate, "convention", "A conventional Python entry file name.", None)

    return list(entries.values())[:MAX_ENTRY_POINTS]


def _export_targets(exports: object) -> list[str]:
    if isinstance(exports, str):
        return [exports]
    if not isinstance(exports, dict):
        return []
    root = exports.get(".", exports)
    if isinstance(root, str):
        return [root]
    if isinstance(root, dict):
        targets = []
        for key in ("source", "import", "default", "require", "node"):
            value = root.get(key)
            if isinstance(value, str):
                targets.append(value)
            elif isinstance(value, dict) and isinstance(value.get("default"), str):
                targets.append(value["default"])
        return targets[:3]
    return []


def _resolve(directory: str, value: str, known: set[str]) -> str | None:
    """Map a manifest path to a stored file, trying TypeScript sources for build output."""

    value = value.strip()
    if not value or value.startswith("/") or "\\" in value:
        return None
    cleaned = posixpath.normpath(posixpath.join(directory, value))
    if cleaned in (".", "") or cleaned.startswith(".."):
        return None
    stem, extension = posixpath.splitext(cleaned)
    candidates = [cleaned]
    if extension == "":
        candidates += [cleaned + ext for ext in CODE_EXTENSIONS] + [posixpath.join(cleaned, "index" + ext) for ext in CODE_EXTENSIONS]
    else:
        candidates += [stem + ext for ext in (".ts", ".tsx", ".mts")]
    relative = cleaned[len(directory) + 1 :] if directory and cleaned.startswith(directory + "/") else cleaned
    for folder in BUILD_FOLDERS:
        if relative.startswith(folder):
            source_stem = posixpath.splitext(posixpath.join(directory, "src", relative[len(folder) :]))[0]
            candidates += [source_stem + ext for ext in CODE_EXTENSIONS]
    for candidate in candidates:
        if candidate in known:
            return candidate
    return None


def folder_roles(paths: list[str], edges: list[dict], rank: dict[str, float]) -> list[dict]:
    """One row per meaningful folder: what it likely holds and how it connects.

    The role comes from the folder name, or from its contents when the name is
    unknown. It is a label for orientation, not a claim about every file.
    """

    groups: dict[str, list[str]] = {}
    for path in paths:
        key = _folder_key(path)
        if key is not None:
            groups.setdefault(key, []).append(path)
    owner = {path: key for key, members in groups.items() for path in members}
    outgoing: Counter[str] = Counter()
    incoming: Counter[str] = Counter()
    for edge in edges:
        source = owner.get(edge["source"])
        target = owner.get(edge["target"])
        if source and target and source != target:
            outgoing[source] += 1
            incoming[target] += 1
    rows = []
    for key, members in groups.items():
        role, basis = _role_for(key, members)
        ranked = sorted((path for path in members if path in rank), key=lambda path: -rank[path])
        rows.append(
            {
                "path": key,
                "role": role,
                "basis": basis,
                "files": len(members),
                "depends_on": outgoing[key],
                "used_by": incoming[key],
                "key_files": ranked[:3],
            }
        )
    rows.sort(key=lambda row: (-row["files"], row["path"]))
    return rows[:MAX_FOLDERS]


def _folder_key(path: str) -> str | None:
    parts = path.split("/")
    if len(parts) < 2:
        return None
    if parts[0] in WORKSPACE_ROOTS and len(parts) >= 3:
        return "/".join(parts[:2])
    if parts[0] in NESTED_ROOTS and len(parts) >= 3:
        return "/".join(parts[:2])
    return parts[0]


def _role_for(key: str, members: list[str]) -> tuple[str | None, str | None]:
    parts = key.split("/")
    if parts[0] in WORKSPACE_ROOTS and len(parts) == 2:
        return "Workspace package", "location"
    name = parts[-1].lower()
    if name in FOLDER_ROLES:
        return FOLDER_ROLES[name], "name"
    extensions = Counter(posixpath.splitext(path)[1].lower() for path in members)
    total = len(members)
    tests = sum(1 for path in members if re.search(r"(\.|_)(test|spec)\.[a-z]+$", path))
    if tests * 2 > total:
        return "Tests", "contents"
    if (extensions[".md"] + extensions[".mdx"]) * 2 > total:
        return "Documentation", "contents"
    if (extensions[".css"] + extensions[".scss"]) * 2 > total:
        return "Styles", "contents"
    if (extensions[".png"] + extensions[".svg"] + extensions[".jpg"] + extensions[".ico"]) * 2 > total:
        return "Static assets", "contents"
    return None, None


def short_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = " ".join(value.split())
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"
