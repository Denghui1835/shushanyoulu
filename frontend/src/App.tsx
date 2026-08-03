import { Layout, Menu } from 'antd'
import {
  MessageOutlined, CalendarOutlined, ReadOutlined, SoundOutlined, GlobalOutlined, UserOutlined, AudioOutlined,
} from '@ant-design/icons'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api } from './api'
import CompanionPage from './pages/CompanionPage'
import PlanPage from './pages/PlanPage'
import BookshelfPage from './pages/BookshelfPage'
import ProjectDetailPage from './pages/ProjectDetailPage'
import KnowledgePage from './pages/KnowledgePage'
import QuizPage from './pages/QuizPage'
import FlashcardPage from './pages/FlashcardPage'
import ReadingPage from './pages/ReadingPage'
import PodcastLibraryPage from './pages/PodcastLibraryPage'
import CommunityPage from './pages/CommunityPage'
import ProfilePage from './pages/ProfilePage'
import TTSTestPage from './pages/TTSTestPage'

const { Sider, Content } = Layout

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const [points, setPoints] = useState(0)

  const refreshStatus = async () => {
    try {
      const s = await api.getStatus()
      setPoints(s.points || 0)
    } catch { /* backend not ready */ }
  }

  useEffect(() => { refreshStatus() }, [location.pathname])

  const menuItems = [
    { key: '/', icon: <MessageOutlined />, label: '伴学首页' },
    { key: '/plan', icon: <CalendarOutlined />, label: '我的计划' },
    { key: '/bookshelf', icon: <ReadOutlined />, label: '我的书架' },
    { key: '/podcasts', icon: <SoundOutlined />, label: '我的播客' },
    { key: '/community', icon: <GlobalOutlined />, label: '作品社区' },
    { key: '/profile', icon: <UserOutlined />, label: '个人中心' },
    { key: '/tts', icon: <AudioOutlined />, label: '语音试听' },
  ]

  const current = menuItems.find(m => m.key === location.pathname)?.key ?? '/bookshelf'

  return (
    <Layout className="yq-layout">
      <Sider width={210} className="yq-sider" theme="light">
        <div className="yq-logo">
          <div className="logo-icon">⚡</div>
          <div>
            <div className="logo-text">书山有路</div>
            <div className="logo-sub">AI 主动伴学</div>
          </div>
        </div>
        <Menu
          className="yq-menu"
          mode="inline"
          selectedKeys={[current]}
          items={menuItems}
          onClick={e => navigate(e.key)}
        />
        <div style={{ color: 'rgba(255,255,255,0.85)', padding: '20px', fontSize: 13 }}>
          <div>⚡ 元气值：<b style={{ fontSize: 16 }}>{points}</b></div>
          <div style={{ opacity: 0.7, marginTop: 6, fontSize: 12 }}>
            每次学习都能攒元气哦
          </div>
        </div>
      </Sider>
      <Content className="yq-content">
        <Routes>
          <Route path="/" element={<CompanionPage onActivity={refreshStatus} />} />
          <Route path="/plan" element={<PlanPage />} />
          <Route path="/bookshelf" element={<BookshelfPage />} />
          <Route path="/project/:id" element={<ProjectDetailPage />} />
          <Route path="/reading" element={<ReadingPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/quiz" element={<QuizPage />} />
          <Route path="/flashcards" element={<FlashcardPage />} />
          <Route path="/podcasts" element={<PodcastLibraryPage />} />
          <Route path="/community" element={<CommunityPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/tts" element={<TTSTestPage />} />
        </Routes>
      </Content>
    </Layout>
  )
}
