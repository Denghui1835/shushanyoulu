import { useEffect, useState, useCallback } from 'react'
import { ScrollView, View, RefreshControl } from 'react-native'
import {
  Appbar, Card, Text, Button, Chip, TextInput, RadioButton, ActivityIndicator, IconButton,
} from 'react-native-paper'
import { useLocalSearchParams } from 'expo-router'
import { api } from '../src/api'
import { Question } from '../../shared/types'

export default function QuizScreen() {
  const params = useLocalSearchParams<{ doc?: string }>()
  const [docs, setDocs] = useState<any[]>([])
  const [docId, setDocId] = useState('')
  const [questions, setQuestions] = useState<Question[]>([])
  const [idx, setIdx] = useState(0)
  const [answer, setAnswer] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)

  const loadDocs = useCallback(async () => {
    const d = await api.listDocuments()
    setDocs(d)
    if (params.doc && d.some((x: any) => x.id === params.doc)) setDocId(params.doc)
    else if (d.length && !docId) setDocId(d[0].id)
  }, [params.doc])

  const load = useCallback(async () => {
    if (!docId) return
    setLoading(true)
    try {
      const res = await api.listQuestions(docId)
      setQuestions(res.questions)
      setIdx(0); setAnswer(''); setResult(null)
    } catch (e: any) { console.warn(e?.message) }
    finally { setLoading(false) }
  }, [docId])

  useEffect(() => { loadDocs() }, [])
  useEffect(() => { if (docId) load() }, [docId])

  const generate = async () => {
    setGenerating(true)
    try { await api.generateQuestions(docId, 8); load() }
    catch (e: any) { console.warn(e?.message) }
    finally { setGenerating(false) }
  }

  const submit = async () => {
    if (!answer.trim()) return
    setResult(await api.gradeQuestion(questions[idx].id, answer))
  }

  const q = questions[idx]

  return (
    <View style={{ flex: 1 }}>
      <Appbar.Header>
        <Appbar.Content title="练习题" />
        <Appbar.Action icon="refresh" onPress={load} />
      </Appbar.Header>

      {/* 资料选择 */}
      <View style={{ paddingHorizontal: 12, paddingTop: 4 }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
          {docs.map(d => (
            <Chip key={d.id} selected={docId === d.id} onPress={() => setDocId(d.id)} compact>
              {d.title}
            </Chip>
          ))}
        </ScrollView>
        <Button icon="creation" onPress={generate} loading={generating} compact style={{ marginTop: 6 }}>
          生成题目
        </Button>
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} />
      ) : !q ? (
        <Text style={{ textAlign: 'center', marginTop: 40, color: '#999' }}>还没有题目，点「生成题目」开始练习</Text>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 12 }} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}>
          <Card mode="outlined">
            <Card.Content>
              <View style={{ flexDirection: 'row', gap: 6, marginBottom: 8 }}>
                <Chip compact>{idx + 1}/{questions.length}</Chip>
                <Chip compact>{q.qtype === 'choice' ? '选择题' : q.qtype === 'fill' ? '填空题' : '简答题'}</Chip>
              </View>
              <Text variant="titleMedium" style={{ lineHeight: 24 }}>{q.question}</Text>

              {q.qtype === 'choice' ? (
                <RadioButton.Group value={answer} onValueChange={setAnswer}>
                  {q.options.map((opt, i) => (
                    <RadioButton.Item key={i} value={opt} label={`${String.fromCharCode(65 + i)}. ${opt}`}
                      disabled={!!result} />
                  ))}
                </RadioButton.Group>
              ) : (
                <TextInput
                  mode="outlined" multiline value={answer} onChangeText={setAnswer}
                  placeholder="写下你的答案" disabled={!!result} style={{ marginTop: 8, minHeight: 80 }}
                />
              )}

              {!result ? (
                <Button mode="contained" onPress={submit} disabled={!answer.trim()} style={{ marginTop: 12 }}>
                  提交
                </Button>
              ) : (
                <>
                  <Card mode="contained" style={{ marginTop: 12, backgroundColor: result.correct ? '#f6ffed' : '#fff2f0' }}>
                    <Card.Content>
                      <Text style={{ color: result.correct ? '#52c41a' : '#ff4d4f', fontWeight: 'bold' }}>
                        {result.correct ? '回答正确！' : '再想想，答案见下'}
                      </Text>
                      <Text variant="bodyMedium" style={{ marginTop: 4 }}><Text style={{ fontWeight: 'bold' }}>答案：</Text>{result.answer}</Text>
                      {result.explanation ? <Text variant="bodySmall" style={{ marginTop: 4, color: '#555' }}>解析：{result.explanation}</Text> : null}
                    </Card.Content>
                  </Card>
                  <Button mode="contained" onPress={() => { setIdx(i => i + 1); setAnswer(''); setResult(null) }} style={{ marginTop: 10 }}>
                    {idx + 1 >= questions.length ? '完成' : '下一题'}
                  </Button>
                </>
              )}
            </Card.Content>
          </Card>
        </ScrollView>
      )}
    </View>
  )
}
