/**
 * 计划表 — 周视图(时间轴浏览) + 日视图(编辑)
 */
import { useEffect, useState } from 'react'
import { Button, Select, TimePicker, message, Spin, Segmented, Typography } from 'antd'
import { LeftOutlined, RightOutlined, CalendarOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import isoWeek from 'dayjs/plugin/isoWeek'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
dayjs.extend(isoWeek)
const { Text } = Typography

interface Slot {
  id: string; schedule_id: string; day_of_week: number
  start_time: string; end_time: string; title: string
  color: string; notify_on_start: boolean; completed: boolean
}
interface Sched { id: string; project_id: string; title: string; week_start_date: string; slots: Slot[] }

const DAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const DAY_COLOR: [string, string][] = [
  ['rgba(255,107,157,.18)', 'rgba(255,107,157,.30)'], // 粉红荧光
  ['rgba(255,166,77,.18)', 'rgba(255,166,77,.30)'],  // 橙色荧光
  ['rgba(255,235,59,.20)', 'rgba(255,235,59,.32)'],  // 明黄荧光
  ['rgba(76,217,100,.18)', 'rgba(76,217,100,.30)'],  // 亮绿荧光
  ['rgba(90,200,250,.18)', 'rgba(90,200,250,.30)'],   // 天蓝荧光
  ['rgba(0,122,255,.18)', 'rgba(0,122,255,.30)'],    // 蓝色荧光
  ['rgba(175,82,250,.18)', 'rgba(175,82,250,.30)'],   // 紫色荧光
]
const H = 52
const tm = (t: string) => { const p = t.split(':'); return +p[0] * 60 + +p[1] }
const tp = (t: string, base: number) => Math.max(0, (tm(t) - base) / 60 * H)
const th = (a: string, b: string) => Math.max(H / 3, (tm(b) - tm(a)) / 60 * H)

export default function SchedulePage() {
  const [sched, setSched] = useState<Sched | null>(null)
  const [loading, setLoading] = useState(true)
  const [weekStart, setWeekStart] = useState(() => dayjs().isoWeekday(1).format('YYYY-MM-DD'))
  const [view, setView] = useState<'week' | 'day'>('week')
  const [editDay, setEditDay] = useState(0)
  const [timeStart, setTimeStart] = useState(7)
  const [timeEnd, setTimeEnd] = useState(23)

  useEffect(() => { load() }, [weekStart])

  const load = async () => {
    setLoading(true)
    try {
      const d = await api.callRaw('/schedules', { method: 'GET', body: undefined })
      setSched((d?.schedules || []).find((s: any) => s.week_start_date === weekStart) || null)
    } catch { setSched(null) } finally { setLoading(false) }
  }

  const put = (id: string, data: any) => api.callRaw(`/schedules/${sched!.id}/slots/${id}`, { method: 'PUT', body: data })
  const post = (data: any) => api.callRaw(`/schedules/${sched!.id}/slots`, { method: 'POST', body: data })
  const del = (id: string) => api.callRaw(`/schedules/${sched!.id}/slots/${id}`, { method: 'DELETE' })
  const updateLocal = (id: string, patch: Partial<Slot>) =>
    setSched(s => s ? { ...s, slots: s.slots.map(sl => sl.id === id ? { ...sl, ...patch } : sl) } : s)

  const ensureSched = async () => {
    if (sched) return
    const projs = await api.listProjects()
    const pid = projs?.[0]?.id || 'default'
    const d = await api.callRaw('/schedules', { method: 'POST', body: { project_id: pid, title: `第${dayjs(weekStart).isoWeek()}周计划`, week_start_date: weekStart } })
    if (d?.slots) for (const s of d.slots) await api.callRaw(`/schedules/${d.id}/slots/${s.id}`, { method: 'DELETE' })
    setSched({ ...d, slots: [] })
  }

  const prev = () => setWeekStart(dayjs(weekStart).subtract(7, 'day').format('YYYY-MM-DD'))
  const next = () => setWeekStart(dayjs(weekStart).add(7, 'day').format('YYYY-MM-DD'))

  return (
    <div className="yq-page">
      <PageHeader
        icon={<CalendarOutlined />}
        title="计划表"
        subtitle="按天 / 时段排学习任务，可标记完成、定时提醒"
      />
      <div className="yq-section" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, padding: '10px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Button size="small" icon={<LeftOutlined />} onClick={prev} />
          <Text strong style={{ minWidth: 160, textAlign: 'center', fontSize: 13 }}>
            {dayjs(weekStart).format('MM/DD')} - {dayjs(weekStart).add(6, 'day').format('MM/DD')}
            <Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>第{dayjs(weekStart).isoWeek()}周</Text>
          </Text>
          <Button size="small" icon={<RightOutlined />} onClick={next} />
          <Button size="small" onClick={() => setWeekStart(dayjs().isoWeekday(1).format('YYYY-MM-DD'))}>本周</Button>
          {view === 'week' && (<>
            <span style={{ color: '#ddd' }}>|</span>
            <Select size="small" style={{ width: 70 }} value={timeStart} onChange={v => setTimeStart(Math.min(v, timeEnd - 1))}
              options={Array.from({ length: 12 }, (_, i) => ({ value: i, label: `${i}:00` }))} />
            <span style={{ fontSize: 12, color: '#999' }}>—</span>
            <Select size="small" style={{ width: 70 }} value={timeEnd} onChange={v => setTimeEnd(Math.max(v, timeStart + 1))}
              options={Array.from({ length: 13 }, (_, i) => ({ value: i + 12, label: `${i + 12}:00` }))} />
          </>)}
        </div>
        <Segmented value={view} onChange={v => { setView(v as 'week' | 'day'); if (v === 'day') setEditDay(0) }}
          options={[{ value: 'week', label: '周视图' }, { value: 'day', label: '日视图' }]} />
      </div>

      {loading ? <Spin style={{ display: 'block', margin: 60 }} /> : view === 'week' ? (
        <WeekView sched={sched} weekStart={weekStart} onEnsure={ensureSched} timeStart={timeStart} timeEnd={timeEnd} />
      ) : (
        <DayView sched={sched} day={editDay} weekStart={weekStart} setDay={setEditDay} onBack={() => setView('week')}
          put={put} post={post} del={del} updateLocal={updateLocal} setSched={setSched} onEnsure={ensureSched} />
      )}
    </div>
  )
}

/* ============ WeekView ============ */
function WeekView({ sched, weekStart, onEnsure, timeStart, timeEnd }: any) {
  if (!sched) {
    return (
      <div className="yq-section yq-empty-state">
        <div className="yq-empty-icon">🗓️</div>
        <p style={{ color: '#8c8fa1' }}>还没有计划表</p>
        <Button type="primary" onClick={onEnsure}>创建计划表</Button>
      </div>
    )
  }

  const T0 = timeStart * 60
  const T1 = timeEnd * 60
  const gh = (T1 - T0) / 60 * H
  const hours: string[] = []
  for (let h = timeStart; h <= timeEnd; h++) hours.push(`${String(h).padStart(2, '0')}:00`)

  const byDay: Slot[][] = Array.from({ length: 7 }, () => [])
  for (const s of (sched.slots || []) as Slot[]) byDay[s.day_of_week].push(s)

  return (
    <div style={{ background: '#f8f9fb', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
        <div style={{ display: 'flex', minWidth: 750 }}>
          {/* time axis */}
          <div style={{ width: 48, flexShrink: 0 }}>
            <div style={{ height: 42, borderBottom: '1px solid #e8eaf0', background: '#fafbfc' }} />
            {hours.map(label => (
              <div key={label} style={{ height: H, borderBottom: '1px solid #eef0f5', fontSize: 10, color: '#a0a4b0', textAlign: 'right', padding: '1px 6px', boxSizing: 'border-box' }}>{label}</div>
            ))}
          </div>
          {/* 7 day columns */}
          {byDay.map((slots, d) => {
            const date = dayjs(weekStart).add(d, 'day')
            const today = date.isSame(dayjs(), 'day')
            return (
              <div key={d} style={{ flex: 1, minWidth: 90, borderLeft: '1px solid #eef0f5' }}>
                <div style={{ height: 42, borderBottom: '1px solid #e8eaf0', background: today ? '#eef0f8' : '#fafbfc', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: today ? '#5b5ea6' : '#333' }}>{DAYS[d]}</div>
                  <div style={{ fontSize: 10, color: '#999' }}>{date.format('MM/DD')}</div>
                </div>
                <div style={{ position: 'relative', height: gh, background: '#fff' }}>
                  {hours.map((_, i) => (
                    <div key={i} style={{ position: 'absolute', top: i * H, left: 0, right: 0, borderBottom: '1px solid #f2f3f7', height: 1 }} />
                  ))}
                  {slots.map((s: Slot, si: number) => {
                    const bg = s.completed ? 'rgba(0,0,0,.05)' : DAY_COLOR[d][si % 2]
                    return (
                      <div key={s.id} style={{
                        position: 'absolute', left: 2, right: 2,
                        top: tp(s.start_time, T0), height: th(s.start_time, s.end_time),
                        background: bg, borderRadius: 3, border: '1px solid rgba(0,0,0,.06)',
                        padding: '3px 5px', overflow: 'hidden', boxSizing: 'border-box',
                        opacity: s.completed ? 0.5 : 1,
                      }}>
                        <div style={{ fontSize: 9, color: '#9ca0b0', marginBottom: 1 }}>{s.start_time}-{s.end_time}</div>
                        {s.title && <div style={{ fontSize: 10, fontWeight: 500, lineHeight: 1.3, textDecoration: s.completed ? 'line-through' : 'none', color: s.completed ? '#8c8fa1' : '#4c4f69' }}>{s.title}</div>}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </div>
      <div style={{ padding: '8px 16px', fontSize: 11, color: '#999', borderTop: '1px solid #eef0f5', background: '#fafbfc' }}>
        {sched.slots.filter((s: Slot) => s.completed).length}/{sched.slots.length} 已完成
      </div>
    </div>
  )
}

/* ============ DayView ============ */
function DayView({ sched, day, weekStart, setDay, onBack, put, post, del, updateLocal, setSched, onEnsure }: any) {
  const date = dayjs(weekStart).add(day, 'day')

  if (!sched) {
    return (
      <div style={{ background: '#fff', borderRadius: 10, textAlign: 'center', padding: 60 }}>
        <p style={{ color: '#999' }}>还没有计划表</p>
        <Button type="primary" onClick={async () => { await onEnsure(); window.location.reload() }}>创建计划表</Button>
      </div>
    )
  }

  const slots: Slot[] = (sched.slots || []).filter((s: Slot) => s.day_of_week === day).sort((a: Slot, b: Slot) => a.start_time.localeCompare(b.start_time))

  const addRow = async () => {
    const last = slots.reduce((m: string, s: Slot) => s.end_time > m ? s.end_time : m, '08:00')
    const h = Math.min(22, parseInt(last.split(':')[0]) + 1)
    const start = `${String(h).padStart(2, '0')}:00`
    const end = `${String(h + 1).padStart(2, '0')}:00`
    const r = await post({ day_of_week: day, start_time: start, end_time: end, title: '', color: '#f6ffed' })
    setSched((s: Sched) => s ? { ...s, slots: [...s.slots, r] } : s)
  }

  const save = async (slot: Slot, title: string) => {
    if (title.trim()) { await put(slot.id, { title: title.trim() }); updateLocal(slot.id, { title: title.trim() }) }
    else { await del(slot.id); setSched((s: Sched) => s ? { ...s, slots: s.slots.filter((sl: Slot) => sl.id !== slot.id) } : s) }
  }

  const toggleDone = async (slot: Slot) => { updateLocal(slot.id, { completed: !slot.completed }); await put(slot.id, { completed: !slot.completed }) }
  const delRow = async (slot: Slot) => { await del(slot.id); setSched((s: Sched) => s ? { ...s, slots: s.slots.filter((sl: Slot) => sl.id !== slot.id) } : s) }

  return (
    <div style={{ background: '#fff', borderRadius: 10, padding: '20px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Button size="small" onClick={() => setDay((d: number) => (d + 6) % 7)} icon={<LeftOutlined />} />
          <Text strong style={{ fontSize: 16 }}>{date.format('YYYY年M月D日')} {DAYS[day]}</Text>
          <Button size="small" onClick={() => setDay((d: number) => (d + 1) % 7)} icon={<RightOutlined />} />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button size="small" onClick={addRow}>+ 添加时间段</Button>
          <Button size="small" onClick={onBack}>← 返回周视图</Button>
        </div>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead><tr style={{ borderBottom: '2px solid #e8e8e8' }}>
          <th style={{ width: 200, padding: '8px 12px', fontSize: 12, color: '#888', textAlign: 'left' }}>时间</th>
          <th style={{ padding: '8px 12px', fontSize: 12, color: '#888', textAlign: 'left' }}>计划</th>
        </tr></thead>
        <tbody>
          {slots.map((s: Slot) => (
            <TimeRow key={s.id} slot={s} onSave={save} onToggle={toggleDone} onDel={delRow} put={put} updateLocal={updateLocal} />
          ))}
        </tbody>
      </table>
      {slots.length === 0 && <div style={{ textAlign: 'center', padding: 40, color: '#ccc' }}>点「添加时间段」开始安排今天</div>}
      <div style={{ textAlign: 'center', marginTop: 16 }}>
        <Button type="dashed" onClick={addRow}>+ 添加时间段</Button>
      </div>
    </div>
  )
}

/* ============ TimeRow ============ */
function TimeRow({ slot, onSave, onToggle, onDel, put, updateLocal }: any) {
  const [text, setText] = useState(slot.title)
  const [focus, setFocus] = useState(false)
  useEffect(() => { setText(slot.title) }, [slot.title])

  const saveText = () => { if (text !== slot.title) onSave(slot, text) }
  const onTime = async (type: 'start' | 'end', val: string) => {
    const s = type === 'start' ? val : slot.start_time
    const e = type === 'end' ? val : slot.end_time
    if (!s || !e || (type === 'start' && s === slot.start_time) || (type === 'end' && e === slot.end_time)) return
    await put(slot.id, { start_time: s, end_time: e }); updateLocal(slot.id, { start_time: s, end_time: e })
  }

  return (
    <tr style={{ borderBottom: '1px solid #f5f5f5' }}>
      <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <TimePicker value={dayjs(slot.start_time, 'HH:mm')} format="HH:mm" size="small" minuteStep={5} style={{ width: 90 }}
            onChange={(v: any) => v && onTime('start', v.format('HH:mm'))} />
          <span style={{ fontSize: 12, color: '#ccc' }}>—</span>
          <TimePicker value={dayjs(slot.end_time, 'HH:mm')} format="HH:mm" size="small" minuteStep={5} style={{ width: 90 }}
            onChange={(v: any) => v && onTime('end', v.format('HH:mm'))} />
        </div>
      </td>
      <td style={{ padding: 8, verticalAlign: 'top' }}>
        <textarea value={text} onChange={e => setText(e.target.value)}
          onFocus={() => setFocus(true)} onBlur={() => { setFocus(false); saveText() }}
          placeholder="输入计划…" rows={2}
          style={{ width: '100%', border: focus ? '1px solid #7c5cfc' : '1px solid transparent', borderRadius: 6, padding: '8px 10px', fontSize: 14, outline: 'none', resize: 'vertical', fontFamily: 'inherit', lineHeight: 1.6, background: slot.completed ? '#f9f9f9' : '#fafafa', color: slot.completed ? '#bbb' : '#333', textDecoration: slot.completed ? 'line-through' : 'none', boxSizing: 'border-box' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer', fontSize: 12, color: '#999' }}>
            <input type="checkbox" checked={slot.completed} onChange={() => onToggle(slot)} style={{ margin: 0 }} /> 完成
          </label>
          <span style={{ flex: 1 }} />
          <Button type="text" size="small" danger onClick={() => onDel(slot)}>删除</Button>
        </div>
      </td>
    </tr>
  )
}
