"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { formatTime, pct, request } from "@/lib/api";
import type { Market, Trade } from "@/lib/types";
import { PriceChart } from "@/components/PriceChart";
import { TradeForm } from "@/components/TradeForm";
import { useAuth } from "@/components/AuthContext";

export default function MarketDetail(){
  const {id}=useParams<{id:string}>();const {user}=useAuth();
  const [market,setMarket]=useState<Market|null>(null);const [history,setHistory]=useState<{at:string;yes_probability:number}[]>([]);
  const [trades,setTrades]=useState<Trade[]>([]);const [error,setError]=useState("");
  const load=useCallback(async()=>{
    try{const [m,h,t]=await Promise.all([
      request<Market>(`/api/markets/${id}`),request<{items:typeof history}>(`/api/markets/${id}/history`),
      request<{items:Trade[]}>(`/api/markets/${id}/trades`) ]);
      setMarket(m);setHistory(h.items);setTrades(t.items);setError("");
    }catch(e){setError(e instanceof Error?e.message:"Could not load market");}
  },[id]);
  useEffect(()=>{if(!user)return;
    void load();
    const timer=window.setInterval(()=>{void load();},5000);
    return ()=>window.clearInterval(timer);
  },[user,load]);
  return <main className="shell">
    <Link href="/" className="muted">← All markets</Link>
    {error&&<p role="alert" className="notice error" style={{marginTop:20}}>{error}</p>}
    {!user?<p>Please <Link href="/login">log in</Link> to view markets.</p>:!market?<p>Loading market...</p>:<>
      <div style={{margin:"24px 0"}}><div className="flex"><span className="tag">{market.jira_issue_key}</span><span className={`chip ${market.status}`}>{market.status}</span></div>
        <h1 style={{fontSize:"clamp(27px,4vw,42px)",margin:"12px 0"}}>{market.question}</h1>
        <p className="muted">Deadline: {formatTime(market.cutoff)}. Resolution uses Jira Done-category status at this exact instant (UTC cutoff).</p>
      </div>
      <section className="grid-stats" style={{marginBottom:20}}>
        <div className="panel"><div className="muted">YES implied probability</div><div className="metric">{pct(market.yes_probability)}</div></div>
        <div className="panel"><div className="muted">NO implied probability</div><div className="big-stat">{pct(market.no_probability)}</div></div>
        <div className="panel"><div className="muted">Shares outstanding</div><div className="big-stat">{(Number(market.q_yes)+Number(market.q_no)).toFixed(1)}</div></div>
      </section>
      <div className="split">
        <div className="stacked">
          <section className="panel"><div className="between"><h2>Price history</h2><span className="muted">YES</span></div><PriceChart points={history}/></section>
          <section className="panel"><h2>Contract details</h2><p>{market.summary}</p>
            <p className="muted">
              Exact cutoff (UTC): <code>{market.cutoff}</code>
            </p>
            <p className="muted">YES pays 1 play credit per outstanding YES share if the issue was in a Jira Done-category status at cutoff. Otherwise NO pays 1 credit per outstanding NO share. Reopened issues are evaluated at the cutoff, not at resolution time.</p>
            <p><a href={`https://rahulrram04.atlassian.net/browse/${encodeURIComponent(market.jira_issue_key)}`} target="_blank" rel="noopener noreferrer" style={{color:"var(--aqua)"}}>View issue in Jira ↗</a></p>
            {market.status==="RESOLVED"&&<p className="notice success">Resolved winner: {market.winner}</p>}
            {market.status==="VOID"&&<p className="notice">Voided. Outstanding shares were paid at pre-void marginal prices.</p>}
          </section>
          <section className="panel"><h2>Recent trades</h2>{!trades.length?<p className="muted">No trades yet.</p>:<div className="table-wrap"><table>
            <thead><tr><th>Side</th><th>Outcome</th><th>Shares</th><th>Credits</th><th>Time</th></tr></thead>
            <tbody>{trades.map((t,i)=><tr key={i}><td>{t.side}</td><td>{t.outcome}</td><td>{t.shares}</td><td>{t.amount}</td><td>{formatTime(t.created_at)}</td></tr>)}</tbody>
          </table></div>}</section>
        </div>
        <div className="stacked"><TradeForm key={market.id} market={market} onDone={load}/>
          <div className="notice">Play credits have no cash value. Consider conflicts of interest when trading on tasks you control.</div>
        </div>
      </div>
    </>}
  </main>;
}
