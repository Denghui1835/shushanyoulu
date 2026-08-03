import { useEffect, useState, useCallback } from 'react'
import { View, ScrollView, RefreshControl, Alert } from 'react-native'
import { Appbar, Card, Text, Button, Chip, TextInput, ActivityIndicator, IconButton } from 'react-native-paper'
import { api } from '../../src/api'
import { getToken, setToken, clearToken } from '../../src/tokenStore'
import { PlazaItem, MeInfo } from '../../../shared/types'

export default function CommunityScreen() {
  const [me, setMe] = useState<MeInfo | null>(null)
  const [plaza, setPlaza] = useState<PlazaItem[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      setPlaza((await api.getPlaza()).items || [])
      if (await getToken()) {
        setMe(await api.me())
      } else setMe(null)
    } catch (e: any) { console.warn(e?.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  const learn = async (id: string) => {
    setBusy(true)
    try { const r = await api.learnProject(id); Alert.alert('已学习', `「${r.title}」已加入你的书架`) }
    catch (e: any) { Alert.alert('学习失败', e?.message) }
    finally { setBusy(false) }
  }

  const togglePublish = async (p: any) => {
    setBusy(true)
    try {
      if (p.is_public) await api.unpublishProject(p.id)
      else await api.publishProject(p.id)
      setMe(await api.me())
    } catch (e: any) { Alert.alert('操作失败', e?.message) }
    finally { setBusy(false) }
  }

  const logout = async () => {
    try { await api.logout() } catch { /* ignore */ }
    await clearToken()
    setMe(null)
  }

  return (
    <View style={{ flex: 1 }}>
      <Appbar.Header>
        <Appbar.Content title="作品社区" />
        {me && <Appbar.Action icon="logout" onPress={logout} />}
      </Appbar.Header>

      {loading ? <ActivityIndicator style={{ marginTop: 60 }} /> : !me ? (
        <AuthForm onSuccess={loadAll} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 12, gap: 8 }}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={loadAll} />}>
          <Chip icon="account">{me.user.username}</Chip>

          <Card mode="outlined">
            <Card.Title title="📦 我的项目" subtitle="发布后其他用户可在广场学习" />
            <Card.Content>
              {me.projects.length === 0 ? <Text style={{ color: '#999' }}>暂无项目</Text> : me.projects.map(p => (
                <View key={p.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 }}>
                  <Text style={{ flex: 1 }}>{p.icon || '📦'} {p.title}</Text>
                  {p.is_public ? <Chip compact icon="check">已公开</Chip> : <Chip compact>私有</Chip>}
                  <IconButton
                    icon={p.is_public ? 'eye-off' : 'earth'} size={18}
                    loading={busy} onPress={() => togglePublish(p)}
                  />
                </View>
              ))}
            </Card.Content>
          </Card>

          <Card mode="outlined">
            <Card.Title title="🌐 广场 · 大家都在学" subtitle="一键学习会复制一份到你的书架" />
            <Card.Content>
              {plaza.length === 0 ? <Text style={{ color: '#999' }}>广场还没有公开项目</Text> : plaza.map(item => (
                <Card key={item.id} mode="contained" style={{ marginBottom: 8, backgroundColor: '#faf8ff' }}>
                  <Card.Content>
                    <Text variant="titleSmall">{item.icon || '📦'} {item.title}</Text>
                    <Text variant="bodySmall" style={{ color: '#666' }}>{item.description || '—'}</Text>
                    <View style={{ flexDirection: 'row', gap: 6, marginTop: 6, alignItems: 'center' }}>
                      <Chip compact>{item.author}</Chip>
                      <Chip compact>{item.chapter_count} 章</Chip>
                      <Button mode="contained" compact loading={busy} onPress={() => learn(item.id)} style={{ marginLeft: 'auto' }}>
                        一键学习
                      </Button>
                    </View>
                  </Card.Content>
                </Card>
              ))}
            </Card.Content>
          </Card>
        </ScrollView>
      )}
    </View>
  )
}

// ---------------------------------------------------------------- 登录 / 注册

function AuthForm({ onSuccess }: { onSuccess: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (username.trim().length < 2 || password.length < 6) {
      Alert.alert('提示', '用户名至少 2 字符，密码至少 6 位'); return
    }
    setBusy(true)
    try {
      const r = mode === 'login' ? await api.login(username.trim(), password) : await api.register(username.trim(), password)
      await setToken(r.token)
      Alert.alert(mode === 'login' ? '登录成功' : '注册成功', '第一个注册的账号会成为社区主人，继承本地数据')
      onSuccess()
    } catch (e: any) { Alert.alert('操作失败', e?.message) }
    finally { setBusy(false) }
  }

  return (
    <View style={{ padding: 24 }}>
      <Text style={{ textAlign: 'center', fontSize: 32, marginBottom: 8 }}>🌐</Text>
      <Text style={{ textAlign: 'center', fontSize: 18, fontWeight: 'bold', marginBottom: 16 }}>作品社区</Text>
      <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 12, marginBottom: 12 }}>
        <Chip selected={mode === 'login'} onPress={() => setMode('login')}>登录</Chip>
        <Chip selected={mode === 'register'} onPress={() => setMode('register')}>注册</Chip>
      </View>
      {mode === 'register' && (
        <Text style={{ color: '#8c6ff0', fontSize: 12, marginBottom: 8 }}>
          第一个注册的账号会成为社区主人，继承本地书架数据。
        </Text>
      )}
      <TextInput mode="outlined" label="用户名" value={username} onChangeText={setUsername} style={{ marginBottom: 8 }} />
      <TextInput mode="outlined" label="密码" secureTextEntry value={password} onChangeText={setPassword} style={{ marginBottom: 12 }} />
      <Button mode="contained" onPress={submit} loading={busy}>
        {mode === 'login' ? '登录' : '注册并进入'}
      </Button>
    </View>
  )
}
