// apps/web/src/lib/ai/tools/__tests__/composeTools.test.ts
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/relay", () => ({
  relay: vi.fn(),
  RelayError: class extends Error {},
}));

// organize.ts pulls in heavy modules; mock them so the import doesn't crash
vi.mock("@/lib/ai/organize/analysis-agent", () => ({ runAnalysis: vi.fn() }));
vi.mock("@/lib/ai/organize/organization-agent", () => ({
  runOrganization: vi.fn(),
  runScaffold: vi.fn(),
  adjustPlan: vi.fn(),
}));
vi.mock("@/lib/ai/organize/expand-plan", () => ({ expandPlan: vi.fn() }));
vi.mock("@/lib/ai/organize/execute-plan", () => ({
  executePlan: vi.fn(),
  validateStateBeforeExecution: vi.fn(),
}));

import { composeTools } from "../index";

describe("composeTools", () => {
  it("exposes the migrated tool set with stable names", () => {
    const tools = composeTools("user-1");
    const names = Object.keys(tools).sort();
    // Pinned: changing this list is a public-contract change. Update intentionally.
    expect(names).toEqual([
      "get_project_state",
      "organize_project",
      "play",
      "scaffold_project",
      "set_bpm",
      "set_channel_enabled",
      "set_channel_pan",
      "set_channel_volume",
      "set_mixer_eq",
      "set_mixer_routing",
      "set_pitch",
      "set_track_volume",
      "stop",
    ]);
  });

  it("every tool has a non-empty description", () => {
    const tools = composeTools("user-1");
    for (const [name, t] of Object.entries(tools)) {
      expect((t as any).description, `${name} description`).toBeTruthy();
      expect(typeof (t as any).description).toBe("string");
    }
  });
});
