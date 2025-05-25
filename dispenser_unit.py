import os
import time
from datetime import datetime
import paho.mqtt.client as mqtt
from gpiozero import LED, Button, PWMLED
from gpiozero.pins.pigpio import PiGPIOFactory
from gpiozero import Servo
import threading

# --- GPIO Setup ---
led = LED(24)                    # Status LED
buzzer = PWMLED(23)             # Buzzer
button = Button(25, pull_up=True)  # Acknowledgement button

factory = PiGPIOFactory()
servo = Servo(18, pin_factory=factory, min_pulse_width=0.0006, max_pulse_width=0.0023)

# --- MQTT Setup ---
BROKER = "broker.emqx.io"
PORT = 1883
COMMAND_TOPIC = "dispenser/command"
STATUS_TOPIC = "dispenser/status"

client = mqtt.Client()
awaiting_ack = False
start_time = None
current_slot = None
TIMEOUT = 60
BLINK_INTERVAL = 0.5
LOG_FILE = "dose_log.txt"

# --- Logging Helper ---
def log_event(slot, action):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(LOG_FILE, "a") as f:
        f.write(f"{timestamp} - Slot {slot} - {action}\n")

# --- Status Publisher ---
def send_status(status):
    client.publish(STATUS_TOPIC, status)
    if current_slot:
        log_event(current_slot, status)

# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, rc):
    print("Connected to broker")
    client.subscribe(COMMAND_TOPIC)

def on_message(client, userdata, msg):
    global awaiting_ack, start_time, current_slot
    payload = msg.payload.decode()
    print(f"MQTT Received: {payload}")

    if payload.startswith("DISPENSE") and not awaiting_ack:
        if ":" in payload:
            parts = payload.split(":")
            current_slot = parts[1].strip()
            print(f"Slot received: {current_slot}")
        else:
            current_slot = "UNKNOWN"
            print("?? No slot number provided in DISPENSE message.")

        log_event(current_slot, "DISPENSE")
        awaiting_ack = True
        start_time = time.time()

# --- Alert Blinking Thread ---
def blink_alert():
    while True:
        if awaiting_ack:
            led.toggle()
            buzzer.on() if buzzer.value == 0 else buzzer.off()
        else:
            led.off()
            buzzer.value = 0
        time.sleep(BLINK_INTERVAL)

# --- Monitor Button and Trigger Servo ---
def monitor_button():
    global awaiting_ack, start_time
    acknowledged = False
    while True:
        if awaiting_ack:
            if button.is_pressed and not acknowledged:
                print("Button pressed: DISPENSING")
                servo.min()
                time.sleep(0.38)
                servo.mid()
                buzzer.off()
                led.off()
                send_status("TAKEN")
                awaiting_ack = False
                acknowledged = True
            elif time.time() - start_time >= TIMEOUT:
                print("Timeout: DOSE MISSED")
                buzzer.off()
                led.off()
                send_status("MISSED")
                awaiting_ack = False
                acknowledged = False
        else:
            acknowledged = False
        time.sleep(0.1)

# --- Start System ---
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_start()

# Start background threads
threading.Thread(target=blink_alert, daemon=True).start()
threading.Thread(target=monitor_button, daemon=True).start()

# Keep script running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()
    print("Shutting down.")
