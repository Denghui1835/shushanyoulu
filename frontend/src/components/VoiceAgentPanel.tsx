import { useEffect, useRef, useState } from 'react'
import {
  Button, Input, Space, Tag, message, Tooltip,
} from 'antd'
import {
  AudioOutlined, AudioMutedOutlined, SendOutlined, CheckOutlined, CloseOutlined,
} from '@ant-design/icons'
import { api } from '../api'

interface Msg { role: 'user' | 'assistant'; content: string }

interface ProposalOp {
  type: 'rename' | 'delete' | 'add' | 'merge'
  chapter?: string
  to?: string
  title?: string
  pages?: string
  chapters?: string[]
}

interface Proposal {
  operations: ProposalOp[]
  new_chapters: any[]
  warnings?: string[]
}

interface Props {
  projectId: string
  /** 应用章节修改成功后回调（前端刷新章节列表） */
  onApplied: () => void
}

const OP_TAG: Record<string, { color: string; label: string }> = {
  rename: { color: 'blue', label: '改名' },
  delete: { color: 'red', label: '删除' },
  add: { color: 'green', label: '新增' },
  merge: { color: 'orange', label: '合并' },
}

/** 语音助手：浏览器原生 Web Speech API 语音输入 + 对话 + 章节修改提案（应用/弃用）。 */
export default function VoiceAgentPanel({ projectId, onApplied }: Props) {
  const [msgs, setMsgs] = useState<Msg[]>([{
    role: 'assistant',
    content: '你好，我是这本书的语音助手。可以直接说话或打字，例如「把第3章改名为…」「删掉第5章」或「把前两章合并」。改目录会先给你预览，确认后再应用。',
  }])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [recording, setRecording] = useState(false)
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const recRef = useRef<any>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [msgs, proposal, busy])

  useEffect(() => () => { try { recRef.current?.abort?.() } catch { /* ignore */ } }, [])

  const stopRecognition = () => {
    try { recRef.current?.stop() } catch { /* ignore */ }
    setRecording(false)
  }

  const startRecognition = () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) {
      message.warning('当前浏览器不支持语音输入，请使用 Chrome 或 Edge')
      return
    }
    stopRecognition()
    const rec = new SR()
    rec.lang = 'zh-CN'
    rec.interimResults = false
    rec.maxAlternatives = 1
    rec.onresult = (e: any) => {
      const t = e.results?.[0]?.[0]?.transcript
      if (t) setInput(v => (v ? `${v}${t}` : t))
    }
    rec.onend = () => setRecording(false)
    rec.onerror = () => setRecording(false)
    recRef.current = rec
    try {
      rec.start()
      setRecording(true)
    } catch {
      message.warning('无法启动语音识别')
    }
  }

  const send = async (text?: string) => {
    const content = (text ?? input).trim()
    if (!content || busy) return
    setInput('')
    setProposal(null)
    const history = msgs.slice(-8).map(m => ({ role: m.role, content: m.content }))
    setMsgs(list => [...list, { role: 'user', content }])
    setBusy(true)
    let reply = ''
    try {
      for await (const evt of api.agentChat(projectId, content, history)) {
        if (typeof evt === 'string') reply += evt
        else if (evt.type === 'delta') reply += evt.content ?? ''
        else if (evt.type === 'edit_proposal') setProposal(evt.proposal)
      }
    } catch (e: any) {
      reply = reply || `⚠️ ${e?.message || '调用失败'}`
    } finally {
      setMsgs(list => [...list, { role: 'assistant', content: reply || '（无回复）' }])
      setBusy(false)
    }
  }

  const applyProposal = async () => {
    if (!proposal) return
    try {
      await api.syncProjectChapters(projectId, proposal.new_chapters)
      message.success('已应用章节修改')
      setProposal(null)
      onApplied()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '应用失败')
    }
  }

  return (
    <div>
      <div
        ref={listRef}
        style={{ height: 300, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}
      >
        {msgs.map((m, i) => (
          <div
            key={i}
            style={{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '88%', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              background: m.role === 'user' ? '#7c5cfc' : '#f2f2f6',
              color: m.role === 'user' ? '#fff' : '#333',
              padding: '8px 12px', borderRadius: 10, fontSize: 14,
            }}
          >
            {m.content}
          </div>
        ))}
        {busy && <div style={{ color: '#999', fontSize: 13 }}>思考中…</div>}
      </div>

      {proposal && (
        <div>
          <div className="title-box-h3">目录变更 · 弃用/还原</div>
          <div style={{ border: '1px solid #f0c36d', borderRadius: 10, padding: 12, marginBottom: 10, background: '#fffbe6' }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>🗂 语音助手提议修改章节</div>
          {proposal.operations.map((op, i) => (
            <div key={i} style={{ fontSize: 13, margin: '3px 0' }}>
              <Tag color={OP_TAG[op.type]?.color} style={{ marginRight: 6 }}>{OP_TAG[op.type]?.label}</Tag>
              {op.type === 'rename' && <>「{op.chapter}」→「{op.to}」</>}
              {op.type === 'delete' && <>删除「{op.chapter}」</>}
              {op.type === 'add' && <>新增「{op.title}」（第 {op.pages} 页）</>}
              {op.type === 'merge' && <>合并 [{op.chapters?.join('、')}] → 「{op.to}」</>}
            </div>
          ))}
          {proposal.warnings?.map((w, i) => (
            <div key={i} style={{ color: '#fa8c16', fontSize: 12, marginTop: 4 }}>⚠️ {w}</div>
          ))}
          <Space style={{ marginTop: 8 }}>
            <Button type="primary" size="small" icon={<CheckOutlined />} onClick={applyProposal}>应用</Button>
            <Button size="small" icon={<CloseOutlined />} onClick={() => setProposal(null)}>弃用</Button>
          </Space>
          </div>
        </div>
      )}

      <Space.Compact style={{ width: '100%' }}>
        <Tooltip title={recording ? '停止录音' : '语音输入'}>
          <Button
            icon={recording ? <AudioMutedOutlined /> : <AudioOutlined />}
            type={recording ? 'primary' : 'default'}
            style={{ width: 44 }}
            onClick={recording ? stopRecognition : startRecognition}
          />
        </Tooltip>
        <Input
          value={input}
          onChange={e => setInput(e.target.value)}
          onPressEnter={() => send()}
          placeholder="语音或打字提问，如「把第3章改名为…」"
          disabled={recording}
        />
        <Button type="primary" icon={<SendOutlined />} loading={busy} onClick={() => send()}>发送</Button>
      </Space.Compact>
    </div>
  )
}
