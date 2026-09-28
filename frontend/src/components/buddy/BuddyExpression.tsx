import type { EyeVariant, MouthVariant } from "@/components/buddy/buddyStates";

/**
 * Pure presentational face — eyes + mouth only. Positioned to sit on the
 * head circle drawn by BuddyIllustration (head center at 100,55, r=42).
 */
export function BuddyExpression({
  eyes,
  mouth,
}: {
  eyes: EyeVariant;
  mouth: MouthVariant;
}) {
  return (
    <>
      <BuddyEyes variant={eyes} />
      <BuddyMouth variant={mouth} />
    </>
  );
}

function BuddyEyes({ variant }: { variant: EyeVariant }) {
  switch (variant) {
    case "wide":
      return (
        <>
          <circle cx="84" cy="51" r="9" fill="white" />
          <circle cx="116" cy="51" r="9" fill="white" />
          <circle cx="85" cy="52" r="4" fill="var(--buddy-navy)" />
          <circle cx="117" cy="52" r="4" fill="var(--buddy-navy)" />
        </>
      );
    case "happy":
      return (
        <>
          <path
            d="M77 52 Q84 42 91 52"
            stroke="white"
            strokeWidth="5"
            strokeLinecap="round"
            fill="none"
          />
          <path
            d="M109 52 Q116 42 123 52"
            stroke="white"
            strokeWidth="5"
            strokeLinecap="round"
            fill="none"
          />
        </>
      );
    case "soft":
      return (
        <>
          <circle cx="84" cy="53" r="6" fill="white" />
          <circle cx="116" cy="53" r="6" fill="white" />
          <circle cx="84.5" cy="53.5" r="2.6" fill="var(--buddy-navy)" />
          <circle cx="116.5" cy="53.5" r="2.6" fill="var(--buddy-navy)" />
        </>
      );
    case "focused":
      return (
        <>
          <rect x="78" y="50" width="14" height="6" rx="3" fill="white" />
          <rect x="110" y="50" width="14" height="6" rx="3" fill="white" />
          <rect x="83" y="50.5" width="5" height="5" rx="1.5" fill="var(--buddy-navy)" />
          <rect x="115" y="50.5" width="5" height="5" rx="1.5" fill="var(--buddy-navy)" />
        </>
      );
    case "thinking":
      return (
        <>
          <circle cx="84" cy="52" r="7" fill="white" />
          <circle cx="116" cy="49" r="7" fill="white" />
          <circle cx="86" cy="52" r="3" fill="var(--buddy-navy)" />
          <circle cx="118" cy="47" r="3" fill="var(--buddy-navy)" />
        </>
      );
    case "sparkle":
      return (
        <>
          <circle cx="84" cy="52" r="7" fill="white" />
          <circle cx="116" cy="52" r="7" fill="white" />
          <circle cx="85" cy="53" r="3" fill="var(--buddy-navy)" />
          <circle cx="117" cy="53" r="3" fill="var(--buddy-navy)" />
          <circle cx="82" cy="49" r="1.4" fill="white" />
          <circle cx="114" cy="49" r="1.4" fill="white" />
        </>
      );
    case "normal":
    default:
      return (
        <>
          <circle cx="84" cy="52" r="7" fill="white" />
          <circle cx="116" cy="52" r="7" fill="white" />
          <circle cx="84" cy="52" r="3" fill="var(--buddy-navy)" />
          <circle cx="116" cy="52" r="3" fill="var(--buddy-navy)" />
        </>
      );
  }
}

function BuddyMouth({ variant }: { variant: MouthVariant }) {
  switch (variant) {
    case "grin":
      return (
        <path
          d="M83 68 Q100 84 117 68"
          stroke="white"
          strokeWidth="4.5"
          strokeLinecap="round"
          fill="none"
        />
      );
    case "open-smile":
      return (
        <path
          d="M82 67 Q100 90 118 67 Q100 80 82 67 Z"
          fill="white"
          opacity="0.95"
        />
      );
    case "small-o":
      return <ellipse cx="100" cy="71" rx="5" ry="6" fill="white" />;
    case "determined":
      return (
        <path
          d="M88 71 Q100 68 112 71"
          stroke="white"
          strokeWidth="4"
          strokeLinecap="round"
          fill="none"
        />
      );
    case "neutral":
      return (
        <path d="M90 70 L110 70" stroke="white" strokeWidth="4" strokeLinecap="round" />
      );
    case "smile":
    default:
      return (
        <path
          d="M86 68 Q100 78 114 68"
          stroke="white"
          strokeWidth="4"
          strokeLinecap="round"
          fill="none"
        />
      );
  }
}
