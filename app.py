import io
import json
import secrets
from datetime import date, datetime
from urllib.parse import quote

import pandas as pd
import streamlit as st
from sqlalchemy import (
    create_engine, text, MetaData, Table, Column, String, Integer, Float,
    Date, DateTime, ForeignKey, select, update, insert, delete, func
)
from sqlalchemy.exc import SQLAlchemyError

st.set_page_config(
    page_title="Smart Clothes House — Gents",
    page_icon="🧥",
    layout="wide",
    initial_sidebar_state="expanded",
)

SHOP_NAME = "Smart Clothes House — Gents"
CATEGORIES = ["Shalwar Kameez", "Kurta", "Waistcoat", "Pant Coat", "Shirt", "Trouser", "Other"]
SIZES = ["S", "M", "L", "XL", "XXL", "Custom", "Free Size"]
PAYMENT_METHODS = ["Cash", "Bank transfer", "Easypaisa/JazzCash", "Other"]
EXPENSE_CATEGORIES = ["Rent", "Electricity", "Transport", "Staff", "Packaging", "Repairs", "Internet/Phone", "Other"]

def now():
    return datetime.now()

def new_id(prefix):
    return f"{prefix}-{now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3).upper()}"

def pkr(value):
    return f"Rs. {float(value or 0):,.2f}"

def phone_digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())

def whatsapp_url(phone, message):
    digits = phone_digits(phone)
    return f"https://wa.me/{digits}?text={quote(message)}" if digits else None

def require_secrets():
    if "auth" not in st.secrets or not st.secrets["auth"].get("password"):
        st.error("Set [auth] password in Streamlit Cloud → App settings → Secrets.")
        st.stop()
    if not st.secrets.get("database_url"):
        st.error("Set database_url in Streamlit Secrets. See README for setup.")
        st.stop()

def db_engine():
    url = str(st.secrets["database_url"])
    # SQLAlchemy's PostgreSQL driver is installed by requirements.txt.
    return create_engine(url, pool_pre_ping=True, future=True)

