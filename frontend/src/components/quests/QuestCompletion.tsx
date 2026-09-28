import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { Card } from "@/components/ui/Card";
import { SlideUp } from "@/components/animations/SlideUp";

/**
 * The final beat after QuestCapabilityInsight (or, if evaluation hasn't
 * produced anything — e.g. no capability mappings exist, or evaluation
 * hasn't run yet — the only beat). Never claims more than "your work was
 * received" plus whatever real, evidence-backed insight actually exists;
 * no fabricated score.
 */
export function QuestCompletion() {
  return (
    <SlideUp duration={0.4}>
      <Card className="text-center">
        <div className="mx-auto h-16 w-16">
          <BuddyIllustration state="celebrating" />
        </div>
        <h2 className="mt-4 font-heading text-xl font-bold text-buddy-navy">Quest submitted</h2>
        <p className="mx-auto mt-2 max-w-sm text-sm text-buddy-text-secondary">
          You submitted your work successfully. Your manager can now review what you produced.
        </p>
      </Card>
    </SlideUp>
  );
}
