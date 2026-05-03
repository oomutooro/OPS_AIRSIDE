"""
Import May 2026 Duty Roster into ShiftRoster table.

Roster source: MAY DUTY ROSTER-2026.docx
Run: python import_may_roster.py

Duty codes:
  D = Day shift
  N = Night shift
  O = Off duty

Shifts:
  A: SSEWANYANA R, BYARUHANGA E, Ssemwanga R, Evon A, Opolot E, Namugenyi R
  B: SUUNA E, MUSINGUZI V, Kyakonye Z, Ssentongo I, Sharif M, Ederu E
  C: MUSAMBI I, OGOLA J, Akandwanaho S, Ssebuwufu F, Bakashaba J, Mukisa E
  D: MUGISHA W, CANDIGA F, Ecuru A, Alele Abel, Matovu M, Abiti M.F
"""
import os
import sys
from datetime import date

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db, bcrypt
from app.models.user import User
from app.models.apron import ShiftRoster

# ---------------------------------------------------------------------------
# Roster data
# ---------------------------------------------------------------------------

# Each shift group: list of (full_name, surname_initial) as they appear in doc
SHIFTS = {
    'A': [
        'Ssewanyana Ronald',
        'Byaruhanga Edgar',
        'Ssemwanga Ronald',
        'Evon Akandwanaho',
        'Opolot Emmanuel',
        'Namugenyi Robinah',
    ],
    'B': [
        'Suuna Edgar',
        'Musinguzi Victor',
        'Kyakonye Ziad',
        'Ssentongo Ivan',
        'Sharif Mohamed',
        'Ederu Edgar',
    ],
    'C': [
        'Musambi Ivan',
        'Ogola John',
        'Akandwanaho Stella',
        'Ssebuwufu Francis',
        'Bakashaba Jackson',
        'Mukisa Edward',
    ],
    'D': [
        'Mugisha William',
        'Candiga Francis',
        'Ecuru Albert',
        'Alele Abel',
        'Matovu Mark',
        'Abiti Mary Florence',
    ],
}

# Daily schedule: (date, ShiftA_duty, ShiftB_duty, ShiftC_duty, ShiftD_duty)
# D=day, N=night, O=off
DAILY_SCHEDULE = [
    (date(2026, 5,  1), 'D', 'O', 'O', 'N'),
    (date(2026, 5,  2), 'N', 'O', 'D', 'O'),
    (date(2026, 5,  3), 'O', 'D', 'N', 'O'),
    (date(2026, 5,  4), 'O', 'N', 'O', 'D'),
    (date(2026, 5,  5), 'D', 'O', 'O', 'N'),
    (date(2026, 5,  6), 'N', 'O', 'D', 'O'),
    (date(2026, 5,  7), 'O', 'D', 'N', 'O'),
    (date(2026, 5,  8), 'O', 'N', 'O', 'D'),
    (date(2026, 5,  9), 'D', 'O', 'O', 'N'),
    (date(2026, 5, 10), 'N', 'O', 'D', 'O'),
    (date(2026, 5, 11), 'O', 'D', 'N', 'O'),
    (date(2026, 5, 12), 'O', 'N', 'O', 'D'),
    (date(2026, 5, 13), 'D', 'O', 'O', 'N'),
    (date(2026, 5, 14), 'N', 'O', 'D', 'O'),
    (date(2026, 5, 15), 'O', 'D', 'N', 'O'),
    (date(2026, 5, 16), 'O', 'N', 'O', 'D'),
    (date(2026, 5, 17), 'D', 'O', 'O', 'N'),
    (date(2026, 5, 18), 'N', 'O', 'D', 'O'),
    (date(2026, 5, 19), 'O', 'D', 'N', 'O'),
    (date(2026, 5, 20), 'O', 'N', 'O', 'D'),
    (date(2026, 5, 21), 'D', 'O', 'O', 'N'),
    (date(2026, 5, 22), 'N', 'O', 'D', 'O'),
    (date(2026, 5, 23), 'O', 'D', 'N', 'O'),
    (date(2026, 5, 24), 'O', 'N', 'O', 'D'),
    (date(2026, 5, 25), 'D', 'O', 'O', 'N'),
    (date(2026, 5, 26), 'N', 'O', 'D', 'O'),
    (date(2026, 5, 27), 'O', 'D', 'N', 'O'),
    (date(2026, 5, 28), 'O', 'N', 'O', 'D'),
    (date(2026, 5, 29), 'D', 'O', 'O', 'N'),
    (date(2026, 5, 30), 'N', 'O', 'D', 'O'),
    (date(2026, 5, 31), 'O', 'D', 'N', 'O'),
]

