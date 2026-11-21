"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { request, formatTime, pct } from "@/lib/api";
import type { Market } from "@/lib/types";
import { useAuth } from "@/components/AuthContext";

export default function Home() {
  const {user,loading}=useAuth();
  const [markets,setMarkets]=useState<Market[]>([]);const [error,setError]=useState("");
  const [query,setQuery]=useState("");const [filter,setFilter]=useState("ALL");
  useEffect(()=>{if(!user)return;request<{items:Market[]}>("/api/markets?limit=100")
    .then(x=>setMarkets(x.items)).catch(x=>setError(x instanceof Error?x.message:"Failed to load markets"));},[user]);
  const visible=useMemo(()=>markets.filter(m=>(filter==="ALL"||m.status===filter)&&
    (m.question+" "+m.jira_issue_key).toLowerCase().includes(query.toLowerCase())),[markets,filter,query]);
  return <main className="shell">
    <section className="hero"><div className="eyebrow">Work-item prediction markets</div>
      <h1>Make delivery risk<br/>visible.</h1>
      <p>Trade YES or NO shares on whether Jira work items will reach Done by a defined deadline. Track how team expectations change.</p>
      <div className="notice">Virtual, nonredeemable credits only. Prices express market-implied probabilities, not calibrated predictions or employee performance scores.</div>
    </section>
    {loading?<p>Loading your session...</p>:!user?<div className="panel">
      <h2>Sign in to explore riverbet</h2><p className="muted">Markets and wallets are visible only to authenticated team members.</p>
      <Link className="btn primary" href="/login">Log in</Link> <Link className="btn" href="/register">Create account</Link>
    </div>:<>
      <div className="between"><h2 style={{margin:0}}>Markets <span className="muted">({markets.length})</span></h2>
        {user.jira_mode==="mock"&&<span className="chip">MOCK JIRA</span>}
      </div>
      <div className="toolbar"><input aria-label="Search markets" placeholder="Search by issue or question" value={query} onChange={e=>setQuery(e.target.value)}/>
        <select aria-label="Market status filter" value={filter} onChange={e=>setFilter(e.target.value)}>
          {["ALL","OPEN","CLOSED","RESOLVED","VOID"].map(s=><option key={s}>{s}</option>)}
        </select>
      </div>
      {error&&<p className="notice error" role="alert">{error}</p>}
      <section className="card-list">{visible.map(m=><Link className="panel market-card" href={`/markets/${m.id}`} key={m.id}>
        <div className="between"><span className="tag">{m.jira_issue_key}</span><span className={`chip ${m.status}`}>{m.status}</span></div>
        <h3>{m.question}</h3>
        <div className="between"><div><div className="muted" style={{fontSize:12}}>YES implied probability</div>
          <div className="metric">{pct(m.yes_probability)}</div></div><span className="muted" style={{fontSize:12}}>Deadline<br/>{formatTime(m.cutoff)}</span></div>
      </Link>)}</section>
      {!error&&visible.length===0&&<div className="panel muted">No markets match. {user.role==="ADMIN"?"Create one in the Admin panel.":"Ask an admin to create a market."}</div>}
    </>}
  </main>;
}
