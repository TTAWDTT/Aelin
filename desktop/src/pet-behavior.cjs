const fs = require("fs");
const path = require("path");

const DEFAULT_BEHAVIOR = Object.freeze({
  state: {
    completionHoldMs: 45_000,
    lateNightStartHour: 23,
    lateNightEndHour: 5,
  },
  coach: {
    longFocusTriggerMin: 45,
    cooldownMs: 20 * 60 * 1000,
    visibleMs: 25 * 60 * 1000,
  },
  hoverGuard: {
    intervalMs: 250,
    marginPx: 18,
    outsideTicks: 4,
  },
  ticker: {
    statePushIntervalMs: 2500,
    processProbeCacheMs: 4500,
    mediaProbeCacheMs: 3500,
  },
  probe: {
    commandTimeoutMs: 5000,
  },
  emotion: {
    focusWarmupMin: 10,
    focusFlowMin: 45,
    focusDeepMin: 90,
    restIdleSec: 240,
    highCpuThreshold: 0.78,
    musicValenceBoost: 8,
    musicEnergyBoost: 6,
  },
});

function isObjectLike(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function deepMerge(base, override) {
  const output = { ...base };
  const patch = isObjectLike(override) ? override : {};
  for (const [key, value] of Object.entries(patch)) {
    if (isObjectLike(value) && isObjectLike(base[key])) {
      output[key] = deepMerge(base[key], value);
      continue;
    }
    output[key] = value;
  }
  return output;
}

function tryReadJson(candidatePath) {
  const full = String(candidatePath || "").trim();
  if (!full) return null;
  try {
    if (!fs.existsSync(full)) return null;
    const raw = fs.readFileSync(full, "utf8");
    const parsed = JSON.parse(raw);
    if (!isObjectLike(parsed)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function buildCandidatePaths({ envPath = "", userDataPath = "", defaultPath = "", resourcesPath = "", isPackaged = false }) {
  const out = [];
  if (envPath) out.push(envPath);
  if (userDataPath) out.push(path.join(userDataPath, "pet-behavior.json"));
  if (defaultPath) out.push(defaultPath);
  if (isPackaged && resourcesPath) out.push(path.join(resourcesPath, "pet-behavior.json"));
  return Array.from(new Set(out.filter(Boolean)));
}

function loadPetBehaviorConfig(options = {}) {
  const defaults = JSON.parse(JSON.stringify(DEFAULT_BEHAVIOR));
  const candidates = buildCandidatePaths(options);
  let merged = defaults;
  let loadedFrom = "";
  for (const candidate of candidates) {
    const parsed = tryReadJson(candidate);
    if (!parsed) continue;
    merged = deepMerge(merged, parsed);
    loadedFrom = candidate;
    break;
  }
  return {
    config: merged,
    loadedFrom,
  };
}

module.exports = {
  DEFAULT_BEHAVIOR,
  loadPetBehaviorConfig,
};
