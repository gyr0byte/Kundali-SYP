import { Suspense } from "react";
import { LoginRouteView } from "@/components/auth/AuthRouteBridges";
import { LoginForm } from "@/components/auth/LoginForm";
import enMessages from "@/i18n/en.json";
import neMessages from "@/i18n/ne.json";
import type { AuthLocale, AuthMessages } from "@/lib/auth/ui-helpers";

export default function LoginPage() {
  const messagesByLocale: Record<AuthLocale, AuthMessages> = {
    en: enMessages.auth,
    ne: neMessages.auth,
  };

  return (
    <Suspense fallback={<LoginForm messagesByLocale={messagesByLocale} />}>
      <LoginRouteView messagesByLocale={messagesByLocale} />
    </Suspense>
  );
}
