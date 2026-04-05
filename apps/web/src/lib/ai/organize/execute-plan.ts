import { relay, RelayError } from "@/lib/relay";
import type { OrganizationPlan, OrganizeAction, EnhancedProjectState } from "@studio-ai/types";

export interface ExecutionResult {
  totalActions: number;
  completedActions: number;
  failures: { action: OrganizeAction; error: string }[];
}

export async function executePlan(
  userId: string,
  plan: OrganizationPlan,
  onProgress?: (completed: number, total: number) => void,
): Promise<ExecutionResult> {
  const result: ExecutionResult = {
    totalActions: plan.actions.length,
    completedActions: 0,
    failures: [],
  };

  for (const action of plan.actions) {
    try {
      const response = await relay(userId, action.type, action.params);
      if (!response.success) {
        result.failures.push({ action, error: response.error ?? "Unknown error" });
      }
    } catch (e) {
      const message = e instanceof RelayError ? e.message : "Relay failed";
      result.failures.push({ action, error: message });
    }

    result.completedActions++;
    onProgress?.(result.completedActions, result.totalActions);
  }

  return result;
}

export async function validateStateBeforeExecution(
  userId: string,
  expectedChannelCount: number,
): Promise<{ valid: boolean; currentChannelCount: number }> {
  try {
    const response = await relay(userId, "get_project_state", {});
    if (!response.success) {
      return { valid: false, currentChannelCount: -1 };
    }
    const state = response.data as EnhancedProjectState;
    return {
      valid: state.channels.length === expectedChannelCount,
      currentChannelCount: state.channels.length,
    };
  } catch {
    return { valid: false, currentChannelCount: -1 };
  }
}
