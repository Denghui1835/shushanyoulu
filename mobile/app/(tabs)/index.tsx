import { useEffect, useState, useRef } from 'react'
import {
  ScrollView, View, TextInput as RNInput, KeyboardAvoidingView, Platform, StyleSheet,
} from 'react-native'
import { Text, Button, Card, Chip, IconButton, ActivityIndicator, Appbar } from 'react-native-paper'
import { api } from '../../src/api'
import { CompanionStatus, CheckIn } from '../../../shared/types'

interface Msg { id: string; role: 'user' | 'assistant'; content: string; streaming?: boolean }

export default function CompanionScreen() {
  const [status, setStatus] = useState<CompanionStatus | null>(null)
  const [checkin, setCheckin] = useState<CheckIn | null>(null)
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sessionId, setSessionId] = useState('')
  const scrollRef = useRef<ScrollView>(null)

  const loadStatus = async () => {
    try {
      const [s, c] = await Promise.all([api.getStatus(), api.getCheckin().catch(() => null)])
      setStatus(s)
      setCheckin(c)
    } catch (e: any) {
      console.warn('连接后端失败，请检查 src/config.ts 的 API 地址', e?.message)
    }
  }

  const init = async () => {
    try {
      const s = await api.getSession()
      setSessionId(s.id)
      const msgs = await api.getMessages(s.id)
      if (msgs.length === 0) {
        setMessages([{ id: 'greeting', role: 'assistant', content: '你好呀！我是元气搭子 ⚡ 我会陪你一起学习。先聊聊你的学习目标吧，我会主动提醒你该做什么。' }])
      } else {
        setMessages(msgs.map((m: any) => ({ id: m.id, role: m.role, content: m.content })))
      }
    } catch { /* backend not ready */ }
    await loadStatus()
  }

  useEffect(() => { init() }, [])

  const send = async () => {
    const text = input.trim()
    if (!text || sending || !sessionId) return
    setInput('')
    const assistantId = `a${Date.now()}`
    setMessages(m => [...m, { id: `u${Date.now()}`, role: 'user', content: text }, { id: assistantId, role: 'assistant', content: '', streaming: true }])
    setSending(true)
    try {
      for await (const delta of api.chat(sessionId, text)) {
        setMessages(m => m.map(x => (x.id === assistantId ? { ...x, content: x.content + delta } : x)))
      }
    } catch (e: any) {
      setMessages(m => m.map(x => (x.id === assistantId ? { ...x, content: `⚠️ ${e?.message}`, streaming: false } : x)))
    } finally {
      setSending(false)
      setMessages(m => m.map(x => (x.streaming ? { ...x, streaming: false } : x)))
      loadStatus()
    }
  }

  const doCheckin = async () => {
    const r = await api.doCheckin()
    setCheckin(r)
    loadStatus()
  }

  return (
    <View style={{ flex: 1 }}>
      <Appbar.Header>
        <Appbar.Content title="元气搭子" subtitle={status?.user?.goal || '先聊聊你的学习目标'} />
        <Chip icon="fire" style={{ marginRight: 8 }} onPress={doCheckin}>
          🔥{checkin?.streak ?? 0}天 {status?.points ?? 0}分
        </Chip>
      </Appbar.Header>

      {/* 状态卡 */}
      <View style={{ paddingHorizontal: 12, paddingTop: 4 }}>
        <Card mode="outlined" style={{ marginBottom: 8 }}>
          <Card.Content>
            <View style={{ flexDirection: 'row', justifyContent: 'space-around' }}>
              <View style={{ alignItems: 'center' }}>
                <Text variant="titleLarge">{status?.points ?? '—'}</Text>
                <Text variant="labelSmall">元气值</Text>
              </View>
              <View style={{ alignItems: 'center' }}>
                <Text variant="titleLarge">{status?.due_cards_count ?? '—'}</Text>
                <Text variant="labelSmall">待复习</Text>
              </View>
              <View style={{ alignItems: 'center' }}>
                <Text variant="titleLarge">{status?.today_tasks?.length ?? '—'}</Text>
                <Text variant="labelSmall">今日任务</Text>
              </View>
            </View>
          </Card.Content>
        </Card>
      </View>

      {/* 对话 */}
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView ref={scrollRef} style={{ flex: 1, paddingHorizontal: 12 }}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}>
          {messages.map(m => (
            <View key={m.id} style={[styles.bubble, m.role === 'user' ? styles.userBubble : styles.aiBubble]}>
              <Text style={{ color: m.role === 'user' ? '#fff' : '#333', lineHeight: 20 }}>
                {m.content}
                {m.streaming && <ActivityIndicator size={10} style={{ marginLeft: 4 }} />}
              </Text>
            </View>
          ))}
        </ScrollView>

        <View style={styles.inputRow}>
          <RNInput
            style={styles.input}
            placeholder="告诉元气搭子你想学什么…"
            value={input}
            onChangeText={setInput}
            onSubmitEditing={send}
            multiline
          />
          <Button mode="contained" onPress={send} disabled={!input.trim() || sending} loading={sending}>
            发送
          </Button>
        </View>
      </KeyboardAvoidingView>
    </View>
  )
}

const styles = StyleSheet.create({
  bubble: { maxWidth: '86%', borderRadius: 12, padding: 10, marginVertical: 4 },
  userBubble: { alignSelf: 'flex-end', backgroundColor: '#7c5cfc' },
  aiBubble: { alignSelf: 'flex-start', backgroundColor: '#f2f2f6' },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, padding: 8 },
  input: { flex: 1, borderWidth: 1, borderColor: '#ddd', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 8, maxHeight: 90 },
})
