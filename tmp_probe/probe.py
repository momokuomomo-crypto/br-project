import json, sys
sys.path.insert(0, "tmp_probe")
from ar.client import Client
c = Client()
cal = c.calendar("2025-11")
print("calendar:", cal["result"], len(cal["body"]))
for ep in ["OtherRaceInfo", "Program", "Odds", "RaceResult"]:
    j = c.post(ep, 2, "2025-11-04", 5)
    print(ep, j.get("result"), len(json.dumps(j)))
