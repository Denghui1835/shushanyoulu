import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button, Space, Spin, Alert, Empty, Tooltip, Progress, Input, message,
} from 'antd'
import {
  AudioOutlined, AudioMutedOutlined, ThunderboltOutlined, ReloadOutlined,
  DownloadOutlined, SoundOutlined, EditFilled,
} from '@ant-design/icons'
import { api } from '../api'

interface PodcastScript {
  id: string | null
  document_id: string
  unit_index: number
  content: string
  status: 'none' | 'generating' | 'done' | 'error'
  error: string
  has_audio: boolean
  audio_seconds: number
}

interface Props {
  docId: string
  unitIndex: number
  unitTitle: string
}

/** AI 播客面板：生成/查看双人对谈文稿 → 合成音频 → 试听/下载。
 *  对标豆包 AI 播客，每个阅读单元独立一条。 */
export default function PodcastPanel({ docId, unitIndex, unitTitle }: Props) {
  const [script, setScript] = useState<PodcastScript | null>(null)
  const [loading, setLoading] = useState(false)     // 文稿查询/生成中
  const [genAudio, setGenAudio] = useState(false)   // 音频合成中
  const [audioUrl, setAudioUrl] = useState('')
  const [audioErr, setAudioErr] = useState('')
  // 文稿修改（打字/语音）
  const [editInstr, setEditInstr] = useState('')
  const [editing, setEditing] = useState(false)
  const [recording, setRecording] = useState(false)
  const recRef = useRef<any>(null)

  useEffect(() => () => { try { recRef.current?.abort?.() } catch { /* ignore */ } }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setAudioErr('')
    try {
      const s = await api.getPodcastScript(docId, unitIndex)
      setScript(s)
      setAudioUrl(s?.status === 'done' && s?.has_audio ? api.podcastAudioUrl(docId, unitIndex) : '')
    } finally { setLoading(false) }
  }, [docId, unitIndex])

  useEffect(() => { load() }, [load])

  const generate = async () => {
    setLoading(true)
    setAudioErr('')
    try {
      const s = await api.generatePodcastScript(docId, unitIndex)
      setScript(s)
      setAudioUrl('')  // 文稿变了，旧音频作废
    } catch (e: any) {
      setScript(prev => prev ? { ...prev, status: 'error', error: e?.response?.data?.detail || '生成失败' } : prev)
    } finally { setLoading(false) }
  }

  const genAudioClick = async () => {
    setGenAudio(true)
    setAudioErr('')
    try {
      const s = await api.generatePodcastAudio(docId, unitIndex)
      setScript(s)
      setAudioUrl(api.podcastAudioUrl(docId, unitIndex))
    } catch (e: any) {
      setAudioErr(e?.response?.data?.detail || '音频生成失败，请稍后重试')
    } finally { setGenAudio(false) }
  }

  const minutes = script?.audio_seconds ? Math.max(1, Math.round(script.audio_seconds / 60)) : 0

  // ---------- 文稿修改：打字 / 语音 ----------
  const stopRecognition = () => {
    try { recRef.current?.stop() } catch { /* ignore */ }
    setRecording(false)
  }
  const startRecognition = () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) { message.warning('当前浏览器不支持语音输入，请使用 Chrome 或 Edge'); return }
    stopRecognition()
    const rec = new SR()
    rec.lang = 'zh-CN'
    rec.interimResults = false
    rec.onresult = (e: any) => {
      const t = e.results?.[0]?.[0]?.transcript
      if (t) setEditInstr(v => (v ? `${v}${t}` : t))
    }
    rec.onend = () => setRecording(false)
    rec.onerror = () => setRecording(false)
    recRef.current = rec
    try { rec.start(); setRecording(true) } catch { message.warning('无法启动语音识别') }
  }

  const applyEdit = async () => {
    const instr = editInstr.trim()
    if (!instr) { message.warning('先输入或说出修改要求'); return }
    setEditing(true)
    try {
      const s = await api.editPodcastScript(docId, unitIndex, instr)
      setScript(s)
      setAudioUrl('')  // 文稿改了，旧音频作废，需重新合成
      setEditInstr('')
      message.success('文稿已按你的要求修改')
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '修改失败')
    } finally { setEditing(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* 头部说明 + 动作 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
        <SoundOutlined style={{ color: '#7c5cfc' }} />
        <b>AI 播客</b>
        <Tag_ title="本单元独立生成一期双主播对谈" />
        <div style={{ marginLeft: 'auto' }}>
          {script?.status !== 'done' && (
            <Button
              size="small" type="primary" icon={<ThunderboltOutlined />}
              loading={loading}
              onClick={generate}
            >
              {script?.id ? '重新生成文稿' : '生成文稿'}
            </Button>
          )}
        </div>
      </div>

      {loading ? (
        <Spin style={{ display: 'block', margin: 24 }} />
      ) : !script || script.status === 'none' ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={`为「${unitTitle}」生成一期双主播 AI 播客`} />
      ) : (
        <>
          {script.status === 'error' && (
            <Alert type="error" showIcon message="文稿生成失败" description={script.error} />
          )}

          {script.status === 'done' && (
            <>
              {/* 文稿预览 */}
              <div style={{ fontSize: 13.5, lineHeight: 1.8, whiteSpace: 'pre-wrap',
                background: '#f7f7fb', borderRadius: 8, padding: 10, maxHeight: 260, overflowY: 'auto' }}>
                {script.content}
              </div>
              <Space wrap size={8}>
                <Button size="small" icon={<ReloadOutlined />} onClick={generate}>重新生成文稿</Button>
                <Button size="small" type="primary" icon={<AudioOutlined />} loading={genAudio} onClick={genAudioClick}>
                  {script.has_audio ? '重新合成音频' : '合成音频'}
                </Button>
                <span style={{ fontSize: 12, color: '#999' }}>约 {minutes} 分钟</span>
              </Space>

              {audioErr && <Alert type="warning" showIcon message={audioErr} style={{ marginTop: 4 }} />}

              {/* 试听 / 下载 */}
              {audioUrl && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
                  <audio controls src={audioUrl} preload="none" style={{ width: '100%', height: 34 }} />
                  <Tooltip title="下载 mp3">
                    <Button size="small" icon={<DownloadOutlined />} href={audioUrl} target="_blank" />
                  </Tooltip>
                </div>
              )}

              {/* 修改文稿：打字 / 语音 */}
              <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 10, marginTop: 4 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <EditFilled style={{ color: '#7c5cfc' }} />
                  <b style={{ fontSize: 13 }}>修改文稿</b>
                  <span style={{ fontSize: 12, color: '#999' }}>打字或语音告诉 AI 怎么改，改后需重新合成音频</span>
                </div>
                <Space.Compact style={{ width: '100%' }}>
                  <Tooltip title={recording ? '停止录音' : '语音输入'}>
                    <Button
                      icon={recording ? <AudioMutedOutlined /> : <AudioOutlined />}
                      type={recording ? 'primary' : 'default'}
                      style={{ width: 40 }}
                      onClick={recording ? stopRecognition : startRecognition}
                    />
                  </Tooltip>
                  <Input
                    value={editInstr}
                    onChange={e => setEditInstr(e.target.value)}
                    onPressEnter={applyEdit}
                    placeholder="如：把开头改成欢迎语 / 加一段主播B的总结"
                    disabled={recording}
                  />
                  <Button type="primary" icon={<EditFilled />} loading={editing} onClick={applyEdit}>修改</Button>
                </Space.Compact>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

function Tag_({ title }: { title: string }) {
  return (
    <span style={{ fontSize: 11, color: '#7c5cfc', background: '#f4f0ff', padding: '1px 6px', borderRadius: 4 }}>
      {title}
    </span>
  )
}
