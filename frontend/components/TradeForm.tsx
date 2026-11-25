"use client";
import { FormEvent, useState } from "react";
import { formatCredits, post } from "@/lib/api";
import type { Market, Quote, Outcome, Side, Holding } from "@/lib/types";

export function TradeForm({market, positions, onDone}:{market:Market;positions:Holding[];onDone:()=>Promise<void>}) {
  const [side,setSide]=useState<Side>("BUY"),[outcome,setOutcome]=useState<Outcome>("YES");
  const [shares,setShares]=useState("1"),[quote,setQuote]=useState<Quote|null>(null);
  const [limit,setLimit]=useState("");const [error,setError]=useState("");
  const [success,setSuccess]=useState("");const [busy,setBusy]=useState(false);
  const [idempotencyKey,setIdempotencyKey]=useState("");
  const heldPosition=positions.find(p=>p.outcome===outcome);
  const oppositePosition=positions.find(p=>p.outcome!==outcome);
  const legacyFractionalPosition=!!heldPosition&&Number(heldPosition.shares)%1!==0;
  const blockedBuy=side==="BUY"&&(!!oppositePosition||legacyFractionalPosition);
  const blockedSell=side==="SELL"&&!heldPosition;
  const fractionalExit=side==="SELL"&&legacyFractionalPosition;
  function reset(){setQuote(null);setError("");setSuccess("");setIdempotencyKey("");}
  function chooseSide(value:Side){
    setSide(value);reset();
    const position=positions.find(p=>p.outcome===outcome);
    setShares(value==="SELL"&&position?position.shares:"1");
  }
  function chooseOutcome(value:Outcome){
    setOutcome(value);reset();
    const position=positions.find(p=>p.outcome===value);
    setShares(side==="SELL"&&position?position.shares:"1");
  }
  async function obtainQuote(e:FormEvent){
    e.preventDefault();setBusy(true);setError("");setSuccess("");
    try{const q=await post<Quote>(`/api/markets/${market.id}/quote`,{side,outcome,shares});
      setQuote(q);setLimit(q.amount);setIdempotencyKey(crypto.randomUUID());}
    catch(e){setQuote(null);setError(e instanceof Error?e.message:"Quote failed");}
    finally{setBusy(false);}
  }
  async function trade(){
    if(!quote)return;setBusy(true);setError("");
    try{
      await post(`/api/markets/${market.id}/orders`,{
        side,outcome,shares,max_cost:side==="BUY"?limit:undefined,
        min_proceeds:side==="SELL"?limit:undefined
      },{"Idempotency-Key":idempotencyKey});
      setSuccess(`Executed ${side} ${shares} ${outcome} shares.`);setQuote(null);setIdempotencyKey("");
      await onDone();
    }catch(err){setError(err instanceof Error?err.message:"Order failed");}
    finally{setBusy(false);}
  }
  return <div className="panel"><h2>Trade</h2>
    <form onSubmit={obtainQuote}>
      <div className="segment" role="group" aria-label="Trade side">{(["BUY","SELL"] as Side[]).map(s=><button key={s} type="button" className={side===s?"active":""} onClick={()=>chooseSide(s)}>{s}</button>)}</div>
      <div className="segment" role="group" aria-label="Trade outcome">{(["YES","NO"] as Outcome[]).map(s=><button key={s} type="button" className={outcome===s?"active":""} onClick={()=>chooseOutcome(s)}>{s}</button>)}</div>
      {positions.length>0&&<p className="muted">Open position: {positions.map(p=>`${p.shares} ${p.outcome}`).join(", ")}. Sell all open shares before buying the opposite outcome.</p>}
      {blockedBuy&&<p role="status" className="notice">{oppositePosition?`Close your existing ${oppositePosition.outcome} position before buying ${outcome} shares.`:`Sell your existing fractional ${outcome} position before buying more shares.`}</p>}
      <div className="field"><label htmlFor="shares">{fractionalExit?"Shares (existing fractional position)":"Shares (whole numbers)"}</label><input id="shares" type="number" min={fractionalExit?"0.000001":"1"} max={side==="SELL"&&heldPosition?heldPosition.shares:"10000"} step={fractionalExit?"0.000001":"1"} required value={shares} onChange={e=>{setShares(e.target.value);reset();}}/></div>
      <button type="submit" disabled={busy||market.status!=="OPEN"||blockedBuy||blockedSell} className="btn full">{busy?"Loading...":"Get executable quote"}</button>
    </form>
    {quote&&<div style={{marginTop:18}}>
      <div className="between"><span className="muted">Quoted {side==="BUY"?"cost":"proceeds"}</span><strong>{formatCredits(quote.amount)} credits</strong></div>
      <div className="field"><label htmlFor="limit">{side==="BUY"?"Maximum cost":"Minimum proceeds"} (credits)</label>
        <input id="limit" type="number" min="0" step="0.000001" value={limit} onChange={e=>setLimit(e.target.value)} /></div>
      <p className="muted" style={{fontSize:12}}>Revalidated server-side when placed. The limit protects you if the price changes.</p>
      <button className="btn primary full" disabled={busy||!limit} onClick={trade}>{busy?"Submitting...":`Confirm ${side} ${outcome}`}</button>
    </div>}
    {error&&<p role="alert" className="notice error" style={{marginTop:14}}>{error}</p>}
    {success&&<p role="status" className="notice success" style={{marginTop:14}}>{success}</p>}
    {market.status!=="OPEN"&&<p className="muted">Trading is closed for this market.</p>}
  </div>;
}