def create_schema(engine):
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS products (
            sku VARCHAR(80) PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            category VARCHAR(80) NOT NULL,
            size VARCHAR(40) NOT NULL,
            color VARCHAR(80) NOT NULL DEFAULT '',
            buy_price NUMERIC(12,2) NOT NULL CHECK (buy_price >= 0),
            sell_price NUMERIC(12,2) NOT NULL CHECK (sell_price >= 0),
            stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
            low_stock INTEGER NOT NULL DEFAULT 2 CHECK (low_stock >= 0),
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS customers (
            customer_id VARCHAR(80) PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            phone VARCHAR(60) NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sales (
            bill_no VARCHAR(100) PRIMARY KEY,
            sold_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            customer_id VARCHAR(80) REFERENCES customers(customer_id),
            customer_name VARCHAR(200) NOT NULL,
            phone VARCHAR(60) NOT NULL DEFAULT '',
            subtotal NUMERIC(12,2) NOT NULL,
            discount NUMERIC(12,2) NOT NULL DEFAULT 0,
            total NUMERIC(12,2) NOT NULL,
            cost NUMERIC(12,2) NOT NULL,
            paid NUMERIC(12,2) NOT NULL DEFAULT 0,
            balance NUMERIC(12,2) NOT NULL DEFAULT 0,
            payment_method VARCHAR(60) NOT NULL,
            status VARCHAR(40) NOT NULL DEFAULT 'Unpaid',
            voided BOOLEAN NOT NULL DEFAULT FALSE
        );
        CREATE TABLE IF NOT EXISTS sale_items (
            item_id VARCHAR(100) PRIMARY KEY,
            bill_no VARCHAR(100) NOT NULL REFERENCES sales(bill_no),
            sku VARCHAR(80) NOT NULL,
            item_name VARCHAR(200) NOT NULL,
            size VARCHAR(40) NOT NULL,
            color VARCHAR(80) NOT NULL DEFAULT '',
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            unit_price NUMERIC(12,2) NOT NULL,
            unit_cost NUMERIC(12,2) NOT NULL,
            line_total NUMERIC(12,2) NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payments (
            payment_id VARCHAR(100) PRIMARY KEY,
            paid_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            customer_id VARCHAR(80) REFERENCES customers(customer_id),
            bill_no VARCHAR(100) REFERENCES sales(bill_no),
            customer_name VARCHAR(200) NOT NULL,
            amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
            method VARCHAR(60) NOT NULL,
            note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS expenses (
            expense_id VARCHAR(100) PRIMARY KEY,
            expense_date DATE NOT NULL,
            category VARCHAR(80) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
            method VARCHAR(60) NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stock_movements (
            movement_id VARCHAR(100) PRIMARY KEY,
            moved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sku VARCHAR(80) NOT NULL,
            item_name VARCHAR(200) NOT NULL,
            change_qty INTEGER NOT NULL,
            reason VARCHAR(120) NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            reference VARCHAR(100) NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales(sold_at);
        CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales(customer_id);
        CREATE INDEX IF NOT EXISTS idx_payments_bill ON payments(bill_no);
        CREATE INDEX IF NOT EXISTS idx_movements_sku ON stock_movements(sku);
        """))

def query_df(engine, sql, params=None):
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})

def one(engine, sql, params=None):
    with engine.connect() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
        return dict(row) if row else None

def login():
    if st.session_state.get("logged_in"):
        return
    st.title("🔒 Smart Clothes House — Owner Login")
    st.caption("Private shop management")
    with st.form("login"):
        password = st.text_input("Owner password", type="password")
        submit = st.form_submit_button("Log in", type="primary")
    if submit:
        expected = str(st.secrets["auth"]["password"])
        if secrets.compare_digest(password, expected):
            st.session_state["logged_in"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

require_secrets()
login()
try:
    engine = db_engine()
    create_schema(engine)
except Exception as exc:
    st.error("Could not connect to the database. Check your database URL and provider settings.")
    st.code(str(exc))
    st.stop()

with st.sidebar:
    st.title("🧥 Smart Clothes House")
    page = st.radio("Navigation", [
        "Dashboard", "Inventory", "New Sale / Bill", "Sales History",
        "Khata / Customer Ledger", "Record Repayment", "Expenses",
        "Stock Adjustment", "Reports & Backups",
    ])
    st.caption("Currency: Pakistani Rupees (PKR)")
    if st.button("Log out", use_container_width=True):
        st.session_state["logged_in"] = False
        st.rerun()

st.title(SHOP_NAME)
st.caption(f"Owner dashboard · {date.today().isoformat()}")

def products_df(active_only=False):
    where = "WHERE active = TRUE" if active_only else ""
    return query_df(engine, f"""
        SELECT sku, name, category, size, color, buy_price, sell_price,
               stock, low_stock, active, updated_at
        FROM products {where} ORDER BY name, size, color
    """)

def save_stock_movement(conn, sku, name, qty, reason, note="", reference=""):
    conn.execute(text("""
        INSERT INTO stock_movements
        (movement_id, sku, item_name, change_qty, reason, note, reference)
        VALUES (:id, :sku, :name, :qty, :reason, :note, :ref)
    """), {"id": new_id("MOV"), "sku": sku, "name": name, "qty": int(qty),
           "reason": reason, "note": note, "ref": reference})

def ensure_customer(conn, name, phone, address=""):
    phone = str(phone or "").strip()
    if phone:
        found = conn.execute(text(
            "SELECT customer_id FROM customers WHERE phone=:phone ORDER BY created_at LIMIT 1"
        ), {"phone": phone}).first()
        if found:
            return found[0]
    cid = new_id("CUS")
    conn.execute(text("""
        INSERT INTO customers (customer_id, name, phone, address)
        VALUES (:id, :name, :phone, :address)
    """), {"id": cid, "name": name.strip() or "Walk-in Customer",
           "phone": phone, "address": address})
    return cid

def invoice_text(sale, items):
    lines = [
        SHOP_NAME, "=" * 34, f"Invoice: {sale['bill_no']}",
        f"Date: {str(sale['sold_at'])[:19]}",
        f"Customer: {sale['customer_name']}", f"Phone: {sale['phone'] or '-'}", "-" * 34
    ]
    for item in items:
        lines.append(f"{item['item_name']} / {item['size']} / {item['color']}")
        lines.append(f"{item['quantity']} x {pkr(item['unit_price'])} = {pkr(item['line_total'])}")
    lines += [
        "-" * 34, f"Subtotal: {pkr(sale['subtotal'])}",
        f"Discount: {pkr(sale['discount'])}", f"TOTAL: {pkr(sale['total'])}",
        f"Paid: {pkr(sale['paid'])}", f"Balance: {pkr(sale['balance'])}",
        f"Payment: {sale['payment_method']}", "", "Thank you for shopping with us!"
    ]
    return "\n".join(lines)

# Dashboard
if page == "Dashboard":
    today_sales = query_df(engine, """
        SELECT * FROM sales WHERE sold_at::date = CURRENT_DATE AND voided=FALSE
    """)
    today_expenses = query_df(engine, "SELECT * FROM expenses WHERE expense_date=CURRENT_DATE")
    revenue = float(today_sales["total"].sum()) if not today_sales.empty else 0
    collected = float(today_sales["paid"].sum()) if not today_sales.empty else 0
    gross = float((today_sales["total"] - today_sales["cost"]).sum()) if not today_sales.empty else 0
    expense_total = float(today_expenses["amount"].sum()) if not today_expenses.empty else 0
    inv = products_df()
    stock_value = float((inv["buy_price"] * inv["stock"]).sum()) if not inv.empty else 0
    due = one(engine, "SELECT COALESCE(SUM(balance),0) AS due FROM sales WHERE voided=FALSE")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Today's sales", pkr(revenue))
    c2.metric("Received on today's bills", pkr(collected))
    c3.metric("Today's gross profit", pkr(gross))
    c4.metric("Today's expenses", pkr(expense_total))
    c1,c2,c3 = st.columns(3)
    c1.metric("Stock at purchase cost", pkr(stock_value))
    c2.metric("Outstanding Khata", pkr(due["due"] if due else 0))
    c3.metric("Estimated profit after recorded expenses today", pkr(gross-expense_total))
    st.subheader("Low-stock alerts")
    if inv.empty:
        st.info("Add your first product in Inventory.")
    else:
        low = inv[(inv["stock"] <= inv["low_stock"]) & (inv["active"] == True)]
        if low.empty:
            st.success("No low-stock products.")
        else:
            st.dataframe(low, use_container_width=True, hide_index=True)
    st.caption("Profit estimates exclude unrecorded costs, taxes, returns, and accounting adjustments.")

# Inventory
elif page == "Inventory":
    st.subheader("Add a product / receive stock")
    with st.form("product_form", clear_on_submit=True):
        sku = st.text_input("Unique SKU / product code").strip().upper()
        name = st.text_input("Product name", placeholder="e.g. Wash-and-wear shalwar kameez")
        col1, col2, col3 = st.columns(3)
        category = col1.selectbox("Category", CATEGORIES)
        size = col2.selectbox("Size", SIZES)
        color = col3.text_input("Color", "Not specified")
        col1, col2, col3, col4 = st.columns(4)
        buy = col1.number_input("Purchase price / unit", min_value=0.0, step=100.0)
        sell = col2.number_input("Selling price / unit", min_value=0.0, step=100.0)
        qty = col3.number_input("Quantity received", min_value=0, step=1)
        low = col4.number_input("Low-stock alert at", min_value=0, value=2, step=1)
        submit = st.form_submit_button("Save product / receive stock", type="primary")
    if submit:
        if not sku or not name:
            st.error("SKU and product name are required.")
        else:
            try:
                with engine.begin() as conn:
                    found = conn.execute(text("SELECT * FROM products WHERE sku=:sku FOR UPDATE"), {"sku": sku}).mappings().first()
                    if found:
                        conn.execute(text("""
                            UPDATE products SET name=:name, category=:category, size=:size,
                            color=:color, buy_price=:buy, sell_price=:sell,
                            stock=stock+:qty, low_stock=:low, active=TRUE,
                            updated_at=CURRENT_TIMESTAMP WHERE sku=:sku
                        """), {"name":name,"category":category,"size":size,"color":color,
                               "buy":buy,"sell":sell,"qty":int(qty),"low":int(low),"sku":sku})
                    else:
                        conn.execute(text("""
                            INSERT INTO products (sku,name,category,size,color,buy_price,sell_price,stock,low_stock)
                            VALUES (:sku,:name,:category,:size,:color,:buy,:sell,:qty,:low)
                        """), {"sku":sku,"name":name,"category":category,"size":size,"color":color,
                               "buy":buy,"sell":sell,"qty":int(qty),"low":int(low)})
                    if qty:
                        save_stock_movement(conn, sku, name, int(qty), "Stock received")
                st.success("Product and stock saved.")
            except SQLAlchemyError as exc:
                st.error("Could not save product. Check that the SKU is unique and the database is available.")
                st.code(str(exc))
    inv = products_df()
    st.subheader("Current stock")
    if inv.empty:
        st.info("No products added yet.")
    else:
        st.dataframe(inv, use_container_width=True, hide_index=True)
        csv = inv.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download inventory CSV", csv, "inventory.csv", "text/csv")
        st.markdown("**Edit product details:** choose a SKU below to update prices or deactivate it.")
        sku_options = inv["sku"].tolist()
        chosen_sku = st.selectbox("Product SKU", sku_options)
        pr = inv[inv["sku"] == chosen_sku].iloc[0]
        with st.form("edit_product"):
            new_buy = st.number_input("Purchase price", min_value=0.0, value=float(pr["buy_price"]), step=100.0)
            new_sell = st.number_input("Selling price", min_value=0.0, value=float(pr["sell_price"]), step=100.0)
            new_low = st.number_input("Low-stock threshold", min_value=0, value=int(pr["low_stock"]), step=1)
            active = st.checkbox("Product is active for sale", value=bool(pr["active"]))
            edit = st.form_submit_button("Update product")
        if edit:
            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE products SET buy_price=:buy, sell_price=:sell,
                    low_stock=:low, active=:active, updated_at=CURRENT_TIMESTAMP
                    WHERE sku=:sku
                """), {"buy":new_buy,"sell":new_sell,"low":int(new_low),"active":active,"sku":chosen_sku})
            st.success("Product updated.")

# New sale
elif page == "New Sale / Bill":
    st.subheader("Create a multi-item invoice")
    inv = products_df(active_only=True)
    inv = inv[inv["stock"] > 0] if not inv.empty else inv
    if inv.empty:
        st.warning("No available stock. Add products first.")
    else:
        if "cart" not in st.session_state:
            st.session_state.cart = []
        sku_to_product = {str(r["sku"]): r.to_dict() for _, r in inv.iterrows()}
        with st.form("cart_add"):
            sku = st.selectbox("Product", list(sku_to_product), format_func=lambda x: f"{x} — {sku_to_product[x]['name']} ({sku_to_product[x]['size']}, {sku_to_product[x]['color']}) · Stock {int(sku_to_product[x]['stock'])}")
            prod = sku_to_product[sku]
            quantity = st.number_input("Quantity", min_value=1, max_value=int(prod["stock"]), value=1, step=1)
            price = st.number_input("Selling price per unit", min_value=0.0, value=float(prod["sell_price"]), step=100.0)
            add = st.form_submit_button("Add item to bill")
        if add:
            existing_idx = next((i for i,x in enumerate(st.session_state.cart) if x["sku"] == sku), None)
            if existing_idx is not None:
                st.warning("This SKU is already in the cart. Remove it first if you want to change its quantity or price.")
            else:
                st.session_state.cart.append({
                    "sku": sku, "name": prod["name"], "size": prod["size"], "color": prod["color"],
                    "quantity": int(quantity), "unit_price": float(price), "unit_cost": float(prod["buy_price"]),
                    "available": int(prod["stock"]), "line_total": int(quantity)*float(price)
                })
                st.rerun()
        if st.session_state.cart:
            cart_df = pd.DataFrame(st.session_state.cart)
            st.dataframe(cart_df[["sku","name","size","color","quantity","unit_price","line_total"]], use_container_width=True, hide_index=True)
            if st.button("Clear bill items"):
                st.session_state.cart = []
                st.rerun()
            subtotal = sum(x["line_total"] for x in st.session_state.cart)
            st.metric("Subtotal", pkr(subtotal))
            with st.form("checkout"):
                customer_name = st.text_input("Customer name", "Walk-in Customer")
                phone = st.text_input("Phone (include country code for WhatsApp)")
                address = st.text_input("Address (optional)")
                discount = st.number_input("Discount (Rs.)", min_value=0.0, max_value=float(subtotal), value=0.0, step=100.0)
                total = subtotal - discount
                st.write(f"**Bill total: {pkr(total)}**")
                paid = st.number_input("Amount received now (Rs.)", min_value=0.0, max_value=float(total), value=float(total), step=100.0)
                method = st.selectbox("Payment method", PAYMENT_METHODS)
                confirm = st.checkbox("I checked the items, prices, discount, and amount received.")
                create_bill = st.form_submit_button("Confirm and save sale", type="primary")
            if create_bill:
                if not confirm:
                    st.error("Confirm the bill details before saving.")
                else:
                    bill_no = new_id("BILL")
                    try:
                        with engine.begin() as conn:
                            customer_id = ensure_customer(conn, customer_name, phone, address)
                            # Lock and validate each SKU to prevent overselling in concurrent sessions.
                            for item in st.session_state.cart:
                                current = conn.execute(text("SELECT stock, name, size, color, buy_price FROM products WHERE sku=:sku FOR UPDATE"), {"sku":item["sku"]}).mappings().first()
                                if not current or int(current["stock"]) < item["quantity"]:
                                    raise ValueError(f"Insufficient stock for SKU {item['sku']}. Refresh inventory and retry.")
                            cost_total = sum(x["quantity"] * x["unit_cost"] for x in st.session_state.cart)
                            conn.execute(text("""
                                INSERT INTO sales
                                (bill_no,customer_id,customer_name,phone,subtotal,discount,total,cost,paid,balance,payment_method,status)
                                VALUES (:bill,:cid,:name,:phone,:subtotal,:discount,:total,:cost,:paid,:balance,:method,:status)
                            """), {"bill":bill_no,"cid":customer_id,"name":customer_name.strip() or "Walk-in Customer",
                                   "phone":phone,"subtotal":subtotal,"discount":discount,"total":total,"cost":cost_total,
                                   "paid":paid,"balance":total-paid,"method":method,
                                   "status":"Paid" if total-paid < 0.005 else ("Partially paid" if paid > 0 else "Unpaid")})
                            for item in st.session_state.cart:
                                conn.execute(text("""
                                    INSERT INTO sale_items
                                    (item_id,bill_no,sku,item_name,size,color,quantity,unit_price,unit_cost,line_total)
                                    VALUES (:id,:bill,:sku,:name,:size,:color,:qty,:price,:cost,:line)
                                """), {"id":new_id("ITEM"),"bill":bill_no,"sku":item["sku"],"name":item["name"],
                                       "size":item["size"],"color":item["color"],"qty":item["quantity"],
                                       "price":item["unit_price"],"cost":item["unit_cost"],"line":item["line_total"]})
                                conn.execute(text("UPDATE products SET stock=stock-:qty, updated_at=CURRENT_TIMESTAMP WHERE sku=:sku"),
                                             {"qty":item["quantity"],"sku":item["sku"]})
                                save_stock_movement(conn,item["sku"],item["name"],-item["quantity"],"Sale",reference=bill_no)
                            if paid > 0:
                                conn.execute(text("""
                                    INSERT INTO payments (payment_id,customer_id,bill_no,customer_name,amount,method,note)
                                    VALUES (:id,:cid,:bill,:name,:amount,:method,:note)
                                """), {"id":new_id("PAY"),"cid":customer_id,"bill":bill_no,
                                       "name":customer_name.strip() or "Walk-in Customer","amount":paid,
                                       "method":method,"note":"Payment at sale"})
                        st.session_state.last_bill = bill_no
                        st.session_state.last_cart = list(st.session_state.cart)
                        st.session_state.cart = []
                        st.success(f"Sale saved. Invoice: {bill_no}")
                        st.rerun()
                    except Exception as exc:
                        st.error("Sale was not completed. No partial sale should be committed; check the error and retry.")
                        st.code(str(exc))
        last_bill = st.session_state.get("last_bill")
        if last_bill:
            sale = one(engine, "SELECT * FROM sales WHERE bill_no=:bill", {"bill":last_bill})
            items = query_df(engine, "SELECT * FROM sale_items WHERE bill_no=:bill ORDER BY item_id", {"bill":last_bill}).to_dict("records")
            if sale:
                invoice = invoice_text(sale, items)
                st.subheader("Latest invoice")
                st.code(invoice)
                st.download_button("Download invoice", invoice.encode("utf-8"), f"{last_bill}.txt", "text/plain")
                link = whatsapp_url(sale["phone"], invoice)
                if link:
                    st.link_button("Share invoice via WhatsApp", link)

# Sales history
elif page == "Sales History":
    st.subheader("Invoice history")
    c1,c2 = st.columns(2)
    start = c1.date_input("From", date.today().replace(day=1), key="sales_from")
    end = c2.date_input("To", date.today(), key="sales_to")
    df = query_df(engine, """
        SELECT bill_no, sold_at, customer_name, phone, subtotal, discount, total,
               cost, paid, balance, payment_method, status
        FROM sales WHERE sold_at::date >= :start AND sold_at::date <= :end
        AND voided=FALSE ORDER BY sold_at DESC
    """, {"start":start,"end":end})
    st.dataframe(df, use_container_width=True, hide_index=True)
    if not df.empty:
        st.download_button("Download filtered sales CSV", df.to_csv(index=False).encode("utf-8-sig"), "sales.csv", "text/csv")
        bill = st.selectbox("Open invoice", df["bill_no"].tolist())
        sale = one(engine, "SELECT * FROM sales WHERE bill_no=:bill", {"bill":bill})
        items = query_df(engine, "SELECT * FROM sale_items WHERE bill_no=:bill", {"bill":bill}).to_dict("records")
        st.code(invoice_text(sale, items))

# Khata
elif page == "Khata / Customer Ledger":
    st.subheader("Outstanding bills")
    due = query_df(engine, """
        SELECT bill_no, sold_at, customer_name, phone, total, paid, balance, status
        FROM sales WHERE voided=FALSE AND balance > 0 ORDER BY sold_at
    """)
    st.dataframe(due, use_container_width=True, hide_index=True)
    total_due = float(due["balance"].sum()) if not due.empty else 0
    st.metric("Total outstanding", pkr(total_due))
    st.subheader("Customer directory")
    customers = query_df(engine, """
        SELECT c.customer_id,c.name,c.phone,c.address,
        COALESCE(SUM(CASE WHEN s.voided=FALSE THEN s.balance ELSE 0 END),0) AS outstanding
        FROM customers c LEFT JOIN sales s ON s.customer_id=c.customer_id
        GROUP BY c.customer_id ORDER BY c.name
    """)
    st.dataframe(customers, use_container_width=True, hide_index=True)
    if not customers.empty:
        cid = st.selectbox("Customer ledger", customers["customer_id"].tolist(),
                           format_func=lambda x: f"{customers[customers['customer_id']==x].iloc[0]['name']} — {customers[customers['customer_id']==x].iloc[0]['phone']}")
        ledger = query_df(engine, """
            SELECT bill_no,sold_at,customer_name,total,paid,balance,status
            FROM sales WHERE customer_id=:cid ORDER BY sold_at DESC
        """, {"cid":cid})
        st.dataframe(ledger, use_container_width=True, hide_index=True)
        ledger_payments = query_df(engine, """
            SELECT paid_at,bill_no,amount,method,note FROM payments
            WHERE customer_id=:cid ORDER BY paid_at DESC
        """, {"cid":cid})
        st.subheader("Payments")
        st.dataframe(ledger_payments, use_container_width=True, hide_index=True)

# Repayment
elif page == "Record Repayment":
    st.subheader("Record a Khata repayment")
    due = query_df(engine, """
        SELECT bill_no,customer_id,customer_name,phone,total,paid,balance
        FROM sales WHERE voided=FALSE AND balance > 0 ORDER BY sold_at
    """)
    if due.empty:
        st.success("No unpaid bills.")
    else:
        bills = due["bill_no"].tolist()
        bill = st.selectbox("Bill", bills, format_func=lambda b: (
            f"{b} — {due[due['bill_no']==b].iloc[0]['customer_name']} — Due {pkr(due[due['bill_no']==b].iloc[0]['balance'])}"
        ))
        rec = due[due["bill_no"] == bill].iloc[0]
        with st.form("repayment_form"):
            amount = st.number_input("Amount received (Rs.)", min_value=0.01, max_value=float(rec["balance"]), value=min(100.0,float(rec["balance"])), step=100.0)
            method = st.selectbox("Method", PAYMENT_METHODS)
            note = st.text_input("Note (optional)")
            submit = st.form_submit_button("Save repayment", type="primary")
        if submit:
            try:
                with engine.begin() as conn:
                    locked = conn.execute(text("SELECT paid,balance,customer_id,customer_name FROM sales WHERE bill_no=:bill FOR UPDATE"), {"bill":bill}).mappings().first()
                    if not locked or amount > float(locked["balance"]):
                        raise ValueError("The outstanding balance changed. Refresh and try again.")
                    new_paid = float(locked["paid"]) + amount
                    new_balance = max(0.0, float(locked["balance"]) - amount)
                    status = "Paid" if new_balance < 0.005 else "Partially paid"
                    conn.execute(text("UPDATE sales SET paid=:paid,balance=:balance,status=:status WHERE bill_no=:bill"),
                                 {"paid":new_paid,"balance":new_balance,"status":status,"bill":bill})
                    conn.execute(text("""
                        INSERT INTO payments (payment_id,customer_id,bill_no,customer_name,amount,method,note)
                        VALUES (:id,:cid,:bill,:name,:amount,:method,:note)
                    """), {"id":new_id("PAY"),"cid":locked["customer_id"],"bill":bill,
                           "name":locked["customer_name"],"amount":amount,"method":method,"note":note})
                st.success(f"Payment saved. Remaining due: {pkr(new_balance)}")
            except Exception as exc:
                st.error("Payment was not saved.")
                st.code(str(exc))
    st.subheader("Recent payments")
    recent = query_df(engine, "SELECT paid_at,bill_no,customer_name,amount,method,note FROM payments ORDER BY paid_at DESC LIMIT 200")
    st.dataframe(recent, use_container_width=True, hide_index=True)

# Expenses
elif page == "Expenses":
    st.subheader("Record business expenses")
    with st.form("expense_form", clear_on_submit=True):
        expense_date = st.date_input("Date", date.today())
        category = st.selectbox("Category", EXPENSE_CATEGORIES)
        description = st.text_input("Description")
        amount = st.number_input("Amount (Rs.)", min_value=0.01, value=100.0, step=100.0)
        method = st.selectbox("Paid using", PAYMENT_METHODS)
        submit = st.form_submit_button("Save expense", type="primary")
    if submit:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO expenses (expense_id,expense_date,category,description,amount,method)
                VALUES (:id,:date,:category,:description,:amount,:method)
            """), {"id":new_id("EXP"),"date":expense_date,"category":category,
                   "description":description,"amount":amount,"method":method})
        st.success("Expense recorded.")
    df = query_df(engine, "SELECT * FROM expenses ORDER BY expense_date DESC, expense_id DESC")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.metric("Total recorded expenses", pkr(float(df["amount"].sum()) if not df.empty else 0))

# Stock adjustment
elif page == "Stock Adjustment":
    st.subheader("Stock correction, damage, or return")
    inv = products_df()
    if inv.empty:
        st.info("Add products first.")
    else:
        sku = st.selectbox("Product SKU", inv["sku"].tolist(),
                           format_func=lambda x: f"{x} — {inv[inv['sku']==x].iloc[0]['name']} (stock {int(inv[inv['sku']==x].iloc[0]['stock'])})")
        reason = st.selectbox("Reason", ["Stock received", "Customer return — resellable", "Damaged item", "Lost / missing", "Stock count correction", "Other"])
        change = st.number_input("Quantity change (+ add, - remove)", min_value=-10000, max_value=10000, value=1)
        note = st.text_input("Note")
        if st.button("Apply stock adjustment", type="primary"):
            if change == 0:
                st.error("Quantity change cannot be zero.")
            else:
                try:
                    with engine.begin() as conn:
                        prod = conn.execute(text("SELECT name,stock FROM products WHERE sku=:sku FOR UPDATE"), {"sku":sku}).mappings().first()
                        if not prod or int(prod["stock"]) + int(change) < 0:
                            raise ValueError("Stock cannot become negative.")
                        conn.execute(text("UPDATE products SET stock=stock+:qty,updated_at=CURRENT_TIMESTAMP WHERE sku=:sku"), {"qty":int(change),"sku":sku})
                        save_stock_movement(conn,sku,prod["name"],int(change),reason,note)
                    st.success("Stock adjustment saved.")
                except Exception as exc:
                    st.error("Stock adjustment failed.")
                    st.code(str(exc))
    moves = query_df(engine, "SELECT moved_at,sku,item_name,change_qty,reason,note,reference FROM stock_movements ORDER BY moved_at DESC LIMIT 500")
    st.subheader("Recent stock movements")
    st.dataframe(moves, use_container_width=True, hide_index=True)

# Reports and backups
elif page == "Reports & Backups":
    st.subheader("Profit and business reports")
    col1,col2 = st.columns(2)
    start = col1.date_input("From date", date.today().replace(day=1), key="report_start")
    end = col2.date_input("To date", date.today(), key="report_end")
    sales_df = query_df(engine, """
        SELECT * FROM sales WHERE sold_at::date >= :start AND sold_at::date <= :end AND voided=FALSE
    """, {"start":start,"end":end})
    expenses_df = query_df(engine, """
        SELECT * FROM expenses WHERE expense_date >= :start AND expense_date <= :end
    """, {"start":start,"end":end})
    revenue = float(sales_df["total"].sum()) if not sales_df.empty else 0
    cost = float(sales_df["cost"].sum()) if not sales_df.empty else 0
    expenses_total = float(expenses_df["amount"].sum()) if not expenses_df.empty else 0
    gross = revenue-cost
    net = gross-expenses_total
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Sales revenue", pkr(revenue))
    c2.metric("Cost of goods sold", pkr(cost))
    c3.metric("Gross profit", pkr(gross))
    c4.metric("Profit after recorded expenses", pkr(net))
    st.caption("Estimates exclude unrecorded expenses, taxes, returns, damaged inventory costs, and other adjustments.")
    if not sales_df.empty:
        sales_df["sale_day"] = pd.to_datetime(sales_df["sold_at"]).dt.date.astype(str)
        daily = sales_df.groupby("sale_day", as_index=False)["total"].sum()
        st.subheader("Sales by day")
        st.bar_chart(daily.set_index("sale_day"))
        st.dataframe(daily, use_container_width=True, hide_index=True)

    st.subheader("Download backups")
    tables = {
        "products": "SELECT * FROM products ORDER BY sku",
        "customers": "SELECT * FROM customers ORDER BY name",
        "sales": "SELECT * FROM sales ORDER BY sold_at DESC",
        "sale_items": "SELECT * FROM sale_items ORDER BY bill_no",
        "payments": "SELECT * FROM payments ORDER BY paid_at DESC",
        "expenses": "SELECT * FROM expenses ORDER BY expense_date DESC",
        "stock_movements": "SELECT * FROM stock_movements ORDER BY moved_at DESC",
    }
    backup = {}
    for name, sql in tables.items():
        frame = query_df(engine, sql)
        backup[name] = frame
        st.download_button(
            f"Download {name.replace('_',' ').title()} CSV",
            frame.to_csv(index=False).encode("utf-8-sig"),
            f"{name}_backup_{date.today().isoformat()}.csv",
            "text/csv",
            key=f"backup_{name}",
        )
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in backup.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
    st.download_button(
        "Download complete Excel backup",
        output.getvalue(),
        f"smart_clothes_backup_{date.today().isoformat()}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.divider()
st.caption("Keep your database credentials private. Download backups regularly and test restore procedures.")
