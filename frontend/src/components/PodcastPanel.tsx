import { useCallback, useEffect, useState } from 'react'
import {
  Button, Space, Spin, Alert, Empty, Tooltip, Progress,
} from 'antd'
import {
  AudioOutlined, ThunderboltOutlined, ReloadOutlined,
  DownloadOutlined, SoundOutlined,
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
