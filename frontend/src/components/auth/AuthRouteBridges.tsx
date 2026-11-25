"use client";

import { useRouter, useSearchParams } from "next/navigation";
import React, { useCallback } from "react";
import { LoginForm } from "@/components/auth/LoginForm";
import { RegisterForm } from "@/components/auth/RegisterForm";
import type { AuthLocale, AuthMessages } from "@/lib/auth/ui-helpers";

interface RouteViewProps {
  messagesByLocale: Record<AuthLocale, AuthMessages>;
}

export function LoginRouteView({ messagesByLocale }: RouteViewProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectParam = searchParams.get("redirect") ?? searchParams.get("next");
  const registeredParam = searchParams.get("registered");

  const handleNavigate = useCallback(
    (href: string) => {
      router.replace(href);
    },
    [router]
  );

  return (
    <LoginForm
      messagesByLocale={messagesByLocale}
      redirectParam={redirectParam}
      registeredParam={registeredParam}
      onNavigate={handleNavigate}
    />
  );
}

export function RegisterRouteView({ messagesByLocale }: RouteViewProps) {
  const router = useRouter();
  const handleNavigate = useCallback(
    (href: string) => {
      router.replace(href);
    },
    [router]
  );

  return <RegisterForm messagesByLocale={messagesByLocale} onNavigate={handleNavigate} />;
}
