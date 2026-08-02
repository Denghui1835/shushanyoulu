# -*- coding: utf-8 -*-
"""验证：多本整书混排 sync（按来源书校验/删除/新建）+ books 元数据 + book-file 接口."""
import asyncio
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
import httpx

BASE = 'http://127.0.0.1:8000'


def build(path, n_chapters, prefix):
    import fitz
    fontfile = "C:/Windows/Fonts/msyh.ttc"

    def put(pg, pt, t, s):
        pg.insert_text(pt, t, fontsize=s, fontname='cjk', fontfile=fontfile)

    doc = fitz.open()
    pg = doc.new_page(); put(pg, (72, 120), f'整书{prefix}', 20)
    pg = doc.new_page(); lines = ['目录']; pr = 1
    for i in range(1, n_chapters + 1):
        lines.append(f'第{i}章 {prefix}{i} .... {pr}'); pr += 3
    y = 80
    for l in lines: put(pg, (72, y), l, 13); y += 26
    pr = 1
    for i in range(1, n_chapters + 1):
        for p in range(3):
            pg = doc.new_page(); put(pg, (520, 40), str(pr), 10)
            if p == 0: put(pg, (72, 60), f'第{i}章 {prefix}{i}', 16)
            put(pg, (72, 100 + p * 40), f'{prefix} 内容。', 12); pr += 1
    doc.save(path); doc.close()
    return pr - 1 + 2


async def import_book(c, pid, path):
    with open(path, 'rb') as f:
        async with c.stream('POST', f'/api/projects/{pid}/import-book',
                            files={'file': ('整书.pdf', f, 'application/pdf')}) as resp:
            async for line in resp.aiter_lines():
                if line.startswith('data:'):
                    evt = json.loads(line[5:].strip())
                    if evt['type'] == 'error': return evt['message']
    return None


async def main():
    import os
    a = 'data/documents/_m_bookA.pdf'; b = 'data/documents/_m_bookB.pdf'
    build(a, 3, '甲'); build(b, 2, '乙')

    async with httpx.AsyncClient(base_url=BASE, timeout=200) as c:
        p = (await c.post('/api/projects', json={'title': '多书测试'})).json(); pid = p['id']
        err = await import_book(c, pid, a); print('[导入] A:', err or 'ok')
        err = await import_book(c, pid, b); print('[导入] B:', err or 'ok')

        d = (await c.get(f'/api/projects/{pid}')).json()
        print('\n[1] books 元数据:', [(x['title'], x['total_pages'], x['chapter_count']) for x in d['project']['books']])
        docs = d['documents']
        print('    章节数:', len(docs), '| 每章 book_ref:', set(x.get('book_ref_document_id') for x in docs))
        # 找两本书的参考章节
        refs = {x.get('book_ref_document_id') for x in docs}
        # 分书
        bookA_docs = [x for x in docs if x['title'].startswith('第1章 甲') or x['title'].startswith('甲')]
        # 简单分组：按 book_ref 归属
        groups = {}
        for x in docs:
            groups.setdefault(x['book_ref_document_id'], []).append(x)
        for rid, grp in groups.items():
            print(f"    书 {rid[:6]}: {[(x['chapter_title'][:12], x['page_start'], x['page_end']) for x in grp]}")

        # [2] 跨书 sync：改 A 的书 + 保留 B 的书 + 从 B 新增一章
        refA, refB = list(refs)[0], list(refs)[1]
        grpA = groups[refA]; grpB = groups[refB]
        new_list = []
        for i, x in enumerate(grpA):
            new_list.append({'document_id': x['id'], 'title': f'{x["chapter_title"]}-改', 'page_start': x['page_start'], 'page_end': x['page_end']})
        for i, x in enumerate(grpB):
            new_list.append({'document_id': x['id'], 'title': x['chapter_title'], 'page_start': x['page_start'], 'page_end': x['page_end']})
        # 从 B 新增一章（source_document_id = refB 的一个章节）
        new_list.append({'document_id': None, 'title': '乙新增章', 'source_document_id': refB, 'page_start': 5, 'page_end': 6})
        d2 = (await c.post(f'/api/projects/{pid}/chapters/sync', json={'chapters': new_list})).json()
        print('\n[2] 跨书 sync 后:')
        for x in d2['documents']:
            print(f"    [{x['title'][:16]:18}] 书ref={x.get('book_ref_document_id', '')[:6]} 第{x['page_start']+1}-{x['page_end']+1}页 sort={x['sort_order']}")
        # 校验 B 的章节都保留（乙新增章 + 原B章）
        b_titles = [x['chapter_title'] for x in d2['documents']]
        print('    B 章节保留:', any('乙' in t for t in b_titles), '| 乙新增章存在:', any('乙新增' in t for t in b_titles))

        # [3] 删除 A 的书章节（列表只保留 B），不误删 B
        d3_docs = d2['documents']
        b_docs = [x for x in d3_docs if x.get('book_ref_document_id') == refB]
        only_b = [{'document_id': x['id'], 'title': x['chapter_title'], 'page_start': x['page_start'], 'page_end': x['page_end']} for x in b_docs]
        d3 = (await c.post(f'/api/projects/{pid}/chapters/sync', json={'chapters': only_b})).json()
        print('\n[3] 只保留 B 后:')
        print('    剩余章节:', [(x['chapter_title'], x.get('book_ref_document_id', '')[:6]) for x in d3['documents']])
        a_left = [x for x in d3['documents'] if x.get('book_ref_document_id') == refA]
        print('    A 章节已删:', len(a_left) == 0, '| B 章节保留:', len(d3['documents']) == len(b_docs))

        # [4] 越界校验：A 书 10 页，给 B 书章节塞个 100 页 → 400
        bad = [{'document_id': x['id'], 'title': 'x', 'page_start': 0, 'page_end': 99} for x in b_docs]
        r = await c.post(f'/api/projects/{pid}/chapters/sync', json={'chapters': bad})
        print('\n[4] 越界 sync 应 400:', r.status_code, r.json().get('detail', '')[:44])

        # [5] book-file 接口
        r = await c.get(f"/api/documents/{b_docs[0]['id']}/book-file")
        print('\n[5] book-file 接口:', r.status_code, r.headers.get('content-type'))

        await c.delete(f'/api/projects/{pid}')
        print('\ncleaned')


asyncio.run(main())
