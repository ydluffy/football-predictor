import { access, readFile } from "node:fs/promises";
import path from "node:path";
import { localArtifactsEnabled } from "@/lib/localArtifacts";

export type DailyOverridePayload = Record<string, unknown>;
export type TaskRegistryPayload = Record<string, unknown>;
export type ControllerStatePayload = Record<string, unknown>;

function dataDirCandidates() {
  if (!localArtifactsEnabled()) return [];
  const cwd = process.cwd();
  return [
    path.resolve(cwd, "..", "football-predictor", "artifacts", "data"),
    path.resolve(cwd, "football-predictor", "artifacts", "data"),
  ];
}

async function firstExistingDir(paths: string[]) {
  for (const candidate of paths) {
    try {
      await access(candidate);
      return candidate;
    } catch {}
  }
  return null;
}

async function readJson(filePath: string) {
  const raw = await readFile(/* turbopackIgnore: true */ filePath, "utf8");
  return JSON.parse(raw) as Record<string, unknown>;
}

export async function loadDailyOverrideBySalesDay(salesDay: string): Promise<DailyOverridePayload | null> {
  const dir = await firstExistingDir(dataDirCandidates());
  if (!dir) return null;
  const filePath = path.join(/* turbopackIgnore: true */ dir, `sporttery_daily_schedule_override_${salesDay}.json`);
  try {
    await access(filePath);
  } catch {
    return null;
  }
  return readJson(filePath);
}

export async function loadTaskRegistryBySalesDay(salesDay: string): Promise<TaskRegistryPayload | null> {
  const dir = await firstExistingDir(dataDirCandidates());
  if (!dir) return null;
  const filePath = path.join(/* turbopackIgnore: true */ dir, `sporttery_task_registry_${salesDay}.json`);
  try {
    await access(filePath);
  } catch {
    return null;
  }
  return readJson(filePath);
}

export async function loadControllerState(): Promise<ControllerStatePayload | null> {
  const dir = await firstExistingDir(dataDirCandidates());
  if (!dir) return null;
  const filePath = path.join(/* turbopackIgnore: true */ dir, "football_automation_controller_state.json");
  try {
    await access(filePath);
  } catch {
    return null;
  }
  return readJson(filePath);
}
