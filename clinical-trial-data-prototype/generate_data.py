"""
Builds clinical_trial.db with SYNTHETIC trial data and plants a known number
of errors. Writes answer_key.csv listing every planted error so run_checks.py
can prove the validation checks find them.

Run:  python generate_data.py
"""
import csv
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

random.seed(42)  # same data every time

DB_PATH = Path("clinical_trial.db")

N_PARTICIPANTS = 500
N_SITES = 10
VISIT_OFFSETS = {1: 0, 2: 14, 3: 28, 4: 56, 5: 84}   # days after enrollment
NORMAL_REFERENCE = {"systolic_bp", "diastolic_bp", "heart_rate", "weight_kg"}

# How many errors of each type to plant
N_MISSING_FIELD = 40       # completed visit with one value left blank
N_NO_MEASUREMENTS = 10     # completed visit with no measurement record at all
N_OUT_OF_RANGE = 30
N_DIASTOLIC_GE_SYSTOLIC = 20
N_OUT_OF_WINDOW = 40
N_DUPLICATE_PARTICIPANTS = 8
N_STATUS_MISMATCH = 15

CITIES = ["Newark", "Boston", "Philadelphia", "Baltimore", "Pittsburgh",
          "Hartford", "Albany", "Richmond", "Providence", "Buffalo"]

# Sites 3 and 7 get more of the planted errors, so the site report has
# something interesting to find.
SITE_ERROR_WEIGHT = {s: (3 if s in (3, 7) else 1) for s in range(1, N_SITES + 1)}


def rand_date(start, end):
    return start + timedelta(days=random.randint(0, (end - start).days))


def weighted_sample(items, k, weight_fn):
    """Pick k items without replacement; higher weight = more likely."""
    keyed = sorted(items, key=lambda x: random.random() ** (1.0 / weight_fn(x)), reverse=True)
    return keyed[:k]


def build_base_data():
    sites = [(i, f"Site {i:02d}", CITIES[i - 1]) for i in range(1, N_SITES + 1)]
    participants, visits, measurements = [], [], {}
    visit_id = 0

    for n in range(1, N_PARTICIPANTS + 1):
        pid = f"P{n:04d}"
        site_id = random.randint(1, N_SITES)
        birth = rand_date(date(1955, 1, 1), date(2005, 12, 31))
        sex = random.choice(["F", "M"])
        enrolled = rand_date(date(2025, 1, 6), date(2025, 4, 30))
        status = random.choices(["Completed", "Active", "Withdrawn"], [0.60, 0.25, 0.15])[0]
        done = {"Completed": 5, "Active": random.randint(1, 4), "Withdrawn": random.randint(1, 3)}[status]

        participants.append({"participant_id": pid, "site_id": site_id, "birth_date": birth.isoformat(),
                             "sex": sex, "status": status, "enrolled_date": enrolled.isoformat()})

        base_sys = random.gauss(122, 10)
        base_dia = random.gauss(78, 6)
        base_hr = random.gauss(72, 8)
        base_wt = random.gauss(75, 13)

        for v in range(1, 6):
            visit_id += 1
            scheduled = enrolled + timedelta(days=VISIT_OFFSETS[v])
            if v <= done:
                shift = random.randint(0, 2) if v == 1 else random.randint(-2, 2)
                vrow = {"visit_id": visit_id, "participant_id": pid, "visit_number": v,
                        "scheduled_date": scheduled.isoformat(),
                        "actual_date": (scheduled + timedelta(days=shift)).isoformat(),
                        "status": "Completed"}
                measurements[visit_id] = {
                    "systolic_bp": int(min(max(base_sys + random.gauss(0, 4), 95), 160)),
                    "diastolic_bp": int(min(max(base_dia + random.gauss(0, 3), 60), 95)),
                    "heart_rate": int(min(max(base_hr + random.gauss(0, 4), 52), 100)),
                    "weight_kg": round(min(max(base_wt + random.gauss(0, 1.0), 50), 120), 1),
                }
            else:
                vrow = {"visit_id": visit_id, "participant_id": pid, "visit_number": v,
                        "scheduled_date": scheduled.isoformat(), "actual_date": None,
                        "status": "Scheduled" if status == "Active" else "Missed"}
            visits.append(vrow)

    return sites, participants, visits, measurements


