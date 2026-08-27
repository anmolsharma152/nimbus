"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";

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

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";

  const refreshUser = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/auth/me`, {
        credentials: "include", // send HTTP-only session cookie
      });

      if (res.ok) {
        const data = await res.json();
        if (data.authenticated && data.user) {
          setUser(data.user);
          return;
        }
      }
      setUser(null);
    } catch (err) {
      console.warn("Auth status check:", err);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = () => {
    // Redirect to backend GitHub OAuth consent screen
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
