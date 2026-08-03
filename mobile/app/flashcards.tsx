import { useEffect, useState, useCallback } from 'react'
import { View, ScrollView } from 'react-native'
import { Appbar, Card, Text, Chip, Button, ActivityIndicator } from 'react-native-paper'
import { useLocalSearchParams } from 'expo-router'
import { api } from '../src/api'
import { Flashcard } from '../../shared/types'
import { REVIEW_RATINGS } from '../../shared/constants'

export default function FlashcardScreen() {
  const params = useLocalSearchParams<{ doc?: string }>()
  const [docs, setDocs] = useState<any[]>([])
  const [docId, setDocId] = useState('')
  const [mode, setMode] = useState<'due' | 'all'>('due')
  const [cards, setCards] = useState<Flashcard[]>([])
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [loading, setLoading] = useState(true)

  const loadDocs = useCallback(async () => {
    const d = await api.listDocuments()
    setDocs(d)
    if (params.doc && d.some((x: any) => x.id === params.doc)) setDocId(params.doc)
    else if (d.length && !docId) setDocId(d[0].id)
  }, [params.doc])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      if (mode === 'due') setCards((await api.getDueCards()).flashcards)
      else if (docId) setCards((await api.listFlashcards(docId)).flashcards)
      setIdx(0); setFlipped(false)
    } catch (e: any) { console.warn(e?.message) }
    finally { setLoading(false) }
  }, [mode, docId])

  useEffect(() => { loadDocs() }, [])
  useEffect(() => { if (docId || mode === 'due') load() }, [mode, docId])

  const review = async (rating: number) => {
    await api.reviewCard(cards[idx].id, rating)
    if (idx + 1 < cards.length) { setIdx(idx + 1); setFlipped(false) }
    else { setCards([]) }
  }

  const card = cards[idx]

  return (
    <View style={{ flex: 1 }}>
      <Appbar.Header>
        <Appbar.Content title="闪卡复习" />
      </Appbar.Header>

      <View style={{ paddingHorizontal: 12, flexDirection: 'row', gap: 8, alignItems: 'center' }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, flex: 1 }}>
          {mode === 'all' && docs.map(d => (
            <Chip key={d.id} selected={docId === d.id} onPress={() => setDocId(d.id)} compact>{d.title}</Chip>
          ))}
        </ScrollView>
        <Chip selected={mode === 'due'} onPress={() => setMode('due')} compact>待复习</Chip>
        <Chip selected={mode === 'all'} onPress={() => setMode('all')} compact>全部</Chip>
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 60 }} />
      ) : !card ? (
        <Text style={{ textAlign: 'center', marginTop: 40, color: '#999' }}>
          {mode === 'due' ? '今天的复习完成啦 🎉' : '这份资料还没有闪卡'}
        </Text>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'center', marginBottom: 8 }}>
            <Chip compact>{idx + 1}/{cards.length}</Chip>
          </View>

          <Card mode="elevated" onPress={() => setFlipped(f => !f)} style={{ paddingVertical: 24 }}>
            <Card.Content style={{ alignItems: 'center', minHeight: 160, justifyContent: 'center' }}>
              {flipped ? (
                <Text variant="titleMedium" style={{ lineHeight: 26 }}>{card.back}</Text>
              ) : (
                <View style={{ alignItems: 'center' }}>
                  {card.visual ? <Text style={{ fontSize: 40 }}>{card.visual.split(' ')[0]}</Text> : null}
                  <Text variant="titleMedium" style={{ lineHeight: 26, marginTop: 6 }}>{card.front}</Text>
                  {card.visual ? <Text style={{ color: '#8c6ff0', fontSize: 12, marginTop: 6 }}>{card.visual}</Text> : null}
                </View>
              )}
            </Card.Content>
          </Card>
          <Text style={{ textAlign: 'center', color: '#999', fontSize: 12, marginTop: 8 }}>点击卡片翻转</Text>

          {flipped && (
            <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
              {REVIEW_RATINGS.map(r => (
                <Button key={r.value} mode="outlined" onPress={() => review(r.value)} style={{ borderColor: r.color }}>
                  {r.label}
                </Button>
              ))}
            </View>
          )}
        </ScrollView>
      )}
    </View>
  )
}
