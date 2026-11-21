"use client";
import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthContext";
import { formatTime, pct, post, request } from "@/lib/api";
import type { Market } from "@/lib/types";

type Audit={action:string;market_id:string;reason:string|null;at:string};
export default function Admin(){
  const {user}=useAuth();const [markets,setMarkets]=useState<Market[]>([]);const [audits,setAudits]=useState<Audit[]>([]);
  const [key,setKey]=useState("KAN-1"),[deadline,setDeadline]=useState(""),[liquidity,setLiquidity]=useState("10");
  const [error,setError]=useState(""),[success,setSuccess]=useState(""),[busy,setBusy]=useState(false);
  async function load(){const [m,a]=await Promise.all([request<{items:Market[]}>("/api/markets?limit=100"),request<{items:Audit[]}>("/api/admin/audit")]);setMarkets(m.items);setAudits(a.items);}
  useEffect(()=>{if(user?.role==="ADMIN")void load().catch(e=>setError(e instanceof Error?e.message:"Could not load admin data"));},[user]);
  async function create(e:FormEvent){
    e.preventDefault();setBusy(true);setError("");setSuccess("");
    try{await post("/api/markets",{jira_issue_key:key,cutoff:new Date(deadline).toISOString(),liquidity});
      setSuccess(`Created a market for ${key}.`);await load();}
    catch(e){setError(e instanceof Error?e.message:"Creation failed");}
    finally{setBusy(false);}
  }
  async function act(m:Market,operation:"sync"|"resolve"|"void"){
    let payload:unknown={};
    if(operation==="void"){
      const reason=prompt("Reason for voiding this market (12+ characters). Outstanding shares will settle at mark-to-market prices:");
      if(!reason)return;
      payload={reason};
      if(!confirm("Confirm irreversible void and payout?"))return;
    }
    setBusy(true);setError("");setSuccess("");
    try{await post(`/api/admin/markets/${m.id}/${operation}`,payload);
      setSuccess(`${operation} completed for ${m.jira_issue_key}.`);await load();}
    catch(e){setError(e instanceof Error?e.message:`${operation} failed`);}
    finally{setBusy(false);}
  }
  return <main className="shell"><div className="eyebrow">Administrator</div><h1>Manage markets</h1>
    {!user?<p>Please <Link href="/login">log in</Link>.</p>:user.role!=="ADMIN"?<p className="notice error">Admin access required.</p>:<>
      <p className="muted">Jira mode: <strong>{user.jira_mode.toUpperCase()}</strong>. riverbet only reads Jira; no issue changes are sent back.</p>
      {error&&<p role="alert" className="notice error">{error}</p>}
      {success&&<p role="status" className="notice success">{success}</p>}
      <div className="split" style={{marginBottom:24}}>
        <section className="panel"><h2>Create market</h2><form onSubmit={create}>
          <div className="field"><label htmlFor="issue">Jira issue key</label><input id="issue" required value={key} onChange={e=>setKey(e.target.value.toUpperCase())} placeholder="KAN-1"/></div>
          <div className="field"><label htmlFor="deadline">Deadline (your local time)</label><input id="deadline" required type="datetime-local" value={deadline} onChange={e=>setDeadline(e.target.value)}/></div>
          <div className="field"><label htmlFor="liquidity">Liquidity (play credits, 1-1000)</label><input id="liquidity" type="number" min="1" max="1000" step="0.01" value={liquidity} onChange={e=>setLiquidity(e.target.value)}/></div>
          <button className="btn primary" disabled={busy}>{busy?"Working...":"Create market"}</button>
        </form></section>
        <section className="panel"><h2>How to resolve</h2>
          <p>Markets automatically close at their immutable deadline. The reconciliation worker fetches complete Jira status history and pays the winning outcome once.</p>
          <p className="muted">Sync fetches the latest issue key and summary; Resolve rechecks history if due. If Jira cannot prove status at cutoff, the market remains closed.</p>
          {user.jira_mode==="mock"&&<div className="notice">Mock issues: KAN-1 (not done), KAN-2 (done), KAN-3 (reopened), KAN-4 (late change).</div>}
        </section>
      </div>
      <section className="panel" style={{marginBottom:22}}><h2>Markets</h2>
        <div className="table-wrap"><table><thead><tr><th>Issue</th><th>Status</th><th>YES</th><th>Deadline</th><th>Actions</th></tr></thead>
          <tbody>{markets.map(m=><tr key={m.id}><td><Link href={`/markets/${m.id}`}>{m.jira_issue_key}</Link></td><td>{m.status}</td><td>{pct(m.yes_probability)}</td>
            <td>{formatTime(m.cutoff)}</td><td><div className="flex" style={{flexWrap:"wrap"}}>
              <button className="btn tiny" disabled={busy} onClick={()=>act(m,"sync")}>Sync</button>
              {m.status==="CLOSED"&&<button className="btn tiny" disabled={busy} onClick={()=>act(m,"resolve")}>Resolve</button>}
              {!["RESOLVED","VOID"].includes(m.status)&&<button className="btn tiny danger" disabled={busy} onClick={()=>act(m,"void")}>Void</button>}
            </div></td></tr>)}</tbody>
        </table></div>{!markets.length&&<p className="muted">No markets created.</p>}</section>
      <section className="panel"><h2>Admin audit</h2><div className="table-wrap"><table><thead><tr><th>Action</th><th>Market</th><th>Reason</th><th>Time</th></tr></thead>
        <tbody>{audits.map((a,i)=><tr key={i}><td>{a.action}</td><td>{a.market_id?.slice(0,8)}</td><td>{a.reason||""}</td><td>{formatTime(a.at)}</td></tr>)}</tbody>
      </table></div></section>
    </>}
  </main>;
}
