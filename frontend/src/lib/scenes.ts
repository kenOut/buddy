import type { SceneKey } from "@/lib/types";

export interface SceneConfig {
  key: SceneKey;
  slug: string;
  label: string;
  short: string;
}

export const SCENES: SceneConfig[] = [
  { key: "welcome", slug: "welcome", label: "Welcome", short: "Welcome" },
  { key: "department", slug: "department", label: "Your Department", short: "Department" },
  { key: "team", slug: "team", label: "Meet Your Team", short: "Team" },
  { key: "reporting_line", slug: "reporting-line", label: "Reporting Line", short: "Reporting" },
  { key: "role", slug: "role", label: "Your Role", short: "Role" },
  { key: "missions", slug: "missions", label: "Your First Missions", short: "Missions" },
  { key: "assessment", slug: "assessment", label: "Quick Assessment", short: "Assessment" },
  { key: "completion", slug: "completion", label: "You're All Set", short: "Done" },
];

export const sceneBySlug = (slug: string): SceneConfig | undefined =>
  SCENES.find((s) => s.slug === slug);

/**
 * The single source of truth for "which scene is on screen" — derived from
 * the URL rather than duplicated as a literal in each scene page. Returns
 * undefined for non-scene routes (e.g. the bare `/onboarding` index).
 *
 * Uses the segment right after `/onboarding/`, not the last segment, so
 * nested routes (e.g. `/onboarding/missions/[missionId]`) still resolve to
 * their parent scene ("missions") instead of failing to match anything.
 */
export const sceneFromPathname = (pathname: string): SceneConfig | undefined => {
  const segments = pathname.split("/").filter(Boolean);
  const slug = segments[1];
  return slug ? sceneBySlug(slug) : undefined;
};

export const sceneIndex = (key: SceneKey): number => SCENES.findIndex((s) => s.key === key);

export const nextScene = (key: SceneKey): SceneConfig | undefined => SCENES[sceneIndex(key) + 1];

export const prevScene = (key: SceneKey): SceneConfig | undefined => SCENES[sceneIndex(key) - 1];

export const sceneProgress = (key: SceneKey): number =>
  Math.round((sceneIndex(key) / (SCENES.length - 1)) * 100);
