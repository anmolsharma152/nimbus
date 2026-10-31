"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { API_BASE } from "@/lib/api";

export interface UserProfile {
  id: number;
  github_id: string;
  username: string;
  display_name: string;
  email: string | null;
  avatar_url: string | null;
  tier: string;
  onboarding_completed: boolean;
  has_github_token: boolean;
  created_at?: string;
}

interface AuthContextType {
  user: UserProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: () => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const apiBase = API_BASE;

  // Resolves to the signed-in user, or null; never rejects
  const loadUser = useCallback(async (): Promise<UserProfile | null> => {
    try {
      const res = await fetch(`${apiBase}/api/auth/me`, {
        credentials: "include", // send HTTP-only session cookie
      });
      const data = res.ok ? await res.json() : null;
      return data?.authenticated && data.user ? data.user : null;
    } catch (err) {
      console.warn("Auth status check:", err);
      return null;
    }
  }, [apiBase]);

  const refreshUser = useCallback(async () => {
    setUser(await loadUser());
    setIsLoading(false);
  }, [loadUser]);

  useEffect(() => {
    let active = true;
    loadUser().then((profile) => {
      if (!active) return;
      setUser(profile);
      setIsLoading(false);
    });
    return () => {
      active = false;
    };
  }, [loadUser]);

  const login = () => {
    // Full navigation: /api/* is proxied to the backend, which redirects to GitHub (not a Next page)
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `${apiBase}/api/auth/github/login`;
  };

  const logout = async () => {
    try {
      await fetch(`${apiBase}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch (err) {
      console.warn("Logout error:", err);
    } finally {
      setUser(null);
      // Full reload on purpose: drops all client state from the signed-in session
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = "/";
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
