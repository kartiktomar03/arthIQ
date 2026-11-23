import { useState } from 'react'
import { ResponsiveContainer, BarChart, Bar, LineChart, Line, Tooltip, Legend, XAxis, YAxis } from 'recharts'
import type { QueryResult } from './api'

export function InsightCard({result}:{result:QueryResult}) {
  const [choice,setChoice] = useState(result.analysis?.charts[0] || 'table')
  const charts = result.analysis?.charts || ['table']
  const rows = result.rows.map(row => Object.fromEntries(row.map((v,i)=>[String(i), i ? Number(v) : String(v)])))
  const graphical = choice === 'line' || choice === 'bar'
  const Chart = choice === 'line' ? LineChart : BarChart
  const horizontal=choice==='bar'
  const trimLabel=(value:unknown)=>String(value).length>18?String(value).slice(0,17)+'…':String(value)
  return <>

    {charts.length>1 && <div className="chart-modes" role="group" aria-label="Visualization">
      {charts.map(mode=><button type="button" key={mode} aria-pressed={choice===mode} onClick={()=>setChoice(mode)}>
        {mode==='kpi'?'KPI':mode==='bar'&&result.columns.length>2?'Grouped bar':mode.charAt(0).toUpperCase()+mode.slice(1)}
      </button>)}</div>}
    {choice==='kpi' && <h2>{result.analysis?.units[0]==='USD'?'$':result.analysis?.units[0] ? result.analysis.units[0]+' ' : ''}{String(result.rows[0]?.[0])} <small>{result.columns[0].replaceAll('_',' ')}</small></h2>}
    {graphical && <ResponsiveContainer width="100%" height={horizontal?Math.max(150,Math.min(360,rows.length*36+55)):235}><Chart data={rows} layout={horizontal?'vertical':'horizontal'} margin={{left:0,right:12,top:8,bottom:2}}>
      {horizontal?<><XAxis type="number" stroke="#526564"/><YAxis type="category" dataKey="0" width={90} tickFormatter={trimLabel} stroke="#526564"/></>:
        <><XAxis dataKey="0" stroke="#526564" tickFormatter={trimLabel}/><YAxis stroke="#526564"/></>}
      <Tooltip contentStyle={{background:"#fff9ef",borderColor:"#2C2621",color:"#2C2621"}} cursor={{fill:"#f5f1e8"}}/><Legend formatter={value=><span style={{color:"var(--ink)"}}>{value}</span>}/>
      {result.columns.slice(1).map((col,i)=>choice==='line'
        ? <Line isAnimationActive={false} key={i} dataKey={String(i+1)} name={[col.replaceAll('_',' '),result.analysis?.units[i+1]].filter(Boolean).join(' · ')} stroke={colors[i%colors.length]}/>
        : <Bar stroke="none" isAnimationActive={false} maxBarSize={26} key={i} dataKey={String(i+1)} name={[col.replaceAll('_',' '),result.analysis?.units[i+1]].filter(Boolean).join(' · ')} fill={colors[i%colors.length]}/>)}
    </Chart></ResponsiveContainer>}
  </>
}
const colors=['#346963','#b76959','#8a7ba2','#9c803c']

