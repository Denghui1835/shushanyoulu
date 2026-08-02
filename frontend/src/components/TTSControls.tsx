import { Button, Select, Slider, Space, Tooltip, Progress } from 'antd'
import {
  PlayCircleOutlined, PauseCircleOutlined, StepBackwardOutlined,
  StepForwardOutlined, StopOutlined, SoundOutlined,
} from '@ant-design/icons'
import type { TTSState, TTSSource } from '../hooks/useTTS'

interface Props {
  state: TTSState
  currentIndex: number
  total: number
  rate: number
  source: TTSSource
  disabled: boolean
  onSourceChange: (s: TTSSource) => void
  onPlayPause: () => void
  onStop: () => void
  onPrev: () => void
  onNext: () => void
  onRateChange: (r: number) => void
}

const RATE_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2].map(v => ({ value: v, label: `${v}x` }))

export default function TTSControls({
  state, currentIndex, total, rate, source, disabled,
  onSourceChange, onPlayPause, onStop, onPrev, onNext, onRateChange,
}: Props) {
  const playing = state === 'playing'
  const paused = state === 'paused'
  const active = playing || paused
  const progress = total > 0 ? Math.round(((currentIndex + 1) / total) * 100) : 0

  return (
    <div className="tts-bar">
      <SoundOutlined style={{ color: '#7c5cfc', fontSize: 16 }} />
      <Select
        size="small" value={source} style={{ width: 120 }}
        options={[
          { value: 'original', label: '读原文' },
          { value: 'summary', label: '读页总结' },
          { value: 'story', label: '听书总结' },
        ]}
        onChange={onSourceChange}
      />
      <Space size={2}>
        <Tooltip title="上一段">
          <Button type="text" size="small" icon={<StepBackwardOutlined />}
            disabled={disabled || !active} onClick={onPrev} />
        </Tooltip>
        <Tooltip title={playing ? '暂停' : '播放/继续'}>
          <Button
            type="primary" shape="circle" icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
            disabled={disabled} onClick={onPlayPause}
          />
        </Tooltip>
        <Tooltip title="下一段">
          <Button type="text" size="small" icon={<StepForwardOutlined />}
            disabled={disabled || !active} onClick={onNext} />
        </Tooltip>
        <Tooltip title="停止">
          <Button type="text" size="small" icon={<StopOutlined />}
            disabled={disabled || !active} onClick={onStop} />
        </Tooltip>
      </Space>

      <Select size="small" value={rate} style={{ width: 76 }} onChange={onRateChange}
        options={RATE_OPTIONS} />

      <div style={{ flex: 1, minWidth: 120, display: 'flex', alignItems: 'center', gap: 8 }}>
        <Progress percent={progress} size="small" style={{ flex: 1, margin: 0 }} />
        <span style={{ fontSize: 12, color: '#999', whiteSpace: 'nowrap' }}>
          {active ? `${currentIndex + 1}/${total}` : '就绪'}
        </span>
      </div>
    </div>
  )
}
