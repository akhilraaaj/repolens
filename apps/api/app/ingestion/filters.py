"""Path rules for files that should not be stored."""

DEPENDENCY_DIRECTORIES = {".git", "node_modules", "vendor", "venv", ".venv", "__pycache__"}
GENERATED_DIRECTORIES = {"dist", "build", ".next", "out", "coverage"}
BINARY_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tgz",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".wasm",
    ".bin",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".class",
    ".jar",
    ".pyc",
)


def skip_reason_for_path(path: str) -> str | None:
    """Return why a relative path is excluded, or None when it should be read."""

    normalized = path.replace("\\", "/").lower()
    segments = [segment for segment in normalized.split("/") if segment]
    if any(segment in DEPENDENCY_DIRECTORIES for segment in segments):
        return "dependency"
    if any(segment in GENERATED_DIRECTORIES for segment in segments):
        return "generated"
    if normalized.endswith(".min.js") or normalized.endswith(".min.css") or normalized.endswith(".map"):
        return "generated"
    if normalized.endswith(BINARY_SUFFIXES):
        return "binary"
    return None
