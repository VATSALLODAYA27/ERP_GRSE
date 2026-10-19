import { MinusOutlined, SendOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import { Button, Input } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { postJson, type User } from '../api'

type Turn = { role: 'user' | 'assistant'; content: string }

// Starter questions for the page the person is on; any other page gets the Control Tower ones.
const SUGGESTIONS: Record<string, string[]> = {
  'Control Tower': ['Which purchase orders are at risk?', 'What should we reorder?', 'Take me to the purchase orders'],
  Requisitions: ['How do I raise a requisition?', 'Who approves a requisition?'],
  'Purchase Orders': ['Which purchase orders are at risk?', 'Who can approve a purchase order?'],
  'Goods Receipts': ['How do I receive goods?'],
  'Vendor Invoices': ['What is a 3-way match?', 'Why is an invoice an exception?'],
  Vendors: ['How is a vendor graded?'],
  'Items & Stock': ['Which items are out of stock?', 'What should we reorder?'],
  'Stock Ledger': ['How do I issue stock to a work order?'],
  'General Ledger': ['Is the trial balance balanced?'],
  Payables: ['What payables are due this week?'],
  'Release Dashboard': ['How many checks are waiting?', 'How do I check a drawing?', 'What can my role do?'],
  'Drawing Register': ['How do I find a drawing?', 'Who can add a drawing?'],
  'New Check': ['What happens with a scanned drawing?', 'Why add the previous revision?'],
  Checks: ['How do I open a check report?', 'Who approves a check?'],
  'Release Gate': ['Which work orders are blocked, and why?', 'What does Warn mean?'],
  'Class Approvals': ['What is this page for?'],
  'Rule Library': ['Why is a rule marked "changed"?', 'Who can approve a rule?'],
  'Audit Log': ['What is recorded here?'],
  Users: ['How do I approve a new account?'],
}

/** Navik: a shipyard engineer in a hard hat and GRSE-blue overalls. */
export function Mascot({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" aria-hidden="true">
      <path d="M20 120C20 98 38 89 60 89s40 9 40 31z" fill="#1D3684" />
      <path d="M49 89l11 13 11-13" fill="#fff" />
      <path d="M60 106v9M55.5 111q4.5 5 9 0M57 108h6" stroke="#fff" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <circle cx="33" cy="62" r="5" fill="#E9B48A" />
      <circle cx="87" cy="62" r="5" fill="#E9B48A" />
      <circle cx="60" cy="60" r="27" fill="#F2C29B" />
      <path d="M31 51a29 27 0 0 1 58 0z" fill="#FFC72C" />
      <rect x="55.5" y="23" width="9" height="28" rx="3" fill="#FFE08A" />
      <rect x="25" y="48" width="70" height="8" rx="4" fill="#E5A800" />
      <circle cx="49.5" cy="66" r="3.3" fill="#1B2340" />
      <circle cx="70.5" cy="66" r="3.3" fill="#1B2340" />
      <circle cx="43" cy="74" r="4" fill="#F08A7B" opacity="0.45" />
      <circle cx="77" cy="74" r="4" fill="#F08A7B" opacity="0.45" />
      <path d="M50 75q10 9 20 0" stroke="#1B2340" strokeWidth="2.6" fill="none" strokeLinecap="round" />
    </svg>
  )
}

/** The helper in the corner of every page. The conversation lives in memory only, so it ends with the tab or the sign-out. */
export default function Helper({ me, page }: { me: User; page: string }) {
  // Starts as the small round button; the person opens it when they want it.
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [draft, setDraft] = useState('')
  const log = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  const ask = useMutation({
    mutationFn: (question: string) => postJson<{ answer: string; go: string | null }>('/helper', { question, page, history: turns.slice(-8) }),
    onSuccess: ({ answer, go }) => {
      setTurns((all) => [...all, { role: 'assistant', content: answer }])
      // Set only when the person asked to be taken somewhere; the server has checked the path.
      if (go) navigate(go)
    },
  })

  const send = (text: string) => {
    const question = text.trim()
    if (!question || ask.isPending) return
    ask.mutate(question)
    setTurns((all) => [...all, { role: 'user', content: question }])
    setDraft('')
  }

  // Keep the newest message in view.
  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight })
  }, [turns, ask.isPending, open])

  if (!open) {
    return (
      <button type="button" className="helper-launcher no-print" aria-label="Open Navik, the helper" onClick={() => setOpen(true)}>
        <Mascot size={52} />
      </button>
    )
  }

  return (
    <section className="helper no-print" aria-label="Navik, the helper">
      <header>
        <span className="helper-face">
          <Mascot size={44} />
        </span>
        <div>
          <strong>Navik</strong>
          <span>SENTINEL shipyard helper</span>
        </div>
        <Button type="text" icon={<MinusOutlined />} aria-label="Minimise the helper" onClick={() => setOpen(false)} />
      </header>
      <div className="helper-log" ref={log} aria-live="polite">
        <p className="helper-bubble">
          Hello {me.name}! I am Navik, your guide to SENTINEL. Ask me how anything on this site works.
        </p>
        {turns.map((turn, i) => (
          <p key={i} className={turn.role === 'user' ? 'helper-bubble mine' : 'helper-bubble'}>
            {turn.content}
          </p>
        ))}
        {ask.isPending && <p className="helper-bubble helper-typing">Navik is typing…</p>}
        {ask.error && <p className="helper-bubble helper-error">{ask.error.message}</p>}
      </div>
      <div className="helper-chips">
        {(SUGGESTIONS[page] ?? SUGGESTIONS['Control Tower']).map((question) => (
          <button key={question} type="button" disabled={ask.isPending} onClick={() => send(question)}>
            {question}
          </button>
        ))}
      </div>
      <footer>
        <Input
          value={draft}
          maxLength={500}
          placeholder="Ask about this site"
          aria-label="Your question for Navik"
          onChange={(e) => setDraft(e.target.value)}
          onPressEnter={() => send(draft)}
        />
        <Button type="primary" icon={<SendOutlined />} aria-label="Send" disabled={!draft.trim()} loading={ask.isPending} onClick={() => send(draft)} />
      </footer>
      <small>Navik answers only about this site. Its answers are written by AI.</small>
    </section>
  )
}
