import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

type Msg = {
  id?: string
  role: 'user' | 'assistant' | 'system'
  content: string
  risk_level?: string | null
}

type ChatResp = {
  conversation_id: string
  user_message_id: string
  assistant_message_id: string
  text: string
  risk_level: string
  provider?: string | null
  model?: string | null
}

type Conversation = {
  id: string
  title: string | null
  archived: boolean
  updated_at: string
}

type ConversationDetail = Conversation & { messages: Msg[] }

const WELCOME: Msg = {
  role: 'assistant',
  content:
    "Hi, I'm here with you. This is a safe, private space. How are you feeling right now?",
}

export default function ChatPage() {
  const qc = useQueryClient()
  const [activeId, setActiveId] = useState<string | null>(null)
  const [draftMessages, setDraftMessages] = useState<Msg[]>([WELCOME])
  const [input, setInput] = useState('')
  const boxRef = useRef<HTMLDivElement>(null)

  const convs = useQuery({
    queryKey: ['conversations'],
    queryFn: async () => {
      const r = await api.get<Conversation[]>('/chat/conversations')
      return r.data
    },
  })

  const active = useQuery({
    queryKey: ['conversation', activeId],
    enabled: !!activeId,
    queryFn: async () => {
      const r = await api.get<ConversationDetail>(
        `/chat/conversations/${activeId}`,
      )
      return r.data
    },
  })

  const messages: Msg[] = activeId
    ? active.data?.messages ?? []
    : draftMessages

  useEffect(() => {
    setTimeout(
      () => boxRef.current?.scrollTo({ top: 1e9, behavior: 'smooth' }),
      30,
    )
  }, [messages.length, active.isFetching])

  const send = useMutation({
    mutationFn: async (content: string) => {
      const r = await api.post<ChatResp>('/chat/message', {
        conversation_id: activeId ?? undefined,
        content,
        max_tokens: 1024,
      })
      return r.data
    },
    onSuccess: async (data) => {
      if (!activeId) setActiveId(data.conversation_id)
      await qc.invalidateQueries({ queryKey: ['conversations'] })
      await qc.invalidateQueries({
        queryKey: ['conversation', data.conversation_id],
      })
    },
    onError: () => {
      // Show a soft failure locally; server persistence is atomic so nothing
      // is left in a half state.
    },
  })

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || send.isPending) return
    setInput('')
    if (!activeId) {
      setDraftMessages((m) => [...m, { role: 'user', content: text }])
    }
    send.mutate(text)
  }

  function newConversation() {
    setActiveId(null)
    setDraftMessages([WELCOME])
  }

  async function archiveActive() {
    if (!activeId) return
    await api.patch(`/chat/conversations/${activeId}`, { archived: true })
    await qc.invalidateQueries({ queryKey: ['conversations'] })
    newConversation()
  }

  return (
    <div className="mx-auto max-w-6xl h-[calc(100vh-57px)] flex px-2 gap-2">
      {/* Sidebar */}
      <aside className="w-60 shrink-0 py-4 hidden sm:flex flex-col border-r border-slate-200 dark:border-slate-800 pr-3">
        <button
          onClick={newConversation}
          className="w-full rounded-md bg-indigo-600 text-white py-2 mb-3 hover:bg-indigo-700"
        >
          + New chat
        </button>
        <div className="overflow-y-auto space-y-1 text-sm">
          {convs.data?.length === 0 && (
            <div className="text-slate-500 italic px-2">No chats yet</div>
          )}
          {convs.data?.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveId(c.id)}
              className={
                'w-full text-left rounded-md px-2 py-1.5 truncate ' +
                (activeId === c.id
                  ? 'bg-slate-200 dark:bg-slate-800'
                  : 'hover:bg-slate-100 dark:hover:bg-slate-800')
              }
              title={c.title ?? 'Untitled'}
            >
              {c.title ?? 'Untitled'}
            </button>
          ))}
        </div>
      </aside>

      {/* Main */}
      <section className="flex-1 flex flex-col min-w-0">
        <div
          ref={boxRef}
          className="flex-1 overflow-y-auto py-4 space-y-3 px-2"
          aria-live="polite"
        >
          {messages.map((m, i) => (
            <div
              key={m.id ?? i}
              className={
                m.role === 'user' ? 'flex justify-end' : 'flex justify-start'
              }
            >
              <div
                className={
                  'max-w-[80%] rounded-2xl px-4 py-2 whitespace-pre-wrap ' +
                  (m.role === 'user'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100')
                }
              >
                {m.content}
                {m.risk_level && m.risk_level !== 'none' && m.role === 'user' && (
                  <div className="mt-1 text-xs opacity-70 uppercase tracking-wide">
                    signal: {m.risk_level}
                  </div>
                )}
              </div>
            </div>
          ))}
          {send.isPending && (
            <div className="text-sm text-slate-500 italic px-2">Thinking…</div>
          )}
        </div>
        <form onSubmit={submit} className="py-3 flex gap-2 px-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type how you're feeling…"
            className="flex-1 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
          />
          <button
            type="submit"
            disabled={send.isPending || !input.trim()}
            className="rounded-md bg-indigo-600 text-white px-4 py-2 hover:bg-indigo-700 disabled:opacity-50"
          >
            Send
          </button>
          {activeId && (
            <button
              type="button"
              onClick={archiveActive}
              className="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-800 text-sm"
              title="Archive this chat"
            >
              Archive
            </button>
          )}
        </form>
        <p className="text-xs text-slate-500 pb-3 text-center px-2">
          This is not medical or crisis care. If you are in immediate danger,
          contact local emergency services.
        </p>
      </section>
    </div>
  )
}
