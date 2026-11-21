"use client";
import { pct } from "@/lib/api";

export function PriceChart({points}:{points:{at:string;yes_probability:number}[]}){
  if(!points.length)return <p className="muted">No price history yet.</p>;
  const width=720,height=210,top=20,bottom=180;
  const times=points.map(x=>new Date(x.at).getTime());
  const lo=Math.min(...times),hi=Math.max(...times);
  const coord=points.map((p,i)=>{
    const x=hi===lo?30+(i/(Math.max(points.length-1,1)))*(width-60):30+((times[i]-lo)/(hi-lo))*(width-60);
    const y=bottom-Math.max(0,Math.min(1,p.yes_probability))*(bottom-top);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return <div><svg viewBox={`0 0 ${width} ${height}`} className="chart" role="img" aria-label={`YES implied probability history, current value ${pct(points[points.length-1].yes_probability)}`}>
    {[0,0.25,0.5,0.75,1].map(v=><g key={v}><line x1={30} x2={width-30} y1={bottom-v*(bottom-top)} y2={bottom-v*(bottom-top)} stroke="#294353" strokeDasharray="3 5"/>
      <text x={2} y={bottom-v*(bottom-top)+4} fill="#9eb8c6" fontSize={12}>{Math.round(v*100)}</text></g>)}
    <polyline points={coord} fill="none" stroke="#5de0cc" strokeWidth={3} strokeLinejoin="round" strokeLinecap="round"/>
  </svg><div className="between muted" style={{fontSize:11}}><span>{new Date(lo).toLocaleString()}</span><span>{new Date(hi).toLocaleString()}</span></div></div>;
}
