function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function toNumber(value, fallback) {
  const num = Number(value);
  return Number.isFinite(num) ? num : Number(fallback);
}

function toInt(value, fallback, min, max) {
  const raw = Math.round(toNumber(value, fallback));
  return clamp(raw, min, max);
}

function toFloat(value, fallback, min, max) {
  const raw = toNumber(value, fallback);
  return clamp(raw, min, max);
}

function normalizeEmotionConfig(behaviorConfig) {
  const cfg = behaviorConfig && typeof behaviorConfig === "object" ? behaviorConfig.emotion || {} : {};
  return {
    focusWarmupMin: toInt(cfg.focusWarmupMin, 10, 1, 720),
    focusFlowMin: toInt(cfg.focusFlowMin, 45, 2, 720),
    focusDeepMin: toInt(cfg.focusDeepMin, 90, 3, 720),
    restIdleSec: toInt(cfg.restIdleSec, 240, 30, 7200),
    highCpuThreshold: toFloat(cfg.highCpuThreshold, 0.78, 0.1, 1),
    musicValenceBoost: toInt(cfg.musicValenceBoost, 8, 0, 50),
    musicEnergyBoost: toInt(cfg.musicEnergyBoost, 6, 0, 50),
  };
}

function resolveFocusStage(workDurationMin, thresholds) {
  const minutes = Math.max(0, toInt(workDurationMin, 0, 0, 7200));
  if (minutes >= thresholds.focusDeepMin) return "deep";
  if (minutes >= thresholds.focusFlowMin) return "flow";
  if (minutes >= thresholds.focusWarmupMin) return "warmup";
  return "none";
}

function moodLabel(mood) {
  const map = {
    calm: "平稳",
    warming_up: "进入状态",
    focused: "稳定专注",
    flow: "心流",
    deep_focus: "深度专注",
    recharging: "休息回血",
    sleepy: "夜深放松",
    strained: "负载偏高",
  };
  return map[String(mood || "calm")] || "平稳";
}

function normalizeOverride(rawOverride) {
  if (!rawOverride || typeof rawOverride !== "object") return null;
  const moodRaw = String(rawOverride.mood || "").trim();
  const mood = moodRaw || undefined;
  const valence = Number.isFinite(Number(rawOverride.valence)) ? toInt(rawOverride.valence, 50, 0, 100) : undefined;
  const energy = Number.isFinite(Number(rawOverride.energy)) ? toInt(rawOverride.energy, 50, 0, 100) : undefined;
  const focus = Number.isFinite(Number(rawOverride.focus)) ? toInt(rawOverride.focus, 30, 0, 100) : undefined;
  const tension = Number.isFinite(Number(rawOverride.tension)) ? toInt(rawOverride.tension, 20, 0, 100) : undefined;
  const label = String(rawOverride.label || "").trim() || undefined;
  const reason = String(rawOverride.reason || "").trim() || undefined;
  const hasPatch = [mood, valence, energy, focus, tension, label, reason].some((item) => item !== undefined);
  if (!hasPatch) return null;
  return {
    mood,
    valence,
    energy,
    focus,
    tension,
    label,
    reason,
  };
}

function computePetEmotion(context = {}, behaviorConfig = {}, override = null) {
  const cfg = normalizeEmotionConfig(behaviorConfig);
  const isWorking = Boolean(context.isWorking);
  const workDurationMin = Math.max(0, toInt(context.workDurationMin, 0, 0, 7200));
  const idleSec = Math.max(0, toInt(context.idleSec, 0, 0, 72_000));
  const cpuUsage = toFloat(context.cpuUsage, 0, 0, 1);
  const isLateNight = Boolean(context.isLateNight);
  const hasMusic = Boolean(context.hasMusic || context.isMusicPlaying);

  let mood = "calm";
  let valence = 55;
  let energy = 52;
  let focus = 18;
  let tension = 16;
  const reasons = [];

  const focusStage = resolveFocusStage(workDurationMin, cfg);
  if (isWorking) {
    mood = "warming_up";
    valence += 4;
    energy += 8;
    focus += 20;
    reasons.push("working");

    if (focusStage === "warmup") {
      mood = "focused";
      focus += 12;
      valence += 3;
      reasons.push("focus_warmup");
    } else if (focusStage === "flow") {
      mood = "flow";
      focus += 24;
      valence += 9;
      energy += 10;
      tension += 4;
      reasons.push("focus_flow");
    } else if (focusStage === "deep") {
      mood = "deep_focus";
      focus += 34;
      valence += 11;
      energy += 12;
      tension += 7;
      reasons.push("focus_deep");
    }
  } else if (idleSec >= cfg.restIdleSec) {
    mood = "recharging";
    valence += 8;
    energy += 10;
    focus -= 4;
    reasons.push("rest_recharge");
  }

  if (cpuUsage >= cfg.highCpuThreshold) {
    tension += 15;
    energy -= 7;
    if (mood !== "deep_focus" && mood !== "flow") {
      mood = "strained";
    }
    reasons.push("cpu_high");
  }

  if (hasMusic) {
    valence += cfg.musicValenceBoost;
    energy += cfg.musicEnergyBoost;
    reasons.push("music_boost");
  }

  if (isLateNight) {
    energy -= 12;
    valence -= 4;
    tension += 4;
    if (!isWorking) {
      mood = "sleepy";
    }
    reasons.push("late_night");
  }

  valence = clamp(Math.round(valence), 0, 100);
  energy = clamp(Math.round(energy), 0, 100);
  focus = clamp(Math.round(focus), 0, 100);
  tension = clamp(Math.round(tension), 0, 100);

  const output = {
    mood,
    label: moodLabel(mood),
    valence,
    energy,
    focus,
    tension,
    focusStage,
    source: "engine",
    reasons: reasons.slice(0, 8),
  };

  const patch = normalizeOverride(override);
  if (!patch) return output;
  const mergedMood = patch.mood || output.mood;
  const merged = {
    ...output,
    ...patch,
    mood: mergedMood,
    label: patch.label || moodLabel(mergedMood),
    source: "override",
  };
  if (patch.reason) {
    merged.reasons = [...output.reasons, `override:${patch.reason}`].slice(-8);
  }
  return merged;
}

module.exports = {
  computePetEmotion,
};
