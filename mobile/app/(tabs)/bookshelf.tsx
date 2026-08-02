import { useEffect, useState, useCallback } from 'react'
import { FlatList, View, RefreshControl } from 'react-native'
import { Appbar, Card, Text, Button, FAB, Dialog, Portal, TextInput, ActivityIndicator } from 'react-native-paper'
import { useRouter } from 'expo-router'
import { api } from '../../src/api'
import { Project } from '../../../shared/types'

export default function BookshelfScreen() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const router = useRouter()

  const load = useCallback(async () => {
    setLoading(true)
    try { setProjects(await api.listProjects()) }
    catch (e: any) { console.warn('书架加载失败', e?.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const create = async () => {
    if (!title.trim()) return
    setCreating(true)
    try {
      const p = await api.createProject({ title: title.trim() })
      setCreateOpen(false)
      setTitle('')
      router.push(`/project/${p.id}`)
    } catch (e: any) { console.warn(e?.message) }
    finally { setCreating(false) }
  }

  return (
    <View style={{ flex: 1 }}>
      <Appbar.Header>
        <Appbar.Content title="我的书架" subtitle="每个项目就是一本「书」" />
      </Appbar.Header>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={projects}
          keyExtractor={p => p.id}
          contentContainerStyle={{ padding: 12, gap: 10 }}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
          ListEmptyComponent={<Text style={{ textAlign: 'center', marginTop: 40, color: '#999' }}>书架还是空的，点右下角创建一个项目吧</Text>}
          renderItem={({ item }) => (
            <Card mode="outlined" onPress={() => router.push(`/project/${item.id}`)}>
              <Card.Content style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                <Text style={{ fontSize: 30 }}>{item.icon || '📚'}</Text>
                <View style={{ flex: 1 }}>
                  <Text variant="titleMedium">{item.title}</Text>
                  <Text variant="bodySmall" style={{ color: '#888' }}>{item.description || '—'}</Text>
                </View>
                <Text variant="labelMedium" style={{ color: '#7c5cfc' }}>{item.document_count} 章</Text>
              </Card.Content>
            </Card>
          )}
        />
      )}

      <Portal>
        <Dialog visible={createOpen} onDismiss={() => setCreateOpen(false)}>
          <Dialog.Title>创建学习项目</Dialog.Title>
          <Dialog.Content>
            <TextInput label="项目名称" value={title} onChangeText={setTitle} placeholder="例如：推理王国" />
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setCreateOpen(false)}>取消</Button>
            <Button mode="contained" onPress={create} loading={creating} disabled={!title.trim()}>创建并打开</Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      <FAB icon="plus" style={{ position: 'absolute', right: 16, bottom: 24, backgroundColor: '#7c5cfc' }}
        onPress={() => setCreateOpen(true)} />
    </View>
  )
}
