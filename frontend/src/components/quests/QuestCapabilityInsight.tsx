import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { FadeIn } from "@/components/animations/FadeIn";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { CapabilityEvidenceStrength, QuestEvaluationResult } from "@/lib/types";

const LEVEL_COPY: Record<CapabilityEvidenceStrength, string> = {
  DEVELOPING: "building",
  CAPABLE: "getting stronger at",
  STRONG: "showing real strength in",
};

const LEVEL_TONE: Record<CapabilityEvidenceStrength, "neutral" | "info" | "success"> = {
  DEVELOPING: "neutral",
  CAPABLE: "info",
  STRONG: "success",
};

/**
 * Same three-beat structure Phase 3A's CapabilityInsight.tsx already
 * proved for Mission (What Buddy Observed -> Capability Insight ->
 * Recommended Focus), adapted to the Quest evaluation contract. Every
 * word displayed here comes from the backend's QuestEvaluationResult —
 * there is no field on that type that could carry a hidden
 * expected_answer/reference_solution, so there's nothing to accidentally
 * leak by rendering it directly.
 */
export function QuestCapabilityInsight({ result }: { result: QuestEvaluationResult }) {
  return (
    <div className="flex flex-col gap-4">
      <ObservationCard summary={result.summary} strengths={result.strengths} developmentAreas={result.development_areas} />
      {result.capabilities.length > 0 && <CapabilitySignalsCard capabilities={result.capabilities} />}
      <RecommendedFocusCard recommendedFocus={result.recommended_focus} />
    </div>
  );
}

function ObservationCard({
  summary,
  strengths,
  developmentAreas,
}: {
  summary: string;
  strengths: string[];
  developmentAreas: string[];
}) {
  return (
    <FadeIn duration={0.4}>
      <Card>
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 shrink-0">
            <BuddyIllustration state="curious" />
          </div>
          <div className="flex-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
              What Buddy observed
            </p>
            <p className="mt-2 text-sm text-buddy-text-primary">{summary}</p>

            {strengths.length > 0 && (
              <ul className="mt-3 space-y-1">
                {strengths.map((s, i) => (
                  <li key={i} className="flex gap-2 text-sm text-buddy-text-secondary">
                    <span aria-hidden="true" className="text-buddy-aurora">
                      +
                    </span>
                    {s}
                  </li>
                ))}
              </ul>
            )}
            {developmentAreas.length > 0 && (
              <ul className="mt-2 space-y-1">
                {developmentAreas.map((d, i) => (
                  <li key={i} className="flex gap-2 text-sm text-buddy-text-secondary">
                    <span aria-hidden="true" className="text-buddy-sunrise">
                      →
                    </span>
                    {d}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Card>
    </FadeIn>
  );
}

function CapabilitySignalsCard({
  capabilities,
}: {
  capabilities: { capability: string; level: CapabilityEvidenceStrength; confidence: number }[];
}) {
  return (
    <FadeIn duration={0.4} delay={0.1}>
      <Card>
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 shrink-0">
            <BuddyIllustration state="encouraging" />
          </div>
          <div className="flex-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
              Capability signals
            </p>
            <ul className="mt-2 flex flex-col gap-2">
              {capabilities.map((c) => (
                <li key={c.capability} className="flex items-center gap-2 text-sm text-buddy-text-primary">
                  <Badge tone={LEVEL_TONE[c.level]}>{c.level.toLowerCase()}</Badge>
                  <span>
                    You&rsquo;re {LEVEL_COPY[c.level]} {c.capability.replace(/_/g, " ")}.
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Card>
    </FadeIn>
  );
}

function RecommendedFocusCard({ recommendedFocus }: { recommendedFocus: string }) {
  return (
    <FadeIn duration={0.4} delay={0.2}>
      <Card>
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 shrink-0">
            <BuddyIllustration state="guide" />
          </div>
          <div className="flex-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
              Recommended focus
            </p>
            <p className="mt-2 text-sm text-buddy-text-primary">{recommendedFocus}</p>
          </div>
        </div>
      </Card>
    </FadeIn>
  );
}
