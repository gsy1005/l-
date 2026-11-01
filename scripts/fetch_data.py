# -*- coding: utf-8 -*-
"""
流动性监测面板 · 数据管道
数据源与源网站 (vincizh.github.io/market-fragility-dashboard) 相同:
  - FRED fredgraph.csv (无需 API key)
  - 纽约联储公开市场操作 API
  - Yahoo Finance (可选, 失败则跳过)
输出: app/public/data.json
"""
import csv
import io
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, date, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "app", "public", "data.json")

UA = {"User-Agent": "Mozilla/5.0 (liquidity-dashboard)"}


def http_get(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_fred(sid):
    """FRED fredgraph.csv -> [(date, float)] 升序"""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    txt = http_get(url)
    rows = []
    for d, v in csv.reader(io.StringIO(txt)):
        if d == "observation_date" or not d:
            continue
        if v in (".", "", None):
            continue
        try:
            rows.append((d, float(v)))
        except ValueError:
            continue
    return rows


def fetch_fred_safe(sid):
    try:
        return fetch_fred(sid)
    except Exception as e:
        print(f"  [warn] FRED {sid} 抓取失败: {e}", file=sys.stderr)
        return []


def latest(rows):
    return rows[-1] if rows else (None, None)


def at_or_before(rows, d):
    """不晚于 d 的最后一个值"""
    val = None
    for dd, v in rows:
        if dd <= d:
            val = v
        else:
            break
    return val


def chg(rows, days):
    """最新值 - 不晚于 (最新日期 - days) 的值"""
    if not rows:
        return None
    d0, v0 = rows[-1]
    base = at_or_before(rows, (date.fromisoformat(d0) - timedelta(days=days)).isoformat())
    return round(v0 - base, 4) if base is not None else None


def pctile_rank(vals, x):
    """x 在 vals 中的百分位 (0-100)"""
    vals = [v for v in vals if v is not None and not math.isnan(v)]
    if not vals or x is None:
        return None
    le = sum(1 for v in vals if v <= x)
    return round(100.0 * le / len(vals), 1)


def window(rows, years=None, days=None):
    if not rows:
        return []
    d0 = date.fromisoformat(rows[-1][0])
    cut = d0 - timedelta(days=(days if days else int(years * 365.25)))
    return [r for r in rows if r[0] >= cut.isoformat()]


def tail_series(rows, years=None, days=None, nd=3):
    return [{"d": d, "v": round(v, nd)} for d, v in window(rows, years, days)]


def zscore(vals, x):
    n = len(vals)
    if n < 10 or x is None:
        return None
    m = sum(vals) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / n)
    return round((x - m) / sd, 2) if sd > 0 else 0.0


# ---------- 日历噪音标记 (月末/季末/缴税日) ----------
def is_calendar_noise(dstr):
    d = date.fromisoformat(dstr)
    # 月末: 当月最后两个日历日内, 或次月第1个工作日附近由数据自身体现, 简化用最后两个自然日
    nxt = d + timedelta(days=1)
    month_end = nxt.day <= 2  # 当天是月末或月末前一天
    quarter_end = month_end and d.month in (3, 6, 9, 12)
    year_end = (d.month == 12 and d.day >= 29) or (d.month == 1 and d.day <= 2)
    tax = (d.month, d.day) in ((4, 15), (4, 16), (6, 15), (9, 15), (9, 16), (12, 15))
    return bool(month_end or quarter_end or year_end or tax)


def status_of(obs_date, cadence_days, now):
    if not obs_date:
        return "missing"
    lag = (now - date.fromisoformat(obs_date)).days
    return "current" if lag <= cadence_days else "stale"


