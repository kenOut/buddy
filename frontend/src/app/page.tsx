import Link from "next/link";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { Button } from "@/components/ui/Button";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-1 flex-col items-center justify-center gap-8 px-6 text-center">
      <div className="h-40 w-40">
        <BuddyIllustration state="welcome" className="h-full w-full" />
      </div>
      <div className="space-y-3">
        <h1 className="font-heading text-3xl font-bold text-buddy-navy sm:text-4xl">Meet Buddy</h1>
        <p className="mx-auto max-w-md text-sm text-buddy-text-secondary sm:text-base">
          Kowri&rsquo;s digital workplace companion — guiding new hires from Day One to ready to
          work.
        </p>
        <p className="mx-auto max-w-md text-xs text-buddy-muted">
          Making financial services accessible to everyone, everywhere in Africa.
        </p>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Link href="/onboarding">
          <Button>Start onboarding</Button>
        </Link>
        <Link href="/admin">
          <Button variant="secondary">Manager portal</Button>
        </Link>
      </div>
    </main>
  );
}
