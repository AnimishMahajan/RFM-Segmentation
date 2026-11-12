import pandas as pd
import numpy as np
import sqlite3
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

from src.sql_handler import rfm_query

def assign_personas(df_rfm: pd.DataFrame, conn):
    cluster_summary = df_rfm.groupby('cluster')[['recency_days', 'frequency', 'monetary_value']].mean()
    sorted_monetary = cluster_summary.sort_values(by='monetary_value', ascending=False).index.to_list()
    sorted_recency = cluster_summary.sort_values(by="recency_days", ascending=False).index.to_list()

    persona_map = {}

    champion_cluster = sorted_monetary[0] if sorted_monetary[0] == sorted_recency[0] else sorted_monetary[0]
    persona_map[champion_cluster] = 'Champions'

    lost_cluster = cluster_summary['recency_days'].idxmax()
    persona_map[lost_cluster] = 'Lost Customers'
    
    # Remaining clusters
    remaining = [c for c in cluster_summary.index if c not in persona_map]
    
    # Sort remaining by recency or frequency to distinguish At-Risk vs Potential Loyalists
    for c in remaining:
        if cluster_summary.loc[c, 'recency_days'] > cluster_summary['recency_days'].mean():
            persona_map[c] = 'At-Risk'
        else:
            persona_map[c] = 'Potential Loyalists'

    df_rfm['segment'] = df_rfm['cluster'].map(persona_map)
    cluster_summary = df_rfm.groupby(['cluster', 'segment'])[['recency_days', 'frequency', 'monetary_value']].mean()
    return cluster_summary, df_rfm
    
def segment_customers(conn):
    df_rfm = rfm_query(conn)

    rfm_logs = pd.DataFrame()
    rfm_logs['recency'] = np.log1p(df_rfm['recency_days'])
    rfm_logs['frequency'] = np.log1p(df_rfm['frequency'])
    rfm_logs['monetary'] = np.log1p(df_rfm['monetary_value'])

    scaler = StandardScaler()
    rfm_scaled = scaler.fit_transform(rfm_logs)

    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
    df_rfm['cluster'] = kmeans.fit_predict(rfm_scaled)

    # print(df_rfm.columns)
    cluster_summery, df_rfm = assign_personas(df_rfm, conn)

    df_rfm.to_sql('customer_rfm_segments', conn, if_exists='replace', index=False)

def caculate_executive_kpis(df):
    """
    return a dictionary of core financial and customer metrics
    """
    total_customers = len(df)
    total_revenue = df['monetary_value'].sum()
    total_orders = df['frequency'].sum()
    aov = total_revenue / total_orders if total_orders > 0 else 0

    at_risk_count = len(df[df['segment'].isin(["At-Risk", "Lost Customers", "Lost Customer"])])
    churn_risk_pct = (at_risk_count / total_customers) * 100 if total_customers > 0 else 0

    return {
        "total_customers": int(total_customers),
        "total_revenue": float(total_revenue),
        "average_order_value": float(aov),
        "churn_risk_percentage": float(churn_risk_pct)
    }

def get_segment_summary(df):
    """
    Returns a DataFrame summarizing counts, revenue, and averages per segment.
    """
    summary = (
        df.groupby('segment')
        .agg(
            customer_count=('customer_id', 'count'),
            total_revenue=('monetary_value', 'sum'),
            avg_recency=('recency_days', 'mean'),
            avg_frequency=('frequency', 'mean'),
            avg_monetary=('monetary_value', 'mean')
        )
    )

    return summary

def get_geographic_breakdown(df, top_n=10):
    """
    Returns a DataFrame of revenue and customer counts for the top N countries 
    segmented by persona.
    """
    top_countries = (
        df.groupby("country")["monetary_value"]
        .sum()
        .nlargest(top_n)
        .index.tolist()
    )

    geo_df = (
        df[df["country"].isin(top_countries)]
        .groupby(["country", "segment"])
        .agg(
            revenue=("monetary_value", "sum"), 
            customers=("customer_id", "count")
        )
        .reset_index()
    )
    
    return geo_df
