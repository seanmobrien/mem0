"use client";

import styles from "./page.module.css";
import { useEffect, useState } from "react";

export default function Home() {
  const [refreshInterval, setRefreshInterval] = useState(1000 * 60 * 5); // 5 minutes in milliseconds
  const [lastResult, setLastResult] = useState<{
    systemAvailable: boolean;
    tablesAvailable?: boolean;
    recordCount?: number;
    message?: string;
  } | null>(null);

  useEffect(() => {
    let timeoutId: NodeJS.Timeout;
    const abortController = new AbortController();

    const fetchStatus = async () => {
      try {
        const response = await fetch("/api/status", { signal: abortController.signal });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        setLastResult({
          systemAvailable: data.systemAvailable,
          tablesAvailable: data.tablesAvailable,
          recordCount: data.recordCount,
          message: data.message,
        });
      } catch (error) {
        console.error("Error fetching status:", error);
        setLastResult({
          systemAvailable: false,
          message: "Failed to fetch status",
        });
      } finally {
        timeoutId = setTimeout(fetchStatus, refreshInterval);
      }
    };

    fetchStatus();

    return () => {
      clearTimeout(timeoutId);
      abortController.abort();
    };
  }, [refreshInterval]);

  const handleRefreshNow = () => {
    setLastResult(null); // Clear last result before manual refresh
    const abortController = new AbortController();
    fetch("/api/status", { signal: abortController.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        setLastResult({
          systemAvailable: data.systemAvailable,
          tablesAvailable: data.tablesAvailable,
          recordCount: data.recordCount,
          message: data.message,
        });
      })
      .catch((error) => {
        console.error("Error fetching status:", error);
        setLastResult({
          systemAvailable: false,
          message: "Failed to fetch status",
        });
      });
  };

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <div>
          <label htmlFor="refresh-rate">Refresh Rate:</label>
          <select
            id="refresh-rate"
            value={refreshInterval}
            onChange={(e) => setRefreshInterval(Number(e.target.value))}
          >
            <option value={5000}>5 seconds</option>
            <option value={30000}>30 seconds</option>
            <option value={60000}>1 minute</option>
            <option value={1000 * 60 * 5}>5 minutes</option>
            <option value={1000 * 60 * 10}>10 minutes</option>
          </select>
        </div>
        <button onClick={handleRefreshNow}>Refresh Now</button>
        <div>
          <h2>Status Check Result:</h2>
          {lastResult ? (
            <ul>
              <li>System Available: {lastResult.systemAvailable ? "Yes" : "No"}</li>
              <li>Tables Available: {lastResult.tablesAvailable ? "Yes" : "No"}</li>
              <li>Record Count: {lastResult.recordCount ?? "N/A"}</li>
              <li>Message: {lastResult.message ?? "No message"}</li>
            </ul>
          ) : (
            <p>No status available yet.</p>
          )}
        </div>
      </main>
      <footer className={styles.footer}>
        <p>
          Dependency: pgvector | Last Response: {lastResult ? new Date().toLocaleTimeString() : "N/A"}
        </p>
      </footer>
    </div>
  );
}
