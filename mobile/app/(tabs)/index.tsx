import { Text } from 'react-native-paper'
import { REVIEW_RATINGS } from '../../../shared/constants'

export default function CompanionScreen() {
  return <Text style={{ padding: 32, fontSize: 16 }}>伴学首页 · 评分档 {REVIEW_RATINGS.length} 档（阶段 5 迁移）</Text>
}
