from pathlib import Path
import pandas as pd
import numpy as np
from typing import Dict

def analyze_dataset(file_path: Path) -> Dict:
    df = pd.read_csv(file_path)
    overview = {
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": df.columns.tolist(),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
    }
    missing = df.isnull().sum().to_dict()
    missing_pct = {k: round(v/len(df)*100,2) for k,v in missing.items() if v>0}
    stats = {}
    try:
        desc = df.describe(include='all', datetime_is_numeric=True).replace({np.nan: None}).to_dict()
        # clean for json
        for col in desc:
            for stat in list(desc[col].keys()):
                val = desc[col][stat]
                if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
                    desc[col][stat]=None
        stats = desc
    except Exception as e:
        stats = {"error": str(e)}

    # distributions: simple hist counts for numeric
    distributions = {}
    for col in df.select_dtypes(include=[np.number]).columns[:5]:
        try:
            hist, bins = np.histogram(df[col].dropna(), bins=5)
            distributions[col]= {"hist": hist.tolist(), "bins": bins.tolist()}
        except: pass

    # correlations
    corr = {}
    num_df = df.select_dtypes(include=[np.number])
    if len(num_df.columns)>=2:
        try:
            c = num_df.corr(numeric_only=True).replace({np.nan: None}).round(3).to_dict()
            # find strongest
            corr = c
        except Exception as e:
            corr = {"error": str(e)}

    # anomalies: z-score outliers
    anomalies = []
    for col in num_df.columns[:5]:
        try:
            vals = num_df[col].dropna()
            if len(vals)<3: continue
            mean = vals.mean()
            std = vals.std()
            if std==0: continue
            outliers = vals[(np.abs(vals-mean) > 3*std)]
            if len(outliers)>0:
                anomalies.append({"column": col, "outlier_count": len(outliers), "outlier_values": outliers.head(5).tolist(), "mean": float(mean), "std": float(std)})
        except: pass

    # distinguish observation vs interpretation: we provide both sections
    observed = []
    if corr:
        for a in num_df.columns:
            for b in num_df.columns:
                if a>=b: continue
                try:
                    val = corr.get(a,{}).get(b)
                    if val is not None and abs(val)>0.5:
                        observed.append(f"Observed: {a} and {b} are correlated with r={val} (does not imply causation) [SOURCE - statistical result]")
                except: pass
    if missing_pct:
        observed.append(f"Observed: Missing values present in {missing_pct} [SOURCE]")
    if anomalies:
        for an in anomalies:
            observed.append(f"Observed: Column {an['column']} has {an['outlier_count']} outliers beyond 3σ [SOURCE]")

    interpretation = [
        "Interpretation: Correlation does not establish causation; confounding variables may exist. [GENERATED]",
        "Interpretation: Outliers may indicate measurement error or genuine extreme conditions; visual inspection recommended. [GENERATED]",
        "Suggested visualizations: histogram for each numeric column, scatter matrix, correlation heatmap. [GENERATED]"
    ]

    research_questions = [
        "What physical mechanism could explain the observed correlation (if any) ?",
        "Are outliers due to experimental error or interesting edge cases?",
        "What additional variables, if collected, would help establish causality?"
    ]

    return {
        "overview": overview,
        "missing_values": missing,
        "missing_percentage": missing_pct,
        "statistics": stats,
        "distributions": distributions,
        "correlations": corr,
        "anomalies": anomalies,
        "observed_results": observed,  # strictly statistical
        "ai_interpretation": interpretation,  # labeled generated
        "suggested_visualizations": ["histogram", "scatter", "boxplot", "correlation heatmap"],
        "research_questions": research_questions,
        "sample_rows": df.head(5).replace({np.nan: None}).to_dict(orient="records")
    }
