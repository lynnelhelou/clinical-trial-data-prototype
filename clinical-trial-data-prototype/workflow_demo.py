"""
Shows the workflow rules and the audit trail in action.
Works on a COPY of the database so clinical_trial.db stays untouched.

Run:  python workflow_demo.py
"""
import shutil
import sqlite3

shutil.copy("clinical_trial.db", "demo_copy.db")
con = sqlite3.connect("demo_copy.db")
con.execute("PRAGMA foreign_keys = ON")


def set_user(name, reason):
    """Tell the database who is making the next change and why."""
    con.execute("UPDATE session_context SET user_name = ?, reason = ? WHERE id = 1", (name, reason))


def try_it(label, sql, params=()):
    try:
        con.execute(sql, params)
        con.commit()
        print(f"  OK       {label}")
    except sqlite3.IntegrityError as e:
        print(f"  BLOCKED  {label}\n           -> {e}")


print("\n1. Walk a new participant through the legal workflow")
set_user("coordinator_amy", "new participant")
con.execute("INSERT INTO participants (participant_id, site_id, status) VALUES ('P9001', 1, 'Screening')")
for new_status in ["Consent", "Enrolled", "Active", "Completed"]:
    set_user("coordinator_amy", f"moved to {new_status}")
    try_it(f"status -> {new_status}",
           "UPDATE participants SET status = ? WHERE participant_id = 'P9001'", (new_status,))

print("\n2. Try an illegal jump (Screening -> Completed)")
set_user("coordinator_amy", "new participant")
con.execute("INSERT INTO participants (participant_id, site_id, status) VALUES ('P9002', 1, 'Screening')")
try_it("Screening -> Completed", "UPDATE participants SET status = 'Completed' WHERE participant_id = 'P9002'")

print("\n3. A data manager corrects an impossible blood pressure")
row = con.execute("SELECT measurement_id, systolic_bp FROM measurements WHERE systolic_bp > 200 LIMIT 1").fetchone()
set_user("data_manager_jlee", "Transcription error; corrected per source document")
try_it(f"measurement {row[0]}: systolic {row[1]} -> 124",
       "UPDATE measurements SET systolic_bp = 124 WHERE measurement_id = ?", (row[0],))

print("\n4. Try to rewrite history in the audit log")
try_it("UPDATE audit_log", "UPDATE audit_log SET changed_by = 'someone_else'")
try_it("DELETE FROM audit_log", "DELETE FROM audit_log")

print("\n5. The audit trail now shows who changed what, when and why:\n")
print(f"  {'table':<13}{'record':<9}{'field':<14}{'old':<11}{'new':<11}{'by':<20}reason")
for r in con.execute("""SELECT table_name, record_id, field_name, old_value, new_value, changed_by, reason
                        FROM audit_log ORDER BY audit_id"""):
    print(f"  {r[0]:<13}{r[1]:<9}{r[2]:<14}{str(r[3]):<11}{str(r[4]):<11}{r[5]:<20}{r[6]}")
con.close()
