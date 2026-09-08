import json, urllib.request, urllib.error, datetime

B = "http://localhost:5173/api/v1"
T = "DEMO2026"


def req(method, path, body=None):
    url = B + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "null")


today = datetime.date.today().strftime("%Y-%m-%d")
tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

# 1. find any eligible room (VACANT_CLEAN or ARRIVAL_LOCKED)
st, rooms = req("GET", f"/tenants/{T}/rooms")
print("rooms_total", len(rooms) if isinstance(rooms, list) else rooms)
print("room_states", sorted({(r.get("state"), r.get("room_type_id")) for r in rooms}))
eligible = [r for r in rooms if r.get("state") in ("vacant_clean", "arrival_locked")]
print("eligible_count", len(eligible), [(r["room_no"], r["state"], r["room_type_id"]) for r in eligible])
room = eligible[0]
room_no = room["room_no"]
rt_id = room["room_type_id"]
print("picked", room_no, "rt", rt_id)

# 2. create booking for that room_type
st, bk = req("POST", f"/tenants/{T}/bookings",
             {"hotel_id": 1, "room_type_id": rt_id, "guest_name": "自动开账测试",
              "check_in_date": today, "check_out_date": tomorrow, "channel": "direct"})
print("create_booking", st, "id=", bk.get("id"), "status=", bk.get("status"))
bid = bk["id"]

# 3. check-in
st, ci = req("POST", f"/tenants/{T}/bookings/{bid}/check-in", {"room_no": room_no})
print("check_in", st, ci if not isinstance(ci, dict) or "status" not in ci else ci.get("status"), "| detail:", ci.get("detail") if isinstance(ci, dict) else "")

# 4. verify auto-opened bill
st, bills = req("GET", f"/tenants/{T}/bills")
auto = [x for x in bills if x.get("booking_id") == bid]
print("auto_bills_count", len(auto))
for x in auto:
    print("  bill_id=", x["id"], "source=", x["source"], "status=", x["status"],
          "balance=", x["balance"], "room_no=", x["room_no"], "guest=", x["guest_name"])

# 5. idempotency: re-check-in should 409
st2, ci2 = req("POST", f"/tenants/{T}/bookings/{bid}/check-in", {"room_no": room_no})
print("re_checkin_status", st2, "(expect 409)")
print("E2E_DONE")
