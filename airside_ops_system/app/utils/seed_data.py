"""
Initial seed data loader for companies, stands, locations, violation types, and form templates.
"""
from app.models.reference import Company, ParkingStand, AirsideLocation, AirsideVehicle
from app.models.form import FormTemplate
from app.models.incident import ViolationType
from app.utils.constants import FORM_DEFINITIONS, PARKING_STANDS, RUNWAYS, TAXIWAYS, VIOLATION_PENALTIES
from app.utils.form_schemas import FORM_SCHEMAS


def seed_companies(db):
    companies = [
        ('NAS', 'GHA'), ('DAS', 'GHA'), ('MONUSCO', 'UN'), ('UN', 'UN'), ('EJAF', 'government'),
        ('Tristar Energy Ltd', 'fuel'), ('Total Energy', 'fuel'), ('Vivo Energy', 'fuel'),
        ('Uganda Air Cargo', 'airline'), ('Eagle Air', 'airline'), ('Air Serv', 'airline'),
        ('Kampala Executive Aviation (KEA)', 'airline'), ('Newrest', 'catering'),
    ]
    for name, ctype in companies:
        if not Company.query.filter_by(name=name).first():
            db.session.add(Company(name=name, company_type=ctype, is_active=True))


def seed_stands(db):
    for apron_name, stand_codes in PARKING_STANDS.items():
        apron_num = apron_name.split()[-1]
        for code in stand_codes:
            if not ParkingStand.query.filter_by(stand_code=code).first():
                stand_no = code.split('S')[-1]
                db.session.add(ParkingStand(
                    stand_code=code,
                    stand_number=stand_no,
                    apron=apron_num,
                    category='C',
                    has_pbb=code.startswith('A1S0') or code.startswith('A2S0'),
                    is_active=True,
                ))


def seed_locations(db):
    for rw in RUNWAYS:
        if not AirsideLocation.query.filter_by(code=rw).first():
            db.session.add(AirsideLocation(code=rw, name=f'Runway {rw}', zone='runway', is_active=True))

    for tw in TAXIWAYS:
        if not AirsideLocation.query.filter_by(code=tw).first():
            db.session.add(AirsideLocation(code=tw, name=f'Taxiway {tw}', zone='taxiway', is_active=True))

    extra = [('APRON1', 'Apron 1', 'apron'), ('APRON2', 'Apron 2', 'apron'),
             ('APRON4', 'Apron 4', 'apron'), ('APRON5', 'Apron 5', 'apron')]
    for code, name, zone in extra:
        if not AirsideLocation.query.filter_by(code=code).first():
            db.session.add(AirsideLocation(code=code, name=name, zone=zone, is_active=True))


def seed_violation_types(db):
    for code, cfg in VIOLATION_PENALTIES.items():
        if not ViolationType.query.filter_by(code=code).first():
            db.session.add(ViolationType(
                code=code,
                description=code.replace('_', ' ').title(),
                standard_penalty_ugx=cfg.get('amount') if cfg.get('currency') == 'UGX' else None,
                standard_penalty_usd=cfg.get('amount') if cfg.get('currency') == 'USD' else None,
                penalty_currency=cfg.get('currency', 'UGX'),
                is_per_unit=cfg.get('per_unit', False),
                unit_description='per unit' if cfg.get('per_unit') else None,
                is_active=True,
            ))


def seed_form_templates(db):
    category_map = {
        1: 'inspection', 2: 'apron', 3: 'apron', 4: 'inspection', 5: 'apron', 6: 'inspection', 7: 'inspection',
        8: 'inspection', 9: 'inspection', 10: 'safety', 11: 'safety', 12: 'report', 13: 'inspection', 14: 'inspection',
        15: 'safety', 16: 'safety', 17: 'permit', 18: 'inspection', 19: 'inspection', 20: 'inspection',
        21: 'inspection', 22: 'inspection', 23: 'apron', 24: 'inspection', 25: 'inspection'
    }
    for number, title in FORM_DEFINITIONS.items():
        if not FormTemplate.query.filter_by(form_number=number).first():
            db.session.add(FormTemplate(
                form_number=number,
                title=title,
                version='1.0',
                category=category_map.get(number, 'inspection'),
                schema_definition=FORM_SCHEMAS.get(number, {}),
                ui_layout={},
                is_active=True,
            ))


def seed_call_sign_vehicles(db):
    call_signs = [
        'Follow me 1', 'Follow me 2', 'Follow me 3',
        'Fire 1', 'Fire 2', 'Fire 3', 'Fire 4', 'Fire 5', 'Fire 6', 'Fire 7', 'Fire 8', 'Fire 9', 'Fire 10',
        'Wildlife 1', 'Wildlife 2', 'Wildlife 3', 'Operations', 'Apron', 'Electrik 1', 'Electrik 2',
        'Sweeper 1', 'Pavements 1', 'Painting 1', 'Maintenance', 'See-Ness 1', 'Aytem 1', 'Dysser 1',
        'Avsek 1', 'Avpol 1', 'Air Force 1', 'Air cargo', 'UN 1', 'UN 02', 'Das Handling 1',
        'Menzies Handling 1', 'Jet 1', 'Total 1', 'Vivo 1', 'Avgas 1', 'Eagle 1', 'Air Serv 1',
        'KEA 1', 'GA 1', 'Newrest 1', 'Contractors 1'
    ]

    for idx, sign in enumerate(call_signs, start=1):
        reg = f'ASD-{idx:03d}'
        if not AirsideVehicle.query.filter_by(registration=reg).first():
            db.session.add(AirsideVehicle(
                registration=reg,
                call_sign=sign,
                vehicle_type='service_vehicle',
                colour='White',
                beacon_colour='yellow',
                adp_code='brown',
                is_active=True,
            ))


def seed_all(db):
    seed_companies(db)
    seed_stands(db)
    seed_locations(db)
    seed_violation_types(db)
    seed_form_templates(db)
    seed_call_sign_vehicles(db)
    db.session.commit()
