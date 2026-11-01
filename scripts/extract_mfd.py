import json, io, os

BASE = os.path.dirname(os.path.abspath(__file__))
html = open(r'C:\Users\Administrator\AppData\Local\Temp\srcsite\index.html', encoding='utf-8').read()
i = html.find('var MFD=')
j = i + len('var MFD=')
depth = 0
k = j
in_str = False
esc = False
while k < len(html):
    ch = html[k]
    if in_str:
        if esc:
            esc = False
        elif ch == '\\':
            esc = True
        elif ch == '"':
            in_str = False
    else:
        if ch == '"':
            in_str = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                break
    k += 1
raw = html[j:k+1]
print('MFD literal length:', len(raw))
try:
    mfd = json.loads(raw)
    print('MFD is pure JSON')
    print('groups:', {g: len(v) for g, v in mfd.items()})
    out = r'C:\Users\Administrator\AppData\Local\Temp\srcsite\mfd.json'
    json.dump(mfd, open(out, 'w', encoding='utf-8'), ensure_ascii=False)
    print('saved', out)
except Exception as e:
    print('not pure json:', e)
    print(raw[:300])
