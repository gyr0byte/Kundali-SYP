"use client";

import Link from "next/link";
import React from "react";
import type { AuthLocale, AuthMessages } from "@/lib/auth/ui-helpers";

interface AuthPanelLayoutProps {
  locale: AuthLocale;
  onLocaleChange: (next: AuthLocale) => void;
  messages: AuthMessages;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}

export function AuthPanelLayout({
  locale,
  onLocaleChange,
  messages,
  title,
  subtitle,
  children,
}: AuthPanelLayoutProps) {
  return (
    <div
      lang={locale}
      className="flex min-h-screen flex-col bg-[var(--kundali-cream)] text-[var(--kundali-ink)]"
    >
      <a
        href="#auth-form-panel"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-[var(--kundali-navy)] focus:px-3 focus:py-2 focus:text-xs focus:font-semibold focus:text-[var(--kundali-cream)]"
      >
        {messages.skipToForm}
      </a>

      <header className="border-b-2 border-[var(--kundali-emerald)] bg-[var(--kundali-navy)] px-4 py-2.5 text-[var(--kundali-cream)] sm:px-6">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-4">
            <Link href="/user" className="flex items-baseline gap-2.5 hover:opacity-90">
              <span className="text-base font-bold tracking-tight">{messages.brandName}</span>
              <span className="text-sm font-semibold text-[#D8E2EC]">{messages.brandNative}</span>
            </Link>
            <Link
              href="/user"
              className="inline-flex min-h-[36px] items-center rounded border border-[#486581] bg-[#1D3B56] px-3 py-1 text-xs font-semibold text-[#F7F6F1] hover:bg-[#24496B]"
            >
              {messages.backToWorkspace}
            </Link>
          </div>

          <div
            className="inline-flex overflow-hidden rounded border border-[#486581]"
            role="group"
            aria-label={messages.localeLabel}
          >
            {(["en", "ne"] as const).map((loc) => (
              <button
                key={loc}
                type="button"
                aria-pressed={locale === loc}
                onClick={() => onLocaleChange(loc)}
                className={`min-h-[36px] px-3 py-1 text-xs font-semibold ${
                  locale === loc
                    ? "bg-[#F7F6F1] text-[#13293D]"
                    : "text-[#D8E2EC] hover:bg-[#1D3B56]"
                }`}
              >
                {loc === "en" ? "EN" : "नेपाली"}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1440px] flex-1 items-start justify-center px-4 py-8 sm:px-6 sm:py-12">
        <section
          id="auth-form-panel"
          aria-labelledby="auth-panel-heading"
          className="w-full max-w-md rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)]"
        >
          <div className="border-b border-[var(--kundali-border-subtle)] bg-[var(--kundali-strip)] px-5 py-4 sm:px-6">
            <p className="inline-block rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-2 py-0.5 font-mono text-[11px] font-medium text-[var(--kundali-emerald)]">
              {messages.observatoryBadge}
            </p>
            <h1
              id="auth-panel-heading"
              className="mt-2.5 text-xl font-bold tracking-tight text-[var(--kundali-navy)]"
            >
              {title}
            </h1>
            <p className="mt-1 text-xs leading-relaxed text-[var(--kundali-muted)]">{subtitle}</p>
          </div>

          <div className="p-5 sm:p-6">{children}</div>
        </section>
      </main>
    </div>
  );
}
