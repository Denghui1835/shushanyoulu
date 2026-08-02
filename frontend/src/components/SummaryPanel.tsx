import { Alert, Skeleton, Button, Empty } from 'antd'
import { FileTextOutlined, ThunderboltOutlined, SoundOutlined } from '@ant-design/icons'

export interface SummaryItem {
  id: string
  scope: 'overall' | 'page' | 'story' | 'concept'
  unit_index: number | null
  content: string
  status: 'generating' | 'done' | 'error'
  error: string
}

interface Props {
  overall: SummaryItem | null
  page: SummaryItem | null
  story: SummaryItem | null
  concept: SummaryItem | null
  onGenerateOverall: () => void
  onGeneratePage: () => void
  onGenerateStory: () => void
  onGenerateConcept: () => void
  onListenStory: () => void
  generatingOverall: boolean
  generatingPage: boolean
  generatingStory: boolean
  generatingConcept: boolean
  unitTitle: string
}

function SummaryBody({ item, generating, emptyText }: {
  item: SummaryItem | null
  generating: boolean
  emptyText: string
}) {
  if (generating) return <Skeleton active paragraph={{ rows: 4 }} />
  if (!item) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
  if (item.status === 'error') {
    return <Alert type="error" showIcon message="总结生成失败" description={item.error || '请稍后重试'} />
  }
  if (item.status === 'done') {
    return <div style={{ fontSize: 13.5, lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>{item.content}</div>
  }
  return <Skeleton active paragraph={{ rows: 4 }} />
}

function SectionHeader({ icon, title, action }: { icon: React.ReactNode; title: string; action?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
      {icon}
      <b>{title}</b>
      <div style={{ marginLeft: 'auto' }}>{action}</div>
    </div>
  )
}

const genBtn = (label: string, onClick: () => void, disabled: boolean) => (
  <Button size="small" type="link" icon={<ThunderboltOutlined />} onClick={onClick} disabled={disabled}>
    {label}
  </Button>
)

export default function SummaryPanel({
  overall, page, story, concept,
  onGenerateOverall, onGeneratePage, onGenerateStory, onGenerateConcept,
  onListenStory,
  generatingOverall, generatingPage, generatingStory, generatingConcept,
  unitTitle,
}: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* 听书式章节总结（百宝箱 · 章节总结） */}
      <div>
        <SectionHeader
          icon={<SoundOutlined style={{ color: '#7c5cfc' }} />}
          title="章节总结 · 听书式"
          action={
            <span style={{ display: 'flex', gap: 2 }}>
              {genBtn(story ? '重生成' : '生成', onGenerateStory, generatingStory)}
              {story?.status === 'done' && (
                <Button size="small" type="link" icon={<SoundOutlined />} onClick={onListenStory}>朗读</Button>
              )}
            </span>
          }
        />
        <SummaryBody item={story} generating={generatingStory} emptyText="像听故事一样，一键生成" />
      </div>

      {/* 概念要点总结（百宝箱 · 概念总结） */}
      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
        <SectionHeader
          icon={<FileTextOutlined style={{ color: '#7c5cfc' }} />}
          title="概念总结"
          action={genBtn(concept ? '重生成' : '生成', onGenerateConcept, generatingConcept)}
        />
        <SummaryBody item={concept} generating={generatingConcept} emptyText="核心概念要点速览" />
      </div>

      {/* 原有：整体总结 + 页级总结 */}
      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
        <SectionHeader
          icon={<FileTextOutlined style={{ color: '#7c5cfc' }} />}
          title="整体总结"
          action={genBtn(overall ? '重生成' : '生成', onGenerateOverall, generatingOverall)}
        />
        <SummaryBody item={overall} generating={generatingOverall} emptyText="还没有整体总结" />
      </div>

      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
        <SectionHeader
          icon={<FileTextOutlined style={{ color: '#7c5cfc' }} />}
          title="本页总结"
          action={
            <>
              <span style={{ fontSize: 11, color: '#7c5cfc', background: '#f4f0ff', padding: '1px 6px', borderRadius: 4, marginRight: 6 }}>
                {unitTitle}
              </span>
              {genBtn(page ? '重生成' : '生成', onGeneratePage, generatingPage)}
            </>
          }
        />
        <SummaryBody item={page} generating={generatingPage} emptyText="还没有本页总结" />
      </div>
    </div>
  )
}
