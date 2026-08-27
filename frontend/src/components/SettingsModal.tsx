"use client";

import React, { useState, useEffect } from "react";
import styles from "./SettingsModal.module.css";
import { useAuth } from "../context/AuthContext";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const { user, isAuthenticated } = useAuth();
  const [geminiKey, setGeminiKey] = useState("");
  const [geminiModel, setGeminiModel] = useState("gemini-3.6-flash");
  const [groqKey, setGroqKey] = useState("");
  const [groqModel, setGroqModel] = useState("openai/gpt-oss-120b");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [openrouterModel, setOpenrouterModel] = useState("cohere/north-mini-code:free");
  
  const [configuredProviders, setConfiguredProviders] = useState<{ [key: string]: boolean }>({});
  const [isSaving, setIsSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://nimbus-api-l32h.onrender.com";

  useEffect(() => {
    if (!isOpen) return;

    if (isAuthenticated) {
      // Fetch status from backend credential vault
      fetch(`${apiBase}/api/settings/credentials`, { credentials: "include" })
        .then((res) => (res.ok ? res.json() : []))
        .then((data) => {
          if (Array.isArray(data)) {
            const map: { [key: string]: boolean } = {};
            data.forEach((item: { provider: string; configured: boolean }) => {
              map[item.provider] = item.configured;
            });
            setConfiguredProviders(map);
          }
        })
        .catch((err) => console.warn("Failed to fetch vault credentials:", err));
    }

    if (typeof window !== "undefined") {
      setGeminiModel(localStorage.getItem("nimbus_gemini_model") || "gemini-3.6-flash");
      setGroqModel(localStorage.getItem("nimbus_groq_model") || "openai/gpt-oss-120b");
      setOpenrouterModel(localStorage.getItem("nimbus_openrouter_model") || "cohere/north-mini-code:free");
    }
  }, [isOpen, isAuthenticated, apiBase]);

  if (!isOpen) return null;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);

    try {
      if (typeof window !== "undefined") {
        localStorage.setItem("nimbus_gemini_model", geminiModel);
        localStorage.setItem("nimbus_groq_model", groqModel);
        localStorage.setItem("nimbus_openrouter_model", openrouterModel);
      }

      // If user is logged in, sync non-empty keys to backend encrypted vault
      if (isAuthenticated) {
        const promises = [];
        if (geminiKey.trim()) {
          promises.push(
            fetch(`${apiBase}/api/settings/credentials/gemini`, {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              credentials: "include",
              body: JSON.stringify({ value: geminiKey.trim() }),
            })
          );
        }
        if (groqKey.trim()) {
          promises.push(
            fetch(`${apiBase}/api/settings/credentials/groq`, {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              credentials: "include",
              body: JSON.stringify({ value: groqKey.trim() }),
            })
          );
        }
        if (openrouterKey.trim()) {
          promises.push(
            fetch(`${apiBase}/api/settings/credentials/openrouter`, {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              credentials: "include",
              body: JSON.stringify({ value: openrouterKey.trim() }),
            })
          );
        }
        await Promise.all(promises);
      }

      setSavedSuccess(true);
      setTimeout(() => {
        setSavedSuccess(false);
        onClose();
      }, 1200);
    } catch (err) {
      console.error("Failed to save credentials:", err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <div className={styles.headerTitle}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "#818cf8" }}>
              <circle cx="12" cy="12" r="3"></circle>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
            </svg>
            <h2>Provider &amp; API Configuration</h2>
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close Settings">✕</button>
        </div>

        <form onSubmit={handleSave} className={styles.body}>
          {/* Tier 1: Gemini */}
          <div className={styles.providerCard}>
            <div className={styles.providerHeader}>
              <span className={styles.tierBadge}>Tier 1 • Primary</span>
              <h3 className={styles.providerName}>Google Gemini</h3>
            </div>
            <div className={styles.inputGroup}>
              <label>Gemini API Key (BYOK override)</label>
              <input
                type="password"
                placeholder="Defaults to server key if left blank"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
              />
            </div>
            <div className={styles.inputGroup}>
              <label>Model Architecture</label>
              <select value={geminiModel} onChange={(e) => setGeminiModel(e.target.value)}>
                <option value="gemini-3.6-flash">gemini-3.6-flash (Fast &amp; High Velocity)</option>
                <option value="gemini-3.7-flash">gemini-3.7-flash (Latest Preview)</option>
                <option value="gemini-3.5-flash">gemini-3.5-flash (Secondary Fallback)</option>
              </select>
            </div>
          </div>

          {/* Tier 2: Groq */}
          <div className={styles.providerCard}>
            <div className={styles.providerHeader}>
              <span className={styles.tierBadgeSecondary}>Tier 2 • Fast Failover</span>
              <h3 className={styles.providerName}>Groq Cloud</h3>
            </div>
            <div className={styles.inputGroup}>
              <label>Groq API Key</label>
              <input
                type="password"
                placeholder="gsk_..."
                value={groqKey}
                onChange={(e) => setGroqKey(e.target.value)}
              />
            </div>
            <div className={styles.inputGroup}>
              <label>Groq Model</label>
              <select value={groqModel} onChange={(e) => setGroqModel(e.target.value)}>
                <option value="openai/gpt-oss-120b">openai/gpt-oss-120b (High Comprehension)</option>
                <option value="llama-3.3-70b-versatile">llama-3.3-70b-versatile (Meta Open Weights)</option>
                <option value="qwen/qwen3.6-27b">qwen/qwen3.6-27b</option>
              </select>
            </div>
          </div>

          {/* Tier 3: OpenRouter */}
          <div className={styles.providerCard}>
            <div className={styles.providerHeader}>
              <span className={styles.tierBadgeTertiary}>Tier 3 • Fallback</span>
              <h3 className={styles.providerName}>OpenRouter</h3>
            </div>
            <div className={styles.inputGroup}>
              <label>OpenRouter API Key</label>
              <input
                type="password"
                placeholder="sk-or-v1-..."
                value={openrouterKey}
                onChange={(e) => setOpenrouterKey(e.target.value)}
              />
            </div>
            <div className={styles.inputGroup}>
              <label>OpenRouter Model</label>
              <select value={openrouterModel} onChange={(e) => setOpenrouterModel(e.target.value)}>
                <option value="cohere/north-mini-code:free">cohere/north-mini-code:free</option>
                <option value="google/gemma-4-31b-it:free">google/gemma-4-31b-it:free</option>
              </select>
            </div>
          </div>

          <div className={styles.actions}>
            {savedSuccess && (
              <span className={styles.successMsg}>✓ Configuration saved to browser storage!</span>
            )}
            <button type="submit" className={styles.saveBtn}>
              Save Configuration
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
