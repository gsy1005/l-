# -*- coding: utf-8 -*-
"""
从官方公开接口直接抓取核心流动性指标 → static-dist/live.js
数据源 (均为免 key 公开接口, GitHub Actions 可达):
  - 纽约联储 markets API: SOFR / EFFR / OBFR / TGCR / BGCR
  - 美国财政部: 日度收益率曲线 (2Y/10Y/30Y), TGA 一般账户余额 (FiscalData)
  - CBOE: VIX 历史收盘
  - FRED (可选补充, 部分网络不可达时自动跳过): IORB / 准备金 / ON RRP / OAS / 美元指数
产出 window.LIVE_DATA, 由页面顶部的"实时快线"横幅渲染
用法: python scripts/live_data.py
"""
import csv
import io
import json
import os
import ssl
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "static-dist")
OUT_JS = os.path.join(OUT_DIR, "live.js")
FLAG = os.path.join(HERE, ".force-rebuild")  # 数据有更新时置位, 供 build_static.py 判断
DEPLOYED_LIVE_JS = "https://gsy1005.github.io/l-/live.js"

UA = {"User-Agent": "Mozilla/5.0"}


def fetch(url: str, timeout: int = 25, insecure: bool = False) -> str:
    req = urllib.request.Request(url, headers=UA)
    ctx = None
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8")


def item(k, label, unit, date, value, prev=None):
    return {"k": k, "label": label, "unit": unit, "date": date,
            "value": round(value, 4), "prev": round(prev, 4) if prev is not None else None}


def from_nyfed():
    """SOFR/TGCR/BGCR + EFFR/OBFR (有效日期与利率)"""
    items = []
    sec = json.loads(fetch("https://markets.newyorkfed.org/api/rates/secured/all/latest.json"))
    uns = json.loads(fetch("https://markets.newyorkfed.org/api/rates/unsecured/all/latest.json"))
    labels = {"SOFR": "SOFR 担保隔夜融资", "TGCR": "TGCR 三方回购", "BGCR": "BGCR 广义回购",
              "EFFR": "EFFR 有效联邦基金", "OBFR": "OBFR 银行隔夜拆借"}
    for src in (sec, uns):
        for r in src.get("refRates", []):
            t = r.get("type")
            if t in labels and r.get("percentRate") is not None:
                items.append(item(t, labels[t], "%", r["effectiveDate"], float(r["percentRate"])))
    return items


def from_treasury_yields():
    """日度国债收益率曲线: 2Y/10Y/30Y"""
    year = time.gmtime().tm_year
    url = (f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
           f"daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
           f"&field_tdr_date_value={year}&page&_format=csv")
    rows = list(csv.DictReader(io.StringIO(fetch(url))))
    items = []
    for col, label in (("2 Yr", "2年期美债"), ("10 Yr", "10年期美债"), ("30 Yr", "30年期美债")):
        vals = [(r["Date"], r[col]) for r in rows if r.get(col)]
        if vals:
            (d, v), (_, pv) = vals[0], (vals[1] if len(vals) > 1 else (None, None))
            # 日期格式 MM/DD/YYYY → YYYY-MM-DD
            m, dd, yy = d.split("/")
            items.append(item(col, label, "%", f"{yy}-{m}-{dd}", float(v),
                              float(pv) if pv else None))
    return items


def from_cboe_vix():
    """VIX 最新收盘"""
    txt = fetch("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv")
    last = txt.strip().splitlines()[-1].split(",")
    m, dd, yy = last[0].split("/")
    return [item("VIX", "VIX 波动率", "", f"{yy}-{m}-{dd}", float(last[4]))]


def from_tga():
    """TGA 财政部一般账户余额 (十亿美元)"""
    url = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
           "v1/accounting/dts/operating_cash_balance?sort=-record_date&page[size]=10")
    data = json.loads(fetch(url, insecure=True))["data"]
    for r in data:
        if "Closing Balance" in r["account_type"] and r.get("close_today_bal") not in (None, "null"):
            return [item("TGA", "TGA 财政部一般账户", "$B", r["record_date"],
                         float(r["close_today_bal"]) / 1000)]  # $M → $B
    for r in data:  # 兜底: 最新日期的开盘余额 (= 前日收盘)
        if "Opening Balance" in r["account_type"] and r.get("open_today_bal") not in (None, "null"):
            return [item("TGA", "TGA 财政部一般账户", "$B", r["record_date"],
                         float(r["open_today_bal"]) / 1000)]
    return []


# FRED 可选补充 (CI 网络可能被 FRED 拦截, 单次短超时探测)
FRED_SERIES = [
    ("IORB",         "IORB 准备金利率",    "%", 1),
    ("WRESBAL",      "银行准备金",         "$B", 0.001),  # FRED 单位: 百万美元 → 十亿
    ("RRPONTSYD",    "ON RRP 隔夜逆回购",  "$B", 1),
    ("BAMLC0A0CM",   "投资级债 OAS",       "%", 1),
    ("BAMLH0A0HYM2", "高收益债 OAS",       "%", 1),
    ("DTWEXBGS",     "广义美元指数",       "",  1),
]


def from_fred_optional():
    items = []
    try:  # 先探测连通性, 10 秒超时
        probe = fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=IORB", timeout=10)
    except Exception as e:
        print("[跳过] FRED 全部 (不可达):", e)
        return items
    for sid, label, unit, scale in FRED_SERIES:
        try:
            rows = []
            csv_text = probe if sid == "IORB" else fetch(
                f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=10)
            for line in csv_text.strip().splitlines()[1:]:
                d, _, v = line.partition(",")
                if v.strip() and v.strip() != ".":
                    rows.append((d.strip(), float(v)))
            if rows:
                items.append(item(sid, label, unit, rows[-1][0], rows[-1][1] * scale,
                                  rows[-2][1] * scale if len(rows) > 1 else None))
        except Exception as e:
            print(f"[跳过] FRED {sid}: {e}")
        time.sleep(0.3)
    return items


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    items = []
    for name, fn in (("纽约联储", from_nyfed), ("美债收益率", from_treasury_yields),
                     ("VIX", from_cboe_vix), ("TGA", from_tga), ("FRED", from_fred_optional)):
        try:
            got = fn()
            items.extend(got)
            print(f"[OK] {name}: {len(got)} 项")
        except Exception as e:
            print(f"[跳过] {name}: {e}")

    # SOFR − IORB 利差 (bp) —— 仪表盘核心指标, IORB 可用时才算
    by_k = {it["k"]: it for it in items}
    if "SOFR" in by_k and "IORB" in by_k:
        spread = round((by_k["SOFR"]["value"] - by_k["IORB"]["value"]) * 100, 1)
        items.insert(0, item("SOFR-IORB", "SOFR − IORB 利差", "bp", by_k["SOFR"]["date"], spread))

    payload = {"updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "items": items}
    js = "window.LIVE_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n"

    # 与线上已部署的 live.js 对比, 不同则置重建标志
    try:
        deployed = fetch(DEPLOYED_LIVE_JS + "?t=" + str(int(time.time())))
        changed = deployed != js
    except Exception:
        changed = True
    if changed:
        open(FLAG, "w").write("1")
    elif os.path.exists(FLAG):
        os.remove(FLAG)

    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"live.js 输出 {len(items)} 项指标, 数据{'有' if changed else '无'}变化")


if __name__ == "__main__":
    main()
