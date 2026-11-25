"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import {
  createAuthSessionManager,
  type AuthMutationResult,
  type AuthSessionManager,
  type AuthSessionSnapshot,
  type LogoutAllResult,
  type LogoutResult,
} from "@/lib/auth/session-client";

export interface AuthSessionContextValue extends AuthSessionSnapshot {
  getSnapshot: () => AuthSessionSnapshot;
  getAccessToken: () => Promise<string | null>;
  refreshSession: (options?: { force?: boolean }) => Promise<string | null>;
  onUnauthorizedRefresh: (failedToken?: string) => Promise<string | null>;
  retrySession: () => Promise<AuthSessionSnapshot>;
  register: (email: string, password: string) => Promise<AuthMutationResult>;
  login: (email: string, password: string) => Promise<AuthMutationResult>;
  logout: () => Promise<LogoutResult>;
  logoutAll: () => Promise<LogoutAllResult>;
}

const SERVER_SNAPSHOT: AuthSessionSnapshot = {
  status: "checking",
  user: null,
  isAuthenticated: false,
  error: null,
  hasRecoverableSession: false,
};

let browserSharedManager: AuthSessionManager | null = null;

function getDefaultAuthSessionManager(): AuthSessionManager {
  if (typeof window === "undefined") {
    return createAuthSessionManager();
  }
  if (!browserSharedManager) {
    browserSharedManager = createAuthSessionManager();
  }
  return browserSharedManager;
}

const AuthSessionContext = createContext<AuthSessionContextValue | null>(null);

interface AuthSessionProviderProps {
  children: React.ReactNode;
  /** Optional injected session manager for tests or custom configuration. */
  manager?: AuthSessionManager;
}

export function AuthSessionProvider({ children, manager }: AuthSessionProviderProps) {
  const [activeManager] = useState<AuthSessionManager>(
    () => manager ?? getDefaultAuthSessionManager()
  );

  const subscribe = useCallback(
    (onStoreChange: () => void) => activeManager.subscribe(onStoreChange),
    [activeManager]
  );
  const getSnapshot = useCallback(() => activeManager.getSnapshot(), [activeManager]);
  const getServerSnapshot = useCallback(
    () => (manager ? manager.getSnapshot() : SERVER_SNAPSHOT),
    [manager]
  );

  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  useEffect(() => {
    void activeManager.bootstrap();
  }, [activeManager]);

  const contextValue = useMemo<AuthSessionContextValue>(
    () => ({
      ...snapshot,
      getSnapshot: () => activeManager.getSnapshot(),
      getAccessToken: () => activeManager.getAccessToken(),
      refreshSession: (options) => activeManager.refreshSession(options),
      onUnauthorizedRefresh: (failedToken) => activeManager.refreshOnUnauthorized(failedToken),
      retrySession: () => activeManager.retrySession(),
      register: (email, password) => activeManager.register(email, password),
      login: (email, password) => activeManager.login(email, password),
      logout: () => activeManager.logout(),
      logoutAll: () => activeManager.logoutAll(),
    }),
    [activeManager, snapshot]
  );

  return (
    <AuthSessionContext.Provider value={contextValue}>
      {children}
    </AuthSessionContext.Provider>
  );
}

export function useAuthSession(): AuthSessionContextValue {
  const ctx = useContext(AuthSessionContext);
  if (!ctx) {
    throw new Error("useAuthSession must be used inside an AuthSessionProvider.");
  }
  return ctx;
}

export function useOptionalAuthSession(): AuthSessionContextValue | null {
  return useContext(AuthSessionContext);
}
