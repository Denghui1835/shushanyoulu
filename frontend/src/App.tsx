import { Layout, Menu } from 'antd'
import {
  MessageOutlined, CalendarOutlined, ReadOutlined, GlobalOutlined, UserOutlined, RiseOutlined, TableOutlined, TeamOutlined,
} from '@ant-design/icons'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api } from './api'
import CompanionPage from './pages/CompanionPage'
import LessonPage from './pages/LessonPage'
import PlanPage from './pages/PlanPage'
import PlanWizardPage from './pages/PlanWizardPage'
import BookshelfPage from './pages/BookshelfPage'
import ProjectDetailPage from './pages/ProjectDetailPage'
import KnowledgePage from './pages/KnowledgePage'
import QuizPage from './pages/QuizPage'
import MockExamPage from './pages/MockExamPage'
import CoursePage from './pages/CoursePage'
import FlashcardPage from './pages/FlashcardPage'
import ReadingPage from './pages/ReadingPage'
import PodcastLibraryPage from './pages/PodcastLibraryPage'
import CommunityPage from './pages/CommunityPage'
import CourseDetailPage from './pages/CourseDetailPage'
import ProfilePage from './pages/ProfilePage'
import TTSTestPage from './pages/TTSTestPage'
import StatsDashboard from './pages/StatsDashboard'
import SchedulePage from './pages/SchedulePage'
import SocialPage from './pages/SocialPage'

const { Sider, Content } = Layout

/** 把任意路由归到侧边栏菜单项，避免子页面高亮错乱 */
function resolveMenuKey(path: string): string {
  if (path === '/') return '/'
  if (path.startsWith('/plan')) return '/plan'
  if (path === '/schedule') return '/schedule'
  if (path === '/stats') return '/stats'
  if (path === '/social') return '/social'
  if (path === '/community') return '/community'
  if (path === '/profile' || path === '/tts') return '/profile'
  // 书架及书内工具（课程/深度教学/刷题/模拟/闪卡/播客/阅读/知识树）
  return '/bookshelf'
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const [points, setPoints] = useState(0)
  const [collapsed, setCollapsed] = useState(false)

  const refreshStatus = async () => {
    try {
      const s = await api.getStatus()
      setPoints(s.points || 0)
    } catch { /* backend not ready */ }
  }

  useEffect(() => { refreshStatus() }, [location.pathname])

  const menuItems: any[] = [
    {
      type: 'group', label: '📚 学习',
      children: [
        { key: '/', icon: <MessageOutlined />, label: '伴学首页' },
        { key: '/bookshelf', icon: <ReadOutlined />, label: '我的书架' },
        { key: '/plan', icon: <CalendarOutlined />, label: '我的计划' },
        { key: '/schedule', icon: <TableOutlined />, label: '计划表' },
        { key: '/stats', icon: <RiseOutlined />, label: '学习统计' },
      ],
    },
    {
      type: 'group', label: '🌐 社区',
      children: [
        { key: '/social', icon: <TeamOutlined />, label: '一起学' },
        { key: '/community', icon: <GlobalOutlined />, label: '作品社区' },
      ],
    },
    {
      type: 'group', label: '👤 我的',
      children: [
        { key: '/profile', icon: <UserOutlined />, label: '个人中心' },
      ],
    },
  ]

  const current = menuItems
    .flatMap(g => (g.type === 'group' && g.children ? g.children : [g]))
    .find(m => m.key === resolveMenuKey(location.pathname))?.key ?? '/bookshelf'

  return (
    <Layout className="yq-layout">
      <Sider
        width={210}
        className="yq-sider"
        theme="light"
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        breakpoint="lg"
      >
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
        <div className="yq-sidebar-footer">
          <div style={{ fontSize: 12, opacity: 0.85 }}>⚡ 元气值</div>
          <div className="num">{points}</div>
          <div className="hint">每次学习都能攒元气哦</div>
        </div>
      </Sider>
      <Content className="yq-content">
        <Routes>
          <Route path="/" element={<CompanionPage onActivity={refreshStatus} />} />
          <Route path="/lesson" element={<LessonPage />} />
          <Route path="/plan" element={<PlanPage />} />
          <Route path="/plan/wizard" element={<PlanWizardPage />} />
          <Route path="/schedule" element={<SchedulePage />} />
          <Route path="/bookshelf" element={<BookshelfPage />} />
          <Route path="/project/:id" element={<ProjectDetailPage />} />
          <Route path="/reading" element={<ReadingPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/quiz" element={<QuizPage />} />
          <Route path="/mock-exam" element={<MockExamPage />} />
          <Route path="/course" element={<CoursePage />} />
          <Route path="/flashcards" element={<FlashcardPage />} />
          <Route path="/podcasts" element={<PodcastLibraryPage />} />
          <Route path="/community" element={<CommunityPage />} />
          <Route path="/social" element={<SocialPage />} />
          <Route path="/course/:id" element={<CourseDetailPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/stats" element={<StatsDashboard />} />
          <Route path="/tts" element={<TTSTestPage />} />
        </Routes>
      </Content>
    </Layout>
  )
}
