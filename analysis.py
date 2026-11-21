"""Reproducible descriptive pipeline. No synthetic data or causal claims."""
from pathlib import Path
import hashlib, json, sqlite3, urllib.request, html, platform
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def run(base=None):
    base = Path(base or Path(__file__).resolve().parent)
    c=json.loads((base/'project.json').read_text()); out=base/'outputs';out.mkdir(exist_ok=True)
    raw=base/'data'/'raw.csv';raw.parent.mkdir(exist_ok=True)
    if not raw.exists():
        with urllib.request.urlopen(c['csv'], timeout=60) as response:
            payload=response.read()
        raw.write_bytes(payload)
    df=pd.read_csv(raw)
    x,y,mode=c['x'],c['y'],c['mode']
    required=[x,y]+(['Survived'] if mode=='survival' else [])+(['pop'] if mode=='fatality' else [])
    absent=set(required)-set(df.columns)
    if absent: raise ValueError(f'Missing required columns: {absent}')
    audit=pd.DataFrame({'dtype':df.dtypes.astype(str),'missing':df.isna().sum(),'missing_pct':100*df.isna().mean(),'distinct':df.nunique()})
    audit.to_csv(out/'quality_audit.csv',index_label='column')
    d=df.copy()
    d[y]=pd.to_numeric(d[y],errors='coerce')
    if mode=='relation': d[x]=pd.to_numeric(d[x],errors='coerce')
    if mode=='time' and x=='date':d[x]=pd.to_datetime(d[x],errors='coerce')
    d=d.dropna(subset=required).copy()
    d=d[np.isfinite(d[y])]
    if mode=='relation':d=d[np.isfinite(d[x])]
    if mode=='fatality':d=d[d['pop']>0]
    # Identical rows may be legitimate repeated experimental measurements; preserve them.
    conn=sqlite3.connect(out/'analysis.sqlite')
    d.to_sql('observations',conn,index=False,if_exists='replace')
    q=(base/'analysis.sql').read_text()
    table=pd.read_sql_query(q,conn);conn.close()
    if table.empty:raise ValueError('No usable records')
    table.to_csv(out/'answer.csv',index=False)
    numeric=d.select_dtypes(include='number').drop(columns=['rownames'],errors='ignore')
    numeric.describe().to_csv(out/'numeric_summary.csv')
    fig,ax=plt.subplots(figsize=(10,5))
    plt.rcParams.update({'font.size':10})
    stats={}
    if mode=='relation':
        ax.scatter(d[x],d[y],s=16,alpha=.45)
        pearson=float(d[[x,y]].corr().iloc[0,1]);spearman=float(d[[x,y]].corr(method='spearman').iloc[0,1])
        stats={'pearson':pearson,'spearman':spearman}
        finding=f'Among {len(d):,} complete observations, Pearson r = {pearson:.3f} and Spearman rho = {spearman:.3f}.'
    elif mode=='time':
        ax.plot(table['segment'],table['metric'])
        if len(table)>15:ax.set_xticks(table['segment'].iloc[::max(1,len(table)//8)])
        finding=f'The first recorded mean is {table.metric.iloc[0]:,.3f}; the last is {table.metric.iloc[-1]:,.3f}. The recorded period, rather than today, defines this comparison.'
    else:
        shown=table.sort_values('metric',ascending=False).head(15)
        ax.barh(shown['segment'].astype(str),shown.metric);ax.invert_yaxis()
        top=shown.iloc[0]
        finding=f'The largest observed {c["metric_label"]} is {top.metric:,.3f} for {top.segment}. This ranking is descriptive, not a recommendation.'
        ax.set_ylabel(x);ax.set_xlabel(c['metric_label'])
    if mode in ('time','relation'): ax.set_xlabel(x);ax.set_ylabel(c['metric_label'])
    ax.set_title(c['title']);fig.tight_layout();fig.savefig(out/'main_chart.png',dpi=160);plt.close(fig)
    # Distribution reveals skew and outliers rather than silently removing them.
    fig,ax=plt.subplots(figsize=(9,4));ax.hist(d[y],bins=30,color='#2563a6');ax.set(xlabel=y,ylabel='Rows (not weighted people)',title='Distribution of '+y);fig.tight_layout();fig.savefig(out/'distribution.png',dpi=140);plt.close(fig)
    manifest={'project':c['title'],'executed_utc':datetime.now(timezone.utc).isoformat(),'source':c['csv'],'documentation':c['doc'],'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'raw_rows':len(df),'analysis_rows':len(d),'excluded_rows':len(df)-len(d),'exact_duplicate_rows':int(df.duplicated().sum()),'duplicates_policy':'Retained; duplicate values do not necessarily mean duplicate entities.','python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,'matplotlib':matplotlib.__version__,**stats}
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2))
    report=f"# {c['title']} — executed results\n\n## Decision question\n{c['question']}\n\n## Evidence\n{finding}\n\nRaw rows: {len(df):,}. Rows used: {len(d):,}. Excluded for missing/nonfinite required values or invalid denominator: {len(df)-len(d):,}.\n\n## Method\n{c['method']}\n\n![Primary chart](main_chart.png)\n\n## Interpretation and limitations\n{c['caveat']} No causal inference, significance claim or production deployment is implied. Missing values are not imputed; identical rows are retained. Small or repeated samples limit uncertainty interpretation.\n\n## Recommended next decision\n{c['action']}\n\n## Reproducibility\nSource and exact downloaded-byte SHA256 are recorded in run_manifest.json. SQL results are in answer.csv and analysis.sqlite. Review quality_audit.csv before interpretation.\n"
    (out/'REPORT.md').write_text(report)
    body='<html><head><meta charset="utf-8"><title>'+html.escape(c['title'])+'</title><style>body{font:17px system-ui;max-width:1100px;margin:40px auto;padding:20px;color:#182d41}img{max-width:100%}td,th{padding:8px;border-bottom:1px solid #ddd}</style></head><body>'
    body+='<h1>'+html.escape(c['title'])+'</h1><p>'+html.escape(c['question'])+'</p><p>'+html.escape(finding)+'</p><img src="main_chart.png"><h2>SQL evidence</h2>'+table.head(50).to_html(index=False)+'<h2>Limitations</h2><p>'+html.escape(c['caveat'])+'</p><h2>Next action</h2><p>'+html.escape(c['action'])+'</p></body></html>'
    (out/'dashboard.html').write_text(body)
    return {'manifest':manifest,'finding':finding,'table':table}
if __name__=='__main__':
    result=run();print(result['finding'])
