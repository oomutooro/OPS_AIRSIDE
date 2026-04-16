"""
Canonical field schemas for Forms 1-25.
These definitions drive dynamic rendering and server-side validation.
"""

FORM_SCHEMAS = {
    1: {
        "title": "Staff Proficiency and Performance Monitoring (Aircraft Marshalling)",
        "sections": [
            {
                "name": "Evaluator Details",
                "fields": ["evaluator_name", "staff_name", "staff_badge", "company", "date", "shift"],
            },
            {
                "name": "Arrival Preparation (1-5)",
                "checklist": [
                    "PPE compliance before duty",
                    "Stand readiness verification",
                    "Communication with ACT confirmed",
                    "FOD/obstacle area clear",
                    "Wingtip safety awareness",
                ],
                "scale": "1-5",
            },
            {
                "name": "Aircraft Parking and Marshalling (1-5)",
                "checklist": [
                    "Correct marshalling signals",
                    "Stop mark accuracy",
                    "Follow Me coordination",
                    "Engine hazard awareness",
                    "Post-parking safety checks",
                ],
                "scale": "1-5",
            },
            {
                "name": "Aerobridge and Turnaround (1-5)",
                "checklist": [
                    "TPBB pre-docking test",
                    "Docking safety confirmation",
                    "Back-off and handoff quality",
                    "Passenger step fallback readiness",
                ],
                "scale": "1-5",
            },
        ],
    },
    2: {
        "title": "Shift Handover/Takeover Form",
        "sections": [
            {"name": "Shift Parties", "fields": ["outgoing_shift", "incoming_shift", "handover_time"]},
            {"name": "Vehicle/Equipment Status", "fields": ["vehicles_status", "equipment_status"]},
            {"name": "Office Tools", "fields": ["radios", "logbooks", "keys", "computers", "defects"]},
            {"name": "Major Events", "fields": ["events_summary", "incidents", "pending_actions"]},
        ],
    },
    3: {
        "title": "Apron Parking Reference Chart",
        "sections": [
            {"name": "Stand Mapping", "fields": ["apron_1_stands", "apron_2_stands", "apron_4_stands", "apron_5_stands"]},
            {"name": "Stop Marks", "fields": ["code_a_mark", "code_b_mark", "code_c_mark", "code_f_procedure"]},
        ],
    },
    4: {
        "title": "Aircraft Parking/Stand Inspection Form",
        "sections": [
            {"name": "Pre-Arrival", "checklist": ["FOD clear", "No spillage", "No obstacles", "Markings visible", "Hydrants accessible"]},
            {"name": "Post-Departure", "checklist": ["FOD collected", "Stand damage check", "Leftover equipment removed", "Spillage treated"]},
        ],
    },
    5: {
        "title": "TPBB Docking Record and Inspection Form",
        "sections": [
            {"name": "Pre-Docking Tests", "checklist": ["Power test", "Emergency stop", "Height alignment", "Intercom functional"]},
            {"name": "Docking", "fields": ["bridge_no", "flight_no", "docking_time", "back_off_time", "operator"]},
        ],
    },
    6: {
        "title": "Manoeuvring Area Inspection Form",
        "sections": [
            {"name": "Runways", "checklist": ["Runway 17/35 condition", "Runway 12/30 condition", "PAPI status", "Lighting", "Signage"]},
            {"name": "Taxiways", "checklist": ["A1", "A2", "A3", "A4", "B", "C1", "C2", "C3", "D", "H1", "J1", "J2", "J3"]},
            {"name": "Perimeter/Vegetation", "checklist": ["Wildlife risk", "Grass height", "Wind socks", "Drainage"]},
        ],
    },
    7: {
        "title": "Apron Inspection Form",
        "sections": [
            {"name": "Apron 1/2/4/5", "checklist": ["Pavement condition", "Stand markings", "Vehicle corridor", "FOD bins", "Hydrants", "Signage"]},
        ],
    },
    8: {
        "title": "Runway Surface Condition Report (GRF)",
        "sections": [
            {"name": "Runway Thirds", "fields": ["third_1_rcam", "third_2_rcam", "third_3_rcam", "coverage_pct", "contaminant_type", "depth_mm"]},
            {"name": "Trigger/Interval", "fields": ["rain_start_time", "report_interval_30min", "all_thirds_dry_time"]},
        ],
    },
    9: {
        "title": "Spillage Control Form",
        "sections": [
            {"name": "Spill Details", "fields": ["spill_type", "estimated_area_m2", "equipment_used", "arffs_notified"]},
            {"name": "Response", "checklist": ["Area isolated", "Absorbent used", "Sawdust avoided for hydraulic", "Disposed safely"]},
        ],
    },
    10: {
        "title": "Airside Incident Report Form",
        "sections": [
            {"name": "Occurrence", "fields": ["date", "time", "location", "incident_type", "severity"]},
            {"name": "Narrative", "fields": ["description", "sequence_of_events", "immediate_actions"]},
            {"name": "Assets/People", "fields": ["aircraft", "vehicle", "injuries", "damage"]},
        ],
    },
    11: {
        "title": "Preliminary Incident and Accident Investigation Form",
        "sections": [
            {"name": "Investigation", "fields": ["investigator", "findings", "probable_cause", "contributing_factors"]},
            {"name": "Recommendations", "fields": ["recommendation_1", "recommendation_2", "deadline"]},
        ],
    },
    12: {
        "title": "Airside Daily Operational Report",
        "sections": [
            {"name": "Shift Summary", "fields": ["shift_date", "shift_type", "leader", "attendance"]},
            {"name": "Operations", "fields": ["movements", "issues", "incidents", "equipment_status"]},
        ],
    },
    13: {
        "title": "Monthly Aircraft Turn Around Audit Form",
        "sections": [
            {
                "name": "Pre-arrival",
                "checklist": [
                    "Stand allocation confirmed",
                    "Stand free of FOD",
                    "Cones/chocks staged",
                    "GPU availability confirmed",
                    "Passenger stairs positioned",
                    "Marshaller brief complete",
                    "Wing walkers assigned when required",
                    "Follow Me readiness confirmed",
                    "Emergency lane clear",
                    "Fuel hydrant access clear",
                ],
            },
            {
                "name": "Arrival",
                "checklist": [
                    "Marshaller in position",
                    "Correct marshalling signal set",
                    "Stop mark accuracy",
                    "Engine hazard zone respected",
                    "Aircraft stopped safely",
                    "Chocks applied promptly",
                    "Cones placed at required points",
                    "PPE compliance all staff",
                    "No unauthorized crossing",
                    "Initial walkaround complete",
                ],
            },
            {
                "name": "PBB/Passenger Steps/Personnel",
                "checklist": [
                    "PBB pre-docking checks complete",
                    "PBB docked without contact risk",
                    "Back-off sequence verified",
                    "Passenger steps secured",
                    "Handrails serviceable",
                    "Ground staff briefing done",
                    "High-visibility vest compliance",
                    "Restricted area access control",
                    "Escort for VVIP maintained",
                    "Pedestrian route maintained",
                ],
            },
            {
                "name": "Tug/Cargo/Servicing/Fuel",
                "checklist": [
                    "Pushback clearance from ACT",
                    "Tug pre-use check done",
                    "Max 3 baggage carts per tug",
                    "Cargo locks secure",
                    "ULDs secured",
                    "Catering truck stabilizers set",
                    "Water lavatory service safe",
                    "Fuel bonding/earthing done",
                    "6m fueling safety zone maintained",
                    "No ignition source in fuel zone",
                    "Spill kit available",
                    "Hydrant emergency stop accessible",
                    "Servicing equipment parked correctly",
                    "No stand traversal violations",
                    "Communication discipline on radio",
                ],
            },
            {
                "name": "Departure",
                "checklist": [
                    "All equipment removed",
                    "FOD final sweep complete",
                    "Doors/holds confirmed closed",
                    "Pushback team in position",
                    "Wing walkers active where required",
                    "Taxi clearances coordinated",
                    "Post-departure stand inspection done",
                    "Spillage check complete",
                    "Operational log updated",
                    "Non-conformance actions assigned",
                ],
            },
        ],
    },
    14: {
        "title": "Apron Equipment Survey During Peak Traffic",
        "sections": [
            {"name": "Equipment Availability", "fields": ["gpu_count", "tug_count", "loader_count", "dolly_count", "catering_count", "fueling_count"]},
            {"name": "Serviceability", "fields": ["serviceable", "unserviceable", "rectification_eta"]},
        ],
    },
    15: {
        "title": "Airside Violation Form",
        "sections": [
            {"name": "Offender", "fields": ["offender_name", "badge", "company", "vehicle_reg"]},
            {"name": "Violation/Penalty", "fields": ["violation_type", "description", "penalty_amount", "currency"]},
            {"name": "Acknowledgements", "fields": ["offender_sign", "employer_commitment"]},
        ],
    },
    16: {
        "title": "On Spot Equipment and Personnel Report Form",
        "sections": [
            {"name": "Observation", "fields": ["location", "personnel", "equipment", "non_compliance", "action_taken"]},
        ],
    },
    17: {
        "title": "Airside Driving Permit (ADP) Application Form",
        "sections": [
            {"name": "Applicant", "fields": ["name", "badge", "company", "license_no", "license_expiry"]},
            {"name": "Categories", "fields": ["brown", "green", "blue", "red"]},
            {"name": "Training", "fields": ["training_completed", "written_score", "pass_mark_70"]},
        ],
    },
    18: {
        "title": "ESSAT Checklist (Motorised Vehicle/Equipment)",
        "sections": [
            {
                "name": "Vehicle and Organization Details",
                "fields": [
                    "organization_company",
                    "airside_vehicle_no",
                    "colour",
                    "type",
                    "manufacture_date",
                    "sticker_no",
                    "sticker_status",
                ],
            },
            {
                "name": "ESSAT Team",
                "fields": [
                    "team_leader_name",
                    "team_leader_organization",
                    "team_member_2_name",
                    "team_member_2_organization",
                    "team_member_3_name",
                    "team_member_3_organization",
                    "team_member_4_name",
                    "team_member_4_organization",
                    "team_member_5_name",
                    "team_member_5_organization",
                    "team_member_6_name",
                    "team_member_6_organization",
                    "team_member_7_name",
                    "team_member_7_organization",
                ],
            },
            {
                "name": "Vehicle and Equipment Status",
                "fields": [
                    "vehicle_equipment_id_no",
                    "vehicle_equipment_description",
                    "defects_observed",
                    "date_of_correction",
                    "status_yes_no",
                ],
                "checklist": [
                    "Starting Condition",
                    "Battery Condition",
                    "Steering Condition",
                    "Exhaust Pipe Emission",
                    "Side/Tail Reflective Materials",
                    "Windscreen with no Cracks / Watering Sprinklers / Wiper Blades",
                    "Adequate Rear-View Mirrors",
                    "Condition of Rear Lenses",
                    "Beacon Color / Yellow",
                    "Lighting Intensity and Flashing Rate",
                ],
            },
            {
                "name": "Electric Motor Vehicle (EMV)",
                "checklist": [
                    "EMV Installed",
                    "Approaching Vehicle Sound for Pedestrians (VSP) System",
                    "Headlamp",
                    "Hand Brake",
                    "Indicators",
                ],
            },
            {
                "name": "Electrical System",
                "checklist": [
                    "Correctly Adjusted Headlights",
                    "Hazard Lights / Indicators",
                    "Brake / Parking / Reverse Lights",
                    "Colour of the Flashing Beacon / Serviceability Status",
                    "Horn / Applicable Siren",
                    "Functionality of Dashboard Instruments",
                    "Work Lights / License Plate Lights",
                    "Fog Lights",
                    "Rear and Side Illuminative Reflectors",
                    "Emergency Stop Switches",
                ],
            },
            {
                "name": "Leakages",
                "checklist": [
                    "Fuel",
                    "PTMO",
                    "Hydraulic Systems",
                    "Water / Foam",
                    "Engine Oil / CC Oil",
                    "Coolant Levels",
                ],
            },
            {
                "name": "Safety Equipment",
                "checklist": [
                    "Serviced Fire Extinguisher",
                    "Valid First Aid Kit",
                    "Stretcher",
                    "Oxygen Bottle",
                    "Gloves / Fixed Wash Basin",
                    "Patient Resuscitating Equipment",
                    "Body Condition",
                    "Bird Scaring Cassettes",
                    "Beacon Colour / Blue",
                    "Lighting Intensity and Flashing Rate",
                ],
            },
            {
                "name": "Braking Systems",
                "checklist": [
                    "Brakes with Adequate Stopping Power",
                    "Condition of the Hand Brake",
                    "Tyres with Adequate Tread and Correct Pressure",
                ],
            },
            {
                "name": "Ground Handling Equipment",
                "checklist": [
                    "Tow Bar Condition",
                    "Work Warning Sirens",
                    "Platform Scissors",
                    "Platform Belts / Platform Rollers",
                    "Hydraulic Lifts / Rams",
                    "Conveyor Belts",
                    "Rubber Guards / Side Guards",
                    "Bed Rollers",
                ],
            },
            {
                "name": "Aerodrome Rescue and Fire Fighting Services (ARFFS)",
                "checklist": [
                    "Ground Sprinklers",
                    "Turret Condition",
                    "Rescue Appliances",
                    "Water Hose Condition",
                    "Flood Lights",
                    "Beacon Colour / Blue",
                    "Lighting Intensity and Flashing Rate",
                ],
            },
            {
                "name": "Entebbe Joint Aviation Facility (EJAF)",
                "checklist": [
                    "Fuel Pump Condition",
                    "Fuel Hose Condition",
                    "Dead Man Condition",
                    "Brake Interlock System",
                    "No Ash Trays in the Cabin",
                    "Warning Safety Signages",
                ],
            },
            {
                "name": "Remarks and Approvals",
                "fields": [
                    "general_remarks",
                    "recommendations",
                    "secretary",
                    "secretary_sign",
                    "chairperson",
                    "chairperson_sign",
                ],
            },
        ],
    },
    19: {
        "title": "Dolly/Cart Audit Form (Non-Motorised)",
        "sections": [
            {"name": "Inspection", "checklist": ["Brakes", "Tyres", "Side reflectors", "Towbar", "Frame condition"]},
            {"name": "Defects", "fields": ["defect_description", "rectification_status", "due_date"]},
        ],
    },
    20: {
        "title": "FOD Form",
        "sections": [
            {"name": "Cleaning Details", "fields": ["date", "start_time", "end_time", "method"]},
            {"name": "Areas", "checklist": ["Aprons", "Taxiways", "Runways", "Vehicle corridor"]},
            {"name": "FOD Types", "fields": ["metal", "plastic", "rubber", "stones", "other", "weight_kg"]},
        ],
    },
    21: {
        "title": "Quarterly FOD Walk Report Form",
        "sections": [
            {"name": "Participants", "fields": ["organizations", "attendance_count"]},
            {"name": "Collection", "fields": ["areas_covered", "fod_types", "total_weight_kg"]},
        ],
    },
    22: {
        "title": "Aircraft Fueling Safety Inspection Checklist",
        "sections": [
            {
                "name": "Personnel & Equipment",
                "checklist": [
                    "Fuel operator valid permit",
                    "Fuel operator PPE complete",
                    "Driver ADP valid",
                    "Vehicle ESSAT sticker valid",
                    "Vehicle beacon operational",
                    "Fire extinguishers serviceable",
                    "Spill kit complete",
                    "Bonding cable available",
                    "Hose integrity check complete",
                    "Emergency stop device functional",
                    "Fuel meter calibration valid",
                    "Communication radio functional",
                ],
            },
            {
                "name": "Pre-fuelling",
                "checklist": [
                    "Fueling request authorized",
                    "Aircraft parked and chocked",
                    "No passengers boarding nearby if prohibited",
                    "Ground power hazards controlled",
                    "Engine and APU status confirmed",
                    "Fuel grade confirmed",
                    "Fuel quantity confirmed",
                    "Drain sample check complete",
                    "No visible leaks before start",
                    "Weather and lightning status acceptable",
                    "Fire cover requirement checked",
                    "ATC/ACT coordination complete",
                ],
            },
            {
                "name": "Fueling Safety Zone",
                "checklist": [
                    "6m radial zone demarcated",
                    "No smoking enforced",
                    "No open flame",
                    "No portable electronic devices",
                    "No unauthorized persons",
                    "Vehicles clear of fueling zone",
                    "Emergency route unobstructed",
                    "Hydrant emergency stop accessible",
                    "FOD bins clear of critical area",
                    "Spill absorbents pre-positioned",
                    "Static discharge precautions active",
                    "Supervisor present",
                ],
            },
            {
                "name": "Fuelling Operations",
                "checklist": [
                    "Bonding connected aircraft-to-truck",
                    "Earthing connection verified",
                    "Hose coupling secure",
                    "Flow initiated gradually",
                    "Pressure within limit",
                    "No nozzle drips/leaks",
                    "Continuous operator attendance",
                    "Fuel vent area monitored",
                    "Interruption procedure known",
                    "Comms with flight crew maintained",
                    "Spill response readiness maintained",
                    "No zone breaches during fueling",
                ],
            },
            {
                "name": "Post-fuelling",
                "checklist": [
                    "Flow stopped per procedure",
                    "Residual pressure safely relieved",
                    "Nozzle disconnected safely",
                    "Bonding removed last",
                    "Leak/spill final check",
                    "Caps and panels secured",
                    "Area restored clean",
                    "Equipment removed from stand",
                    "Fuel documents signed",
                    "Quantity reconciliation complete",
                    "Any anomaly reported",
                    "Fueling completion logged",
                ],
            },
        ],
    },
    23: {
        "title": "Staff Deployment/Parking Plan Form",
        "sections": [
            {"name": "Traffic Plan", "fields": ["scheduled_movements", "non_scheduled_movements"]},
            {"name": "Deployment", "fields": ["officers", "runway_inspection", "enforcement", "pbb_ops", "special_ops"]},
        ],
    },
    24: {
        "title": "Tank Farm Inspection Checklist",
        "sections": [
            {"name": "QC/Product Docs", "checklist": ["QC logs current", "Product certificates", "Calibration records"]},
            {"name": "Facilities", "checklist": ["Loading bay", "Storage tanks", "Filtration", "Hydrant ops", "Into-plane"]},
        ],
    },
    25: {
        "title": "Low Visibility Procedure Implementation Form",
        "sections": [
            {"name": "Preparatory", "checklist": ["RVR monitoring", "Stakeholder pre-alert", "Follow Me readiness"]},
            {"name": "Low Visibility Phase", "checklist": ["RVR < 550m confirmed", "Escort active", "Movement restrictions"]},
            {"name": "Termination", "checklist": ["RVR recovery confirmed", "Stakeholder notification", "Normal ops resumed"]},
        ],
    },
}
