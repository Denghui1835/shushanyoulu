import { useEffect, useState, useCallback, useRef } from 'react'
import { FlatList, View, RefreshControl, Alert } from 'react-native'
import { Appbar, Card, Text, Chip, IconButton, ActivityIndicator, List } from 'react-native-paper'
import { Audio } from 'expo-av'
import { api } from '../../src/api'

interface PodcastItem {
  id: string
  document_id: string
  unit_index: number
  doc_title: string
  unit_title: string
  content: string
  status: string
  has_audio: boolean
  audio_seconds: number
}

export default function PodcastScreen() {
  const [podcasts, setPodcasts] = useState<PodcastItem[]>([])
  const [loading, setLoading] = useState(true)
  const soundRef = useRef<Audio.Sound | null>(null)
  const [playingId, setPlayingId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try { setPodcasts((await api.listPodcasts()).podcasts || []) }
    catch (e: any) { console.warn('播客加载失败', e?.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => () => { soundRef.current?.unloadAsync() }, [])

  const playPause = async (p: PodcastItem) => {
    if (playingId === p.id) {
      const s = soundRef.current
      if (s) {
        const st = await s.getStatusAsync()
        if (st.isLoaded && st.isPlaying) await s.pauseAsync()
        else if (st.isLoaded) await s.playAsync()
      }
      return
    }
    // 切到另一条：先停旧的
    await soundRef.current?.unloadAsync()
    setPlayingId(p.id)
    try {
      const { sound } = await Audio.Sound.createAsync(
        { uri: api.podcastAudioUrl(p.document_id, p.unit_index) },
        { shouldPlay: true },
      )
      soundRef.current = sound
      sound.setOnPlaybackStatusUpdate(st => {
        if (st.isLoaded && st.didJustFinish) { setPlayingId(null) }
      })
    } catch (e: any) {
      Alert.alert('播放失败', String(e?.message || e))
      setPlayingId(null)
    }
  }

  return (
    <View style={{ flex: 1 }}>
      <Appbar.Header>
        <Appbar.Content title="我的播客" subtitle="每章一期的双主播 AI 播客" />
      </Appbar.Header>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 60 }} />
      ) : (
        <FlatList
          data={podcasts}
          keyExtractor={p => p.id}
          contentContainerStyle={{ padding: 12, gap: 8 }}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
          ListEmptyComponent={<Text style={{ textAlign: 'center', marginTop: 40, color: '#999' }}>还没有播客，去「阅读」页生成吧</Text>}
          renderItem={({ item }) => (
            <Card mode="outlined">
              <Card.Content>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <IconButton
                    icon={playingId === item.id ? 'pause-circle' : 'play-circle'}
                    size={36}
                    iconColor="#7c5cfc"
                    disabled={!item.has_audio}
                    onPress={() => playPause(item)}
                  />
                  <View style={{ flex: 1 }}>
                    <Text variant="titleSmall">{item.unit_title}</Text>
                    <Text variant="bodySmall" style={{ color: '#888' }}>{item.doc_title}</Text>
                  </View>
                  <View style={{ alignItems: 'flex-end', gap: 4 }}>
                    {item.has_audio
                      ? <Chip compact icon="check">{Math.round(item.audio_seconds / 60)}分钟</Chip>
                      : <Chip compact>未合成音频</Chip>}
                  </View>
                </View>
              </Card.Content>
            </Card>
          )}
        />
      )}
    </View>
  )
}