DUTY_MAP = {
    'D': 'day',
    'N': 'night',
    'O': 'off',
}

CYCLE_INDEX = {
    'day': 0,
    'night': 1,
    'off': 2,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    return name.lower().strip()


def _find_or_create_user(full_name: str, shift_letter: str, admin_user_id: int) -> User:
    """Return an existing user matched by full_name, or create a new operator account."""
    # Try exact match first
    user = User.query.filter(
        db.func.lower(User.full_name) == _normalize(full_name)
    ).first()
    if user:
        return user, False

    # Try partial match on any word in the name
    parts = full_name.lower().split()
    for part in parts:
        if len(part) < 3:
            continue
        user = User.query.filter(
            User.full_name.ilike(f'%{part}%'),
            User.role == 'operator',
        ).first()
        if user:
            return user, False

    # Create new operator account
    surname = full_name.split()[0].lower()
    base_username = surname
    username = base_username
    counter = 1
    while User.query.filter_by(username=username).first():
        username = f'{base_username}{counter}'
        counter += 1

    temp_password = 'Airside@2026!'
    new_user = User(
        username=username,
        email=f'{username}@airside.ebb',
        full_name=full_name,
        role='operator',
        department='Airside Operations',
        is_active=True,
    )
    new_user.set_password(temp_password)
    db.session.add(new_user)
    db.session.flush()  # get ID before commit
    return new_user, True


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

def run():
    app = create_app('development')
    with app.app_context():
        admin = User.query.filter_by(role='admin').first()
        admin_id = admin.id if admin else None

        # Resolve all shift members to user records
        print('\n=== Resolving staff to user accounts ===')
        shift_users = {}  # shift_letter -> list of User
        created_users = []
        for shift_letter, members in SHIFTS.items():
            shift_users[shift_letter] = []
            for name in members:
                user, was_created = _find_or_create_user(name, shift_letter, admin_id)
                shift_users[shift_letter].append(user)
                status = '✓ CREATED' if was_created else '  matched'
                print(f'  Shift {shift_letter}: {status} → {user.full_name} (id={user.id}, username={user.username})')
                if was_created:
                    created_users.append(user)

        db.session.commit()

        # Insert ShiftRoster entries
        print('\n=== Inserting ShiftRoster entries ===')
        created_count = 0
        updated_count = 0
        skipped_count = 0

        shift_order = ['A', 'B', 'C', 'D']

        for row in DAILY_SCHEDULE:
            duty_date = row[0]
            codes = {shift_order[i]: row[i + 1] for i in range(4)}

            for shift_letter, code in codes.items():
                duty_type = DUTY_MAP[code]
                cycle_idx = CYCLE_INDEX.get(duty_type, 2)
                users = shift_users[shift_letter]

                for user in users:
                    # Check for existing leave/override — never overwrite
                    existing = ShiftRoster.query.filter_by(
                        user_id=user.id,
                        duty_date=duty_date,
                    ).first()

                    if existing:
                        if existing.duty_type in ('leave', 'study_leave', 'office'):
                            skipped_count += 1
                            continue
                        existing.duty_type = duty_type
                        existing.cycle_day_index = cycle_idx
                        existing.notes = f'may2026_roster|shift_{shift_letter}'
                        existing.created_by_user_id = admin_id
                        updated_count += 1
                    else:
                        db.session.add(ShiftRoster(
                            duty_date=duty_date,
                            user_id=user.id,
                            duty_type=duty_type,
                            cycle_day_index=cycle_idx,
                            notes=f'may2026_roster|shift_{shift_letter}',
                            created_by_user_id=admin_id,
                        ))
                        created_count += 1

        db.session.commit()

        print(f'\n=== Import complete ===')
        print(f'  Roster entries created : {created_count}')
        print(f'  Roster entries updated : {updated_count}')
        print(f'  Skipped (leave/office) : {skipped_count}')
        if created_users:
            print(f'\n  New user accounts created ({len(created_users)}):')
            print(f'  {"Name":<30} {"Username":<20} {"Temp password"}')
            print(f'  {"-"*30} {"-"*20} {"-"*15}')
            for u in created_users:
                print(f'  {u.full_name:<30} {u.username:<20} Airside@2026!')
            print('\n  ⚠ Ask each staff member to change their password on first login.')
        else:
            print('\n  All staff matched to existing user accounts.')

        print('\n  View the roster at: http://127.0.0.1:5000/apron/shift-roster')


if __name__ == '__main__':
    run()
