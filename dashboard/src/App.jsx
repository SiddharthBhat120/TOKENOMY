import { useEffect, useState, useCallback } from 'react'
import { get } from './api.js'
import Overview from './Overview.jsx'
import Playground from './Playground.jsx'
import Benchmark from './Benchmark.jsx'
import Requests from './Requests.jsx'

const TABS = [
  ['overview', 'Overview'],
  ['playground', 'Playground'],
  ['benchmark', 'Benchmark'],
  ['requests', 'Requests'],
]

export default function App() {
  const [tab, setTab] = useState(() => location.hash.slice(1) || 'overview')
  const [health, setHealth] = useState(null)
  const [config, setConfig] = useState(null)
  const [tick, setTick] = useState(0)
  const [auto, setAuto] = useState(true)

  const refresh = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    const on = () => setTab(location.hash.slice(1) || 'overview')
    addEventListener('hashchange', on)
    return () => removeEventListener('hashchange', on)
  }, [])

  useEffect(() => {
    get('/health').then(setHealth).catch(() => setHealth(null))
    get('/config').then(setConfig).catch(() => {})
  }, [tick])

  useEffect(() => {
    if (!auto) return
    const id = setInterval(refresh, 10000)
    return () => clearInterval(id)
  }, [auto, refresh])

  return (
    <div className="shell">
      <header className="top">
        <a className="brand" href="#overview">
          <span className="mark" aria-hidden="true">
            <svg viewBox="0 0 32 32"><path d="M8 16.5l5 5L24 10.5" /></svg>
          </span>
          <span>
            <b>Tokenomy</b>
            <small>LLM gateway · cost control</small>
          </span>
        </a>
        <nav>
          {TABS.map(([id, label]) => (
            <a key={id} href={`#${id}`} className={tab === id ? 'on' : ''}>{label}</a>
          ))}
        </nav>
        <div className="top-right">
          <label className="switch" title="Refresh every 10 seconds">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            <span />Live
          </label>
          <span className={'status ' + (health ? 'up' : 'down')}>
            <i />{health ? 'Gateway online' : 'Gateway offline'}
          </span>
        </div>
      </header>

      <main>
        {tab === 'overview' && <Overview tick={tick} config={config} />}
        {tab === 'playground' && <Playground config={config} onSent={refresh} />}
        {tab === 'benchmark' && <Benchmark />}
        {tab === 'requests' && <Requests tick={tick} />}
      </main>

      <footer className="foot">
        <span>Drop-in: point the <code>openai</code> SDK at <code>/v1</code> and use model <code>tokenomy/auto</code>.</span>
        <span>
          {config && <>cheap <code>{config.cheap_model}</code> · strong <code>{config.strong_model}</code> · router {config.router_mode} · threshold {config.semantic_threshold}</>}
        </span>
      </footer>
    </div>
  )
}
