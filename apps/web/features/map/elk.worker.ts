// Inside a worker, elk-worker installs its own self.onmessage dispatcher that
// elk-api speaks to. The bundler loads this script asynchronously, so messages
// posted before it runs are dropped; announce readiness once the dispatcher exists.
import "elkjs/lib/elk-worker.min.js";

self.postMessage({ ready: true });
