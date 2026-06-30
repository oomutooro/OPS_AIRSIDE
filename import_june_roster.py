"""
Import June 2026 Duty Roster into ShiftRoster table.

Roster source: C:/Users/Administrator/Desktop/DUTY ROSTER FOR JUNE.docx
Run: python import_june_roster.py

Duty codes:
  D = Day shift
  N = Night shift
  O = Off duty
"""
import os
from datetime import date

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.apron import ShiftRoster

# ---------------------------------------------------------------------------
# Roster data
# ---------------------------------------------------------------------------

# Shift members normalized to full names.
SHIFTS = {
    "A": [
        "Ssewanyana Ronald",
        "Byaruhanga Edgar",
        "Ssemwanga Ronald",
        "Evon Akandwanaho",
        "Opolot Emmanuel",
        "Namugenyi Robinah",
    ],
    "B": [
        "Musinguzi Victor",
        "Kyakonye Ziad",
        "Sharif Mohamed",
        "Ederu Edgar",
        "Ssentongo Ivan",
    ],
    "C": [
        "Musambi Isaac",
        "Ogola John",
        "Akandwanaho Stella",
        "Mukisa Edward",
        "Bakashaba Jackson",
        "Asewu Moses",
    ],
    "D": [
        "Mugisha William",
        "Candiga Francis",
        "Ecuru Albert",
        "Alele Abel",
        "Matovu Mark",
        "Abiti Mary Florence",
    ],
}

# Additional names present in the June roster document (leave/support notes)
# that should also have accounts available.
ADDITIONAL_USERS = [
    "Suuna Emmanuel",
    "Ssebuwufu Francis",
    "Ssali P",
    "Ssemwogerere Sadrack Shad",
    "Agaba Prossy",
    "Abbey Magala",
    "Okena Ivan Katenta",
    "Ebu Derrick",
    "Nahamya Frank",
]

DUTY_MAP = {
    "D": "day",
    "N": "night",
    "O": "off",
}

CYCLE_INDEX = {
    "day": 0,
    "night": 1,
    "off": 2,
}

# June pattern from the roster document.
# For Shift A/B/C/D, the 4-day cycle is:
# 1: O N O D
# 2: D O O N
# 3: N O D O
# 4: O D N O
JUNE_PATTERN = [
    ("O", "N", "O", "D"),
    ("D", "O", "O", "N"),
    ("N", "O", "D", "O"),
    ("O", "D", "N", "O"),
]


def build_daily_schedule():
    """Build (date, A, B, C, D) rows for June 1-30, 2026."""
    schedule = []
    for day in range(1, 31):
        codes = JUNE_PATTERN[(day - 1) % len(JUNE_PATTERN)]
        schedule.append((date(2026, 6, day), *codes))
    return schedule


DAILY_SCHEDULE = build_daily_schedule()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    return " ".join(name.lower().strip().split())


def _find_or_create_user(full_name: str):
    """Return an existing user matched by full_name, or create a new operator account."""
    norm_name = _normalize(full_name)

    # Try exact normalized full name first.
    user = User.query.filter(
        db.func.lower(db.func.trim(User.full_name)) == norm_name
    ).first()
    if user:
        return user, False

    # Try matching all name parts (>= 2 chars) to catch minor formatting differences.
    parts = [p for p in norm_name.split() if len(p) >= 2]
    query = User.query
    for part in parts:
        query = query.filter(User.full_name.ilike(f"%{part}%"))
    user = query.first()
    if user:
        return user, False

    # Create new operator account.
    base_username = "".join(ch for ch in norm_name.split()[0] if ch.isalnum()) or "user"
    username = base_username
    counter = 1
    while User.query.filter_by(username=username).first():
        username = f"{base_username}{counter}"
        counter += 1

    email = f"{username}@airside.ebb"
    email_counter = 1
    while User.query.filter_by(email=email).first():
        email = f"{username}{email_counter}@airside.ebb"
        email_counter += 1

    temp_password = "Airside@2026!"
    new_user = User(
        username=username,
        email=email,
        full_name=full_name,
        role="operator",
        department="Airside Operations",
        is_active=True,
    )
    new_user.set_password(temp_password)
    db.session.add(new_user)
    db.session.flush()
    return new_user, True


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

def run():
    app = create_app("development")
    with app.app_context():
        admin = User.query.filter_by(role="admin").first()
        admin_id = admin.id if admin else None

        print("\n=== Resolving staff to user accounts ===")
        shift_users = {}
        created_users = []

        # Ensure all shift members exist and collect them per shift.
        for shift_letter, members in SHIFTS.items():
            shift_users[shift_letter] = []
            for name in members:
                user, was_created = _find_or_create_user(name)
                shift_users[shift_letter].append(user)
                status = "CREATED" if was_created else "matched"
                print(
                    f"  Shift {shift_letter}: {status:<7} -> "
                    f"{user.full_name} (id={user.id}, username={user.username})"
                )
                if was_created:
                    created_users.append(user)

        # Ensure additional names from document also have accounts.
        print("\n=== Ensuring additional roster names have accounts ===")
        for name in ADDITIONAL_USERS:
            user, was_created = _find_or_create_user(name)
            status = "CREATED" if was_created else "matched"
            print(f"  Extra: {status:<7} -> {user.full_name} (id={user.id}, username={user.username})")
            if was_created:
                created_users.append(user)

        db.session.commit()

        print("\n=== Inserting ShiftRoster entries (June 2026) ===")
        created_count = 0
        updated_count = 0
        skipped_count = 0

        shift_order = ["A", "B", "C", "D"]

        for row in DAILY_SCHEDULE:
            duty_date = row[0]
            codes = {shift_order[i]: row[i + 1] for i in range(4)}

            for shift_letter, code in codes.items():
                duty_type = DUTY_MAP[code]
                cycle_idx = CYCLE_INDEX.get(duty_type, 2)
                users = shift_users[shift_letter]

                for user in users:
                    existing = ShiftRoster.query.filter_by(
                        user_id=user.id,
                        duty_date=duty_date,
                    ).first()

                    if existing:
                        if existing.duty_type in ("leave", "study_leave", "office"):
                            skipped_count += 1
                            continue
                        existing.duty_type = duty_type
                        existing.cycle_day_index = cycle_idx
                        existing.notes = f"june2026_roster|shift_{shift_letter}"
                        existing.created_by_user_id = admin_id
                        updated_count += 1
                    else:
                        db.session.add(
                            ShiftRoster(
                                duty_date=duty_date,
                                user_id=user.id,
                                duty_type=duty_type,
                                cycle_day_index=cycle_idx,
                                notes=f"june2026_roster|shift_{shift_letter}",
                                created_by_user_id=admin_id,
                            )
                        )
                        created_count += 1

        db.session.commit()

        print("\n=== Import complete ===")
        print(f"  Roster entries created : {created_count}")
        print(f"  Roster entries updated : {updated_count}")
        print(f"  Skipped (leave/office) : {skipped_count}")

        if created_users:
            print(f"\n  New user accounts created ({len(created_users)}):")
            print(f"  {'Name':<30} {'Username':<20} {'Temp password'}")
            print(f"  {'-' * 30} {'-' * 20} {'-' * 15}")
            for u in created_users:
                print(f"  {u.full_name:<30} {u.username:<20} Airside@2026!")
            print("\n  Ask each staff member to change their password on first login.")
        else:
            print("\n  All staff matched to existing user accounts.")

        print("\n  View the roster at: http://127.0.0.1:5000/apron/shift-roster")


if __name__ == "__main__":
    run()
