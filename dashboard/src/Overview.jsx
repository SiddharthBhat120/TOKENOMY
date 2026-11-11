import { useEffect, useState } from 'react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { get, usd, pct, ms, shortModel } from './api.js'

const C = { mint: '#3ddc97', amber: '#ffb547', coral: '#ff6b6b', sky: '#5ab0ff', violet: '#a78bfa', grid: '#232a35', text: '#8b95a7' }
const STATUS_COLORS = { exact_hit: C.mint, semantic_hit: C.sky, miss: C.amber, error: C.coral }

function Kpi({ label, value, sub, accent }) {
  return (
    <div className={'kpi ' + (accent || '')}>
      <span className="kpi-label">{label}</span>
      <b className="kpi-value">{value}</b>
      {sub && <span className="kpi-sub">{sub}</span>}
    </div>
  )
}

function Receipt({ s }) {
  const perReq = s.requests ? s.money_saved_usd / s.requests : 0
  return (
    <div className="receipt">
      <div className="receipt-head">
        <span>RECEIPT</span><span>#{String(s.requests).padStart(5, '0')}</span>
      </div>
      <div className="line"><span>Without TokenSaver</span><span>{usd(s.cost_without_tokensaver_usd)}</span></div>
      <div className="line"><span>You actually paid</span><span>{usd(s.total_cost_usd)}</span></div>
      <div className="line dim"><span>Exact cache hits</span><span>{s.exact_hits}</span></div>
      <div className="line dim"><span>Smart cache hits</span><span>{s.semantic_hits}</span></div>
      <div className="line dim"><span>Routed to cheap model</span><span>{s.routed_to_cheap}</span></div>
      <div className="line total"><span>SAVED</span><span>{usd(s.money_saved_usd)}</span></div>
      <div className="stamp">{pct(s.percent_saved)} OFF</div>
      <p className="projection">
        At <b>1M requests / month</b> this mix saves about <b>{usd(perReq * 1_000_000)}</b>.
      </p>
    </div>
  )
}

