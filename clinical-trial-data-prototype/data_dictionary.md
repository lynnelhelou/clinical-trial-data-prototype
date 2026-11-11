# Data dictionary

All data is synthetic. NULL in a measurement column means "not entered".

| Table | Column | Type | Rule / meaning |
|---|---|---|---|
| sites | site_id | integer, PK | Research site |
| sites | site_name, city | text | |
| participants | participant_id | text, PK | e.g. P0001 |
| participants | site_id | integer, FK | Site where the participant is enrolled |
| participants | birth_date, sex | text | sex is F or M |
| participants | status | text | Screening, Consent, Enrolled, Active, Completed, Withdrawn, Screen Failed |
| participants | enrolled_date | text (YYYY-MM-DD) | Also the date of visit 1 |
| visits | visit_id | integer, PK | |
| visits | participant_id | text, FK | |
| visits | visit_number | integer | 1 to 5; unique per participant |
| visits | scheduled_date | text | Enrollment date + 0, 14, 28, 56, 84 days |
| visits | actual_date | text | Required window: within 3 days of scheduled_date |
| visits | status | text | Scheduled, Completed, Missed |
| measurements | measurement_id | integer, PK | |
| measurements | visit_id | integer, FK, unique | One row per completed visit |
| measurements | systolic_bp, diastolic_bp | integer | mmHg. Diastolic must be lower than systolic |
| measurements | heart_rate | integer | beats per minute |
| measurements | weight_kg | real | |
| reference_ranges | measurement, min_value, max_value | | Allowed limits (configuration) |
| allowed_transitions | from_status, to_status | | Legal participant status changes (configuration) |
| session_context | user_name, reason | | Set by the app before edits so triggers know who and why |
| audit_log | audit_id ... changed_at | | Append-only history of edits, deletes and status changes |

## Required at every completed visit
Systolic BP, diastolic BP, heart rate, weight.

## Participant workflow
Screening -> Consent -> Enrolled -> Active -> Completed.
Withdrawn is allowed from Consent, Enrolled, and Active. Screen Failed is allowed from Screening.
