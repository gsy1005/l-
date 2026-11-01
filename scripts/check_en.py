# -*- coding: utf-8 -*-
import json, re, sys, io
from html.parser import HTMLParser
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

class TP(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texts = []
    def handle_data(self, d):
        d = d.strip()
        if d:
            self.texts.append(d)

data = json.load(open('app/public/site.json', encoding='utf-8'))
pat = re.compile(r"[A-Za-z]+(?:\s+[A-Za-z'\-]+){4,}")
seen = set()
out = []

def scan_html(html, where):
    p = TP()
    try:
        p.feed(html)
    except Exception:
        return
    for t in p.texts:
        for m in pat.finditer(t):
            s = m.group(0)
            if s not in seen:
                seen.add(s)
                out.append((where, s))

def walk_blocks(blocks, where):
    for b in blocks:
        t = b.get('type')
        if t == 'html':
            scan_html(b.get('html',''), where)
        elif t in ('cardgrid','expander','layer'):
            for it in b.get('items', []):
                scan_html(it.get('html','') or it.get('title','') or '', where)
        for ch in b.get('blocks', []) or []:
            walk_blocks([ch], where)

for sec in data.get('sections', []):
    walk_blocks(sec.get('blocks', []), sec.get('id','?'))

print(len(out))
for w, s in out:
    print('---', w)
    print(s)
