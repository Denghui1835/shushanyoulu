import { useEffect, useState } from 'react'
import { Card, Button, Tag, Empty, Spin, message, Alert, Space } from 'antd'
import { GlobalOutlined, DownloadOutlined } from '@ant-design/icons'
import { api } from '../api'

interface CommunityItem {
  title: string
  description?: string
  author?: string
  icon?: string
  file_url: string
  updated_at?: string
}

/** 作品社区：浏览共享目录中的项目，一键下载并导入。 */
export default function CommunityPage() {
  const [data, setData] = useState<any>({ configured: false, items: [], message: '' })
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState<Record<string, boolean>>({})

  const load = async () => {
    setLoading(true)
    try { setData(await api.getCommunityCatalog()) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const doImport = async (item: CommunityItem) => {
    setImporting(s => ({ ...s, [item.file_url]: true }))
    try {
      const p = await api.communityImport(item.file_url)
      message.success(`「${p.title}」已导入到你的书架！`)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '导入失败')
    } finally {
      setImporting(s => ({ ...s, [item.file_url]: false }))
    }
  }

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 120 }} />

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <div className="page-card" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <GlobalOutlined style={{ fontSize: 26, color: '#7c5cfc' }} />
        <div>
          <h2 style={{ margin: 0 }}>作品社区</h2>
          <div style={{ color: '#999', fontSize: 13 }}>下载大家分享的学习项目，导入到自己的书架</div>
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <Button icon={<DownloadOutlined />} onClick={load}>刷新</Button>
        </div>
      </div>

      {!data.configured ? (
        <div className="page-card" style={{ padding: 40 }}>
          <Alert
            type="info" showIcon
            message="社区目录还没配置"
            description={
              <div style={{ lineHeight: 1.9 }}>
                社区采用「文件导出/导入」：把书架里导出的 .yqp 文件放到共享位置（网盘 / GitHub 仓库），
                再写一个 catalog.json，并在 <b>backend/.env</b> 填它的直链：
                <br />
                <code style={{ background: '#f4f0ff', padding: '1px 6px', borderRadius: 4 }}>
                  COMMUNITY_CATALOG_URL=https://.../catalog.json
                </code>
                <br />
                catalog.json 格式：<code style={{ background: '#f4f0ff', padding: '1px 6px', borderRadius: 4 }}>
                  {'{"items": [{"title": "…", "description": "…", "author": "…", "icon": "📚", "file_url": "https://…/x.yqp", "updated_at": "2026-08-02"}]}'}
                </code>
                <br />
                你自己的项目：书架里每个项目右下角「下载」图标即可导出 .yqp。
              </div>
            }
          />
        </div>
      ) : (
        <>
          {data.message && <Alert type="warning" showIcon message={data.message} style={{ marginBottom: 12 }} />}
          {data.items.length === 0 ? (
            <div className="page-card" style={{ textAlign: 'center', padding: 60 }}>
              <Empty description="社区暂时还没有作品，快去分享第一个吧" />
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 14 }}>
              {data.items.map((item: CommunityItem, i: number) => (
                <Card key={i} className="yq-book-card">
                  <div style={{ fontSize: 34 }}>{item.icon || '📦'}</div>
                  <b style={{ fontSize: 15 }}>{item.title}</b>
                  <div style={{ color: '#666', fontSize: 12, minHeight: 40, marginTop: 6 }}>
                    {item.description || '—'}
                  </div>
                  <Space style={{ marginTop: 8 }}>
                    {item.author && <Tag color="purple">{item.author}</Tag>}
                    {item.updated_at && <Tag>{item.updated_at.slice(0, 10)}</Tag>}
                  </Space>
                  <div style={{ marginTop: 10 }}>
                    <Button type="primary" size="small" icon={<DownloadOutlined />}
                      loading={!!importing[item.file_url]}
                      onClick={() => doImport(item)}>
                      下载并导入
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
