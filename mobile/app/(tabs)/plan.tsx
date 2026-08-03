import { useEffect, useState, useCallback } from 'react'
import { FlatList, View, RefreshControl } from 'react-native'
import { Appbar, Card, Text, Button, Chip, ActivityIndicator, Checkbox } from 'react-native-paper'
import dayjs from 'dayjs'
import { api } from '../../src/api'
import { StudyPlan } from '../../../shared/types'

const TYPE_LABEL: Record<string, string> = { learn: '学习', practice: '练习', review: '复习', chat: '问答' }

export default function PlanScreen() {
  const [data, setData] = useState<StudyPlan>({ plan: null, tasks: [] })
  const [loading, setLoading] = useState(true)
  const [adjusting, setAdjusting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try { setData(await api.getPlan()) }
    catch (e: any) { console.warn('计划加载失败', e?.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const complete = async (taskId: string) => {
    await api.completeTask(taskId)
    load()
  }

  const adjust = async () => {
    setAdjusting(true)
    try { await api.adjustPlan(); load() }
    catch (e: any) { console.warn(e?.message) }
    finally { setAdjusting(false) }
  }

  const today = dayjs().format('YYYY-MM-DD')
  const doneCount = data.tasks.filter(t => t.status === 'done').length

  if (loading) return <ActivityIndicator style={{ marginTop: 60 }} />

  if (!data.plan) {
    return (
      <View style={{ flex: 1 }}>
        <Appbar.Header><Appbar.Content title="我的计划" /></Appbar.Header>
        <View style={{ alignItems: 'center', padding: 40 }}>
          <Text style={{ fontSize: 40 }}>📋</Text>
          <Text style={{ marginTop: 12, color: '#666' }}>还没有学习计划</Text>
          <Text style={{ color: '#999', marginTop: 6, textAlign: 'center' }}>
            去「伴学」首页告诉小书虫你的目标，它就会为你制定计划
          </Text>
        </View>
      </View>
    )
  }

  return (
    <View style={{ flex: 1 }}>
      <Appbar.Header>
        <Appbar.Content title={data.plan.title} />
        <Button icon="sync" loading={adjusting} onPress={adjust} compact>调整</Button>
      </Appbar.Header>

      <Card mode="outlined" style={{ margin: 12 }}>
        <Card.Content>
          <Text variant="bodyMedium" style={{ color: '#666' }}>{data.plan.summary}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 }}>
            <Chip icon="check-circle">{doneCount}/{data.tasks.length} 完成</Chip>
            <Chip icon="calendar">共 {data.plan.total_days} 天</Chip>
          </View>
        </Card.Content>
      </Card>

      <FlatList
        data={data.tasks}
        keyExtractor={t => t.id}
        contentContainerStyle={{ paddingHorizontal: 12, paddingBottom: 20, gap: 8 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
        renderItem={({ item }) => {
          const done = item.status === 'done'
          const isToday = item.scheduled_date === today
          return (
            <Card mode={isToday && !done ? 'contained' : 'outlined'}>
              <Card.Content style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Checkbox
                  status={done ? 'checked' : 'unchecked'}
                  onPress={() => !done && complete(item.id)}
                  disabled={done}
                />
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Chip compact>{TYPE_LABEL[item.type] || item.type}</Chip>
                    {isToday && !done && <Chip compact icon="today" style={{ backgroundColor: '#f4f0ff' }}>今天</Chip>}
                  </View>
                  <Text variant="titleSmall" style={{ marginTop: 4, textDecorationLine: done ? 'line-through' : 'none', opacity: done ? 0.6 : 1 }}>
                    {item.title}
                  </Text>
                  {item.description ? <Text variant="bodySmall" style={{ color: '#888' }}>{item.description}</Text> : null}
                </View>
              </Card.Content>
            </Card>
          )
        }}
      />
    </View>
  )
}
