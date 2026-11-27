"use client";

import { useEffect, useEffectEvent, useRef, useState, type ReactNode } from "react";
import { useAuthSession } from "@/components/auth/AuthSessionProvider";
import type en from "@/i18n/admin.en.json";
import {
  adminIssue, astrologerStatuses, fetchAdminRecords, fetchAdminTotals, roles, submitAdminAction,
  type AdminAction, type AdminIssue, type AdminQuery, type AdminRecords, type AdminRole, type AstrologerStatus,
} from "@/lib/api/admin";
import type { Locale } from "@/lib/kundali/types";

export type AdminMessages = typeof en;
export type AdminSection = "overview" | "users" | "astrologers" | "audit" | "planned";
type AccessIssue = Extract<AdminIssue, "expired" | "forbidden">;
type Action = { action: AdminAction; id: string; label: string; expected: string };
const limit = 20;
export const adminSheet = "min-w-0 rounded border border-[var(--kundali-border)] bg-white";
export const adminButton = "inline-flex min-h-11 items-center rounded border border-[var(--kundali-border)] bg-white px-3 py-2 text-sm font-semibold text-[var(--kundali-navy)] hover:bg-[var(--kundali-strip)] disabled:opacity-60";
const primary = "min-h-11 rounded bg-[var(--kundali-navy)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--kundali-navy-hover)] disabled:opacity-60";
const selectClass = "min-h-11 rounded border border-[var(--kundali-border)] bg-white px-2 text-sm";

const eventNames = {
  "auth:register": "eventRegister", "auth:lockout": "eventLockout", "auth:token_reuse_detected": "eventReuse",
  "auth:password_change": "eventPassword", "auth:password_reset": "eventReset", "user:deactivate": "eventDeactivate",
  "user:reactivate": "eventReactivate", "astrologer:apply": "eventApply", "astrologer:approve": "eventApprove",
  "astrologer:suspend": "eventSuspend", "profile:create": "eventCreate", "profile:update": "eventUpdate",
  "profile:delete": "eventDelete", other: "other",
} as const;
const targetNames = {
  user: "targetUser", astrologer_profile: "targetAstrologer", birth_profile: "targetBirth", token_family: "targetSession",
} as const;

