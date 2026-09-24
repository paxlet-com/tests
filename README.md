# paxlet-com/tests — Autonomous Taskand & Paxlet Docker E2E Testing Framework

> **Standard**: `wellmanifest.new-project/v2`  
> **Silnik**: Docker Compose, Playwright / CDP, Pytest / Node.js  
> **Zakres**: Weryfikacja E2E autonomii systemu Taskand, kompilacji planów w języku naturalnym przez nl-dsl-sh, integralności paczek Paxlet oraz hermetycznego wykonania w izolowanych kontenerach Docker.

---

## 🚀 Cel projektu

Projekt `paxlet-com/tests` stanowi niezależny, izolowany framework walidacji i testów End-to-End (E2E) dla całego ekosystemu `paxlet-com`:
- **Taskand**: weryfikacja trójwarstwowej orkiestracji autonomicznej (Planner → Validator → Orchestrator), Gateway API (:8077) oraz integracji MCP.
- **nl-dsl-sh**: kompilacja celów z języka naturalnego do bezpiecznych planów i skryptów w trybie offline i online.
- **Paxlet**: packaging, weryfikacja integralności manifestów, hermetyczne środowiska wykonawcze oraz certyfikaty kryptograficzne (`receipt.json`).
- **Izolacja Docker E2E**: uruchamianie testów w kontenerach bez dostępu do sieci produkcyjnej, ze sprawdzaniem uprawnień i odporności na awarie (*fail-closed*).
