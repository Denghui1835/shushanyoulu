import { useEffect, useState } from 'react'
import {
  Card, Button, Steps, Tag, Checkbox, InputNumber, Select, message, Spin, Typography, Divider, Space,
} from 'antd'
import { RocketOutlined, LeftOutlined, RightOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

const { Title, Paragraph, Text } = Typography

const TIME_SLOTS = ['清晨', '上午', '中午', '下午', '晚上', '睡前']
const DAY_OPTIONS = [3, 5, 7, 14, 21, 30]

interface CurriculumItem { topic: string; desc: string }

export default function PlanWizardPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [curriculum, setCurriculum] = useState<Record<string, Record<string, CurriculumItem[]>>>({})
  const [category, setCategory] = useState('')
  const [categorySub, setCategorySub] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [slots, setSlots] = useState<string[]>(['晚上'])
  const [minutes, setMinutes] = useState(30)
  const [days, setDays] = useState(7)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.getCurriculum().then(setCurriculum).catch(() => { /* ignore */ })
  }, [])

  const subCats = curriculum[category] || {}
  const topics = (subCats[categorySub] || []).map(t => t.topic)

  const generate = async () => {
    if (selected.length === 0) { message.warning('至少选一门想学的课呀'); return }
    setLoading(true)
    try {
      const r = await api.generateWizardPlan({
        courses: selected, time_slots: slots, daily_minutes: minutes, total_days: days,
      })
      message.success(`计划「${r.plan?.title || ''}」生成成功！`)
      navigate('/plan')
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '生成失败，稍后再试')
    } finally { setLoading(false) }
  }

  return (
    <div className="yq-page" style={{ maxWidth: 760, margin: '0 auto' }}>
      <Title level={3} style={{ marginTop: 0 }}>
        <ThunderboltOutlined style={{ color: '#fa8c16' }} /> AI 一键生成计划表
      </Title>
      <Paragraph type="secondary">
        回答几个小问题，AI 帮你排好每天学什么、什么时候学。生成后还能随时手动改。
      </Paragraph>

      <Steps
        current={step}
        size="small"
        items={[{ title: '选课程' }, { title: '选时段' }, { title: '定投入' }]}
        style={{ marginBottom: 24 }}
      />

      {/* Step 1: 选课程 */}
      {step === 0 && (
        <Card title="你想先学哪些课？" size="small">
          <Space style={{ marginBottom: 12 }} wrap>
            <Select
              value={category}
              onChange={c => { setCategory(c); setCategorySub(''); setSelected([]) }}
              style={{ width: 130 }}
              placeholder="学科门类"
              options={Object.keys(curriculum).map(s => ({ value: s, label: s }))}
            />
            {category && (
              <Select
                value={categorySub}
                onChange={s => { setCategorySub(s); setSelected([]) }}
                style={{ width: 180 }}
                placeholder="一级学科"
                options={Object.keys(subCats).map(s => ({ value: s, label: s }))}
              />
            )}
          </Space>
          <Divider plain style={{ margin: '8px 0' }}>勾选想学的知识点（可多选）</Divider>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {topics.map(t => (
              <Tag.CheckableTag
                key={t}
                checked={selected.includes(t)}
                onChange={c => {
                  setSelected(prev => c ? [...prev, t] : prev.filter(x => x !== t))
                }}
                style={{ fontSize: 14, padding: '4px 12px', borderRadius: 6 }}
              >
                {t}
              </Tag.CheckableTag>
            ))}
          </div>
          <Paragraph type="secondary" style={{ marginTop: 12 }}>已选：{selected.length || 0} 个知识点</Paragraph>
        </Card>
      )}

      {/* Step 2: 选时段 */}
      {step === 1 && (
        <Card title="你一般什么时候有空学习？" size="small">
          <Checkbox.Group
            options={TIME_SLOTS}
            value={slots}
            onChange={v => setSlots(v as string[])}
            style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
          />
          <Paragraph type="secondary" style={{ marginTop: 12 }}>
            AI 会把任务排进你选的时段，比如你选「晚上」，计划就安排晚上学。
          </Paragraph>
        </Card>
      )}

      {/* Step 3: 定投入 */}
      {step === 2 && (
        <Card title="每天能投入多少？" size="small">
          <div style={{ marginBottom: 16 }}>
            <Text>每天学习时长：</Text>
            <InputNumber min={10} max={480} step={10} value={minutes} onChange={v => setMinutes(v || 30)}
              addonAfter="分钟" style={{ marginLeft: 8 }} />
          </div>
          <div>
            <Text>计划持续：</Text>
            <Select value={days} onChange={setDays} style={{ marginLeft: 8, width: 120 }}
              options={DAY_OPTIONS.map(d => ({ value: d, label: `${d} 天` }))} />
          </div>
          <Paragraph type="secondary" style={{ marginTop: 16 }}>
            已选 {selected.length} 门课，每天 {minutes} 分钟，共 {days} 天。
          </Paragraph>
        </Card>
      )}

      {/* 底部导航 */}
      <div style={{ marginTop: 24, textAlign: 'right' }}>
        {step > 0 && (
          <Button icon={<LeftOutlined />} onClick={() => setStep(s => s - 1)} style={{ marginRight: 8 }}>
            上一步
          </Button>
        )}
        {step < 2 ? (
          <Button type="primary" icon={<RightOutlined />} onClick={() => setStep(s => s + 1)}>
            下一步
          </Button>
        ) : (
          <Button type="primary" icon={<RocketOutlined />} onClick={generate} loading={loading}>
            ✨ 一键生成计划表
          </Button>
        )}
      </div>
    </div>
  )
}
