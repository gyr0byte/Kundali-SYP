import { Suspense } from "react";
import { RegisterRouteView } from "@/components/auth/AuthRouteBridges";
import { RegisterForm } from "@/components/auth/RegisterForm";
import enMessages from "@/i18n/en.json";
import neMessages from "@/i18n/ne.json";
import type { AuthLocale, AuthMessages } from "@/lib/auth/ui-helpers";

export default function RegisterPage() {
  const messagesByLocale: Record<AuthLocale, AuthMessages> = {
    en: enMessages.auth,
    ne: neMessages.auth,
  };

  return (
    <Suspense fallback={<RegisterForm messagesByLocale={messagesByLocale} />}>
      <RegisterRouteView messagesByLocale={messagesByLocale} />
    </Suspense>
  );
}
