import { spawn } from "node:child_process";

function readOption(args, name, fallback) {
  const direct = args.find((item) => item.startsWith(`${name}=`));

  if (direct) {
    const [, value = ""] = direct.split("=");

    return value || fallback;
  }

  const idx = args.findIndex((item) => item === name);

  if (idx >= 0 && args[idx + 1]) {
    return args[idx + 1];
  }

  return fallback;
}

function normalizeWarmHost(hostname) {
  if (!hostname || hostname === "0.0.0.0" || hostname === "::") {
    return "127.0.0.1";
  }

  return hostname;
}

function toDocPath(slug) {
  if (!Array.isArray(slug) || !slug.length) {
    return "/docs";
  }

  return `/docs/${slug.map((segment) => encodeURIComponent(segment)).join("/")}`;
}

async function warmupDocs(baseUrl) {
  try {
    const docsResponse = await fetch(`${baseUrl}/docs`, {
      cache: "no-store",
    });

    if (!docsResponse.ok) {
      return;
    }

    const manifestResponse = await fetch(`${baseUrl}/api/docs-manifest`, {
      cache: "no-store",
    });

    if (!manifestResponse.ok) {
      return;
    }

    const manifest = await manifestResponse.json();
    const extraPaths = (manifest.searchEntries ?? [])
      .slice(0, 4)
      .map((entry) => toDocPath(entry?.slug))
      .filter(Boolean);

    await Promise.allSettled(
      extraPaths.map((path) =>
        fetch(`${baseUrl}${path}`, {
          cache: "no-store",
        }),
      ),
    );
  } catch {
    // best-effort warmup only
  }
}

const passThroughArgs = process.argv.slice(2);
const child = spawn("next", ["dev", ...passThroughArgs], {
  env: process.env,
  shell: process.platform === "win32",
  stdio: ["inherit", "pipe", "pipe"],
});

const hostname = readOption(passThroughArgs, "--hostname", "127.0.0.1");
const port = readOption(passThroughArgs, "--port", "3000");
const warmHost = normalizeWarmHost(hostname);
const baseUrl = `http://${warmHost}:${port}`;
let isWarmed = false;

const onLine = (line) => {
  if (isWarmed) {
    return;
  }

  if (line.includes("Ready in")) {
    isWarmed = true;
    void warmupDocs(baseUrl);
  }
};

child.stdout.on("data", (chunk) => {
  const text = chunk.toString();

  process.stdout.write(text);
  text.split(/\r?\n/).forEach(onLine);
});

child.stderr.on("data", (chunk) => {
  process.stderr.write(chunk.toString());
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }

  process.exit(code ?? 0);
});
