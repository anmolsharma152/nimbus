"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import styles from "./settings.module.css";
import { useAuth } from "../../context/AuthContext";

interface CredentialStatus {
  provider: string;
  configured: boolean;
  updated_at: string | null;
}

export default function SettingsPage() {
  const { user, isAuthenticated, isLoading: isAuthLoading } = useAuth();
  const [credentials, setCredentials] = useState<CredentialStatus[]>([]);
  const [inputValues, setInputValues] = useState<{ [key: string]: string }>({});
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";

  const fetchCredentials = async () => {
    if (!isAuthenticated) return;
    try {
      const res = await fetch(`${apiBase}/api/settings/credentials`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setCredentials(data);
        }
      }
    } catch (err) {
      console.warn("Failed to load credentials:", err);
    }
  };

  useEffect(() => {
    fetchCredentials();
  }, [isAuthenticated, apiBase]);

  const handleSaveCredential = async (provider: string) => {
    const val = inputValues[provider]?.trim();
    if (!val) return;

    setLoading(true);
    setStatusMsg(null);

    try {
      const res = await fetch(`${apiBase}/api/settings/credentials/${provider}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ value: val }),
      });

      if (res.ok) {
        setStatusMsg(`✓ Saved ${provider} credential to encrypted vault.`);
        setInputValues((prev) => ({ ...prev, [provider]: "" }));
        fetchCredentials();
      } else {
        const err = await res.json();
        setStatusMsg(`❌ Failed: ${err.detail || "Error saving key"}`);
      }
    } catch (err: any) {
      setStatusMsg(`❌ Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCredential = async (provider: string) => {
    if (!confirm(`Are you sure you want to remove the stored ${provider} key from your vault?`)) return;

    setLoading(true);
    setStatusMsg(null);

    try {
      const res = await fetch(`${apiBase}/api/settings/credentials/${provider}`, {
        method: "DELETE",
        credentials: "include",
      });

      if (res.ok) {
        setStatusMsg(`✓ Removed ${provider} credential.`);
        fetchCredentials();
      }
    } catch (err: any) {
      setStatusMsg(`❌ Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const providerMeta: { [key: string]: { name: string; tier: string; desc: string; placeholder: string } } = {
    gemini: {
      name: "Google Gemini (BYOK)",
      tier: "Tier 1",
      desc: "Primary agent model architecture. Overrides default server key with your personal Google AI Studio key.",
      placeholder: "AIzaSy...",
    },
    groq: {
      name: "Groq Cloud",
      tier: "Tier 2",
      desc: "Secondary failover pool executing openai/gpt-oss-120b on ultra-fast LPU inference.",
      placeholder: "gsk_...",
    },
    openrouter: {
      name: "OpenRouter",
      tier: "Tier 3",
      desc: "Tertiary failover accessing open weights models like Cohere North Mini Code and Gemma.",
      placeholder: "sk-or-v1-...",
    },
    github_pat: {
      name: "GitHub Personal Access Token (PAT)",
      tier: "Git & PRs",
      desc: "Fine-grained personal access token override for private repository cloning and user-attributed Draft PR dispatch.",
      placeholder: "github_pat_... or ghp_...",
    },
  };

  return (
    <main className={styles.container}>
      <header className={styles.header}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>Settings &amp; Credential Vault</h1>
        </div>
        <p className={styles.subtitle}>
          Manage your personal BYOK LLM API keys and GitHub tokens. All secrets are encrypted at rest with Fernet AES-256 before being written to PostgreSQL.
        </p>
      </header>

      {/* Account Info Section */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Connected Account</h2>
        {isAuthenticated && user ? (
          <div className={styles.profileCard}>
            <div className={styles.profileInfo}>
              {user.avatar_url ? (
                <img src={user.avatar_url} alt={user.username} className={styles.avatar} />
              ) : (
                <div className={styles.avatar} style={{ background: "#4f46e5" }} />
              )}
              <div className={styles.nameBlock}>
                <span className={styles.name}>{user.display_name || user.username}</span>
                <span className={styles.username}>@{user.username} • {user.email || "No public email"}</span>
              </div>
            </div>
            <span className={styles.tierBadge}>{user.tier} Tier</span>
          </div>
        ) : (
          <div className={styles.profileCard}>
            <div className={styles.nameBlock}>
              <span className={styles.name}>Not Signed In</span>
              <span className={styles.username}>Sign in with GitHub to access your encrypted credential vault.</span>
            </div>
            <Link
              href="/login"
              style={{
                background: "#ffffff",
                color: "#09090b",
                fontWeight: 600,
                fontSize: "0.85rem",
                padding: "8px 16px",
                borderRadius: "8px",
                textDecoration: "none",
              }}
            >
              Sign In
            </Link>
          </div>
        )}
      </section>

      {/* Encrypted Vault Section */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Encrypted AI &amp; Git Credentials</h2>

        {statusMsg && (
          <div style={{ marginBottom: "16px", padding: "10px 14px", borderRadius: "8px", background: "rgba(255, 255, 255, 0.05)", fontSize: "0.85rem", color: "#f4f4f5" }}>
            {statusMsg}
          </div>
        )}

        <div className={styles.vaultGrid}>
          {["gemini", "groq", "openrouter", "github_pat"].map((providerKey) => {
            const meta = providerMeta[providerKey];
            const statusItem = credentials.find((c) => c.provider === providerKey);
            const isConfigured = statusItem?.configured ?? false;

            return (
              <div key={providerKey} className={styles.vaultCard}>
                <div className={styles.vaultCardHeader}>
                  <div className={styles.providerTitle}>
                    <span>{meta.name}</span>
                    <span style={{ fontSize: "0.72rem", color: "#818cf8", fontFamily: "monospace" }}>[{meta.tier}]</span>
                  </div>
                  <span className={`${styles.statusPill} ${isConfigured ? styles.configured : styles.notConfigured}`}>
                    {isConfigured ? "● Configured" : "○ Not Configured"}
                  </span>
                </div>

                <p className={styles.helpText}>{meta.desc}</p>

                <div className={styles.vaultInputRow}>
                  <input
                    type="password"
                    className={styles.keyInput}
                    placeholder={isConfigured ? "•••••••••••••••• (Leave blank or enter new key)" : meta.placeholder}
                    value={inputValues[providerKey] || ""}
                    onChange={(e) => setInputValues({ ...inputValues, [providerKey]: e.target.value })}
                    disabled={!isAuthenticated || loading}
                  />
                  <button
                    type="button"
                    className={styles.saveBtn}
                    onClick={() => handleSaveCredential(providerKey)}
                    disabled={!isAuthenticated || loading || !inputValues[providerKey]?.trim()}
                  >
                    Save
                  </button>
                  {isConfigured && (
                    <button
                      type="button"
                      className={styles.deleteBtn}
                      onClick={() => handleDeleteCredential(providerKey)}
                      disabled={!isAuthenticated || loading}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </main>
  );
}
