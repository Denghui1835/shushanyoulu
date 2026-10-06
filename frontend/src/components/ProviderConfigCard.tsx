import { useEffect, useMemo, useState } from 'react'
import {
  Alert, AutoComplete, Button, Input, Popconfirm, Space, Tag, Tooltip, message,
} from 'antd'
import {
  CheckCircleOutlined, CloseCircleOutlined, DeleteOutlined, EyeOutlined,
  LoadingOutlined, ReloadOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { api } from '../api'

/**
 * 一档能力的服务商配置卡（文本 / 视觉 / 语音）。
 *
 * 为什么是「一档一张卡」而不是一个通用表单：各家服务商的能力并不通用 ——
 * DeepSeek 只有文本、没有语音；反过来 edge 语音不需要任何 Key。
 * 一个「Key + 地址 + 模型名」的三元组表达不了这件事，用户想配语音也没有入口。
 *
 * 凭据形状随服务商变（edge 无、volc 要 app_id+access_token、azure 要 key+region、
 * LLM 要 api_key），所以字段由后端下发的 preset 动态渲染，前端不硬编码。
 */
export default function ProviderConfigCard({
  capability, label, hint, presets, config, onChanged,
}: {
  capability: string
  label: string
  hint: string
  presets: any[]
  config: any
  onChanged: () => void
}) {
  const [provider, setProvider] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [secret, setSecret] = useState<Record<string, string>>({})
  const [options, setOptions] = useState<Record<string, string>>({})
  const [fetchedModels, setFetchedModels] = useState<string[]>([])
  const [fetching, setFetching] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [sampleAudio, setSampleAudio] = useState('')
  // 用户是否手改过 base_url / model —— 手改过就别被预设默认值覆盖
  const [touched, setTouched] = useState(false)

  const preset = useMemo(
    () => presets.find(p => p.provider === provider) || null, [presets, provider])

  // 载入：已配置则回填已存的值，否则默认选第一个服务商
  useEffect(() => {
    if (config?.configured) {
      setProvider(config.provider || '')
      setBaseUrl(config.base_url || '')
      setModel(config.model || '')
      setOptions(config.options || {})
      setSecret({})
      setTouched(true)
    } else {
      const first = presets[0]
      setProvider(first?.provider || '')
      setBaseUrl(first?.base_url || '')
      setModel(first?.models?.[0] || '')
      setOptions(Object.fromEntries((first?.option_fields || []).map(
        (f: any) => [f.key, f.default ?? ''])))
      setSecret({})
      setTouched(false)
    }
    setFetchedModels([])
    setSampleAudio('')
  }, [config, presets])

  const switchProvider = (p: any) => {
    setProvider(p.provider)
    setFetchedModels([])
    setSampleAudio('')
    // 切服务商时用预设默认值自动填 —— 这正是「系统怎么知道该用哪个模型」的答案：
    // 预设给了可用的默认，用户不必自己猜模型名。
    setBaseUrl(p.base_url || '')
    setModel(p.models?.[0] || '')
    setOptions(Object.fromEntries(
      (p.option_fields || []).map((f: any) => [f.key, f.default ?? ''])))
    setTouched(false)
  }

  const pullModels = async () => {
    setFetching(true)
    try {
      const r = await api.listProviderModels({ provider, base_url: baseUrl, secret })
      setFetchedModels(r.models || [])
      message[r.supported ? 'success' : 'info'](
        r.supported ? `拉到 ${r.models.length} 个模型` : (r.hint || '该服务未提供模型列表'))
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '拉取失败')
    } finally { setFetching(false) }
  }

  const payload = () => ({
    provider, base_url: baseUrl, model, secret, options,
  })

  const doTest = async () => {
    setTesting(true)
    setSampleAudio('')
    try {
      const r = await api.testProviderConfig({ capability, ...payload() })
      message.success(r.message || '连接成功')
      if (r.sample_audio_b64) setSampleAudio(`data:audio/mpeg;base64,${r.sample_audio_b64}`)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '连接失败')
    } finally { setTesting(false) }
  }

  const doSave = async () => {
    setSaving(true)
    try {
      await api.saveProviderConfig(capability, payload())
      message.success(`「${label}」已保存`)
      setSecret({})
      setSampleAudio('')
      onChanged()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '保存失败')
    } finally { setSaving(false) }
  }

  const doDelete = async () => {
    try {
      await api.deleteProviderConfig(capability)
      message.success(`「${label}」已删除，回退默认`)
      onChanged()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    }
  }

  const modelChoices = useMemo(() => {
    const set = new Set<string>([...(preset?.models || []), ...fetchedModels])
    return [...set].map(m => ({ value: m }))
  }, [preset, fetchedModels])

  const configured = !!config?.configured

  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <b>{label}</b>
        {configured ? (
          config.needs_refill ? (
            <Tooltip title="凭据已存但解不开（加密密钥变过），请重新填写">
              <Tag icon={<CloseCircleOutlined />} color="warning">需重新填写</Tag>
            </Tooltip>
          ) : (
            <Tag icon={<CheckCircleOutlined />} color="success">
              已配置 · {config.masked_key || config.provider}
            </Tag>
          )
        ) : (
          <Tag color="default">未配置</Tag>
        )}
        {configured && (
          <Popconfirm title={`删除「${label}」配置？将回退到系统默认。`} onConfirm={doDelete}>
            <Button size="small" danger type="text" icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        )}
      </div>

      <div style={{ color: '#999', fontSize: 12, marginBottom: 8 }}>{hint}</div>

      {/* 服务商选择 */}
      <div style={{ marginBottom: 10 }}>
        <Space wrap size={6}>
          {presets.map(p => (
            <Tag.CheckableTag
              key={p.provider}
              checked={provider === p.provider}
              onChange={() => switchProvider(p)}
              style={{
                cursor: 'pointer', padding: '3px 10px', borderRadius: 14,
                border: '1px solid ' + (provider === p.provider ? '#7c5cfc' : '#e5e5e5'),
                background: provider === p.provider ? '#f9f0ff' : '#fff',
              }}
            >
              {p.label}
            </Tag.CheckableTag>
          ))}
        </Space>
      </div>

      {preset?.note && (
        <Alert type="info" showIcon style={{ marginBottom: 10, fontSize: 12 }}
          message={preset.note} />
      )}

      {/* 动态字段 */}
      <Space direction="vertical" size={8} style={{ width: '100%', maxWidth: 560 }}>
        {(preset?.secret_fields || []).map((f: any) => (
          <div key={f.key}>
            <div style={{ fontSize: 12, color: '#666', marginBottom: 2 }}>
              {f.label}{f.required && <span style={{ color: '#ff4d4f' }}> *</span>}
              {configured && config.secret_set?.[f.key] && (
                <span style={{ color: '#52c41a', marginLeft: 6 }}>（已存，留空则不修改）</span>
              )}
            </div>
            <Input.Password
              value={secret[f.key] || ''}
              placeholder={f.placeholder || ''}
              autoComplete="new-password"
              style={{ maxWidth: 380 }}
              onChange={e => setSecret(s => ({ ...s, [f.key]: e.target.value }))}
            />
          </div>
        ))}

        {preset?.base_url !== undefined && (
          <div>
            <div style={{ fontSize: 12, color: '#666', marginBottom: 2 }}>接口地址（含版本段）</div>
            <Input
              value={baseUrl}
              placeholder={preset?.base_url || 'https://example.com/v1'}
              style={{ maxWidth: 380 }}
              onChange={e => { setBaseUrl(e.target.value); setTouched(true) }}
            />
          </div>
        )}

        {!!(preset?.models?.length || fetchedModels.length || preset?.supports_model_list) && (
          <div>
            <div style={{ fontSize: 12, color: '#666', marginBottom: 2 }}>
              模型名
              {!touched && preset?.models?.length ? (
                <span style={{ color: '#bbb', marginLeft: 6 }}>（已按预设填好，可改）</span>
              ) : null}
            </div>
            <Space.Compact style={{ width: 380 }}>
              <AutoComplete
                value={model}
                options={modelChoices}
                style={{ flex: 1 }}
                placeholder="deepseek-chat"
                onChange={v => { setModel(v); setTouched(true) }}
                filterOption={(input, opt) =>
                  String(opt?.value || '').toLowerCase().includes(input.toLowerCase())}
              />
              {preset?.supports_model_list && (
                <Button
                  icon={fetching ? <LoadingOutlined /> : <ReloadOutlined />}
                  onClick={pullModels}
                  disabled={fetching || !baseUrl}
                >拉取列表</Button>
              )}
            </Space.Compact>
          </div>
        )}

        {(preset?.option_fields || []).map((f: any) => (
          <div key={f.key}>
            <div style={{ fontSize: 12, color: '#666', marginBottom: 2 }}>{f.label}</div>
            <Input
              value={options[f.key] ?? ''}
              style={{ maxWidth: 380 }}
              onChange={e => setOptions(o => ({ ...o, [f.key]: e.target.value }))}
            />
          </div>
        ))}
      </Space>

      <Space style={{ marginTop: 12 }} wrap>
        <Button
          type="primary" icon={<ThunderboltOutlined />}
          loading={saving} onClick={doSave}
        >保存并启用</Button>
        <Button loading={testing} onClick={doTest}>测试连接</Button>
        {sampleAudio && (
          <Space size={4}>
            <EyeOutlined style={{ color: '#52c41a' }} />
            <audio controls src={sampleAudio} style={{ height: 32 }} />
          </Space>
        )}
      </Space>
    </div>
  )
}
