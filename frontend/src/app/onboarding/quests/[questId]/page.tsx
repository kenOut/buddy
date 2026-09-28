import { QuestWorkspace } from "@/components/quests/QuestWorkspace";

export default async function QuestWorkspacePage({
  params,
}: PageProps<"/onboarding/quests/[questId]">) {
  const { questId } = await params;
  return <QuestWorkspace questId={questId} />;
}
