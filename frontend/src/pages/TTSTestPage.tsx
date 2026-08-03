import { useEffect, useState } from 'react'
import { Card, Select, Input, Button, Space, Tag, message, Spin } from 'antd'
import { SoundOutlined, PauseCircleOutlined } from '@ant-design/icons'
import { useTTSPlay } from '../hooks/useTTSPlay'

interface Voice { provider: string; id: string; name: string }

/** 语音试听：选音色 → 输入文本 → 合成并播放（豆包/edge/azure）。 */
export default function TTSTestPage() {
  const [voices, setVoices] = useState<Voice[]>([])
  const [provider, setProvider] = useState('edge')
  const [voice, setVoice] = useState('zh-CN-XiaoxiaoNeural')
  const [text, setText] = useState('你好，我是小书虫，欢迎来到书山有路！坚持每天学习一点点，知识就会越积越多。')
  const [loading, setLoading] = useState(true)
  const tts = useTTSPlay()

  const load = async () => {
    setLoading(true)
    try {
      const d = await fetch('/api/tts/voices').then(r => r.json())
      setVoices(d.voices || [])
      setProvider(d.voices?.[0]?.provider || 'edge')
      setVoice(d.voices?.[0]?.id || '')
    } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const voicesOfProvider = voices.filter(v => v.provider === provider)
  const providers = [...new Set(voices.map(v => v.provider))]

  const synth = async () => {
    if (!text.trim()) { message.warning('先输入文本'); return }
    try {
      await tts.play(text, voice, provider)
    } catch (e: any) {
      message.error(e?.message || '合成失败')
    }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />

  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      <div className="page-card">
        <Space align="center" style={{ marginBottom: 12 }}>
          <SoundOutlined style={{ fontSize: 24, color: '#7c5cfc' }} />
          <b style={{ fontSize: 17 }}>语音试听</b>
          <Tag color="purple">豆包 / edge / Azure</Tag>
        </Space>

        {/* Provider 选择 */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ color: '#666', marginBottom: 6 }}>音色方案（provider）</div>
          <Space wrap>
            {providers.map(p => (
              <Tag key={p} color={provider === p ? 'purple' : 'default'} style={{ cursor: 'pointer', padding: '3px 10px' }}
                onClick={() => { setProvider(p); setVoice(voices.filter(v => v.provider === p)[0]?.id || '') }}>
                {p === 'edge' ? 'Edge（免费）' : p === 'volc_mega' ? '豆包·大模型音色' : p === 'volc_standard' ? '豆包·普通音色' : p}
              </Tag>
            ))}
          </Space>
          <div style={{ color: '#bbb', fontSize: 12, marginTop: 4 }}>
            {provider.includes('volc') ? '需要 .env 配置 VOLC_APP_ID / VOLC_ACCESS_TOKEN' : 'edge 免费免配置'}
          </div>
        </div>

        {/* 音色选择 */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ color: '#666', marginBottom: 6 }}>音色</div>
          <Select style={{ width: 360 }} value={voice} onChange={setVoice}
            options={voicesOfProvider.map(v => ({ value: v.id, label: v.name }))} />
        </div>

        {/* 文本输入 */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ color: '#666', marginBottom: 6 }}>文本</div>
          <Input.TextArea rows={4} value={text} onChange={e => setText(e.target.value)} maxLength={2000} />
        </div>

        <Space>
          <Button type="primary" icon={<SoundOutlined />} loading={tts.busy} onClick={synth}>
            合成并播放
          </Button>
          {tts.playing && <Button icon={<PauseCircleOutlined />} onClick={tts.stop}>停止</Button>}
        </Space>
      </div>
    </div>
  )
}
