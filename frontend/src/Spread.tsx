import type {ReactNode} from 'react'

export const number=(n:number)=>String(n).padStart(2,'0')

export function Leaf({running,label,page,children}:{running:string,label:string,page:number,children:ReactNode}){
  return <section className="leaf"><div className="running"><span>{running}</span><span>ArthIQ</span></div>
    {children}<div className="folio"><span>{label}</span><b>{number(page)}</b></div></section>
}

export function Engraving(){
  return <svg className="engraving" viewBox="0 0 300 160" aria-hidden="true">
    <circle cx="205" cy="53" r="35" fill="#d8b76d"/>
    <g stroke="#476d67" strokeWidth="1.15" fill="#faf8ee">
      {Array.from({length:18},(_,i)=>{const d=i*2.9;return <path key={i} d={`M20 ${75+d} Q85 ${54+d} 150 ${93+d} Q212 ${50+d} 280 ${51+d} L280 ${49+d} Q211 ${42+d} 150 ${85+d} Q85 ${43+d} 20 ${66+d} Z`}/>})}
    </g><path d="M205 96l15 -5v32l-8 -4 -7 7z" fill="#ab483f"/></svg>
}
