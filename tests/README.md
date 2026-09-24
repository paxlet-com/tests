# 🧪 Paxlet-Com Autonomy E2E Test Suite

Zestaw testów End-to-End weryfikujący autonomię, bezpieczeństwo i determinizm ekosystemu **Taskand**, **Paxlet** oraz **nl-dsl-sh**.

---

## 🎯 Zakres weryfikacji autonomii

1. **Dekompozycja i planowanie w języku naturalnym (`nl-dsl-sh`)**:
   - Przyjmowanie celów w języku naturalnym (np. polskie zapytania).
   - Wyszukiwanie i reużywanie zweryfikowanych skryptów z katalogów (`Catalog.import_script`).
   - Deterministyczna kompilacja do kodu Python / Bash z walidacją składni.

2. **Hermetyzacja i pakiety Paxlet (`paxlet`)**:
   - Eksport skompilowanego planu do struktury paczki Paxlet (`export_paxlet`).
   - Weryfikacja integralności manifestu (`validate_manifest`).
   - Kryptograficzne sumowanie zawartości (`package_digest`).

3. **Izolacja wykonania i certyfikacja (`receipt.json`)**:
   - Uruchamianie w odseparowanym środowisku (`paxlet.runtime.run_action`).
   - Egzekwowanie zasady fail-closed: podanie błędnego skrótu lub modyfikacja plików paczki blokuje wykonanie (`Paxlet digest mismatch`).
   - Generowanie niezmiennego dowodu wykonania ze znacznikami czasu, skrótem pakietu i kodem wyjścia.

4. **Integracja CLI Taskand**:
   - Weryfikacja podkomend `taskand shell plan|export|verify|run`.
   - Zabezpieczenie przed wyciekiem uprawnień między procesami `shell-build` i `shell-run`.

---

## 🚀 Uruchomienie

### 1. Testy lokalne (z dedykowanym środowiskiem Taskand):
```bash
./tests/run_e2e.sh local
```

### 2. Testy w izolowanym środowisku Docker Compose:
```bash
./tests/run_e2e.sh docker
```
lub bezpośrednio:
```bash
docker compose -f tests/docker/compose.e2e.yml up --build --abort-on-container-exit
```
