import pandas as pd
import random

areas = [1, 2, 3, 4]
weekdays = list(range(7))  # 0=Mon, 6=Sun
slots = ["Morning", "Afternoon", "Evening"]

data = []

for area in areas:
    for day in weekdays:
        if area == 1:
            past_rate = random.randint(70, 100)
        elif area == 2:
            past_rate = random.randint(50, 85)
        elif area == 3:
            past_rate = random.randint(60, 90)
        else:
            past_rate = random.randint(40, 75)

        if past_rate >= 80:
            preferred_slot = "Morning"
        elif past_rate >= 60:
            preferred_slot = "Afternoon"
        else:
            preferred_slot = "Evening"

        data.append({
            "area": area,
            "weekday": day,
            "past_success_rate": past_rate,
            "preferred_slot": preferred_slot
        })

df = pd.DataFrame(data)
df.to_csv("ml/dataset.csv", index=False)
print("✅ Smart dataset.csv created in ml/ folder!")
