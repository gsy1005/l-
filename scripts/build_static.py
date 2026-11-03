# -*- coding: utf-8 -*-
"""
整页复制源站并做文本级汉化 → static-dist/index.html
源站是自包含单文件 (内嵌 CSS + Plotly 图表 JS + 数据), 因此:
- 保留全部结构 / 样式 / 脚本, 版式与源站完全一致
- 只替换文本节点 (跳过 <script>/<style>), 删除方法与数据健康板块, 剥离外链与数据源署名
用法: python scripts/build_static.py [--cached]
"""
import os
import re
import sys
import urllib.request

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import i18n
from scrape_source import SRC_URL, sanitize_text

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_HTML = os.path.join(HERE, "cache", "index.html")
OUT_DIR = os.path.join(HERE, "..", "static-dist")
OUT_HTML = os.path.join(OUT_DIR, "index.html")

DROP_SECTION_IDS = ("sec-methods",)  # 用户要求删除的板块


def fetch_source() -> str:
    req = urllib.request.Request(SRC_URL + "/", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8")
    os.makedirs(os.path.dirname(CACHE_HTML), exist_ok=True)
    with open(CACHE_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    return html


def remove_source_attribution(body: Tag):
    """删除 <b>Source(s):</b> 到下一个 <br> 之间的署名内容"""
    for b in body.find_all("b"):
        if b.get_text(strip=True).lower().rstrip(":") in ("source", "sources", "official sources"):
            sib = b.next_sibling
            b.decompose()
            while sib is not None:
                nxt = sib.next_sibling
                if isinstance(sib, Tag) and sib.name == "br":
                    sib.decompose()
                    break
                if isinstance(sib, (Tag, NavigableString)):
                    sib.extract()
                sib = nxt


def dedup_bilingual_titles(body: Tag):
    """阶段标题: 已有中文 zh 副标时, 去掉前面的英文主标"""
    for st in body.find_all("span", class_="stage-title"):
        zh = st.find("span", class_="zh")
        if zh:
            for child in list(st.contents):
                if child is zh:
                    break
                child.extract()


def in_script_or_style(node) -> bool:
    p = node.parent
    while p is not None:
        if isinstance(p, Tag) and p.name in ("script", "style"):
            return True
        p = p.parent
    return False


def translate_text_nodes(soup: BeautifulSoup):
    n_changed = 0
    for txt in soup.find_all(string=True):
        if in_script_or_style(txt):
            continue
        raw = str(txt)
        if not raw.strip():
            continue
        new = i18n.translate_text(sanitize_text(raw))
        if new != raw:
            txt.replace_with(new)
            n_changed += 1
    return n_changed


SITE_URL = "https://gsy1005.github.io/l-/"
LIVE_FLAG = os.path.join(HERE, ".force-rebuild")  # live_data.py 检测到官方数据有更新时置位

# 实时快线横幅: 官方数据直连, 数据在 live.js 中, 由 hourly 任务更新
LIVE_STRIP_HTML = """
<div id="live-strip">
  <div class="ls-head">实时快线 · 官方数据直连 <span id="ls-updated"></span></div>
  <div class="ls-items" id="ls-items"></div>
</div>
<style>
#live-strip{margin:10px 20px 0;background:var(--surface,#141720);border:1px solid var(--border,#1e2530);border-left:3px solid #6366f1;border-radius:10px;padding:10px 14px}
.ls-head{font-size:12px;font-weight:700;color:#cbd5e1;letter-spacing:.04em;margin-bottom:8px}
.ls-head span{color:#64748b;font-weight:400;margin-left:8px}
.ls-items{display:flex;gap:10px;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}
.ls-items::-webkit-scrollbar{display:none}
.ls-item{flex:0 0 auto;min-width:118px;background:var(--bg,#0f131b);border:1px solid var(--border,#1e2530);border-radius:8px;padding:8px 10px}
.ls-k{font-size:11px;color:#94a3b8;white-space:nowrap}
.ls-v{font-size:17px;font-weight:700;color:#e2e8f0;font-variant-numeric:tabular-nums;margin-top:2px}
.ls-dt{font-size:10.5px;color:#64748b;margin-top:2px;white-space:nowrap}
.ls-d{margin-left:5px}
.ls-d.up{color:#f87171}.ls-d.down{color:#34d399}.ls-d.flat{color:#64748b}
</style>
<script src="live.js"></script>
<script>
(function(){
  function fmt(it){
    var v=it.value;
    if(it.unit==='$B'&&Math.abs(v)>=1000)return (v/1000).toFixed(2)+'T';
    if(it.unit==='%')return v.toFixed(2)+'%';
    if(it.unit==='bp')return v.toFixed(1)+' bp';
    if(it.unit==='$B')return v.toFixed(0)+'B';
    return v.toFixed(2);
  }
  function render(){
    var D=window.LIVE_DATA, box=document.getElementById('ls-items');
    if(!D||!D.items||!D.items.length){var s=document.getElementById('live-strip');if(s)s.style.display='none';return;}
    document.getElementById('ls-updated').textContent='更新于 '+D.updated;
    var html='';
    D.items.forEach(function(it){
      var d='';
      if(it.prev!=null){var diff=it.value-it.prev;
        var cls=diff>0.0001?'up':(diff<-0.0001?'down':'flat');
        var sym=diff>0.0001?'▲':(diff<-0.0001?'▼':'–');
        d='<span class="ls-d '+cls+'">'+sym+' '+Math.abs(diff).toFixed(2)+'</span>';}
      html+='<div class="ls-item"><div class="ls-k">'+it.label+'</div><div class="ls-v">'+fmt(it)+'</div><div class="ls-dt">'+it.date+d+'</div></div>';
    });
    box.innerHTML=html;
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render);else render();
})();
</script>
"""


def set_gh_output(key: str, value: str):
    """写 GitHub Actions step 输出 (本地运行时静默跳过)"""
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def timestamp_of(html: str, label: str):
    m = re.search(label + r"[:：]?\s*((?:20\d\d)-\d\d-\d\d\s+\d\d:\d\d\s*UTC)", html)
    return m.group(1).strip() if m else None


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def main():
    if "--cached" in sys.argv and os.path.exists(CACHE_HTML):
        html = open(CACHE_HTML, encoding="utf-8").read()
        print("使用缓存:", CACHE_HTML)
    else:
        html = fetch_source()
        print("已抓取源站:", len(html), "字节")

    # 定时运行时: 源站时间戳与线上一致 且 官方实时数据也无更新 → 跳过部署 (省资源; push/手动触发总是全量部署)
    if not os.environ.get("FORCE") and "--cached" not in sys.argv:
        src_ts = timestamp_of(html, "Last updated")
        try:
            ours = fetch_url(SITE_URL + "?t=" + str(int(__import__("time").time())))
            our_ts = timestamp_of(ours, "更新于")
        except Exception as e:
            our_ts = None
            print("读取线上站点失败, 照常部署:", e)
        live_changed = os.path.exists(LIVE_FLAG)
        print("源站时间:", src_ts, "| 线上时间:", our_ts, "| 实时数据有更新:", live_changed)
        if src_ts and src_ts == our_ts and not live_changed:
            set_gh_output("changed", "false")
            print("数据未变化, 跳过部署")
            return
    set_gh_output("changed", "true")
    if os.path.exists(LIVE_FLAG):
        os.remove(LIVE_FLAG)

    soup = BeautifulSoup(html, "lxml")

    # 1. 删除指定板块及其导航入口
    for sid in DROP_SECTION_IDS:
        sec = soup.find("details", id=sid)
        if sec:
            sec.decompose()
            print("已删除板块:", sid)
        for a in soup.find_all("a", attrs={"data-target": sid}):
            a.decompose()
        for a in soup.find_all("a", href=f"#{sid}"):
            a.decompose()

    body = soup.body
    # 2. 剥离站外链接 (保留站内 # 锚点: 传导链卡片等依赖)
    for a in body.find_all("a", href=True):
        if a["href"].startswith(("http://", "https://")):
            a.unwrap()
    # 3. 数据源署名与双语标题去重
    remove_source_attribution(body)
    dedup_bilingual_titles(body)
    # 4. 全文文本节点汉化 (不动 script/style)
    n = translate_text_nodes(soup)
    print("汉化文本节点:", n)
    # 5. 语言标记
    if soup.html:
        soup.html["lang"] = "zh-CN"
    # 6. 在页头下方注入"实时快线"横幅 (数据来自官方接口, 见 scripts/live_data.py)
    header = soup.find("div", class_="header")
    if header:
        frag = BeautifulSoup(LIVE_STRIP_HTML, "html.parser")
        for el in reversed(list(frag.contents)):
            header.insert_after(el)
        print("已注入实时快线横幅")

    os.makedirs(OUT_DIR, exist_ok=True)
    doctype = "<!doctype html>\n" if html.lstrip().lower().startswith("<!doctype") else ""
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(doctype + str(soup))
    print("输出:", os.path.abspath(OUT_HTML), os.path.getsize(OUT_HTML) // 1024, "KB")


if __name__ == "__main__":
    main()
