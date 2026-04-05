import type { RoleGroup } from "@studio-ai/types";

interface RoleColor {
  base: [number, number, number]; // [R, G, B]
  hex: string;
}

const ROLE_COLORS: Record<RoleGroup, RoleColor> = {
  drums:  { base: [229, 62, 62],   hex: "#E53E3E" },
  bass:   { base: [49, 130, 206],  hex: "#3182CE" },
  leads:  { base: [56, 161, 105],  hex: "#38A169" },
  pads:   { base: [128, 90, 213],  hex: "#805AD5" },
  fx:     { base: [214, 158, 46],  hex: "#D69E2E" },
  vocals: { base: [213, 63, 140],  hex: "#D53F8C" },
  other:  { base: [113, 128, 150], hex: "#718096" },
};

function lighten(rgb: [number, number, number], percent: number): [number, number, number] {
  const factor = percent / 100;
  return [
    Math.round(rgb[0] + (255 - rgb[0]) * factor),
    Math.round(rgb[1] + (255 - rgb[1]) * factor),
    Math.round(rgb[2] + (255 - rgb[2]) * factor),
  ];
}

function rgbToInt(rgb: [number, number, number]): number {
  return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2];
}

function rgbToHex(rgb: [number, number, number]): string {
  return "#" + rgb.map(c => c.toString(16).padStart(2, "0")).join("").toUpperCase();
}

export function getChannelColor(
  roleGroup: RoleGroup,
  positionInGroup: number,
  groupSize: number,
): { int: number; hex: string } {
  const role = ROLE_COLORS[roleGroup];
  const lightenPercent = groupSize <= 1
    ? 0
    : Math.min((positionInGroup / (groupSize - 1)) * 40, 40);
  const rgb = lighten(role.base, lightenPercent);
  return { int: rgbToInt(rgb), hex: rgbToHex(rgb) };
}

export function getRoleGroupHex(roleGroup: RoleGroup): string {
  return ROLE_COLORS[roleGroup].hex;
}
