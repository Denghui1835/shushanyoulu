import { useEffect, useState, useCallback } from 'react'
import { FlatList, View, RefreshControl, Alert } from 'react-native'
import { Appbar, Card, Text, Chip, IconButton, ActivityIndicator, FAB } from 'react-native-paper'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { api } from '../../src/api'
import { ProjectDetail, Chapter } from '../../../shared/types'

export default function ProjectDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>()
  const router = useRouter()
  const [data, setData] = useState<ProjectDetail | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try { setData(await api.getProject(id)) }
    catch (e: any) { Alert.alert('加载失败', e?.message) }
    finally { setLoading(false) }
  }, [id])

  useEffect(() => { load() }, [load])

  if (loading || !data) return <ActivityIndicator style={{ marginTop: 60 }} />

  const chapters = data.documents.filter((c: Chapter) => !c.is_group)

  return (
    <View style={{ flex: 1 }}>
      <Appbar.Header>
        <Appbar.BackAction onPress={() => router.back()} />
        <Appbar.Content title={`${data.project.icon || '📚'} ${data.project.title}`} />
      </Appbar.Header>

      <FlatList
        data={chapters}
        keyExtractor={c => c.id}
        contentContainerStyle={{ padding: 12, gap: 8 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
        renderItem={({ item }) => (
          <Card mode="outlined" onPress={() => router.push(`/reading?doc=${item.id}`)}>
            <Card.Content style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Text style={{ fontSize: 22 }}>📖</Text>
              <View style={{ flex: 1 }}>
                <Text variant="titleSmall">{item.chapter_title || item.title}</Text>
                <View style={{ flexDirection: 'row', gap: 6, marginTop: 4 }}>
                  <Chip compact>{item.chunk_count} 片段</Chip>
                  {item.question_count > 0 && <Chip compact>题{item.question_count}</Chip>}
                  {item.flashcard_count > 0 && <Chip compact>卡{item.flashcard_count}</Chip>}
                </View>
              </View>
              <View style={{ flexDirection: 'row' }}>
                <IconButton icon="creation" size={18} onPress={() => router.push(`/quiz?doc=${item.id}`)} />
                <IconButton icon="cards" size={18} onPress={() => router.push(`/flashcards?doc=${item.id}`)} />
              </View>
            </Card.Content>
          </Card>
        )}
      />
    </View>
  )
}
