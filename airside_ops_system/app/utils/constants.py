"""
System-wide constants and business rules from the Airside Operations manual.
"""

# Airport frequencies
ATM_FREQUENCY = '118.1 MHz'  # Air Traffic Management/Tower
ACT_FREQUENCY = '121.9 MHz'  # Apron Control Tower

# Speed limits (km/h)
SPEED_LIMITS = {
    'within_15m_of_aircraft': 5,
    'vehicle_corridor': 25,
    'perimeter_roads': 40,
}

# Safety distances (meters)
SAFETY_DISTANCES = {
    'wingtip_clearance': 5,
    'refuelling_aircraft_clearance': 15,
    'engine_front_clearance': 7.5,
    'engine_behind_idle_clearance': 76,
    'taxiway_edge_turf_clearance': 45,
    'fueling_safety_zone_radius': 6,
}

# ADP colour codes
ADP_COLOUR_CODES = {
    'red': 'Apron equipment',
    'green': 'Fuel, pushback, highloaders, ambulift, catering, fire trucks',
    'blue': 'Ramp bus, coaster',
    'brown': 'Cars, vans, pick-ups, forklifts, towing tractors, electric tugs',
}

# Violation penalties from Attachment 1
VIOLATION_PENALTIES = {
    'over_speeding': {'amount': 100000, 'currency': 'UGX'},
    'spills_per_sqm': {'amount': 500000, 'currency': 'UGX', 'per_unit': True},
    'no_reflective_vest': {'amount': 100000, 'currency': 'UGX'},
    'no_national_license': {'amount': 100000, 'currency': 'UGX'},
    'no_adp': {'amount': 100000, 'currency': 'UGX'},
    'no_airside_vehicle_permit': {'amount': 200000, 'currency': 'UGX'},
    'no_airside_safety_requirement': {'amount': 100000, 'currency': 'UGX', 'per_unit': True},
    'no_essat_sticker': {'amount': 100000, 'currency': 'UGX'},
    'dangerous_mechanical_condition': {'amount': 300000, 'currency': 'UGX'},
    'grounded_equipment_no_essat': {'amount': 300000, 'currency': 'UGX'},
    'traversing_aircraft_stands': {'amount': 300000, 'currency': 'UGX'},
    'runway_incursion': {'amount': 500000, 'currency': 'UGX'},
    'cross_taxiway_without_atc': {'amount': 300000, 'currency': 'UGX'},
    'parking_outside_designated_area': {'amount': 100000, 'currency': 'UGX'},
    'obstruct_fuel_emergency_stop': {'amount': 100000, 'currency': 'UGX'},
    'failure_to_give_way_aircraft': {'amount': 300000, 'currency': 'UGX'},
    'leave_equipment_on_stand': {'amount': 100000, 'currency': 'UGX', 'per_unit': True},
    'dolly_without_brakes': {'amount': 300000, 'currency': 'UGX', 'per_unit': True},
    'uld_unsecured': {'amount': 300000, 'currency': 'UGX', 'per_unit': True},
    'smoking_airside': {'amount': 1000, 'currency': 'USD'},
    'special_fire_cover': {'amount': 1000, 'currency': 'USD'},
}

# Runways and taxiways
RUNWAYS = ['17/35', '12/30']
TAXIWAYS = ['A1', 'A2', 'A3', 'A4', 'B', 'C1', 'C2', 'C3', 'D', 'H1', 'J1', 'J2', 'J3']

# Parking stand codes
PARKING_STANDS = {
    'Apron 1': ['A1S01', 'A1S02', 'A1S03', 'A1S04', 'A1S05', 'A1S06', 'A1S07', 'A1S08', 'A1S09', 'A1S10', 'A1S11',
                'A1S20', 'A1S21', 'A1S22', 'A1S23', 'A1S24', 'A1S25'],
    'Apron 2': ['A2S01', 'A2S02', 'A2S03', 'A2S04', 'A2S05', 'A2S06'],
    'Apron 4': ['A4S01', 'A4S02', 'A4S03', 'A4S04', 'A4S05', 'A4S06', 'A4S07', 'A4S08', 'A4S09'],
    'Apron 5': ['A5S50', 'A5S51', 'A5S51A', 'A5S51B', 'A5S52', 'A5S53'],
}

# Form metadata
FORM_DEFINITIONS = {
    1: 'Staff Proficiency and Performance Monitoring (Aircraft Marshalling)',
    2: 'Shift Handover/Takeover Form',
    3: 'Apron Parking Reference Chart',
    4: 'Aircraft Parking/Stand Inspection Form',
    5: 'TPBB Docking Record and Inspection Form',
    6: 'Manoeuvring Area Inspection Form',
    7: 'Apron Inspection Form',
    8: 'Runway Surface Condition Report (GRF)',
    9: 'Spillage Control Form',
    10: 'Airside Incident Report Form',
    11: 'Preliminary Incident and Accident Investigation Form',
    12: 'Airside Daily Operational Report',
    13: 'Monthly Aircraft Turn Around Audit Form',
    14: 'Apron Equipment Survey During Peak Traffic',
    15: 'Airside Violation Form',
    16: 'On Spot Equipment and Personnel Report Form',
    17: 'Airside Driving Permit (ADP) Application Form',
    18: 'ESSAT Checklist (Motorised Vehicle/Equipment)',
    19: 'Dolly/Cart Audit Form (Non-Motorised)',
    20: 'FOD Form',
    21: 'Quarterly FOD Walk Report Form',
    22: 'Aircraft Fueling Safety Inspection Checklist',
    23: 'Staff Deployment/Parking Plan Form',
    24: 'Tank Farm Inspection Checklist',
    25: 'Low Visibility Procedure Implementation Form',
}
