"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { formatCredits, formatTime, request } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import type { Portfolio } from "@/lib/types";

type MyOrder={id:string;market_id:string;side:string;outcome:string;shares:string;amount:string;at:string};
export default function PortfolioPage(){
  const {user}=useAuth();const [portfolio,setPortfolio]=useState<Portfolio|null>(null);
  const [orders,setOrders]=useState<MyOrder[]>([]);const [error,setError]=useState("");
  useEffect(()=>{if(!user)return;
    const load=()=>{void Promise.all([request<Portfolio>("/api/me/portfolio"),request<{items:MyOrder[]}>("/api/me/orders")])
      .then(([p,o])=>{setPortfolio(p);setOrders(o.items);setError("");})
      .catch(e=>setError(e instanceof Error?e.message:"Failed to load portfolio"));};
    load();
    const timer=window.setInterval(load,5000);
    return ()=>window.clearInterval(timer);
  },[user]);
  return <main className="shell"><div className="eyebrow">Your account</div><h1>Portfolio</h1>
    {error&&<p role="alert" className="notice error">{error}</p>}
    {!user?<p>Please <Link href="/login">log in</Link>.</p>:!portfolio?<p>Loading portfolio...</p>:<>
      <div className="grid-stats" style={{marginBottom:24}}>
        <div className="panel"><div className="muted">Available play credits</div><div className="big-stat">{formatCredits(portfolio.balance)}</div></div>
        <div className="panel"><div className="muted">Active position value (approx.)</div><div className="big-stat">{formatCredits(portfolio.active_position_value)}</div></div>
        <div className="panel"><div className="muted">Active + available</div><div className="big-stat">{formatCredits(Number(portfolio.balance)+Number(portfolio.active_position_value))}</div></div>
      </div>
      <section className="panel" style={{marginBottom:20}}><h2>Holdings</h2>
        <div className="table-wrap"><table><thead><tr><th>Market</th><th>Side</th><th>Shares</th><th>Status</th><th>Active value</th></tr></thead>
          <tbody>{portfolio.holdings.map(h=><tr key={h.market_id+h.outcome}><td><Link href={`/markets/${h.market_id}`}>{h.question}</Link></td>
            <td>{h.outcome}</td><td>{h.shares}</td><td>{h.status}</td><td>{h.mark_to_market}</td></tr>)}</tbody>
        </table></div>{!portfolio.holdings.length&&<p className="muted">No positions yet.</p>}
      </section>
      <section className="panel"><h2>Order history</h2><div className="table-wrap"><table>
        <thead><tr><th>Market</th><th>Side</th><th>Outcome</th><th>Shares</th><th>Credits</th><th>Time</th></tr></thead>
        <tbody>{orders.map(o=><tr key={o.id}><td><Link href={`/markets/${o.market_id}`}>View market</Link></td><td>{o.side}</td>
          <td>{o.outcome}</td><td>{o.shares}</td><td>{o.amount}</td><td>{formatTime(o.at)}</td></tr>)}</tbody>
      </table></div>{!orders.length&&<p className="muted">No orders yet.</p>}</section>
    </>}
  </main>;
}