function AdminTable({ caption, columns, rows }: {
  caption: string;
  columns: string[];
  rows: { id: string; cells: ReactNode[] }[];
}) {
  return (
    <table role="table" className="block w-full text-start text-sm sm:table">
      <caption className="sr-only">{caption}</caption>
      <thead role="rowgroup" className="sr-only bg-[var(--kundali-strip)] sm:not-sr-only sm:table-header-group">
        <tr role="row">
          {columns.map((label) => <th role="columnheader" key={label} scope="col" className="px-3 py-2 text-start font-semibold">{label}</th>)}
        </tr>
      </thead>
      <tbody role="rowgroup" className="block sm:table-row-group">
        {rows.map(({ id, cells }) => (
          <tr role="row" key={id} className="block border-b border-[var(--kundali-border-subtle)] p-3 last:border-b-0 sm:table-row sm:p-0">
            {cells.map((content, index) => (
              <td role="cell" key={columns[index]} className="grid min-w-0 grid-cols-[minmax(5rem,.8fr)_minmax(0,1.2fr)] items-start gap-2 py-1.5 [overflow-wrap:anywhere] sm:table-cell sm:px-3 sm:py-2.5 sm:align-top">
                <span aria-hidden="true" className="font-semibold text-[var(--kundali-muted)] sm:hidden">{columns[index]}</span>
                <div className="min-w-0">{content}</div>
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Confirmation({ target, busy, t, cancel, confirm }: {
  target: Action; busy: boolean; t: AdminMessages; cancel: () => void; confirm: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return (
    <dialog ref={dialog} aria-labelledby="admin-confirm-title" aria-describedby="admin-confirm-consequence"
      onCancel={(event) => { event.preventDefault(); if (!busy) cancel(); }}
      className="m-auto w-[min(28rem,calc(100%-2rem))] rounded border border-[var(--kundali-border)] bg-white p-5 text-[var(--kundali-ink)] shadow-lg backdrop:bg-[var(--kundali-navy)]/55">
      <h2 id="admin-confirm-title" className="text-lg font-semibold">{t[target.action]}</h2>
      <p className="mt-2 font-semibold [overflow-wrap:anywhere]">{target.label}</p>
      <p className="mt-1 font-mono text-xs text-[var(--kundali-muted)] [overflow-wrap:anywhere]">{target.id}</p>
      <p id="admin-confirm-consequence" className="mt-3 text-sm leading-relaxed">{t[`${target.action}Body`]}</p>
      <div className="mt-5 flex flex-wrap justify-end gap-2">
        <button type="button" className={adminButton} disabled={busy} onClick={cancel}>{t.cancel}</button>
        <button type="button" className={primary} disabled={busy} onClick={confirm}>{busy ? t.submitting : t.confirm}</button>
      </div>
      <p role="status" className="sr-only">{busy ? t.submitting : ""}</p>
    </dialog>
  );
}

export function AdminDataView({ section, t, locale, actorId, onDenied }: {
  section: Exclude<AdminSection, "planned">;
  t: AdminMessages;
  locale: Locale;
  actorId: string;
  onDenied: (issue: AccessIssue) => void;
}) {
  const auth = useAuthSession();
  const [role, setRole] = useState<AdminRole | "">("");
  const [activity, setActivity] = useState<"" | "active" | "inactive">("");
  const [status, setStatus] = useState<AstrologerStatus | "">("");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [records, setRecords] = useState<AdminRecords | null>(null);
  const [totals, setTotals] = useState<number[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [target, setTarget] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<"done" | "protected" | "stale" | "mutationError" | null>(null);
  const readRequest = useRef<AbortController | null>(null);
  const mutation = useRef<AbortController | null>(null);
  const query: AdminQuery = section === "users"
    ? { section, role: role || undefined, active: activity ? activity === "active" : undefined }
    : section === "astrologers" ? { section, status: status || undefined } : { section: "audit" };

  const load = useEffectEvent(async (signal: AbortSignal) => section === "overview"
    ? { kind: "totals" as const, data: await fetchAdminTotals(auth, signal) }
    : { kind: "records" as const, data: await fetchAdminRecords(auth, query, limit, offset, signal) });

  useEffect(() => {
    const request = new AbortController();
    readRequest.current = request;
    void load(request.signal).then((result) => {
      if (request.signal.aborted) return;
      if (result.kind === "totals") setTotals(result.data);
      else if (offset > 0 && offset >= result.data.page.total) {
        setOffset(Math.max(0, Math.floor((result.data.page.total - 1) / limit) * limit));
      } else setRecords(result.data);
    }).catch((error: unknown) => {
      if (request.signal.aborted) return;
      const issue = adminIssue(error);
      if (issue === "expired" || issue === "forbidden") onDenied(issue);
      else setLoadFailed(true);
    });
    return () => {
      request.abort();
      if (readRequest.current === request) readRequest.current = null;
    };
  }, [section, role, activity, status, offset, revision, onDenied]);

  useEffect(() => () => mutation.current?.abort(), []);

  function refresh(nextOffset = offset) {
    readRequest.current?.abort();
    setRecords(null);
    setTotals(null);
    setLoadFailed(false);
    setOffset(nextOffset);
    setRevision((previous) => previous + 1);
  }

  async function confirmAction() {
    if (!target || mutation.current || (target.id === actorId && (target.action === "deactivate" || target.action === "approve"))) return;
    const request = new AbortController();
    mutation.current = request;
    setBusy(true);
    let outcome: typeof feedback = "done";
    try {
      // Refresh the same filtered page before changing a record the operator saw.
      const fresh = await fetchAdminRecords(auth, query, limit, offset, request.signal);
      const current = fresh.section === "users"
        ? fresh.page.items.find(({ id }) => id === target.id)
        : fresh.section === "astrologers" ? fresh.page.items.find(({ user_id }) => user_id === target.id) : undefined;
      const signature = current && ("role" in current
        ? JSON.stringify([current.email, current.role, current.is_active])
        : JSON.stringify([current.display_name, current.tradition, current.status]));
      if (signature !== target.expected) outcome = "stale";
      else await submitAdminAction(auth, target.action, target.id, request.signal);
    } catch (error) {
      if (request.signal.aborted) return;
      const issue = adminIssue(error);
      if (issue === "expired" || issue === "forbidden") {
        onDenied(issue);
        return;
      }
      outcome = issue === "failed" ? "mutationError" : issue;
    } finally {
      if (mutation.current === request) mutation.current = null;
      if (!request.signal.aborted) {
        setTarget(null);
        setBusy(false);
      }
    }
    if (!request.signal.aborted) {
      setFeedback(outcome);
      refresh();
    }
  }

  const number = new Intl.NumberFormat(locale);
  const date = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });
  function timestamp(value: string | null) {
    const milliseconds = value ? Date.parse(value) : NaN;
    return Number.isFinite(milliseconds) && value
      ? <time dateTime={value} className="tabular-nums">{date.format(milliseconds)}</time> : t.none;
  }
  const actionButton = (action: Action) => (
    <button type="button" className={adminButton} onClick={() => { setFeedback(null); setTarget(action); }}>{t[action.action]}</button>
  );

  let table: ReactNode;
  if (records?.section === "users") {
    table = <AdminTable caption={t.users} columns={[t.email, t.role, t.status, t.date, t.actions]}
      rows={records.page.items.map((row) => ({
        id: row.id,
        cells: [
          <span key="account" className="font-semibold">{row.email}</span>,
          t[row.role], row.is_active ? t.active : t.inactive, timestamp(row.created_at),
          row.id === actorId ? t.self : actionButton({
            id: row.id, label: row.email, action: row.is_active ? "deactivate" : "reactivate",
            expected: JSON.stringify([row.email, row.role, row.is_active]),
          }),
        ],
      }))} />;
  } else if (records?.section === "astrologers") {
    table = <AdminTable caption={t.astrologers} columns={[t.name, t.tradition, t.status, t.approvalDate, t.actions]}
      rows={records.page.items.map((row) => {
        const base = { id: row.user_id, label: row.display_name, expected: JSON.stringify([row.display_name, row.tradition, row.status]) };
        return { id: row.user_id, cells: [
          <div key="profile"><p className="font-semibold">{row.display_name}</p><p className="font-mono text-xs text-[var(--kundali-muted)]">{row.user_id}</p></div>,
          row.tradition, t[row.status], timestamp(row.approved_at),
          <div key="actions" className="flex flex-wrap gap-1.5">
            {row.status !== "approved" && row.user_id !== actorId ? actionButton({ ...base, action: "approve" }) : null}
            {row.status !== "suspended" ? actionButton({ ...base, action: "suspend" }) : null}
          </div>,
        ] };
      })} />;
  } else if (records?.section === "audit") {
    table = <AdminTable caption={t.audit} columns={[t.date, t.action, t.actor, t.target]}
      rows={records.page.items.map((row) => ({
        id: row.id, cells: [
          timestamp(row.created_at), t[eventNames[row.action]],
          <span key="actor" className="font-mono text-xs">{row.actor_id ?? t.none}</span>,
          row.target_type ? <div key="target">{t[targetNames[row.target_type]]}
            {row.target_id ? <p className="font-mono text-xs">{row.target_id}</p> : null}
          </div> : t.none,
        ],
      }))} />;
  }

  const pagination = records?.page;
  const ready = Boolean(totals || records);
  return (
    <div className="space-y-4">
      {feedback ? <p role={feedback === "done" ? "status" : "alert"} className={`${adminSheet} p-3 text-sm`}>{t[feedback]}</p> : null}
      <section className={adminSheet} aria-label={section === "overview" ? t.totals : t[section]}>
        <div className="flex flex-wrap items-end gap-3 border-b border-[var(--kundali-border)] p-3 sm:px-5">
          {section === "overview" ? <h2 className="text-lg font-semibold">{t.totals}</h2> : null}
          {section === "users" ? (
            <>
              <div className="grid gap-1 text-sm font-semibold"><label htmlFor="admin-role">{t.role}</label>
                <select id="admin-role" className={selectClass} value={role} onChange={(event) => {
                  setRole(roles.find((entry) => entry === event.target.value) ?? ""); refresh(0);
                }}><option value="">{t.all}</option>{roles.map((entry) => <option key={entry} value={entry}>{t[entry]}</option>)}</select>
              </div>
              <div className="grid gap-1 text-sm font-semibold"><label htmlFor="admin-status">{t.status}</label>
                <select id="admin-status" className={selectClass} value={activity} onChange={(event) => {
                  setActivity(event.target.value === "active" ? "active" : event.target.value === "inactive" ? "inactive" : ""); refresh(0);
                }}><option value="">{t.all}</option><option value="active">{t.active}</option><option value="inactive">{t.inactive}</option></select>
              </div>
            </>
          ) : section === "astrologers" ? (
            <div className="grid gap-1 text-sm font-semibold"><label htmlFor="admin-status">{t.status}</label>
              <select id="admin-status" className={selectClass} value={status} onChange={(event) => {
                setStatus(astrologerStatuses.find((entry) => entry === event.target.value) ?? ""); refresh(0);
              }}><option value="">{t.all}</option>{astrologerStatuses.map((entry) => <option key={entry} value={entry}>{t[entry]}</option>)}</select>
            </div>
          ) : null}
          <button type="button" className={`${adminButton} ms-auto`} onClick={() => { setFeedback(null); refresh(); }} disabled={!ready && !loadFailed}>{t.refresh}</button>
        </div>
        {section === "astrologers" || section === "audit" ? (
          <p className="border-b border-[var(--kundali-border-subtle)] px-3 py-2 text-sm leading-relaxed text-[var(--kundali-muted)] sm:px-5">
            {section === "astrologers" ? t.credentialNote : t.auditNote}
          </p>
        ) : null}
        {loadFailed ? <p role="alert" className="p-4 text-sm text-[var(--kundali-crimson)]">{t.failed}</p> : null}
        {!ready && !loadFailed ? <p role="status" className="p-4 text-sm text-[var(--kundali-muted)]">{t.loading}</p> : null}
        {totals ? <dl className="divide-y divide-[var(--kundali-border-subtle)] px-4 sm:px-5">
          {[t.totalUsers, t.totalPending, t.totalAudit].map((label, index) => (
            <div key={label} className="flex items-center justify-between gap-3 py-4">
              <dt className="font-semibold">{label}</dt><dd className="font-mono text-xl tabular-nums">{number.format(totals[index])}</dd>
            </div>
          ))}
        </dl> : null}
        {pagination && (pagination.items.length ? table : <p role="status" className="p-4 text-sm">{t.noRecords}</p>)}
        {pagination && pagination.total > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--kundali-border)] p-3 sm:px-5">
            <p role="status" className="text-sm tabular-nums text-[var(--kundali-muted)]">
              {t.range.replace("{start}", number.format(pagination.items.length ? offset + 1 : 0))
                .replace("{end}", number.format(offset + pagination.items.length)).replace("{total}", number.format(pagination.total))}
            </p>
            <div className="flex gap-2">
              <button type="button" className={adminButton} disabled={offset === 0} onClick={() => refresh(offset - limit)}>{t.previous}</button>
              <button type="button" className={adminButton} disabled={offset + limit >= pagination.total} onClick={() => refresh(offset + limit)}>{t.next}</button>
            </div>
          </div>
        ) : null}
      </section>
      {target ? <Confirmation target={target} busy={busy} t={t} cancel={() => setTarget(null)} confirm={() => void confirmAction()} /> : null}
    </div>
  );
}
