import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { get, usd, pct, ms } from './api.js'
import { Empty } from './Overview.jsx'

export default function Benchmark() {
  const [r, setR] = useState(undefined)
  useEffect(() => { get('/benchmark').then(setR).catch(() => setR(null)) }, [])

  if (r === undefined) return <div className="loading">Loading…</div>
  if (!r) return <Empty title="No benchmark yet" body={<>Run <code>python benchmark/run.py</code> to measure savings and quality on 1,000 prompts.</>} />

  const cost = [
    { name: 'Strong model only', v: r.baseline.cost_usd, c: '#ffb547' },
    { name: 'Through TokenSaver', v: r.tokensaver.cost_usd, c: '#3ddc97' },
  ]
  const q = r.quality || {}
  const projection = r.projection || null

  return (
    <div className="page">
      <section className="hero bench">
        <div>
          <p className="eyebrow">Benchmark · {r.prompts.toLocaleString()} prompts · {r.date}</p>
          <h1><span className="mint">{pct(r.percent_saved)}</span> cheaper</h1>
          <p className="lede">with <b>{pct(q.equal_or_better_pct)}</b> of sampled answers judged as good as the strong model's ({q.sample} judged by {q.judge}).</p>
        </div>
        <div className="bench-facts">
          <div><span>Cache hit rate</span><b>{pct(r.tokensaver.cache_hit_rate)}</b></div>
          <div><span>Routed to cheap model</span><b>{pct(r.tokensaver.routed_cheap_pct)}</b></div>
          <div><span>Avg latency</span><b>{ms(r.tokensaver.avg_latency_ms)} <small>vs {ms(r.baseline.avg_latency_ms)}</small></b></div>
          <div><span>Model calls avoided</span><b>{(r.baseline.calls - r.tokensaver.calls).toLocaleString()}</b></div>
        </div>
      </section>

      <section className="grid-2">
        <div className="panel">
          <div className="panel-head"><h3>Total cost <em>{r.pricing_note}</em></h3></div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={cost} margin={{ left: 10, right: 10, top: 10 }}>
              <CartesianGrid stroke="#232a35" vertical={false} />
              <XAxis dataKey="name" stroke="#8b95a7" fontSize={12} />
              <YAxis stroke="#8b95a7" fontSize={11} tickFormatter={(v) => usd(v, { compact: true })} width={80} />
              <Tooltip contentStyle={{ background: '#11161e', border: '1px solid #2a3240', borderRadius: 10 }} formatter={(v) => usd(v)} cursor={{ fill: '#ffffff08' }} />
              <Bar dataKey="v" radius={[6, 6, 0, 0]}>{cost.map((d) => <Cell key={d.name} fill={d.c} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="panel">
          <div className="panel-head"><h3>Answer quality <em>judge vs strong-model answer</em></h3></div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={Object.entries(q.distribution || {}).map(([k, v]) => ({ k, v }))} margin={{ left: -10, right: 10, top: 10 }}>
              <CartesianGrid stroke="#232a35" vertical={false} />
              <XAxis dataKey="k" stroke="#8b95a7" fontSize={12} />
              <YAxis stroke="#8b95a7" fontSize={11} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#11161e', border: '1px solid #2a3240', borderRadius: 10 }} cursor={{ fill: '#ffffff08' }} />
              <Bar dataKey="v" name="answers" fill="#a78bfa" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head"><h3>Results</h3></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Metric</th><th className="r">Strong model only</th><th className="r">TokenSaver</th></tr></thead>
            <tbody>
              <tr><td>Model calls</td><td className="r mono">{r.baseline.calls.toLocaleString()}</td><td className="r mono">{r.tokensaver.calls.toLocaleString()}</td></tr>
              <tr><td>Total cost</td><td className="r mono">{usd(r.baseline.cost_usd)}</td><td className="r mono">{usd(r.tokensaver.cost_usd)}</td></tr>
              <tr><td>Average latency</td><td className="r mono">{ms(r.baseline.avg_latency_ms)}</td><td className="r mono">{ms(r.tokensaver.avg_latency_ms)}</td></tr>
              <tr><td>Exact / smart cache hits</td><td className="r mono">—</td><td className="r mono">{r.tokensaver.exact_hits} / {r.tokensaver.semantic_hits}</td></tr>
              <tr><td>Routed to cheap model</td><td className="r mono">—</td><td className="r mono">{pct(r.tokensaver.routed_cheap_pct)}</td></tr>
            </tbody>
          </table>
        </div>
        {projection && (
          <p className="note">If the same traffic used <b>{projection.strong}</b> as the strong model and <b>{projection.cheap}</b> as the cheap one,
            cost would drop from <b>{usd(projection.baseline_usd)}</b> to <b>{usd(projection.tokensaver_usd)}</b> ({pct(projection.percent_saved)} saved). Same token counts, public list prices.</p>
        )}
      </section>
    </div>
  )
}