def plant_errors(participants, visits, measurements):
    """Modify the clean data in memory. Returns the answer key rows."""
    key = []
    site_of = {p["participant_id"]: p["site_id"] for p in participants}
    weight = lambda v: SITE_ERROR_WEIGHT[site_of[v["participant_id"]]]
    by_pid = {}
    for v in visits:
        by_pid.setdefault(v["participant_id"], []).append(v)

    # 1. Status mismatch: participant marked Completed but one visit was actually missed
    used = set()
    completed_people = [p for p in participants if p["status"] == "Completed"]
    chosen = weighted_sample(completed_people, N_STATUS_MISMATCH,
                             lambda p: SITE_ERROR_WEIGHT[p["site_id"]])
    for p in chosen:
        v = random.choice(by_pid[p["participant_id"]])
        v["status"], v["actual_date"] = "Missed", None
        measurements.pop(v["visit_id"], None)
        used.update(x["visit_id"] for x in by_pid[p["participant_id"]])
        key.append(("status_mismatch", p["participant_id"], "Completed but a visit was missed"))

    # Pool of untouched completed visits for the other error types
    def pool(min_visit=1):
        return [v for v in visits if v["status"] == "Completed"
                and v["visit_id"] not in used and v["visit_number"] >= min_visit]

    # 2. Out-of-window visits (visit 2+ only)
    for v in weighted_sample(pool(2), N_OUT_OF_WINDOW, weight):
        v["actual_date"] = (date.fromisoformat(v["scheduled_date"])
                            + timedelta(days=random.randint(8, 20))).isoformat()
        used.add(v["visit_id"])
        key.append(("out_of_window", v["visit_id"], "actual date far from scheduled date"))

    # 3. Missing value in a completed visit
    for v in weighted_sample(pool(), N_MISSING_FIELD, weight):
        field = random.choice(["systolic_bp", "diastolic_bp", "heart_rate", "weight_kg"])
        measurements[v["visit_id"]][field] = None
        used.add(v["visit_id"])
        key.append(("missing_required", v["visit_id"], f"{field} left blank"))

    # 4. Completed visit with no measurement record at all
    for v in weighted_sample(pool(), N_NO_MEASUREMENTS, weight):
        measurements.pop(v["visit_id"])
        used.add(v["visit_id"])
        key.append(("missing_required", v["visit_id"], "no measurement record"))

    # 5. Out-of-range values (chosen so they don't also trip the BP-order check)
    bad_values = [("systolic_bp", lambda: random.randint(230, 260)),
                  ("diastolic_bp", lambda: random.randint(15, 25)),
                  ("heart_rate", lambda: random.choice([random.randint(200, 240), random.randint(5, 20)])),
                  ("weight_kg", lambda: random.choice([random.randint(10, 20), random.randint(300, 400)]))]
    for v in weighted_sample(pool(), N_OUT_OF_RANGE, weight):
        field, gen = random.choice(bad_values)
        measurements[v["visit_id"]][field] = gen()
        used.add(v["visit_id"])
        key.append(("out_of_range", v["visit_id"], f"{field} set to impossible value"))

    # 6. Diastolic >= systolic (both values still inside the allowed ranges)
    for v in weighted_sample(pool(), N_DIASTOLIC_GE_SYSTOLIC, weight):
        val = random.randint(100, 115)
        measurements[v["visit_id"]]["systolic_bp"] = val
        measurements[v["visit_id"]]["diastolic_bp"] = val
        used.add(v["visit_id"])
        key.append(("diastolic_ge_systolic", v["visit_id"], f"BP entered as {val}/{val}"))

    # 7. Duplicate participants: same person registered twice under a new ID
    originals = random.sample([p for p in participants if p["status"] == "Completed"
                               and p["participant_id"] not in {k[1] for k in key}],
                              N_DUPLICATE_PARTICIPANTS)
    next_n = N_PARTICIPANTS
    for p in originals:
        next_n += 1
        dup = dict(p, participant_id=f"P{next_n:04d}", status="Screening")
        participants.append(dup)
        key.append(("duplicate_participant", f"{p['participant_id']} / {dup['participant_id']}",
                    "same site, birth date, sex and enrollment date"))
    return key


def write_db(sites, participants, visits, measurements):
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(Path("schema.sql").read_text())
    con.executemany("INSERT INTO sites VALUES (?,?,?)", sites)
    con.executemany(
        "INSERT INTO participants VALUES (:participant_id,:site_id,:birth_date,:sex,:status,:enrolled_date)",
        participants)
    con.executemany(
        "INSERT INTO visits VALUES (:visit_id,:participant_id,:visit_number,:scheduled_date,:actual_date,:status)",
        visits)
    con.executemany(
        "INSERT INTO measurements (visit_id, systolic_bp, diastolic_bp, heart_rate, weight_kg) "
        "VALUES (?,?,?,?,?)",
        [(vid, m["systolic_bp"], m["diastolic_bp"], m["heart_rate"], m["weight_kg"])
         for vid, m in sorted(measurements.items())])
    con.commit()
    con.close()


def main():
    sites, participants, visits, measurements = build_base_data()
    key = plant_errors(participants, visits, measurements)
    write_db(sites, participants, visits, measurements)
    with open("answer_key.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["error_type", "record", "detail"])
        w.writerows(key)
    print(f"Created {DB_PATH} with {len(participants)} participants, {len(visits)} visits, "
          f"{len(measurements)} measurement records.")
    print(f"Planted {len(key)} errors (listed in answer_key.csv).")


if __name__ == "__main__":
    main()