const fmtTime = (t, bucket) => {
  const d = new Date(t * 1000)
  return bucket === 'day' ? d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    : d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

export default function Overview({ tick }) {
  const [s, setS] = useState(null)
  const [ts, setTs] = useState([])
  const [models, setModels] = useState([])
  const [recent, setRecent] = useState([])
  const [bucket, setBucket] = useState('minute')
  const [err, setErr] = useState(null)

  useEffect(() => {
    Promise.all([
      get('/stats'), get(`/stats/timeseries?bucket=${bucket}&since_hours=${bucket === 'day' ? 720 : bucket === 'hour' ? 168 : 24}`),
      get('/stats/models'), get('/requests?limit=8'),
    ]).then(([a, b, c, d]) => { setS(a); setTs(b); setModels(c); setRecent(d.items); setErr(null) })
      .catch((e) => setErr(e.message))
  }, [tick, bucket])

  if (err) return <Empty title="Can't reach the gateway" body={<>Start it with <code>uvicorn tokensaver.app:app --port 8000</code> and refresh.</>} />
  if (!s) return <div className="loading">Loading…</div>
  if (!s.requests) return <Empty title="No traffic yet" body={<>Send a request from the <a href="#playground">Playground</a>, run <code>python examples/client.py</code>, or run the benchmark.</>} />

  const pie = [
    { name: 'Exact hits', key: 'exact_hit', value: s.exact_hits },
    { name: 'Smart hits', key: 'semantic_hit', value: s.semantic_hits },
    { name: 'Misses', key: 'miss', value: s.misses },
    { name: 'Errors', key: 'error', value: s.errors },
  ].filter((d) => d.value > 0)

  return (
    <div className="page">
      <section className="hero">
        <div>
          <p className="eyebrow">Money saved so far</p>
          <h1><span className="mint">{usd(s.money_saved_usd)}</span> <small>of {usd(s.cost_without_tokensaver_usd)}</small></h1>
          <p className="lede">{pct(s.percent_saved)} cheaper than sending every request to the strong model, across {s.requests.toLocaleString()} requests.</p>
        </div>
        <Receipt s={s} />
      </section>

      <section className="kpis">
        <Kpi label="Requests" value={s.requests.toLocaleString()} sub={`${s.tokens.toLocaleString()} tokens`} />
        <Kpi label="Spent" value={usd(s.total_cost_usd)} sub="actual provider cost" accent="amber" />
        <Kpi label="Saved" value={pct(s.percent_saved)} sub={usd(s.money_saved_usd)} accent="mint" />
        <Kpi label="Cache hit rate" value={pct(s.cache_hit_rate)} sub={`${s.exact_hits} exact · ${s.semantic_hits} smart`} accent="sky" />
        <Kpi label="Latency (hit)" value={ms(s.avg_latency_hit_ms)} sub={`vs ${ms(s.avg_latency_miss_ms)} on a miss`} />
        <Kpi label="Routed cheap" value={s.routed ? pct(100 * s.routed_to_cheap / s.routed) : '—'} sub={`${s.routed_to_cheap} of ${s.routed} auto-routed`} accent="violet" />
      </section>

      <section className="grid-2">
        <div className="panel span-2">
          <div className="panel-head">
            <h3>Cost vs. cost without TokenSaver <em>cumulative</em></h3>
            <div className="seg">
              {['minute', 'hour', 'day'].map((b) => <button key={b} className={b === bucket ? 'on' : ''} onClick={() => setBucket(b)}>{b}</button>)}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={ts} margin={{ left: 4, right: 12, top: 10 }}>
              <defs>
                <linearGradient id="gBase" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.amber} stopOpacity={0.35} /><stop offset="100%" stopColor={C.amber} stopOpacity={0} /></linearGradient>
                <linearGradient id="gCost" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.mint} stopOpacity={0.45} /><stop offset="100%" stopColor={C.mint} stopOpacity={0} /></linearGradient>
              </defs>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="t" tickFormatter={(t) => fmtTime(t, bucket)} stroke={C.text} fontSize={11} />
              <YAxis tickFormatter={(v) => usd(v, { compact: true })} stroke={C.text} fontSize={11} width={78} />
              <Tooltip contentStyle={{ background: '#11161e', border: '1px solid #2a3240', borderRadius: 10 }}
                labelFormatter={(t) => new Date(t * 1000).toLocaleString()} formatter={(v, n) => [usd(v), n]} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area type="monotone" dataKey="cum_baseline" name="Without TokenSaver" stroke={C.amber} fill="url(#gBase)" strokeWidth={2} />
              <Area type="monotone" dataKey="cum_cost" name="With TokenSaver" stroke={C.mint} fill="url(#gCost)" strokeWidth={2.4} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <div className="panel-head"><h3>Where answers came from</h3></div>
          <ResponsiveContainer width="100%" height={230}>
            <PieChart>
              <Pie data={pie} dataKey="value" nameKey="name" innerRadius={58} outerRadius={88} paddingAngle={3} stroke="none">
                {pie.map((d) => <Cell key={d.key} fill={STATUS_COLORS[d.key]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#11161e', border: '1px solid #2a3240', borderRadius: 10 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <div className="panel-head"><h3>Requests per model</h3></div>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={models.map((m) => ({ ...m, name: shortModel(m.model), misses: m.requests - m.hits }))} margin={{ left: -10, right: 10, top: 10 }}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="name" stroke={C.text} fontSize={11} />
              <YAxis stroke={C.text} fontSize={11} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#11161e', border: '1px solid #2a3240', borderRadius: 10 }} cursor={{ fill: '#ffffff08' }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="misses" name="Called model" stackId="a" fill={C.violet} radius={[0, 0, 4, 4]} />
              <Bar dataKey="hits" name="Served from cache" stackId="a" fill={C.mint} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head"><h3>Latest requests</h3><a href="#requests" className="link">All requests →</a></div>
        <RequestTable rows={recent} />
      </section>
    </div>
  )
}

export function StatusPill({ s }) {
  const label = { exact_hit: 'exact hit', semantic_hit: 'smart hit', miss: 'miss', error: 'error' }[s] || s
  return <span className={'pill ' + s}>{label}</span>
}

export function RequestTable({ rows }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Time</th><th>Prompt</th><th>Cache</th><th>Route</th><th>Model used</th><th className="r">Tokens</th><th className="r">Cost</th><th className="r">Saved</th><th className="r">Latency</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="mono dim">{new Date(r.ts * 1000).toLocaleTimeString()}</td>
              <td className="prompt" title={r.prompt_preview}>{r.prompt_preview || '—'}</td>
              <td><StatusPill s={r.cache_status} /></td>
              <td>{r.route_tier ? <span className={'tier ' + r.route_tier}>{r.route_tier}</span> : <span className="dim">—</span>}</td>
              <td className="mono">{shortModel(r.model_used)}</td>
              <td className="r mono">{r.prompt_tokens + r.completion_tokens}</td>
              <td className="r mono">{usd(r.cost_usd)}</td>
              <td className="r mono mint">{usd(r.baseline_cost_usd - r.cost_usd)}</td>
              <td className="r mono">{ms(r.latency_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Empty({ title, body }) {
  return (
    <div className="empty">
      <div className="empty-mark"><svg viewBox="0 0 32 32"><path d="M8 16.5l5 5L24 10.5" /></svg></div>
      <h2>{title}</h2>
      <p>{body}</p>
    </div>
  )
}
