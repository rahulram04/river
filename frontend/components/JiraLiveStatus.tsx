"use client";
import { useEffect, useState } from "react";
import { request } from "@/lib/api";

type IssueStatus = {
  issue_key: string;
  summary: string;
  status_category: "done" | "new" | "indeterminate";
  checked_at: string;
  source: "JIRA_LIVE" | "JIRA_MOCK";
};

export function JiraLiveStatus({ marketId }: { marketId: string }) {
  const [issue, setIssue] = useState<IssueStatus | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    async function poll() {
      try {
        const data = await request<IssueStatus>(`/api/jira/markets/${encodeURIComponent(marketId)}/status`);
        if (active) { setIssue(data); setError(false); }
      } catch {
        if (active) setError(true);
      }
    }
    void poll();
    const timer = setInterval(() => { void poll(); }, 60_000);
    return () => { active = false; clearInterval(timer); };
  }, [marketId]);

  if (error) return <p className="muted" role="status">Jira status unavailable. Settlement will be deferred if Jira cannot verify history.</p>;
  if (!issue) return <p className="muted">Checking Jira status...</p>;
  const labels = {done: "Done", new: "To do", indeterminate: "In progress"};
  const source = issue.source === "JIRA_LIVE" ? "Live Jira" : "Mock Jira";
  return <p className="muted" role="status">
    {source}: <strong>{labels[issue.status_category]}</strong> (checked {new Date(issue.checked_at).toLocaleTimeString()}; refreshes every minute).
    Current status does not determine the market outcome until its cutoff.
  </p>;
}
