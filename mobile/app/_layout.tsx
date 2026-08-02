import { PaperProvider } from 'react-native-paper'
import { Stack } from 'expo-router'
import { SafeAreaProvider } from 'react-native-safe-area-context'

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <PaperProvider>
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="project/[id]" />
          <Stack.Screen name="reading" />
          <Stack.Screen name="quiz" />
          <Stack.Screen name="flashcards" />
        </Stack>
      </PaperProvider>
    </SafeAreaProvider>
  )
}
