import streamlit as st
import sqlite3
import os
import random
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import pickle
from datetime import datetime, timezone
from sklearn.ensemble import RandomForestClassifier
from twilio.rest import Client  # <-- Twilio import

DB_FILE = "deliveries.db"
MODEL_PATH = "slot_model.pkl"
DATASET = "ml/dataset.csv"

# ============ DATABASE SETUP ============
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            recipient TEXT,
            phone TEXT,
            address TEXT,
            slot TEXT,
            otp TEXT,
            photo_path TEXT,
            status TEXT,
            fallback_used INTEGER,
            created_at TEXT,
            predicted_slot TEXT,
            confidence REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ============ Twilio Helper ============
def send_otp_sms(recipient_number, otp):
    account_sid = "YOUR_TWILIO_SID"
    auth_token = "YOUR_TWILIO_AUTH_TOKEN"
    client = Client(account_sid, auth_token)
    
    message = client.messages.create(
        body=f"Your parcel has been delivered at the designated safe place.\nTo confirm delivery, share this OTP with the Postman: {otp}",
        from_='+1234567890',  # Your Twilio number
        to=recipient_number
    )
    return message.sid

# ============ DB HELPERS ============
def book_delivery(sender, recipient, phone, address, slot, predicted_slot=None, confidence=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    otp = str(random.randint(1000, 9999))  # 4-digit OTP for recipient
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO deliveries
        (sender, recipient, phone, address, slot, otp, photo_path, status, fallback_used, created_at, predicted_slot, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (sender, recipient, phone, address, slot, otp, None, "Scheduled", 0, now, predicted_slot, confidence))
    conn.commit()
    delivery_id = c.lastrowid
    conn.close()
    
    # Send OTP via Twilio
    try:
        sms_sid = send_otp_sms(phone, otp)
    except Exception as e:
        sms_sid = f"Failed to send SMS: {e}"
    
    return delivery_id, otp, sms_sid

def verify_delivery(delivery_id, otp_input, photo):
    if not delivery_id or not otp_input:
        return False, " Please enter Delivery ID and OTP"
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT otp FROM deliveries WHERE id=?", (delivery_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        return False, " Delivery ID not found"
    if result[0].strip() != otp_input.strip():
        conn.close()
        return False, " Invalid OTP"

    photo_path = None
    if photo:
        os.makedirs("proof_photos", exist_ok=True)
        photo_path = os.path.join("proof_photos", f"delivery_{delivery_id}.jpg")
        with open(photo_path, "wb") as f:
            f.write(photo.getbuffer())

    c.execute("UPDATE deliveries SET status=?, photo_path=? WHERE id=?", ("Delivered", photo_path, delivery_id))
    conn.commit()
    conn.close()
    return True, " Delivery Verified & Completed!"

def get_deliveries_for_today():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    c.execute("SELECT id, sender, recipient, phone, address, slot, predicted_slot, confidence, status FROM deliveries WHERE created_at LIKE ?", (f"{today_date}%",))
    deliveries = c.fetchall()
    conn.close()
    return deliveries

def update_delivery_status(delivery_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE deliveries SET status=? WHERE id=?", (status, delivery_id))
    conn.commit()
    conn.close()

# ============ ML HELPERS ============
def train_model():
    df = pd.read_csv(DATASET)
    X = df[["area", "weekday", "past_success_rate"]]
    y = df["preferred_slot"]
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

def predict_slot(area, weekday, past_success_rate):
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    X_new = pd.DataFrame([[area, weekday, past_success_rate]], 
                         columns=["area", "weekday", "past_success_rate"])
    prediction = model.predict(X_new)
    proba = model.predict_proba(X_new)
    confidence = max(proba[0])
    return prediction[0], confidence

# ============ STREAMLIT UI ============
st.sidebar.title(" AI Delivery System")
menu = ["Sender Portal", "Postman Portal", "Delivery Day", "Analytics / ML Dashboard"]
choice = st.sidebar.radio("Select View", menu)

# ----- Sender Portal -----
if choice == "Sender Portal":
    st.header("📨 Sender Portal - Book Delivery")
    sender = st.text_input("Sender Name")
    recipient = st.text_input("Recipient Name")
    phone = st.text_input("Recipient Phone (+countrycode)")
    address = st.text_area("Address")
    
    # ML-assisted slot recommendation
    st.subheader(" Slot Recommendation")
    area = st.selectbox("Area (1-4)", [1,2,3,4])
    weekday = st.slider("Weekday (0=Mon, 6=Sun)", 0,6,2)
    past_rate = st.slider("Past Success Rate (%)", 0,100,70)
    recommended_slot, confidence = predict_slot(area, weekday, past_rate)
    st.info(f"Recommended Slot: {recommended_slot} (Confidence: {confidence:.2f})")
    slot = st.selectbox("Choose Delivery Slot", ["Morning", "Afternoon", "Evening"], index=["Morning","Afternoon","Evening"].index(recommended_slot))

    if st.button("Book Slot"):
        if sender and recipient and phone and address:
            delivery_id, otp, sms_sid = book_delivery(sender, recipient, phone, address, slot, recommended_slot, confidence)
            st.success(f" Delivery booked! ID: {delivery_id}")
            st.info(f" OTP: {otp} (sent via SMS, SID: {sms_sid})")
        else:
            st.warning(" Fill all details including phone number.")

# ----- Postman Portal -----
elif choice == "Postman Portal":
    st.header(" Postman Portal - Verify Delivery")
    delivery_id = st.number_input("Enter Delivery ID", min_value=1, step=1)
    otp_input = st.text_input("Enter OTP", max_chars=6)
    photo = st.file_uploader("Upload Proof Photo", type=["jpg","png","jpeg"])
    if st.button("Verify Delivery"):
        success, message = verify_delivery(delivery_id, otp_input, photo)
        if success:
            st.success(message)
        else:
            st.error(message)

# ----- Delivery Day -----
elif choice == "Delivery Day":
    st.header(" Deliveries Scheduled Today")
    deliveries_today = get_deliveries_for_today()
    if deliveries_today:
        for d in deliveries_today:
            st.write(f"ID: {d[0]} | Sender: {d[1]} | Recipient: {d[2]} | Phone: {d[3]} | Slot: {d[5]} | Predicted: {d[6]} | Confidence: {d[7]:.2f} | Status: {d[8]}")
            if st.button(f"Mark Delivered - ID {d[0]}"):
                update_delivery_status(d[0], "Delivered")
                st.success(f" Delivery {d[0]} marked delivered.")
    else:
        st.info("No deliveries today.")

# ----- ML / Analytics Dashboard -----
elif choice == "Analytics / ML Dashboard":
    st.header(" Delivery Analytics & ML Insights")
    if not os.path.exists(MODEL_PATH):
        st.warning(" Model not trained. Training now...")
        train_model()
    df = pd.read_csv(DATASET)
    st.write(" Dataset Preview", df.head())
    st.write("Available columns in df:", df.columns.tolist())

    st.subheader(" Slot Predictor")
    area = st.selectbox("Area", [1,2,3,4])
    weekday = st.slider("Weekday (0=Mon,6=Sun)",0,6,2)
    past_rate = st.slider("Past Success Rate (%)",0,100,70)
    if st.button("Recommend Slot"):
        slot, conf = predict_slot(area, weekday, past_rate)
        st.success(f"Recommended Slot: {slot} (Confidence: {conf:.2f})")

    st.subheader(" Delivery Success Rates Before vs After AI")
    fig, ax = plt.subplots()
    sns.barplot(x="preferred_slot", y="past_success_rate", data=df, ax=ax)
    st.pyplot(fig)

    st.subheader("🌡 Delivery Success Heatmap (Area vs Weekday)")
    fig2, ax2 = plt.subplots()
    heatmap_data = df.pivot_table(index="area", columns="weekday", values="past_success_rate")
    sns.heatmap(heatmap_data, annot=True, cmap="YlGnBu", ax=ax2)
    st.pyplot(fig2)
