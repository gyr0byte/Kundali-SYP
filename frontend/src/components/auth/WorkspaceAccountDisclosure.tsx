"use client";

import { useEffect, useRef, useState } from "react";
import { useAuthSession } from "./AuthSessionProvider";
import commonEn from "@/i18n/en.json";
import commonNe from "@/i18n/ne.json";
import { classifyLogoutAllOutcome, classifyLogoutOutcome, type LogoutOutcomeBanner } from "@/lib/auth/ui-helpers";
import type { Locale } from "@/lib/kundali/types";

const common = { en: commonEn.userWorkspace, ne: commonNe.userWorkspace };
const button = "inline-flex min-h-11 items-center rounded border border-[var(--kundali-border)] bg-white px-3 py-2 text-sm font-semibold text-[var(--kundali-navy)] hover:bg-[var(--kundali-strip)] disabled:opacity-60";
const primary = "inline-flex min-h-11 items-center justify-center rounded bg-[var(--kundali-navy)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--kundali-navy-hover)] disabled:opacity-60";
const note = "text-sm leading-relaxed text-[var(--kundali-muted)]";

export function WorkspaceAccountDisclosure({ locale, label, onFeedback }: {
  locale: Locale;
  label: string;
  onFeedback: (outcome: LogoutOutcomeBanner) => void;
}) {
  const auth = useAuthSession();
  const labels = common[locale];
  const disclosure = useRef<HTMLDetailsElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (confirm) cancel.current?.focus();
  }, [confirm]);

  function close() {
    if (disclosure.current) {
      disclosure.current.open = false;
      disclosure.current.querySelector("summary")?.focus();
    }
    setConfirm(false);
  }

  async function logout(all: boolean) {
    setBusy(true);
    try {
      onFeedback(all
        ? classifyLogoutAllOutcome(await auth.logoutAll(), labels)
        : classifyLogoutOutcome(await auth.logout(), labels));
    } finally {
      setBusy(false);
      close();
    }
  }

  return (
    <details ref={disclosure} className="group/account relative" onToggle={(event) => {
      if (!event.currentTarget.open) setConfirm(false);
    }} onKeyDown={(event) => {
      if (event.key === "Escape" && disclosure.current?.open) {
        event.stopPropagation();
        close();
      }
    }}>
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded border border-white/35 px-2.5 text-xs font-semibold hover:bg-white/10 [&::-webkit-details-marker]:hidden">
        {label}<span aria-hidden="true">⌄</span>
      </summary>
      <div className="absolute top-full right-0 z-30 mt-2 hidden w-[min(19rem,calc(100vw-1.5rem))] rounded border border-[var(--kundali-border)] bg-white p-2 text-[var(--kundali-ink)] shadow-lg group-open/account:block">
        <p className="border-b border-[var(--kundali-border)] p-2 text-sm font-semibold [overflow-wrap:anywhere]">{auth.user?.email}</p>
        {confirm ? (
          <div role="group" aria-label={labels.logoutConfirmTitle} className="space-y-2 p-2">
            <p className="text-sm font-semibold text-[var(--kundali-crimson)]">{labels.logoutConfirmTitle}</p>
            <p className={note}>{labels.logoutConfirmBody}</p>
            <div className="flex flex-wrap gap-2">
              <button ref={cancel} type="button" className={button} disabled={busy} onClick={close}>{labels.logoutConfirmCancel}</button>
              <button type="button" className={primary} disabled={busy} onClick={() => void logout(true)}>{labels.logoutConfirmProceed}</button>
            </div>
          </div>
        ) : (
          <div className="grid">
            <button type="button" disabled={busy} onClick={() => void logout(false)} className="min-h-11 rounded px-2 text-start text-sm hover:bg-[var(--kundali-strip)]">{busy ? labels.signingOutButton : labels.signOutButton}</button>
            <button type="button" disabled={busy} onClick={() => setConfirm(true)} className="min-h-11 rounded px-2 text-start text-sm text-[var(--kundali-crimson)] hover:bg-[var(--kundali-crimson-bg)]">{labels.signOutAllButton}</button>
          </div>
        )}
      </div>
    </details>
  );
}
