import { OnboardingChrome } from "@/components/onboarding/OnboardingChrome";
import { OnboardingProvider } from "@/lib/onboarding-context";

export default function OnboardingLayout({ children }: LayoutProps<"/onboarding">) {
  return (
    <OnboardingProvider>
      <OnboardingChrome>{children}</OnboardingChrome>
    </OnboardingProvider>
  );
}
