import { useEffect, useRef, useState } from 'react'
import { get, post, usd, ms, shortModel } from './api.js'
import { StatusPill } from './Overview.jsx'
import Markdown from './md.jsx'

const SAMPLES = [
  ['Easy FAQ', 'How do I reset my password?'],
  ['Paraphrase it', 'I forgot my password, how can I reset it?'],
  ['Trap: looks similar', 'How do I reset my username?'],
  ['Easy', 'Translate "good morning" to Hindi.'],
  ['Hard', 'Design a URL shortener that handles 50k requests per second. Explain the database choice and trade-offs step by step.'],
  ['Code', 'Write a Python function that merges overlapping intervals, with type hints and tests.'],
]

export default function Playground({ config, onSent }) {
  const [prompt, setPrompt] = useState(SAMPLES[0][1])
  const [model, setModel] = useState('tokensaver/auto')
  const [temperature, setTemperature] = useState(0)
  const [skip, setSkip] = useState(false)
  const [route, setRoute] = useState(null)
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState([])
  const timer = useRef()

  useEffect(() => {
    clearTimeout(timer.current)
    if (!prompt.trim()) return setRoute(null)
    timer.current = setTimeout(() => {
      get('/router/explain?prompt=' + encodeURIComponent(prompt)).then(setRoute).catch(() => setRoute(null))
    }, 250)
  }, [prompt])

  async function send() {
    if (!prompt.trim() || busy) return
    setBusy(true)
    const t0 = performance.now()
    const res = await post('/v1/chat/completions',
      { model, temperature, max_tokens: 300, messages: [{ role: 'user', content: prompt }] },
      skip ? { 'X-TokenSaver-Cache': 'skip' } : {})
    const wall = performance.now() - t0
    setHistory((h) => [{ id: Date.now(), prompt, res, wall }, ...h].slice(0, 12))
    setBusy(false)
    onSent?.()
  }

  const models = ['tokensaver/auto', config?.cheap_model, config?.strong_model].filter(Boolean)

  return (
    <div className="page play">
      <section className="panel compose">
        <div className="panel-head">
          <h3>Try it <em>every request goes through the real gateway</em></h3>
        </div>
        <div className="samples">
          {SAMPLES.map(([label, text]) => (
            <button key={label} onClick={() => setPrompt(text)} className={prompt === text ? 'on' : ''}>{label}</button>
          ))}
        </div>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={4}
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send() }}
          placeholder="Ask anything…" aria-label="Prompt" />
        <div className="controls">
          <label>Model
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <label>Temperature <b>{temperature.toFixed(1)}</b>
            <input type="range" min="0" max="1" step="0.1" value={temperature} onChange={(e) => setTemperature(+e.target.value)} />
          </label>
          <label className="check"><input type="checkbox" checked={skip} onChange={(e) => setSkip(e.target.checked)} /> Skip cache</label>
          <button className="primary" onClick={send} disabled={busy}>{busy ? 'Thinking…' : 'Send  ⌃↵'}</button>
        </div>
        {temperature > (config?.cache_max_temperature ?? 0.3) && (
          <p className="hint">Temperature above {config?.cache_max_temperature ?? 0.3} is never cached: the caller is asking for varied answers.</p>
        )}
        {route && model === 'tokensaver/auto' && (
          <div className={'route-card ' + route.tier}>
            <div>
              <span className="eyebrow">Router decision (live)</span>
              <b>{route.tier === 'easy' ? 'EASY → cheap model' : 'HARD → strong model'}</b>
              <span className="mono">{shortModel(route.model)}</span>
            </div>
            <div className="meter"><i style={{ width: `${Math.round(route.score * 100)}%` }} /><span>difficulty {Math.round(route.score * 100)}</span></div>
            <ul>{route.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          </div>
        )}
      </section>

      <section className="results">
        {!history.length && <p className="dim center">Your answers appear here with cache status, model, cost and latency. Tip: send the FAQ, then the paraphrase, then the trap.</p>}
        {history.map(({ id, prompt, res, wall }) => {
          const x = res.data.x_tokensaver || {}
          const answer = res.ok ? res.data.choices?.[0]?.message?.content : res.data.error?.message
          return (
            <article key={id} className={'answer ' + (res.ok ? '' : 'err')}>
              <header>
                <p className="q">{prompt}</p>
                <div className="chips">
                  <StatusPill s={res.ok ? x.cache_status : 'error'} />
                  {x.route && <span className={'tier ' + x.route}>{x.route}</span>}
                  {x.model_used && <span className="chip mono">{shortModel(x.model_used)}</span>}
                  {x.similarity && <span className="chip mono">sim {x.similarity.toFixed(3)}</span>}
                  <span className="chip mono">{ms(x.latency_ms ?? wall)}</span>
                  {res.ok && <span className="chip mono">cost {usd(x.cost_usd)}</span>}
                  {res.ok && x.cost_without_tokensaver_usd > x.cost_usd && <span className="chip mono mint">saved {usd(x.cost_without_tokensaver_usd - x.cost_usd)}</span>}
                </div>
              </header>
              {x.matched_prompt && <p className="matched">Reused the answer to: “{x.matched_prompt}”</p>}
              <div className="body">{res.ok ? <Markdown text={answer} /> : answer}</div>
            </article>
          )
        })}
      </section>
    </div>
  )
}
