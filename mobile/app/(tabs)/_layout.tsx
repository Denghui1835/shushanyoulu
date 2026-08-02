import { Tabs } from 'expo-router'
import { Text } from 'react-native-paper'

export default function TabsLayout() {
  return (
    <Tabs screenOptions={{ tabBarActiveTintColor: '#7c5cfc' }}>
      <Tabs.Screen name="index" options={{ title: '伴学', tabBarIcon: () => <Text>⚡</Text> }} />
      <Tabs.Screen name="plan" options={{ title: '计划', tabBarIcon: () => <Text>📅</Text> }} />
      <Tabs.Screen name="bookshelf" options={{ title: '书架', tabBarIcon: () => <Text>📚</Text> }} />
      <Tabs.Screen name="podcasts" options={{ title: '播客', tabBarIcon: () => <Text>🎙️</Text> }} />
      <Tabs.Screen name="community" options={{ title: '社区', tabBarIcon: () => <Text>🌐</Text> }} />
    </Tabs>
  )
}
