"use strict";

export const COLLECT_COOLDOWN_MS = 24 * 60 * 60 * 1000; // 24h
const STORAGE_KEY = "copilot_last_collect";

/** Returns true if the last collection was less than COOLDOWN ago. */
export function shouldSkipCollection() {
  const lastCollect = parseInt(localStorage.getItem(STORAGE_KEY) || "0", 10);
  return Date.now() - lastCollect < COLLECT_COOLDOWN_MS;
}

/** Marks the current timestamp as the last collection time. */
export function markCollected() {
  localStorage.setItem(STORAGE_KEY, String(Date.now()));
}
