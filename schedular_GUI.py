import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from datetime import datetime
import paho.mqtt.client as mqtt
import threading
import time
import os
import json
import logging
import tkinter as tk  

# Logging setup
logging.basicConfig(filename='dispenser.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# MQTT Setup
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
COMMAND_TOPIC = "dispenser/command"
STATUS_TOPIC = "dispenser/status"

client = mqtt.Client()
reconnect_interval = 1
max_reconnect_interval = 32

schedule = []
current_slot = 1
lock = threading.Lock()

# ---- GUI Setup ----
root = ttk.Window(themename="flatly")
root.title("Smart Medication Scheduler")
root.geometry("450x500")
root.resizable(False, False)

# GUI Elements
title = ttk.Label(root, text="Smart Medication Scheduler", font=("Helvetica", 18, "bold"))
title.pack(pady=10)

slot_label = ttk.Label(root, text=f"Enter time for Slot {current_slot}", font=("Helvetica", 11))
slot_label.pack()

time_entry = ttk.Entry(root, font=("Helvetica", 12), width=20)
time_entry.insert(0, "HH:MM")
time_entry.pack(pady=5)

def on_entry_click(e):
    if time_entry.get() == "HH:MM":
        time_entry.delete(0, tk.END)
        time_entry.config(foreground="black")

def on_focusout(e):
    if time_entry.get() == "":
        time_entry.insert(0, "HH:MM")
        time_entry.config(foreground="gray")

time_entry.bind("<FocusIn>", on_entry_click)
time_entry.bind("<FocusOut>", on_focusout)

add_button = ttk.Button(root, text="Add Slot", bootstyle="success", width=18)
add_button.pack(pady=6)

clear_button = ttk.Button(root, text="Clear All", bootstyle="danger", width=18)
clear_button.pack(pady=2)

ttk.Label(root, text="Scheduled Slots", font=("Helvetica", 12, "bold")).pack(pady=(10, 0))
schedule_list = tk.Listbox(root, font=("Helvetica", 11), height=5, width=30,
                           bg="white", fg="#dc3545", selectbackground="#f8d7da")
schedule_list.pack(pady=6)

status_label = ttk.Label(root, text="", font=("Helvetica", 11, "bold"))
status_label.pack(pady=10)

footer = ttk.Label(root, text="Developed by Yours Truly", font=("Helvetica", 9))
footer.pack(side="bottom", pady=5)

# ---- Functions ----

def save_schedules():
    try:
        with open('schedules.json', 'w') as f:
            json.dump(schedule, f)
        logger.info("Schedules saved.")
    except Exception as e:
        logger.error(f"Error saving: {e}")

def load_schedules():
    global schedule, current_slot
    try:
        if os.path.exists("schedules.json"):
            with open("schedules.json", "r") as f:
                loaded = json.load(f)
                schedule.extend([(t, s) for t, s in loaded if datetime.strptime(t, "%H:%M")])
                for t, s in schedule:
                    schedule_list.insert(tk.END, f"{t} : Slot {s}")
                    current_slot = max(current_slot, s + 1)
                if current_slot > 3:
                    time_entry.config(state="disabled")
                    add_button.config(state="disabled")
                    slot_label.config(text="All 3 slots scheduled.")
                else:
                    slot_label.config(text=f"Enter time for Slot {current_slot}")
            logger.info("Schedules loaded.")
    except Exception as e:
        logger.error(f"Error loading: {e}")

def add_schedule():
    global current_slot
    t = time_entry.get().strip()
    try:
        datetime.strptime(t, "%H:%M")
        with lock:
            if t in [s[0] for s in schedule]:
                status_label.config(text="Duplicate time not allowed", bootstyle="warning")
                root.after(5000, lambda: status_label.config(text=""))
                return
            if schedule and t <= schedule[-1][0]:
                status_label.config(text="Time must be after previous slot", bootstyle="warning")
                root.after(5000, lambda: status_label.config(text=""))
                return
            schedule.append((t, current_slot))
            schedule_list.insert(tk.END, f"{t} : Slot {current_slot}")
            time_entry.delete(0, tk.END)
            save_schedules()
            logger.info(f"Added: {t} for Slot {current_slot}")
            if current_slot < 3:
                current_slot += 1
                slot_label.config(text=f"Enter time for Slot {current_slot}")
            else:
                time_entry.config(state="disabled")
                add_button.config(state="disabled")
                slot_label.config(text="All 3 slots scheduled.")
    except ValueError:
        status_label.config(text="Invalid format (use HH:MM)", bootstyle="danger")
        root.after(5000, lambda: status_label.config(text=""))

def clear_all():
    global schedule, current_slot
    with lock:
        schedule.clear()
        schedule_list.delete(0, tk.END)
        current_slot = 1
        slot_label.config(text="Enter time for Slot 1")
        time_entry.config(state="normal")
        add_button.config(state="normal")
        if os.path.exists("schedules.json"):
            os.remove("schedules.json")
        logger.info("Cleared all schedules.")
        status_label.config(text="All slots cleared", bootstyle="success")
        root.after(5000, lambda: status_label.config(text=""))

def play_alert(message):
    if message == "MISSED":
        os.system('espeak "Medication missed. Check patient."')
    elif message == "TAKEN":
        os.system('espeak "Medication is taken by patient."')

def send_command(slot):
    try:
        client.publish(COMMAND_TOPIC, f"DISPENSE:{slot}")
        status_label.config(text=f"Sent: DISPENSE for slot{slot}", bootstyle="success")
        root.after(5000, lambda: status_label.config(text=""))
    except Exception as e:
        logger.error(f"Failed to publish: {e}")
        status_label.config(text="Failed to send command", bootstyle="danger")

def on_connect(client, userdata, flags, rc):
    global reconnect_interval
    if rc == 0:
        logger.info("Connected to MQTT broker")
        client.subscribe(STATUS_TOPIC)
        reconnect_interval = 1
        status_label.config(text="Connected to MQTT", bootstyle="success")
        root.after(5000, lambda: status_label.config(text=""))
    else:
        logger.error(f"MQTT connect failed: {rc}")
        status_label.config(text="MQTT connection failed", bootstyle="danger")
        root.after(5000, lambda: status_label.config(text=""))

def on_disconnect(client, userdata, rc):
    global reconnect_interval
    logger.warning(f"Disconnected: {rc}")
    time.sleep(reconnect_interval)
    reconnect_interval = min(reconnect_interval * 2, max_reconnect_interval)
    try:
        client.reconnect()
    except Exception as e:
        logger.error(f"Reconnect failed: {e}")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        logger.info(f"Received: {payload}")
        if payload == "TAKEN":
            status_label.config(text="Medication Taken", bootstyle="success")
            play_alert("TAKEN")
        elif payload == "MISSED":
            status_label.config(text="Medication Missed", bootstyle="danger")
            play_alert("MISSED")
        root.after(5000, lambda: status_label.config(text=""))
    except Exception as e:
        logger.error(f"MQTT msg error: {e}")
        status_label.config(text="Message error", bootstyle="danger")

def time_checker():
    while True:
        now = datetime.now().strftime("%H:%M")
        with lock:
            for t, slot in schedule[:]:
                if now == t:
                    send_command(slot)
                    schedule.remove((t, slot))
                    save_schedules()
                    logger.info(f"Triggered: {t}, Slot {slot}")
        time.sleep(30)

# Bind buttons
add_button.config(command=add_schedule)
clear_button.config(command=clear_all)

# MQTT Setup
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
except Exception as e:
    logger.error(f"Initial connection failed: {e}")
    status_label.config(text="MQTT connection failed", bootstyle="danger")

# Load previous schedule and start thread
load_schedules()
threading.Thread(target=time_checker, daemon=True).start()

# Run GUI
root.mainloop()
client.loop_stop()
client.disconnect()
logger.info("Application closed.")
