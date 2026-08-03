import { useEffect, useState } from 'react'
import { ScrollView, View, Alert } from 'react-native'
import { Appbar, Card, Text, Button, Avatar, TextInput, Chip, ActivityIndicator } from 'react-native-paper'
import { useRouter } from 'expo-router'
import { api } from '../../src/api'
import { getToken, clearToken } from '../../src/tokenStore'

export default function ProfileScreen() {
  const router = useRouter()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [goal, setGoal] = useState('')
  const [key, setKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [saving, setSaving] = useState(false)
  const [keyInfo, setKeyInfo] = useState<any>(null)

  const load = async () => {
    setLoading(true)
    try {
      if (!(await getToken())) { setData(null); return }
      const p = await api.getProfileInfo()
      setData(p)
      setName(p.user.name); setGoal(p.user.goal || '')
      setKeyInfo(await api.getApiKey())
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const save = async () => {
    setSaving(true)
    try { await api.updateProfileInfo({ name, goal }); Alert.alert('已保存'); load() }
    catch (e: any) { Alert.alert('保存失败', e?.message) }
    finally { setSaving(false) }
  }

  const saveKey = async () => {
    if (!key) return
    setSaving(true)
    try {
      const r = await api.saveApiKey({ api_key: key, base_url: baseUrl, model })
      Alert.alert('已保存', r.masked_key ? `Key: ${r.masked_key}` : '后续 AI 功能将使用你的 Key')
      setKey(''); setBaseUrl(''); setModel('')
      setKeyInfo(await api.getApiKey())
    } catch (e: any) { Alert.alert('保存失败', e?.message) }
    finally { setSaving(false) }
  }

  const logout = async () => {
    try { await api.logout() } catch { /* ignore */ }
    await clearToken()
    setData(null)
  }

  if (loading) return <ActivityIndicator style={{ marginTop: 60 }} />

  if (!data) {
    return (
      <View style={{ flex: 1 }}>
        <Appbar.Header><Appbar.Content title="个人中心" /></Appbar.Header>
        <View style={{ alignItems: 'center', padding: 40 }}>
          <Text style={{ fontSize: 44 }}>👤</Text>
          <Text style={{ marginTop: 12, color: '#666' }}>登录后才能查看个人中心</Text>
          <Button mode="contained" style={{ marginTop: 12 }} onPress={() => router.push('/community')}>去登录</Button>
        </View>
      </View>
    )
  }

  const s = data.stats || {}
  const u = data.user || {}

  return (
    <View style={{ flex: 1 }}>
      <Appbar.Header><Appbar.Content title="个人中心" /></Appbar.Header>
      <ScrollView contentContainerStyle={{ padding: 12, gap: 10 }}>
        {/* 头像 + 基本信息 */}
        <Card mode="outlined">
          <Card.Content style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <Avatar.Text size={56} label={(u.name || '书')[0]} style={{ backgroundColor: '#7c5cfc' }} />
            <View style={{ flex: 1 }}>
              <Text variant="titleMedium">{u.name}</Text>
              <Text variant="bodySmall" style={{ color: '#888' }}>@{u.username || '本地用户'}</Text>
              <View style={{ flexDirection: 'row', gap: 6, marginTop: 4 }}>
                <Chip compact>{u.wechat_bound ? '已绑微信' : '用户名密码'}</Chip>
                {u.api_key_set && <Chip compact icon="key">自有 Key</Chip>}
              </View>
            </View>
            <Button mode="outlined" compact onPress={logout}>退出</Button>
          </Card.Content>
        </Card>

        {/* 统计 */}
        <Card mode="outlined">
          <Card.Title title="📊 学习统计" />
          <Card.Content>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {[['项目', s.projects], ['题目', s.questions], ['闪卡', s.flashcards], ['播客', s.podcasts], ['连续打卡', s.streak], ['元气值', `⚡${s.points}`]].map(([l, v]) => (
                <Chip key={l as string} compact>{l} {v}</Chip>
              ))}
            </View>
          </Card.Content>
        </Card>

        {/* 资料编辑 */}
        <Card mode="outlined">
          <Card.Title title="学习资料" />
          <Card.Content style={{ gap: 8 }}>
            <TextInput mode="outlined" label="昵称" value={name} onChangeText={setName} />
            <TextInput mode="outlined" label="学习目标" value={goal} onChangeText={setGoal} multiline />
            <Button mode="contained" onPress={save} loading={saving}>保存</Button>
          </Card.Content>
        </Card>

        {/* API 设置 */}
        <Card mode="outlined">
          <Card.Title title="🔑 API 设置（使用自己的 Key）" />
          <Card.Content style={{ gap: 8 }}>
            <Text variant="bodySmall" style={{ color: '#888' }}>
              填写你自己的 API Key，AI 功能将用你的 Key（费用自理）；不填则用系统默认 Key。
            </Text>
            {keyInfo?.configured && <Chip compact icon="check">已配置 {keyInfo.masked_key}</Chip>}
            <TextInput mode="outlined" label="API Key" value={key} onChangeText={setKey} secureTextEntry placeholder="sk-..." />
            <TextInput mode="outlined" label="Base URL（可留空）" value={baseUrl} onChangeText={setBaseUrl} placeholder="https://api.deepseek.com" />
            <TextInput mode="outlined" label="模型名（可留空）" value={model} onChangeText={setModel} placeholder="deepseek-chat" />
            <Button mode="contained" onPress={saveKey} loading={saving}>保存</Button>
          </Card.Content>
        </Card>
      </ScrollView>
    </View>
  )
}
