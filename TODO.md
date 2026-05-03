# OPS_AIRSIDE — Feature Todo List

Last updated: 3 May 2026

---

## ✅ Done

### Core Architecture
- [x] Flask blueprint structure, RBAC, Flask-Login, Flask-WTF, CSRF, rate limiting
- [x] All 25 form schemas defined (`form_schemas.py`)
- [x] Dynamic form renderer for all inspection forms
- [x] Dedicated templates for Forms 2, 5, 10, 11, 12, 15, 16, 17, 23 via their own routes
- [x] Dedicated HTML templates for Forms 1, 4, 6–9, 13–14, 18–22, 24–25

### Workflows & Audit
- [x] Hierarchical escalation chain (operator → inspector → auditor → supervisor)
- [x] `IssueWorkflow` auto-created on every form submission
- [x] `AuditLog` immutable table + logging on submit
- [x] System-wide audit trail page (`/admin/audit-trail`)
- [x] Form submission history panel (below every form)
- [x] Report Overview panel (top of every form)

### AODB Integration
- [x] Live flight sync + FlightMovement cache
- [x] Flight autocomplete on all forms with flight fields
- [x] Stand allocation with AODB live schedule
- [x] TPBB write-back to AODB (`BTI`/`BTO`)
- [x] Rolling 2-hour window for today's AODB lists
- [x] Write-back queue monitoring page

### Budget & Procurement
- [x] Budget allocations with line items, revisions, delete
- [x] 9-stage procurement workflow with full audit trail
- [x] Spending tracking with Chart.js
- [x] Budget reports (5 types) with PDF/Excel export
- [x] UGX comma formatting throughout

### UI & Navigation
- [x] Section dashboards for Inspection, Safety, Permit, Apron
- [x] Sidebar grouped into labeled sections with dashboard entry points
- [x] ESSAT contextual quick links on Forms 18 & 19
- [x] Interactive Apron Stand Map (state machine, Code C split-stand logic)
- [x] Layout reference map viewer (PDF.js)

---

## ❌ Not Yet Done

### 1. Secondary pages missing the Report Overview panel
These pages have their own templates but **no `page_overview` dict** is passed from their routes — so there's no summary/history panel at the top:
- [ ] `apron/staff_deployment.html`
- [ ] `apron/tpbb_operations.html`
- [ ] `safety/fod_walk_schedule.html`
- [ ] `permits/vehicle_registration.html`
- [ ] `permits/company_management.html`

### 2. Per-report drill-down (detail view)
- [ ] The **Related Reports** table shows past submissions with status/workflow badges, but there is **no clickable link to open a single submission** and review its full data. A `view_submission/<id>` route and detail template don't exist yet.

### 3. Form 3 — Apron Parking Reference Chart
- [ ] No dedicated HTML page or route. The layout reference viewer partially covers it visually, but Form 3 has no submission path.

### 4. Form field-level parity (several forms are thin)
Some schemas are minimal stubs — not fully matching the actual paper form:
- [ ] Form 19 (ESSAT Non-Motorised / Dolly Cart Audit) — 5 checklist items vs. the detailed Form 18 treatment
- [ ] Forms 20, 21, 23, 24, 25 — basic schemas only, not validated against the actual paper forms field-by-field

### 5. Section dashboard charts
- [ ] The four section dashboards (`section_overview.html`) show only stat cards and link lists. **No Chart.js graphs** (e.g. submissions over time, status breakdown pie) yet.

### 6. Two-factor authentication (2FA/TOTP)
- [ ] `PyOTP` is in requirements, `two_factor.html` template exists, but **2FA is not enforced or fully wired** — it's listed as optional structure only.

### 7. PWA / Offline sync — not fully wired
- [ ] `pwa_sw.js`, `offline_sync.js`, and `manifest.webmanifest` exist, but the **service worker is not confirmed registered**, and offline draft caching via IndexedDB isn't fully tested end-to-end.

### 8. Email notifications
- [ ] `notification_service.py` exists but **no notification triggers are wired** to workflow escalations, approvals, or rejections.

### 9. PDF export on individual form submissions
- [ ] `pdf_generator.py` exists. Budget reports export works. But **individual form submission PDF export** (print a filled Form 18, etc.) isn't wired to any route.

### 10. Production hardening items (from §13 checklist)
All of these are outstanding by design for production deployment:
- [ ] AODB live credentials and connectivity test
- [ ] HTTPS + HSTS + Nginx reverse proxy
- [ ] MFA enforcement for privileged roles
- [ ] Antivirus scanning for file uploads
- [ ] Immutable DB-level audit policy (triggers)
- [ ] CI/CD pipeline, monitoring, backup/DR

---

## Priority Order

| Priority | Item |
|----------|------|
| High | Report drill-down detail view |
| High | `page_overview` panel on 5 secondary pages |
| Medium | Email notifications on workflow escalations |
| Medium | 2FA enforcement for admin/supervisor |
| Medium | Form 19 + other thin schemas fleshed out |
| Medium | Section dashboard charts |
| Low | Form 3 page |
| Low | PWA offline sync validation |
| Production | AODB credentials, HTTPS, MFA, CI/CD |
