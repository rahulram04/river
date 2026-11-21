export type Outcome = "YES" | "NO";
export type Side = "BUY" | "SELL";
export type MarketStatus = "OPEN" | "CLOSED" | "RESOLVED" | "VOID";

export interface User {
  id: string;
  email: string;
  role: "ADMIN" | "MEMBER";
  csrf_token: string;
  jira_mode: "mock" | "live";
}
export interface Market {
  id: string;
  jira_issue_key: string;
  jira_issue_id: string;
  jira_project_key: string;
  summary: string;
  question: string;
  status: MarketStatus;
  cutoff: string;
  created_at: string;
  liquidity: string;
  q_yes: string;
  q_no: string;
  yes_probability: number;
  no_probability: number;
  winner: Outcome | null;
  resolution_evidence: Record<string, unknown> | null;
}
export interface Quote {
  side: Side;
  outcome: Outcome;
  shares: string;
  amount: string;
  yes_probability: number;
  expires_on_trade: boolean;
  note: string;
}
export interface Holding {
  market_id: string;
  question: string;
  outcome: Outcome;
  shares: string;
  status: MarketStatus;
  mark_to_market: string;
  winner: Outcome | null;
}
export interface Portfolio {
  balance: string;
  active_position_value: string;
  holdings: Holding[];
}
export interface Trade {
  side: Side;
  outcome: Outcome;
  shares: string;
  amount: string;
  created_at: string;
}
