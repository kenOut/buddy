import { MissionWorkspace } from "@/components/scenes/MissionWorkspace";

export default async function MissionWorkspacePage({
  params,
}: PageProps<"/onboarding/missions/[missionId]">) {
  const { missionId } = await params;
  return <MissionWorkspace missionId={missionId} />;
}
