"use client";

import styles from "./page.module.css";
import { useEffect, useState } from "react";

export default function Home() {
  const [refreshInterval, setRefreshInterval] = useState(1000 * 60 * 5); // 5 minutes in milliseconds
  const [lastResult, setLastResult] = useState<{
    systemAvailable: boolean;
    tablesAvailable?: boolean;
    recordCount?: number;
    messages?: string[]  ;
  } | null>(null);
  const [inError, setInError] = useState(false);

  useEffect(() => {
    let timeoutId: NodeJS.Timeout;
    const abortController = new AbortController();

    const periodicFetch = async () => {
      const fetchStatus = async () => {
        let data;
        try {
          const response = await fetch("/api/status", { signal: abortController.signal });
          data = await response.json();
          setLastResult(data);                    
        } catch (error) {
          console.error("Error fetching status:", error);
          setLastResult(data = {
            systemAvailable: false,
            messages: ["Failed to fetch status"],
          });
        }
        const isResultFailure = !data?.systemAvailable || data?.tablesAvailable === false || (data?.recordCount ?? 1) <= 0;
        if (isResultFailure != inError) {
          setInError(isResultFailure);
        }
      };
      await fetchStatus();
      timeoutId = setTimeout(periodicFetch, refreshInterval);
    };

    periodicFetch();

    return () => {
      clearTimeout(timeoutId);
      abortController.abort();
    };
  }, [refreshInterval, inError]);

  const statusColor = inError ? "red" : "green";
  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <div>
          <h1 style={{'textAlign': 'center', 'width': '100%', paddingBottom: '1.2em'}}>Postgresql Dependency Status</h1>
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
        <button onClick={() => window.location.reload()}>Refresh Now</button>
        <div>
          <h2 style={{paddingBottom: "1.1em"}}>Status Check Result:</h2>
          {lastResult ? (
            <ul style={{ listStyleType: "none", padding: 0, color: statusColor }}>
              <li>System Available: {lastResult.systemAvailable ? "Yes" : "No"}</li>
              <li>Tables Available: {lastResult.tablesAvailable ? "Yes" : "No"}</li>
              {typeof lastResult.recordCount === 'number' && (<li>Record Count: {lastResult.recordCount}</li>)}
                  {Array.isArray(lastResult.messages) && lastResult.messages.length > 0 && (
                    <li >
                    <ul style={{ listStyleType: "none", paddingLeft: "1.2em" }}>
                      {lastResult.messages.map((msg, index) => <li key={index}>{msg}</li>)}
                    </ul>
                    </li>
                  )}                 
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
