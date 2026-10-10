"""인플레만 칸 XLU 100 vs XLU 50 + BIL 50 비교 (2026-10-10). 확정 전략(보험 15·주식 칸 2배 조건) 위에서 칸 비중만 바꾼다.
초장기 대리(주식 50 + 현금 50)는 research_longrun_ic.py 참조.

    python3 research_xlu_bil_compare.py
"""
import sys; sys.path.insert(0,".")
import pandas as pd, numpy as np, run_16_matrix_experiments as r16
from test_all_16_combinations import compute_signals, load_master_data
from research_cssa_strategies import mix, stats
prices,t5,vix,baa,dtb3=load_master_data()
sig,_=compute_signals(prices,t5,vix,baa,fred_lag=1)
orig_rw, orig_lev = r16.regime_weights, r16.leverage
def rw_half(row,p2,p3,prm,ief_ma):
    w=orig_rw(row,p2,p3,prm,ief_ma)
    return {"XLU":0.5,"BIL":0.5} if w=={"XLU":1.0} else w
pens=lambda past,p1,p4,prm:(0.5,False) if past[0]["fng"]>85 else (1.0,False)
def run(half,pension):
    r16.regime_weights = rw_half if half else orig_rw
    if pension: r16.leverage=pens
    try: return r16.simulate(sig,prices,dtb3,0,0,1,0)
    finally: r16.regime_weights, r16.leverage = orig_rw, orig_lev
last=pd.Timestamp("2026-09-30")
pent=pd.read_csv("data/pension_mix_backtest.csv",index_col=0,parse_dates=True)["PENT"]; pent.index=pent.index.to_period("M").to_timestamp("M")
me=sorted(sig.groupby([sig.index.year,sig.index.month]).apply(lambda x:x.index[-1]).values)
io=pd.Series({pd.Timestamp(d).to_period("M").to_timestamp("M")+pd.offsets.MonthEnd(1): bool(not sig.loc[d,"growth_on"] and sig.loc[d,"inflation_on"]) for d in me})  # 다음 달 수익이 인플레만 칸
R={}
for nm,h,p in (("일반 XLU100",0,0),("일반 XLU50+BIL50",1,0),("연금IC XLU100",0,1),("연금IC XLU50+BIL50",1,1)):
    r=run(h,p); m=r["monthly_ret"]; m.index=m.index.to_period("M").to_timestamp("M"); m=m[m.index<=last]; R[nm]=(r,m)
for k in ("XLU100","XLU50+BIL50"):
    m=R["연금IC "+k][1]; df=pd.concat({"IC":m,"PENT":pent},axis=1).dropna(); R["연금혼합 "+k]=(None,mix(df.IC,df.PENT,0.5))
rows={}
for n,(r,m) in R.items():
    s=stats(m); hot=m[io.reindex(m.index).fillna(False).astype(bool)]
    d={"CAGR":s["CAGR"],"MDD월":s["MDD"],"Vol":s["Vol"],"Calmar":s["Calmar"],"최악월":s["worst"],
       "인플레만달 n":len(hot),"인플레만달 누적":(1+hot).prod()-1,"인플레만달 최악":hot.min()}
    if r is not None: d.update({"MDD일":r["MDD"],"2008MDD":r["2008_MDD"],"2022":r["2022_Ret"]})
    for a,b in (("2008-01","2008-12"),("2022-01","2022-12"),("2003","2016"),("2017","2026")):
        sub=m.loc[a:b]; d[f"{a[:4]}~{b[:4]}"]=(1+sub).prod()**(12/len(sub))-1 if len(sub)>12 else (1+sub).prod()-1
    rows[n]=d
T=pd.DataFrame(rows).T
print(T.drop(columns=["인플레만달 n"]).map(lambda x:f"{x:+.1%}" if pd.notna(x) else "—").to_string())
print("인플레만 달 수:", T["인플레만달 n"].to_dict())
r1,m1=R["일반 XLU100"]; r2,m2=R["일반 XLU50+BIL50"]
hm=io[io].index; d=pd.DataFrame({"XLU100":m1,"half":m2}).reindex(hm).dropna()
print("인플레만 달 월별 (일반):"); print((d*100).round(1).to_string())
