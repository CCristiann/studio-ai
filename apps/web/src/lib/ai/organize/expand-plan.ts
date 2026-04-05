import type {
  AIPlan,
  OrganizationPlan,
  OrganizeAction,
  PreviewGroup,
  EnhancedProjectState,
  RoleGroup,
} from "@repo/types";
import { getChannelColor, getRoleGroupHex } from "./colors";

export function expandPlan(
  aiPlan: AIPlan,
  projectState: EnhancedProjectState,
): OrganizationPlan {
  const actions: OrganizeAction[] = [];
  const groupMap = new Map<RoleGroup, { index: number; oldName: string; newName: string }[]>();

  for (const assignment of aiPlan.channelAssignments) {
    const group = groupMap.get(assignment.roleGroup) ?? [];
    const channel = projectState.channels.find(c => c.index === assignment.index);
    group.push({
      index: assignment.index,
      oldName: channel?.name ?? `Channel ${assignment.index}`,
      newName: assignment.newName,
    });
    groupMap.set(assignment.roleGroup, group);
  }

  for (const [roleGroup, channels] of groupMap) {
    for (let i = 0; i < channels.length; i++) {
      const ch = channels[i];
      const color = getChannelColor(roleGroup, i, channels.length);

      actions.push({ type: "rename_channel", params: { index: ch.index, name: ch.newName } });
      actions.push({ type: "set_channel_color", params: { index: ch.index, color: color.int } });

      const channel = projectState.channels.find(c => c.index === ch.index);
      if (channel && channel.insert >= 0) {
        actions.push({ type: "rename_mixer_track", params: { index: channel.insert, name: ch.newName } });
        actions.push({ type: "set_mixer_track_color", params: { index: channel.insert, color: color.int } });
      }

      const patternIndex = ch.index + 1;
      const pattern = projectState.patterns.find(p => p.index === patternIndex);
      if (pattern) {
        actions.push({ type: "rename_pattern", params: { index: patternIndex, name: ch.newName } });
        actions.push({ type: "set_pattern_color", params: { index: patternIndex, color: color.int } });
      }
    }
  }

  for (const fix of aiPlan.routingFixes) {
    actions.push({ type: "set_channel_insert", params: { index: fix.channelIndex, insert: fix.assignedInsert } });
    const assignment = aiPlan.channelAssignments.find(a => a.index === fix.channelIndex);
    if (assignment) {
      const group = groupMap.get(assignment.roleGroup) ?? [];
      const posInGroup = group.findIndex(c => c.index === fix.channelIndex);
      const color = getChannelColor(assignment.roleGroup, Math.max(posInGroup, 0), group.length);
      actions.push({ type: "rename_mixer_track", params: { index: fix.assignedInsert, name: assignment.newName } });
      actions.push({ type: "set_mixer_track_color", params: { index: fix.assignedInsert, color: color.int } });
    }
  }

  const groups: PreviewGroup[] = [];
  for (const [roleGroup, channels] of groupMap) {
    groups.push({
      roleGroup,
      colorHex: getRoleGroupHex(roleGroup),
      channels,
    });
  }

  const routingFixPreviews = aiPlan.routingFixes.map(fix => {
    const assignment = aiPlan.channelAssignments.find(a => a.index === fix.channelIndex);
    return {
      channelIndex: fix.channelIndex,
      channelName: assignment?.newName ?? `Channel ${fix.channelIndex}`,
      assignedInsert: fix.assignedInsert,
    };
  });

  return {
    actions,
    preview: { groups, routingFixes: routingFixPreviews },
  };
}
