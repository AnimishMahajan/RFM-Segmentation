import sqlite3
import pandas as pd

def create_table(conn):
    ddl_query = """
    CREATE TABLE IF NOT EXISTS customers (
        customer_id INTEGER PRIMARY KEY,
        country TEXT NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS products (
        stock_code TEXT PRIMARY KEY,
        description TEXT
    );
    
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_no TEXT NOT NULL,
        stack_code TEXT,
        quantity INTEGER NOT NULL,
        invoice_date TIMESTAMP NOT NULL,
        unit_priceREAL NOT NULL,
        customer_id INTEGER,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY (stack_code) REFERENCES products(stock_code)
    );
    """

    cursor = conn.cursor()
    cursor.executescript(ddl_query)
    conn.commit()
    cursor.close()

def readFile_and_addData(conn, file_path):
    # cursor = conn.cursor()
    df = pd.read_csv(file_path, encoding="ISO-8859-1")
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=['Customer ID'])

    df_customers = df[['Customer ID', 'Country']].drop_duplicates(subset=['Customer ID']).copy()
    df_customers.columns = ['customer_id', 'country']
    df_customers['customer_id'] = df_customers['customer_id'].astype(int)
    df_customers.to_sql('customers', conn, if_exists='replace', index=False)

    df_products = df[['StockCode', 'Description']].drop_duplicates(subset=['StockCode']).copy()
    df_products.columns = ['stock_code', 'description']
    df_products.to_sql('products', conn, if_exists='replace', index=False)

    df_transactions = df[['Invoice', 'StockCode', 'Quantity', 'InvoiceDate', 'Price', 'Customer ID']].copy()
    df_transactions.columns = ['invoice_no', 'stock_code', 'quantity', 'invoice_date', 'unit_price', 'customer_id']
    df_transactions['customer_id'] = df_transactions['customer_id'].astype(int)
    df_transactions['quantity'] = df_transactions['quantity'].astype(int)
    df_transactions.to_sql('transactions', conn, if_exists='replace', index=False)

    conn.commit()

def rfm_query(conn):
    rmf_query = """
WITH cleaned_transactions AS (
    SELECT
        t.customer_id,
        c.country,
        t.invoice_no,
        t.invoice_date,
        (t.quantity * t.unit_price) AS line_total
    FROM transactions t
    INNER JOIN customers c
    ON t.customer_id = c.customer_id
    WHERE t.invoice_no NOT LIKE 'C%'
        AND t.quantity > 0
),

customer_rfm AS (
    SELECT
        customer_id,
        country,

        -- Recency: Days between last purchase and dataset end date
        CAST(
            julianday((SELECT MAX(invoice_date) FROM transactions)) - julianday(MAX(invoice_date)) 
            AS INTEGER
        ) AS recency_days,

        -- Frequency: Unique invoices placed
        COUNT(DISTINCT invoice_no) AS frequency,
        
        -- Monetary: Total spend
        SUM(line_total) AS monetary_value
    
    FROM cleaned_transactions
    GROUP BY customer_id, country
)

SELECT *
FROM customer_rfm
WHERE monetary_value > 0;
"""
    df_rfm = pd.read_sql(rmf_query, conn)
    return df_rfm

def fetch_customer_segments(conn):
    query = "SELECT * FROM customer_rfm_segments"
    df = pd.read_sql(query, conn)
    return df