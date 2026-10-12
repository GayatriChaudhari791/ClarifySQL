
import sqlite3
from pathlib import Path

# Create the data folder if it doesn't exist
Path("data").mkdir(exist_ok=True)

# Connect to the database
conn = sqlite3.connect("data/sales.db")
cursor = conn.cursor()

# Create tables
cursor.executescript("""
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
    sale_id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    sale_date TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
""")

# Insert sample data only when tables are empty
if cursor.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
    cursor.executemany(
        "INSERT INTO customers VALUES (?, ?, ?)",
        [
            (1, "Aarav", "Pune"),
            (2, "Ananya", "Mumbai"),
            (3, "Rohan", "Sangli"),
            (4, "Meera", "Pune"),
            (5, "Ishaan", "Mumbai"),
        ],
    )

if cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
    cursor.executemany(
        "INSERT INTO products VALUES (?, ?, ?, ?)",
        [
            (1, "Laptop", "Electronics", 55000),
            (2, "Headphones", "Electronics", 2000),
            (3, "Office Chair", "Furniture", 8000),
            (4, "Desk", "Furniture", 12000),
            (5, "Keyboard", "Accessories", 1500),
        ],
    )

if cursor.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0:
    cursor.executemany(
        "INSERT INTO sales VALUES (?, ?, ?, ?, ?)",
        [
            (1, 1, 1, 2, "2026-01-10"),
            (2, 2, 2, 5, "2026-01-15"),
            (3, 3, 3, 3, "2026-02-01"),
            (4, 1, 4, 1, "2026-02-10"),
            (5, 4, 5, 2, "2026-02-15"),
            (6, 5, 1, 10, "2026-03-01"),
            (7, 2, 3, 4, "2026-03-05"),
            (8, 3, 2, 2, "2026-03-10"),
            (9, 1, 5, 1, "2026-03-15"),
            (10, 4, 4, 1, "2026-03-20"),
        ],
    )

conn.commit()
conn.close()

print("Success! ClarifySQL sales database is ready.")
