import { useLocalSearchParams } from 'expo-router'
import { Text } from 'react-native-paper'

export default function ProjectDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>()
  return <Text style={{ padding: 32 }}>项目详情 {id}（阶段 5 迁移）</Text>
}
