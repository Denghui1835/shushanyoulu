import { Layout, Menu, Button, Avatar, Space } from 'antd'
import {
  MessageOutlined, CalendarOutlined, ReadOutlined, GlobalOutlined, UserOutlined, RiseOutlined, TableOutlined, TeamOutlined,
  SoundOutlined, SafetyOutlined,
} from '@ant-design/icons'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api, getAuthToken, setAuthToken } from './api'
import AuthModal from './components/AuthModal'
import LoginPage from './pages/LoginPage'
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
import ListenPage from './pages/ListenPage'
import CommunityPage from './pages/CommunityPage'
import CourseDetailPage from './pages/CourseDetailPage'
import ProfilePage from './pages/ProfilePage'
import TTSTestPage from './pages/TTSTestPage'
import StatsDashboard from './pages/StatsDashboard'
import SchedulePage from './pages/SchedulePage'
import SocialPage from './pages/SocialPage'
import AdminPage from './pages/AdminPage'

const { Sider, Content } = Layout

/** 把任意路由归到侧边栏菜单项，避免子页面高亮错乱 */
function resolveMenuKey(path: string): string {
  if (path === '/') return '/'
  if (path.startsWith('/plan')) return '/plan'
  if (path === '/schedule') return '/schedule'
  if (path === '/stats') return '/stats'
  if (path === '/social') return '/social'
  if (path === '/listen') return '/listen'
  if (path === '/community') return '/community'
  if (path.startsWith('/admin')) return '/admin'  // 不写就会 fall through 到 /bookshelf，左侧高亮错位
  if (path === '/profile' || path === '/tts' || path === '/login') return '/profile'
  // 书架及书内工具（课程/深度教学/刷题/模拟/闪卡/播客/阅读/知识树）
  return '/bookshelf'
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const [points, setPoints] = useState(0)
  const [collapsed, setCollapsed] = useState(false)
  const [authOpen, setAuthOpen] = useState(false)
  const [user, setUser] = useState<any>(null)

  const refreshStatus = async () => {
    try {
      const s = await api.getStatus()
      setPoints(s.points || 0)
    } catch { /* backend not ready */ }
  }

  useEffect(() => { refreshStatus() }, [location.pathname])

  // 每次路由变化同步一次登录态：token 失效/退出后顶栏自动变回「登录/注册」
  useEffect(() => {
    if (!getAuthToken()) { setUser(null); return }
    let alive = true
    api.me().then(r => { if (alive) setUser(r?.user ?? null) })
      .catch(() => { if (alive) { setAuthToken(''); setUser(null) } })
    return () => { alive = false }
  }, [location.pathname])

  const menuItems: any[] = [
    {
      type: 'group', label: '📚 学习',
      children: [
        { key: '/', icon: <MessageOutlined />, label: '伴学首页' },
        { key: '/listen', icon: <SoundOutlined />, label: '听读' },
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
        // 只有管理员看得到入口；后端每个 /api/admin/* 都另有 require_admin 兜底
        ...(user?.is_admin
          ? [{ key: '/admin', icon: <SafetyOutlined />, label: '用户管理' }]
          : []),
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
        {/* 顶栏账号区：未登录 → 打开登录/注册弹窗；已登录 → 显示头像，点进个人中心 */}
        <div style={{ position: 'fixed', top: 12, right: 18, zIndex: 100 }}>
          {user ? (
            <Button
              type="text"
              onClick={() => navigate('/profile')}
              style={{ background: '#fff', boxShadow: '0 1px 6px rgba(0,0,0,.08)', borderRadius: 20, padding: '2px 12px 2px 4px' }}
            >
              <Space size={6}>
                <Avatar size={26} style={{ background: '#7c5cfc' }}>{(user.name || '书')[0]}</Avatar>
                <span>{user.name}</span>
              </Space>
            </Button>
          ) : (
            <Button type="primary" ghost icon={<UserOutlined />} onClick={() => setAuthOpen(true)}>
              登录 / 注册
            </Button>
          )}
        </div>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<CompanionPage onActivity={refreshStatus} />} />
          <Route path="/lesson" element={<LessonPage />} />
          <Route path="/plan" element={<PlanPage />} />
          <Route path="/plan/wizard" element={<PlanWizardPage />} />
          <Route path="/schedule" element={<SchedulePage />} />
          <Route path="/bookshelf" element={<BookshelfPage />} />
          <Route path="/project/:id" element={<ProjectDetailPage />} />
          <Route path="/reading" element={<ReadingPage />} />
          <Route path="/listen" element={<ListenPage />} />
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
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/stats" element={<StatsDashboard />} />
          <Route path="/tts" element={<TTSTestPage />} />
        </Routes>
      </Content>
      <AuthModal
        open={authOpen}
        onClose={() => setAuthOpen(false)}
        onSuccess={u => { setUser(u); setAuthOpen(false) }}
      />
    </Layout>
  )
}
