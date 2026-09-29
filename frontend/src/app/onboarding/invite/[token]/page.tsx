import { InviteExchange } from "@/components/onboarding/InviteExchange";

export default async function InvitePage({
  params,
}: PageProps<"/onboarding/invite/[token]">) {
  const { token } = await params;
  return <InviteExchange token={token} />;
}
