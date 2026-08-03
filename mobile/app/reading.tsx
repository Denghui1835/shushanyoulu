import { useEffect, useState, useCallback } from 'react'
import { ScrollView, View } from 'react-native'
import { Appbar, Text, Chip, IconButton, ActivityIndicator } from 'react-native-paper'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { api } from '../src/api'
import { ReadingUnit } from '../../shared/types'

export default function ReadingScreen() {
  const params = useLocalSearchParams<{ doc?: string }>()
  const router = useRouter()
  const [units, setUnits] = useState<ReadingUnit[]>([])
  const [cur, setCur] = useState(0)
  const [title, setTitle] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!params.doc) return
    setLoading(true)
    try {
      const d = await api.getReadingContent(params.doc)
      setUnits(d.units)
      setTitle(d.title)
      setCur(0)
    } catch (e: any) { console.warn(e?.message) }
    finally { setLoading(false) }
  }, [params.doc])

  useEffect(() => { load() }, [load])

  const unit = units[cur]

  return (
    <View style={{ flex: 1 }}>
      <Appbar.Header>
        <Appbar.BackAction onPress={() => router.back()} />
        <Appbar.Content title={title || '阅读'} />
        <IconButton icon="chevron-left" disabled={cur <= 0} onPress={() => setCur(c => c - 1)} />
        <Chip compact>{units.length ? `${cur + 1}/${units.length}` : '-'}</Chip>
        <IconButton icon="chevron-right" disabled={cur >= units.length - 1} onPress={() => setCur(c => c + 1)} />
      </Appbar.Header>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 60 }} />
      ) : !unit ? (
        <Text style={{ textAlign: 'center', marginTop: 40, color: '#999' }}>暂无内容</Text>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16 }}>
          <Text variant="titleMedium" style={{ marginBottom: 8 }}>{unit.title}</Text>
          <Text style={{ lineHeight: 26, fontSize: 15 }}>{unit.text}</Text>
        </ScrollView>
      )}
    </View>
  )
}
