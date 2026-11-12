from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from src import sql_handler, analysis

db_path = Path('ecommerce.db')
file_path = Path('data/online_retail_II.csv')
html_file_path = Path(__file__).parent / 'index.html'

def get_db_connection():
    return sqlite3.connect(db_path)

def ensure_data_initialized():
    """Ensure database tables and customer segments are prepared."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='customer_rfm_segments'")
        exists = cursor.fetchone()[0] > 0
        if exists:
            cursor.execute("SELECT count(*) FROM customer_rfm_segments")
            if cursor.fetchone()[0] > 0:
                return
    finally:
        conn.close()

    # Recreate and populate if missing
    conn = get_db_connection()
    try:
        sql_handler.create_table(conn)
        if file_path.exists():
            sql_handler.readFile_and_addData(conn, file_path)
        analysis.segment_customers(conn)
    finally:
        conn.close()

def compute_dashboard_payload():
    """Compute KPIs, segment summary, and geographic breakdown from database."""
    conn = get_db_connection()
    try:
        df = sql_handler.fetch_customer_segments(conn)
        if df.empty:
            raise ValueError("No customer segment data available in database.")
        
        kpis = analysis.caculate_executive_kpis(df)
        segment_summary = analysis.get_segment_summary(df)
        geo_df = analysis.get_geographic_breakdown(df)

        # Convert DataFrames to JSON-serializable list of dicts
        segment_summary_records = segment_summary.reset_index().to_dict(orient="records")
        geo_records = geo_df.to_dict(orient="records")

        return {
            "kpis": kpis,
            "segment_summary": segment_summary_records,
            "geo_data": geo_records
        }
    finally:
        conn.close()

def reload_and_recompute_all():
    """Rescans CSV file, updates database tables, runs KMeans segmentation, and computes fresh payload."""
    if not file_path.exists():
        raise FileNotFoundError(f"Data file '{file_path}' not found.")

    conn = get_db_connection()
    try:
        sql_handler.create_table(conn)
        sql_handler.readFile_and_addData(conn, file_path)
        analysis.segment_customers(conn)
    finally:
        conn.close()

    return compute_dashboard_payload()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure database tables & segmentation data are ready
    ensure_data_initialized()
    yield

app = FastAPI(
    title="Customer RFM Segmentation Dashboard",
    description="Executive dashboard displaying KPIs, customer segments, and geological breakdown.",
    lifespan=lifespan
)

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """Serve the dashboard HTML webpage directly without Jinja2."""
    if not html_file_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard index.html file not found.")
    
    with open(html_file_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/api/data")
def get_dashboard_data():
    """API endpoint providing KPIs, segment summary, and geological breakdown."""
    try:
        payload = compute_dashboard_payload()
        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.api_route("/api/refresh", methods=["GET", "POST"])
def refresh_dashboard_data():
    """Rescans the CSV file, re-populates the database, recalculates RFM clusters, and returns updated metrics."""
    try:
        payload = reload_and_recompute_all()
        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh data from CSV: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("  RFM Customer Segmentation Dashboard is running!")
    print("  Access the dashboard at: http://127.0.0.1:8000")
    print("="*60 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
