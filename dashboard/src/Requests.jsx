import { useEffect, useState } from 'react'
import { get, post } from './api.js'
import { RequestTable, Empty } from './Overview.jsx'

const PAGE = 25

export default function Requests({ tick }) {
  const [page, setPage] = useState(0)
  const [data, setData] = useState(null)

  useEffect(() => {
    get(`/requests?limit=${PAGE}&offset=${page * PAGE}`).then(setData).catch(() => setData({ total: 0, items: [] }))
  }, [tick, page])

  if (!data) return <div className="loading">Loading…</div>
  if (!data.total) return <Empty title="No requests logged yet" body="Every call through the gateway shows up here." />
  const pages = Math.ceil(data.total / PAGE)

  async function reset(what) {
    if (!confirm(`Reset ${what}? This cannot be undone.`)) return
    await post(`/admin/reset?what=${what}`)
    setPage(0)
    location.reload()
  }

  return (
    <div className="page">
      <section className="panel">
        <div className="panel-head">
          <h3>All requests <em>{data.total.toLocaleString()} logged</em></h3>
          <div className="seg">
            <button onClick={() => reset('cache')}>Clear cache</button>
            <button onClick={() => reset('stats')}>Clear stats</button>
          </div>
        </div>
        <RequestTable rows={data.items} />
        <div className="pager">
          <button disabled={page === 0} onClick={() => setPage(page - 1)}>← Newer</button>
          <span className="mono dim">page {page + 1} / {pages}</span>
          <button disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Older →</button>
        </div>
      </section>
    </div>
  )
}
