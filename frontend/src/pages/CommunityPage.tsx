import { useEffect, useState } from 'react'
import { Card, Tag, Empty, Spin, message, Space, Input, Segmented, Button, Typography } from 'antd'
import {
  SearchOutlined, FireOutlined, ReadOutlined, StarOutlined, ForkOutlined,
  FileTextOutlined, UserOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api, getAuthToken } from '../api'

const { Title, Paragraph, Text } = Typography

interface PlazaItem {
  id: string; title: string; description?: string; icon?: string
  subject?: string; category?: string; category_sub?: string; category_label?: string
  author?: string; chapter_count: number
  learn_count?: number; star_count?: number; fork_count?: number; created_at?: string
}

// 番茄小说式封面渐变色板（按课程 id 取色）
const GRADIENTS = [
  'linear-gradient(135deg,#f093fb 0%,#f5576c 100%)',
  'linear-gradient(135deg,#4facfe 0%,#00f2fe 100%)',
  'linear-gradient(135deg,#43e97b 0%,#38f9d7 100%)',
  'linear-gradient(135deg,#fa709a 0%,#fee140 100%)',
  'linear-gradient(135deg,#30cfd0 0%,#330867 100%)',
  'linear-gradient(135deg,#a18cd1 0%,#fbc2eb 100%)',
  'linear-gradient(135deg,#fddb92 0%,#d1fdff 100%)',
  'linear-gradient(135deg,#ff9a9e 0%,#fecfef 100%)',
]

function hashIdx(s: string) {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 997
  return h % GRADIENTS.length
}

export default function CommunityPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')        // 一级：门类，''=全部
  const [categorySub, setCategorySub] = useState('')  // 二级：子学科，''=全部
  const [sort, setSort] = useState<'new' | 'hot'>('new')
  const [items, setItems] = useState<PlazaItem[]>([])
  const [catTree, setCatTree] = useState<Record<string, string[]>>({})
  const [loading, setLoading] = useState(true)
  const loggedIn = !!getAuthToken()

  const load = async () => {
    setLoading(true)
    try {
      const d = await api.getPlaza({
        search: search.trim(), category, category_sub: categorySub, sort,
      })
      setItems(d.items || [])
    } catch { /* backend */ } finally { setLoading(false) }
  }

  useEffect(() => {
    api.getCategories().then(setCatTree).catch(() => {})
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, categorySub, sort])

  return (
    <div className="yq-page">
      {/* 顶部：标题 + 搜索 + 排序 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>
            <GlobalIcon /> 内容广场
          </Title>
          <Text type="secondary">人人能学，人人能教——好课会被传抄和续写</Text>
        </div>
        <Space wrap>
          <Input.Search
            placeholder="搜索课程 / 知识点 / 创作者"
            allowClear
            style={{ width: 240 }}
            prefix={<SearchOutlined />}
            onSearch={() => load()}
          />
          <Segmented
            value={sort}
            onChange={v => setSort(v as 'new' | 'hot')}
            options={[
              { label: <span><FireOutlined /> 热门</span>, value: 'hot' },
              { label: <span>🆕 最新</span>, value: 'new' },
            ]}
          />
        </Space>
      </div>

      {/* 分类：学科门类 → 一级学科 */}
      <div style={{ margin: '16px 0', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {['', ...Object.keys(catTree)].map(c => (
            <Tag.CheckableTag
              key={c || '全部'}
              checked={category === c}
              onChange={() => { setCategory(c); setCategorySub('') }}
              style={{ fontSize: 14, padding: '4px 14px', borderRadius: 16 }}
            >
              {c || '🏛 全部'}
            </Tag.CheckableTag>
          ))}
        </div>
        {category && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, paddingLeft: 4 }}>
            {['', ...(catTree[category] || [])].map(s => (
              <Tag.CheckableTag
                key={s || '全部子'}
                checked={categorySub === s}
                onChange={() => setCategorySub(s)}
                style={{ fontSize: 13, padding: '2px 10px', borderRadius: 12, color: '#666' }}
              >
                {s || '全部'}
              </Tag.CheckableTag>
            ))}
          </div>
        )}
      </div>

      {/* 课程卡片流（番茄书架式） */}
      {loading ? <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div> : items.length === 0 ? (
        <Empty description="还没有公开课程，快去发布第一门吧！"
          style={{ padding: 40 }}>
          {loggedIn ? (
            <Button type="primary" onClick={() => navigate('/bookshelf')}>去我的书架发布</Button>
          ) : (
            <Text type="secondary">登录后就能收藏 / Fork / 提建议 / 发布课程</Text>
          )}
        </Empty>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
          {items.map((it: PlazaItem) => (
            <Card
              key={it.id}
              hoverable
              size="small"
              style={{ overflow: 'hidden', borderRadius: 12 }}
              styles={{ body: { padding: 0 } }}
              onClick={() => navigate(`/course/${it.id}`)}
            >
              {/* 封面 */}
              <div style={{
                background: GRADIENTS[hashIdx(it.id || it.title || '')],
                height: 96, display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 44,
              }}>
                {it.icon || '📘'}
              </div>
              <div style={{ padding: '10px 12px' }}>
                <b style={{ fontSize: 15 }}>{it.title}</b>
                <div style={{ color: '#888', fontSize: 12, margin: '4px 0 6px' }}>
                  <UserOutlined /> {it.author || '匿名'} · {it.category_label || it.subject || '未分类'}
                </div>
                <div style={{ color: '#666', fontSize: 12, minHeight: 32, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                  {it.description || '—'}
                </div>
                <div style={{ marginTop: 8, color: '#999', fontSize: 12, display: 'flex', gap: 10 }}>
                  <span><ReadOutlined /> {it.learn_count || 0}</span>
                  <span><StarOutlined /> {it.star_count || 0}</span>
                  <span><ForkOutlined /> {it.fork_count || 0}</span>
                  <span><FileTextOutlined /> {it.chapter_count}</span>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function GlobalIcon() {
  return <span style={{ color: '#fa541c' }}><ThunderboltOutlined /></span>
}
