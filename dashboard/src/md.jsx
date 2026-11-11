// Tiny, safe markdown renderer for answers: headings, bullets, numbered lists, **bold**, `code`, code blocks.
import { Fragment } from 'react'

function inline(text, key) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) return <b key={key + i}>{p.slice(2, -2)}</b>
    if (p.startsWith('`') && p.endsWith('`')) return <code key={key + i}>{p.slice(1, -1)}</code>
    return <Fragment key={key + i}>{p}</Fragment>
  })
}

export default function Markdown({ text = '' }) {
  const out = []
  const blocks = text.split(/```/)
  blocks.forEach((block, bi) => {
    if (bi % 2 === 1) {
      out.push(<pre key={'c' + bi}><code>{block.replace(/^[a-z]*\n/, '')}</code></pre>)
      return
    }
    let list = null
    const flush = () => { if (list) { out.push(list.ordered ? <ol key={'l' + out.length}>{list.items}</ol> : <ul key={'l' + out.length}>{list.items}</ul>); list = null } }
    block.split('\n').forEach((line, li) => {
      const k = `${bi}-${li}`
      const t = line.trim()
      const bullet = t.match(/^[*-]\s+(.*)/)
      const num = t.match(/^\d+[.)]\s+(.*)/)
      if (bullet || num) {
        const ordered = !!num
        if (!list || list.ordered !== ordered) { flush(); list = { ordered, items: [] } }
        list.items.push(<li key={k}>{inline((bullet || num)[1], k)}</li>)
        return
      }
      flush()
      if (!t) return
      const h = t.match(/^#{1,4}\s+(.*)/)
      if (h) out.push(<h4 key={k}>{inline(h[1], k)}</h4>)
      else out.push(<p key={k}>{inline(t, k)}</p>)
    })
    flush()
  })
  return <div className="md">{out}</div>
}