def main():
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    print("抓取 FRED 数据 ...")
    S = {}
    fred_ids = [
        "SOFR", "IORB", "EFFR", "OBFR", "TGCRRATE", "SOFR99", "SOFRVOL",
        "WRESBAL", "WTREGEN", "WALCL", "RRPONTSYD", "WLCFLPCL", "SWPT",
        "H41RESPPALGTRFNWW", "WLRRAFOIAL",
        "GDP", "DGS30", "DGS10", "THREEFYTP10",
        "BAMLH0A0HYM2", "BAMLC0A0CM", "BAMLH0A3HYC", "BAMLH0A1HYBB",
        "NFCI", "VIXCLS", "VXVCLS", "DTWEXBGS", "DCOILWTICO",
    ]
    for sid in fred_ids:
        S[sid] = fetch_fred_safe(sid)
        d, v = latest(S[sid])
        print(f"  {sid:22s} n={len(S[sid]):5d}  last={d} {v}")
        time.sleep(0.4)

    # ---------- A. 资金价格: SOFR - IORB (bp) ----------
    sofr = dict(S["SOFR"])
    sofr_iorb = []
    for d, v in S["IORB"]:
        if d in sofr:
            sofr_iorb.append((d, round((sofr[d] - v) * 100, 1)))  # bp
    non_cal = [(d, v) for d, v in sofr_iorb if not is_calendar_noise(d)]
    filt_med = None
    if len(non_cal) >= 5:
        last5 = sorted(v for _, v in non_cal[-5:])
        filt_med = last5[2]
    last3_ok = len(non_cal) >= 3 and all(v >= 3.0 for _, v in non_cal[-3:])
    leg_a = (filt_med is not None and filt_med >= 3.0) and last3_ok
    d_so, v_so = latest(sofr_iorb)
    chg1_so = round(v_so - sofr_iorb[-2][1], 1) if len(sofr_iorb) > 1 else None

    # ---------- B. 准备金 (WRESBAL, 原始单位: 百万美元 -> 转为十亿美元) ----------
    res = [(d, v / 1000.0) for d, v in S["WRESBAL"]]  # $B
    d_r, v_r = latest(res)
    res_T = round(v_r / 1000, 3)
    r1 = chg(res, 7)
    r4 = chg(res, 28)
    leg_b_level = res_T <= 2.90
    leg_b_flow = (r4 is not None and r4 <= -50)
    leg_b = leg_b_level and leg_b_flow
    res_elev = res_T <= 2.85 or (r4 is not None and r4 <= -100)

    # ---------- C. TGA (WTREGEN, 百万美元 -> 十亿美元) ----------
    tga = [(d, v / 1000.0) for d, v in S["WTREGEN"]]  # $B
    d_t, v_t = latest(tga)
    tga_T = round(v_t / 1000, 3)
    t1 = chg(tga, 7)
    t4 = chg(tga, 28)
    leg_c_level = tga_T >= 0.90
    leg_c_flow = (t4 is not None and t4 >= 50)
    leg_c = leg_c_level and leg_c_flow
    tga_elev = tga_T >= 1.00 or (t4 is not None and t4 >= 100)

    resonance = sum([leg_a, leg_b, leg_c])
    res_state = ["正常", "关注", "警示", "结构性顶部风险信号"][resonance]

    # ---------- 后备工具 ----------
    def billions(rows, unit):
        """统一转成 $B. unit: 'B' 或 'M'"""
        f = 1.0 if unit == "B" else 0.001
        return [(d, v * f) for d, v in rows]

    srf = billions(S["RRPONTSYD"], "B")          # 常备回购便利, 日度 $B
    srf7 = round(sum(v for _, v in window(srf, days=7)), 2)
    srf_p95 = None
    w3 = [v for _, v in window(srf, years=3)]
    if w3:
        w3s = sorted(w3)
        srf_p95 = round(w3s[int(0.95 * (len(w3s) - 1))], 2)
    dw = billions(S["WLCFLPCL"], "M")            # 贴现窗口, 周度 millions -> $B
    d_dw, v_dw = latest(dw)
    dw4 = chg(dw, 28)
    dw3 = sorted(v for _, v in window(dw, years=3))
    dw_p95 = round(dw3[int(0.95 * (len(dw3) - 1))], 2) if dw3 else None
    swpt = billions(S["SWPT"], "M")              # 央行互换 millions -> $B
    d_sw, v_sw = latest(swpt)
    sw3 = sorted(v for _, v in window(swpt, years=3))
    sw_p95 = round(sw3[int(0.95 * (len(sw3) - 1))], 2) if sw3 else None
    fima = billions(S["H41RESPPALGTRFNWW"], "M")  # FIMA 回购 millions -> $B
    d_fi, v_fi = latest(fima)
    fi3 = sorted(v for _, v in window(fima, years=3))
    fi_p95 = round(fi3[int(0.95 * (len(fi3) - 1))], 2) if fi3 else None
    rrpfo = billions(S["WLRRAFOIAL"], "M")       # 外国官方逆回购池
    d_fo, v_fo = latest(rrpfo)
    fo4 = chg(rrpfo, 28)

    def backstop_state(level, floor, p95):
        if level is None:
            return "quiet"
        if floor is not None and level < floor:
            return "quiet"
        if p95 is not None and level >= p95:
            return "elevated"
        return "in_use"

    bs = {
        "srf": {"level": round(srf7, 2), "state": backstop_state(srf7, 1.0, srf_p95), "p95": srf_p95, "asof": latest(srf)[0]},
        "dw": {"level": round(v_dw, 2), "state": ("elevated" if (dw_p95 is not None and v_dw >= dw_p95 and (dw4 or 0) > 0) else ("in_use" if dw_p95 is not None and v_dw >= dw_p95 else "quiet")), "p95": dw_p95, "asof": d_dw, "chg4w": dw4},
        "swaps": {"level": round(v_sw, 2), "state": backstop_state(v_sw, 5.0, sw_p95), "p95": sw_p95, "asof": d_sw},
        "fima": {"level": round(v_fi, 2), "state": backstop_state(v_fi, 1.0, fi_p95), "p95": fi_p95, "asof": d_fi},
        "rrpfo": {"level": round(v_fo, 1), "chg4w": round(fo4, 1) if fo4 is not None else None, "asof": d_fo},
    }
    in_use = sum(1 for k in ("srf", "dw", "swaps", "fima") if bs[k]["state"] in ("in_use", "elevated"))

    # ---------- 回购分布与成交量 ----------
    tgcr = dict(S["TGCRRATE"])
    tgcr_iorb = [(d, round((tgcr[d] - v) * 100, 1)) for d, v in S["IORB"] if d in tgcr]
    d_tg, v_tg = latest(tgcr_iorb)
    tg5 = sorted(v for _, v in tgcr_iorb[-5:])
    tg_med5 = tg5[2] if len(tg5) == 5 else None

    sofr99 = dict(S["SOFR99"])
    tail = [(d, round((v99 - sofr[d]) * 100, 1)) for d, v99 in S["SOFR99"] if d in sofr] if False else \
           [(d, round((sofr99[d] - v) * 100, 1)) for d, v in S["SOFR"] if d in sofr99]
    d_tl, v_tl = latest(tail)
    tl_pct = pctile_rank([v for _, v in window(tail, years=2)], v_tl)

    vol = S["SOFRVOL"]  # $B
    d_vl, v_vl = latest(vol)
    vol20 = [v for _, v in vol[-21:-1]]
    vol20avg = round(sum(vol20) / len(vol20), 0) if vol20 else None
    vol_pct = pctile_rank([v for _, v in window(vol, years=2)], v_vl)

    # ---------- 净流动性 (WALCL - TGA - RRP), WALCL 单位百万 -> 十亿 ----------
    walcl = dict((d, v / 1000.0) for d, v in S["WALCL"])  # -> $B
    tga_d = dict(tga)
    rrp_d = dict(S["RRPONTSYD"])  # $B
    common = sorted(set(walcl) & set(tga_d) & set(rrp_d))
    netliq = [(d, round(walcl[d] - tga_d[d] - rrp_d[d], 1)) for d in common]
    d_nl, v_nl = latest(netliq)
    nl1 = chg(netliq, 7)
    nl4 = chg(netliq, 28)
    # 近 26 周驱动分解
    drivers = []
    for i in range(max(1, len(netliq) - 26), len(netliq)):
        d = netliq[i][0]
        prev = netliq[i - 1][0]
        drivers.append({
            "d": d,
            "fed": round(walcl[d] - walcl[prev], 1),
            "tga": round(-(tga_d[d] - tga_d[prev]), 1),
            "rrp": round(-(rrp_d[d] - rrp_d[prev]), 1),
        })

    # ---------- 准备金/GDP ----------
    gdp = S["GDP"]  # 季度 $B
    rg = []
    for d, v in res:
        g = at_or_before(gdp, d)
        if g:
            rg.append((d, round(100.0 * v / g, 2)))
    d_rg, v_rg = latest(rg)
    rg156 = [v for _, v in rg[-156:]]
    rg_pct = pctile_rank(rg156, v_rg)
    rg_recent_pct = [pctile_rank(rg156, v) for _, v in rg[-2:]]
    rg_state = "normal"
    if len(rg_recent_pct) == 2 and all(p is not None and p < 10 for p in rg_recent_pct):
        rg_state = "elevated"
    elif len(rg_recent_pct) == 2 and all(p is not None and p < 20 for p in rg_recent_pct):
        rg_state = "warning"

    # ---------- 信用 ----------
    def credit_card(sid, years=3):
        rows = S[sid]
        d, v = latest(rows)
        c20 = chg(rows, 20)
        pct = pctile_rank([x for _, x in window(rows, years=years)], v)
        chgs = [rows[i][1] - at_or_before(rows, (date.fromisoformat(rows[i][0]) - timedelta(days=20)).isoformat())
                for i in range(max(1, len(rows) - 504), len(rows))]
        chgs = [c for c in chgs if c is not None]
        z = zscore(chgs, c20)
        return {"asof": d, "level": round(v * 100, 0) if v < 50 else round(v, 2), "chg20": round(c20 * 100, 0) if v < 50 else c20,
                "pct": pct, "z": z, "series": tail_series([(dd, vv * 100) for dd, vv in rows], years=3, nd=0)}

    hy = credit_card("BAMLH0A0HYM2")
    ig = credit_card("BAMLC0A0CM")
    ccc = dict(S["BAMLH0A3HYC"])
    bb = dict(S["BAMLH0A1HYBB"])
    cccbb = [(d, round((ccc[d] - bb[d]) * 100, 0)) for d in sorted(set(ccc) & set(bb))]
    d_cb, v_cb = latest(cccbb)
    cb20 = chg(cccbb, 20)
    cb_pct = pctile_rank([v for _, v in window(cccbb, years=3)], v_cb)
    nfci = S["NFCI"]
    d_nf, v_nf = latest(nfci)
    nf_pct = pctile_rank([v for _, v in window(nfci, years=3)], v_nf)

    def cred_state(pct, z):
        if pct is None:
            return "normal"
        if pct >= 90 and (z or 0) > 1:
            return "stress"
        if pct >= 75:
            return "watch"
        return "normal"

    # ---------- 利率与期限溢价 ----------
    def rates_card(sid, years=17):
        rows = S[sid]
        d, v = latest(rows)
        return {"asof": d, "level": round(v, 2), "chg20": chg(rows, 20),
                "pct": pctile_rank([x for _, x in window(rows, years=years)], v),
                "series": tail_series(rows, years=3)}

    dgs30 = rates_card("DGS30")
    dgs10 = rates_card("DGS10")
    tp10 = rates_card("THREEFYTP10", years=10)

    # ---------- VIX 期限结构 ----------
    vix = dict(S["VIXCLS"])
    vxv = dict(S["VXVCLS"])
    common_v = sorted(set(vix) & set(vxv))
    d_vx = common_v[-1] if common_v else None
    vix_lvl = vix[d_vx] if d_vx else None
    vxv_lvl = vxv[d_vx] if d_vx else None
    slope = round(vxv_lvl - vix_lvl, 2) if d_vx else None
    term_state = "contango" if (slope is not None and slope > 0) else "backwardation"
    vix_pct = pctile_rank([v for _, v in window(S["VIXCLS"], years=3)], vix_lvl)

    # ---------- 美元指数 & 油价 ----------
    dxy = S["DTWEXBGS"]
    d_dx, v_dx = latest(dxy)
    wti = S["DCOILWTICO"]
    d_wt, v_wt = latest(wti)

    # ---------- LPI 综合指数 (周度, 0-100) ----------
    def weekly_last(rows):
        """日度 -> 每周最后一个观测"""
        out = {}
        for d, v in rows:
            key = date.fromisoformat(d).isocalendar()[:2]
            out[key] = (d, v)
        return sorted(out.values())

    def inv_pct_series(rows, years=3):
        """返回 (周序列, 最新百分位); 用于越高越危险的指标"""
        w = window(rows, years=years)
        vals = [v for _, v in w]
        return w, vals

    f_short = pctile_rank([v for _, v in window(sofr_iorb, years=3)], v_so)
    nl_vals = [v for _, v in window(netliq, years=3)]
    f_netliq = pctile_rank(nl_vals, v_nl)
    f_netliq = round(100 - f_netliq, 1) if f_netliq is not None else None  # 越低越危险
    f_vol = vix_pct
    f_dur = pctile_rank([v for _, v in window(S["THREEFYTP10"], years=3)], S["THREEFYTP10"][-1][1] if S["THREEFYTP10"] else None)
    factors = {
        "short": {"name": "短端资金利率", "value": f_short, "asof": d_so},
        "netliq": {"name": "净流动性", "value": f_netliq, "asof": d_nl},
        "vol": {"name": "波动放大器", "value": f_vol, "asof": d_vx},
        "dur": {"name": "久期供给(期限溢价代理)", "value": f_dur, "asof": S["THREEFYTP10"][-1][0] if S["THREEFYTP10"] else None},
    }
    fvals = [f["value"] for f in factors.values() if f["value"] is not None]
    lpi = round(sum(fvals) / len(fvals), 1) if fvals else None
    lpi_state = "稳健" if lpi is None else ("稳健" if lpi < 40 else "中性" if lpi < 60 else "偏高" if lpi < 80 else "极端")

    # LPI 历史 (周度): 用三因子历史百分位近似 (SOFR-IORB, 净流动性, VIX)
    lpi_hist = []
    w_so3 = window(sofr_iorb, years=3)
    w_nl3 = window(netliq, years=3)
    w_vx3 = window(S["VIXCLS"], years=3)
    nl_d = dict(w_nl3)
    vx_w = weekly_last(w_vx3)
    so_w = weekly_last(w_so3)
    vx_d = dict(vx_w)
    for d, v in so_w:
        nlv = at_or_before(w_nl3, d)
        vxv2 = at_or_before(vx_w, d)
        if nlv is None or vxv2 is None:
            continue
        p1 = pctile_rank([x for _, x in w_so3], v)
        p2 = pctile_rank(nl_vals, nlv)
        p3 = pctile_rank([x for _, x in w_vx3], vxv2)
        if None in (p1, p2, p3):
            continue
        lpi_hist.append({"d": d, "v": round((p1 + (100 - p2) + p3) / 3, 1)})
    lpi_hist = lpi_hist[-156:]

    # ---------- NY Fed 常备回购操作 (补充确认, 可选) ----------
    nyfed_repo = None
    for api in ("https://markets.newyorkfed.org/api/rp/all/results/last/10.json",
                "https://markets.newyorkfed.org/api/rp/secured/all/results/last/10.json"):
        try:
            j = json.loads(http_get(api))
            ops = j.get("repo", {}).get("operations", [])
            if ops:
                tot7 = 0.0
                n_nonzero = 0
                for op in ops:
                    det = op.get("details", [])
                    amt = sum(float(x.get("acceptedAmt", 0) or 0) for x in det) / 1e9
                    tot7 += amt
                    if amt > 0:
                        n_nonzero += 1
                nyfed_repo = {"asof": ops[-1].get("operationDate"), "sum7": round(tot7, 2), "nonzero_days": n_nonzero}
                break
        except Exception as e:
            print(f"  [warn] NY Fed repo 抓取失败({api}): {e}", file=sys.stderr)

    # ---------- 压力日历 (未来120天, 规则生成) ----------
    fomc = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
            "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"]
    cal = []
    for i in range(120):
        d = today + timedelta(days=i)
        iso = d.isoformat()
        if iso in fomc:
            cal.append({"d": iso, "t": "FOMC 利率决议", "k": "fomc"})
        nxt = d + timedelta(days=1)
        if nxt.day == 1:
            label = "季末结算日" if d.month in (3, 6, 9, 12) else "月末结算日"
            cal.append({"d": iso, "t": label, "k": "monthend"})
        if (d.month, d.day) in ((4, 15), (6, 15), (9, 15), (12, 15)):
            cal.append({"d": iso, "t": "企业预估缴税日 (TGA 流入)", "k": "tax"})
        if d.weekday() == 2 and d.day <= 7 and d.month in (2, 5, 8, 11):
            cal.append({"d": iso, "t": "季度再融资公告 (惯例首个周三)", "k": "refunding"})
    cal = sorted(cal, key=lambda x: x["d"])[:24]

    # ---------- 数据健康 ----------
    health = []
    cad = {"SOFR": 4, "IORB": 4, "EFFR": 4, "TGCRRATE": 4, "SOFR99": 4, "SOFRVOL": 4,
           "WRESBAL": 10, "WTREGEN": 10, "WALCL": 10, "RRPONTSYD": 4, "WLCFLPCL": 10,
           "SWPT": 10, "H41RESPPALGTRFNWW": 10, "WLRRAFOIAL": 10, "GDP": 100,
           "DGS30": 4, "DGS10": 4, "THREEFYTP10": 4, "BAMLH0A0HYM2": 4, "BAMLC0A0CM": 4,
           "BAMLH0A3HYC": 4, "BAMLH0A1HYBB": 4, "NFCI": 10, "VIXCLS": 4, "VXVCLS": 4,
           "DTWEXBGS": 10, "DCOILWTICO": 4, "OBFR": 4}
    names = {"SOFR": "担保隔夜融资利率", "IORB": "准备金余额利率", "EFFR": "有效联邦基金利率",
             "TGCRRATE": "三方一般抵押回购利率", "SOFR99": "SOFR 第99分位", "SOFRVOL": "SOFR 成交量",
             "WRESBAL": "银行准备金余额", "WTREGEN": "财政部一般账户 TGA", "WALCL": "美联储总资产",
             "RRPONTSYD": "常备回购便利用量", "WLCFLPCL": "贴现窗口一级信贷", "SWPT": "央行流动性互换",
             "H41RESPPALGTRFNWW": "FIMA 回购便利", "WLRRAFOIAL": "外国官方逆回购池", "GDP": "名义 GDP",
             "DGS30": "30年期国债收益率", "DGS10": "10年期国债收益率", "THREEFYTP10": "10年期限溢价",
             "BAMLH0A0HYM2": "高收益债 OAS", "BAMLC0A0CM": "投资级公司债 OAS",
             "BAMLH0A3HYC": "CCC 级 OAS", "BAMLH0A1HYBB": "BB 级 OAS", "NFCI": "芝加哥联储金融状况指数",
             "VIXCLS": "VIX 波动率指数", "VXVCLS": "VIX3M", "DTWEXBGS": "广义美元指数",
             "DCOILWTICO": "WTI 原油", "OBFR": "隔夜银行融资利率"}
    for sid in fred_ids:
        d, _ = latest(S[sid])
        health.append({"id": sid, "name": names.get(sid, sid), "asof": d,
                       "status": status_of(d, cad.get(sid, 10), today),
                       "cadence": "周度" if cad.get(sid, 4) >= 7 else "日度"})

    out = {
        "generatedAt": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "fetchedBeijing": now_utc.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M (北京)"),
        "trio": {
            "resonance": resonance, "state": res_state,
            "a": {"asof": d_so, "level": v_so, "chg1": chg1_so, "filtMed": filt_med, "leg": leg_a,
                  "last3": [v for _, v in non_cal[-3:]]},
            "b": {"asof": d_r, "levelT": res_T, "chg1w": r1, "chg4w": r4,
                  "speed": round(r4 / 4, 0) if r4 is not None else None,
                  "leg": leg_b, "levelMet": leg_b_level, "flowMet": leg_b_flow, "elevated": res_elev},
            "c": {"asof": d_t, "levelT": tga_T, "chg1w": t1, "chg4w": t4,
                  "speed": round(t4 / 4, 0) if t4 is not None else None,
                  "leg": leg_c, "levelMet": leg_c_level, "flowMet": leg_c_flow, "elevated": tga_elev},
        },
        "backstops": bs, "backstopInUse": in_use,
        "repoDisp": {
            "tgcrIorb": {"asof": d_tg, "level": v_tg, "med5": tg_med5},
            "tail": {"asof": d_tl, "level": v_tl, "pct": tl_pct},
            "vol": {"asof": d_vl, "levelT": round(v_vl / 1000, 2), "avg20T": round(vol20avg / 1000, 2) if vol20avg else None, "pct": vol_pct},
        },
        "netliq": {"asof": d_nl, "levelT": round(v_nl / 1000, 2), "chg1w": nl1, "chg4w": nl4, "drivers": drivers},
        "resGdp": {"asof": d_rg, "level": v_rg, "pct": rg_pct, "state": rg_state},
        "nyfedRepo": nyfed_repo,
        "credit": {"hy": hy, "ig": ig,
                   "cccbb": {"asof": d_cb, "level": v_cb, "chg20": cb20, "pct": cb_pct},
                   "nfci": {"asof": d_nf, "level": round(v_nf, 2), "pct": nf_pct}},
        "rates": {"dgs30": dgs30, "dgs10": dgs10, "tp10": tp10},
        "vixTerm": {"asof": d_vx, "vix": vix_lvl, "vxv": vxv_lvl, "slope": slope, "state": term_state, "vixPct": vix_pct},
        "context": {"dxy": {"asof": d_dx, "level": v_dx}, "wti": {"asof": d_wt, "level": v_wt}},
        "lpi": {"value": lpi, "state": lpi_state, "factors": factors, "hist": lpi_hist},
        "calendar": cal,
        "health": health,
        "series": {
            "sofrIorb": [{**x, "cal": is_calendar_noise(x["d"])} for x in tail_series(sofr_iorb, years=3, nd=1)],
            "reserves": tail_series([(d, v / 1000) for d, v in res], years=3),
            "tga": tail_series([(d, v / 1000) for d, v in tga], years=3),
            "netliq": tail_series([(d, v / 1000) for d, v in netliq], years=3),
            "hyOas": hy["series"], "igOas": ig["series"],
            "cccbb": tail_series(cccbb, years=3, nd=0),
            "dgs30": dgs30["series"], "tp10": tp10["series"],
            "vix": tail_series(S["VIXCLS"], years=2),
            "sofrTail": tail_series(tail, years=2, nd=1),
            "sofrVol": tail_series(vol, years=1, nd=0),
        },
    }
    for k in ("hy", "ig"):
        out["credit"][k].pop("series", None)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n已写出 {OUT} ({os.path.getsize(OUT)//1024} KB)")
    print(f"共振: {resonance}/3 {res_state} | LPI: {lpi} {lpi_state}")


if __name__ == "__main__":
    main()
