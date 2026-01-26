# Product Requirement Document (PRD)

## Projektname
Robuste Scraping- & Monitoring-Architektur für JobTrends

## Autor
Sebastian Winkler

## Status
Draft – Entscheidungs- & Umsetzungsgrundlage

---

## 1. Ziel & Motivation

Das bestehende Scraping-System liefert funktionale Ergebnisse, ist jedoch anfällig für:
- stille Datenfehler (Fake-200s, leere Responses, Parser-Drift)
- Race Conditions bei parallelen Runs
- aggressive Inactive-Markierung bei temporären Fehlern
- fehlende Differenzierung von Fehlerursachen

Ziel dieses Projekts ist es, das System **produktionsrobust**, **selbstdiagnostizierend** und **skalierbar** zu machen – ohne unnötige Over-Engineering-Komplexität.

**Leitprinzipien:**
- Fail fast, fail loud
- Data Integrity > Durchsatz
- Automatisierte Reaktionen statt manueller Debugging-Schleifen

---

## 2. Nicht-Ziele

- Kein vollständiger Rewrite auf Async-only-Architektur
- Kein generisches Crawling-Framework
- Kein UI-Dashboard (Monitoring erfolgt über DB + Cloud Logging)

---

## 3. Zielarchitektur (High Level)

- **Scraper (Python)**
  - Konfigurierbar pro Company/Profile
  - Strukturierte Fehlerklassifikation

- **Postgres (Supabase / Cloud SQL)**
  - Run-Monitoring & States
  - Aktueller Master-State (Jobs)

- **Google Cloud Storage (GCS)**
  - Detail-Payloads (raw)
  - Historische Master-Snapshots (Audit/Backup)

- **Cloud Logging**
  - Strukturierte Logs (JSON)
  - Alerting über Queries

---

## 4. Funktionale Anforderungen

### 4.1 Konfiguration & Secrets (P0)

**Anforderungen:**
- Alle Credentials (DB, Proxy, GCS) ausschließlich über ENV / Secret Manager
- Zentrale Config-Validierung beim Start
- Abbruch mit `status=config_error`, wenn Config unvollständig

**Akzeptanzkriterien:**
- Kein Secret im Code oder Logs
- Fehlende ENV-Var → Abbruch < 1s Laufzeit

---

### 4.2 Fehlerklassifikation & Recovery (P0)

**Failure Types (kanonisch):**
- success
- blocked
- rate_limited
- empty_suspect
- parse_error
- dependency_error
- config_error

**Anforderungen:**
- Jeder Run endet mit genau einem Failure Type
- Retry-/Backoff-Logik abhängig vom Failure Type

**Akzeptanzkriterien:**
- Monitoring zeigt klare Fehlerursachen
- Automatisierte Reaktionen möglich (z. B. Proxy-Switch bei `blocked`)

---

### 4.3 WAF- & Block-Detection (P0)

**Anforderungen:**
- Content-Type Validation (JSON erwartet, HTML geliefert → block_suspect)
- Body-Hash / Content-Length Heuristiken
- JSON-Parse-Errors als Block-Signal

**Akzeptanzkriterien:**
- Fake-200s werden erkannt
- `empty_suspect` statt falschem `success`

---

### 4.4 Run Confidence Gating (P0)

**Anforderungen:**
- Berechnung eines Confidence Scores pro Run
- Kritische Aktionen nur bei hoher Confidence:
  - Inactive-Markierung
  - Master-State-Update

**Akzeptanzkriterien:**
- Keine massenhaften False-Inactive-Spikes mehr

---

### 4.5 Inactive Grace Period (P0)

**Anforderungen:**
- Jobs erst nach N Tagen ohne Sichtung inactive setzen (Default: 3–7)
- Alternativ: nur bei High-Confidence-Runs

**Akzeptanzkriterien:**
- Temporäre Scraper-Ausfälle führen nicht zu Datenkorruption

---

### 4.6 Master-State Konsistenz & Performance (P0)

**Anforderungen:**
- O(N²)-Lookups eliminieren (Indexierung beim Laden)
- Race-Condition-Schutz:
  - Option A: GCS Generation Preconditions (CAS)
  - Option B: DB Advisory Lock pro `company_key`

**Akzeptanzkriterien:**
- Keine verlorenen Updates bei parallelen Runs
- Lineare Performance bei >10.000 Jobs

---

### 4.7 Stage-Duration Tracking (P1)

**Stages:**
- fetch_list
- parse_list
- fetch_details
- save_master

**Anforderungen:**
- Dauer pro Stage im Monitoring speichern

**Akzeptanzkriterien:**
- Bottlenecks klar identifizierbar

---

### 4.8 Datenvalidierung & Schema Drift (P1)

**Anforderungen:**
- Required vs Optional Fields definieren
- Invalid-Rate tracken
- Alert bei plötzlichem Schema-Drift (>X % invalid)

**Optional:**
- Pydantic Models für normalisierte Jobs

---

### 4.9 Logging & Observability (P1)

**Anforderungen:**
- Strukturierte JSON-Logs
- Pflichtfelder: run_id, company_key, stage, failure_type
- Log-Level-Konventionen (DEBUG / INFO / WARNING / ERROR)

---

### 4.10 Proxy-Strategie (P1)

**Anforderungen:**
- Adaptive Proxy-Nutzung (on failure escalation)
- Sticky Sessions für zusammenhängende Requests
- Optional: Region/Country-Switch bei Blocks

---

### 4.11 Testing & Regression-Schutz (P1)

**Anforderungen:**
- Golden Fixtures (sanitized API Responses)
- Contract Tests für Parser
- CI-Smoketest für Top-Targets

**Akzeptanzkriterien:**
- API-Änderungen werden vor Produktion erkannt

---

## 5. Nicht-funktionale Anforderungen

- **Stabilität:** Kein Datenverlust bei Partial Failures
- **Skalierbarkeit:** 1000+ Companies täglich möglich
- **Kostenkontrolle:** Rate-Limits, Budgets, Max-Runtime
- **Wartbarkeit:** Klare Failure Types & Logs

---

## 6. Priorisierung

### P0 (Must-Have)
- Secrets & Config Validation
- Failure Taxonomie
- WAF/Block Detection
- Run Confidence Gating
- Inactive Grace Period
- Master-State Locking + O(N²)-Fix

### P1 (Should-Have)
- Stage Durations
- Schema Drift Detection
- Structured Logging
- Proxy Intelligence
- Golden Fixtures & Contract Tests

### P2 (Nice-to-Have)
- Async/Parallel Fetching
- DLQ für selektive Failures
- Vollständige Migration Master → Postgres

---

## 7. Erfolgskriterien (KPIs)

- <1 % False-Inactive-Events
- Deutliche Reduktion von `empty` oder `fake success` Runs
- Schnellere Root-Cause-Analyse (<10 Min)
- Stabiler Betrieb bei erhöhter Parallelität

---

## 8. Offene Entscheidungen

- CAS über GCS vs DB Advisory Locks
- Pydantic-Einsatzumfang
- Zeitpunkt Async-Migration
- Snapshot-Frequenz für GCS

---

## 9. Nächste Schritte

1. P0-Items final priorisieren
2. Technische Spikes für CAS vs DB Lock
3. Monitoring-Schema finalisieren
4. Iterative Umsetzung pro Company-Template

