/** The mascot's in-story name — the product/app is still "Buddy"; this is
 * who Buddy is when he introduces himself. */
export const BUDDY_NAME = "Heimdal of Kowri";

export type BuddyState =
  | "welcome"
  | "friendly"
  | "guide"
  | "curious"
  | "focused"
  | "thinking"
  | "encouraging"
  | "success"
  | "celebrating";

export type EyeVariant = "normal" | "wide" | "happy" | "soft" | "focused" | "sparkle" | "thinking";
export type MouthVariant =
  | "smile"
  | "grin"
  | "neutral"
  | "open-smile"
  | "small-o"
  | "determined";

export interface BuddyPose {
  /** Whole-body tilt, in degrees. */
  bodyTilt: number;
  /** Per-arm rotation, in degrees, pivoted at the shoulder. */
  leftArmRotate: number;
  rightArmRotate: number;
  /** Idle bob amplitude in px — 0 keeps Buddy essentially still. */
  bobAmplitude: number;
  /** Idle bob duration in seconds — lower feels more energetic. */
  bobDuration: number;
  /** Whether the raised arm should read as a wave (adds a wag motion). */
  waving?: boolean;
}

export interface BuddyStateConfig {
  eyes: EyeVariant;
  mouth: MouthVariant;
  pose: BuddyPose;
  /** Soft glow behind Buddy — undefined means no glow. */
  glow?: {
    color: string;
    intensity: number; // 0–1
  };
}

const baseIdle = { bobAmplitude: 6, bobDuration: 4 };

export const BUDDY_STATES: Record<BuddyState, BuddyStateConfig> = {
  welcome: {
    eyes: "happy",
    mouth: "grin",
    pose: { bodyTilt: -2, leftArmRotate: -10, rightArmRotate: 35, waving: true, ...baseIdle },
  },
  friendly: {
    eyes: "normal",
    mouth: "smile",
    pose: { bodyTilt: 0, leftArmRotate: -6, rightArmRotate: 6, ...baseIdle },
  },
  guide: {
    eyes: "soft",
    mouth: "smile",
    pose: { bodyTilt: -3, leftArmRotate: -6, rightArmRotate: -18, ...baseIdle },
    glow: { color: "var(--buddy-cyan)", intensity: 0.18 },
  },
  curious: {
    eyes: "wide",
    mouth: "small-o",
    pose: { bodyTilt: 5, leftArmRotate: -4, rightArmRotate: 4, bobAmplitude: 4, bobDuration: 3.4 },
  },
  focused: {
    eyes: "focused",
    mouth: "determined",
    pose: { bodyTilt: 0, leftArmRotate: -2, rightArmRotate: 2, bobAmplitude: 3, bobDuration: 5 },
    glow: { color: "var(--buddy-cyan)", intensity: 0.14 },
  },
  thinking: {
    eyes: "thinking",
    mouth: "small-o",
    pose: { bodyTilt: -4, leftArmRotate: -8, rightArmRotate: -55, bobAmplitude: 3, bobDuration: 4.5 },
  },
  encouraging: {
    eyes: "happy",
    mouth: "grin",
    pose: { bodyTilt: -2, leftArmRotate: -35, rightArmRotate: 10, bobAmplitude: 7, bobDuration: 3.2 },
    glow: { color: "var(--buddy-aurora)", intensity: 0.2 },
  },
  success: {
    eyes: "happy",
    mouth: "open-smile",
    pose: { bodyTilt: 0, leftArmRotate: -45, rightArmRotate: 45, bobAmplitude: 8, bobDuration: 2.8 },
    glow: { color: "var(--buddy-aurora)", intensity: 0.28 },
  },
  celebrating: {
    eyes: "sparkle",
    mouth: "open-smile",
    pose: { bodyTilt: 0, leftArmRotate: -55, rightArmRotate: 55, bobAmplitude: 10, bobDuration: 2.2 },
    glow: { color: "var(--buddy-sunrise)", intensity: 0.32 },
  },
};
