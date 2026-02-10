# CCGX Exporter

[![CI](https://github.com/tom-da-costa/ccgx_exporter/actions/workflows/ci.yml/badge.svg)](https://github.com/tom-da-costa/ccgx_exporter/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Deux outils Python pour interagir avec un **Victron Color Control GX (CCGX)** via son broker MQTT local :

| Script | Rôle |
|---|---|
| `main.py` | Exporter Prometheus — expose les métriques sur `/metrics` |
| `api_server.py` | API HTTP — expose la dernière valeur de chaque topic en JSON |

Les données sont lues en temps réel depuis le broker MQTT embarqué du CCGX (`N/#`). Un keepalive est envoyé automatiquement toutes les 30 secondes pour maintenir le flux de données.

---

## Prérequis

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/)
- CCGX accessible en réseau avec le broker MQTT activé (port 1883 par défaut)

> **Activer le broker MQTT sur le CCGX :** Menu → Settings → Services → MQTT on LAN → Activé

---

## Installation

```bash
git clone https://github.com/tom-da-costa/ccgx_exporter.git
cd ccgx_exporter
uv sync
```

---

## Docker

L'image est publiée automatiquement sur le GitHub Container Registry à chaque push sur `master` et à chaque tag `v*`.

```bash
# Dernière version stable
docker pull ghcr.io/tom-da-costa/ccgx_exporter:latest

# Exporter Prometheus
docker run -p 9877:9877 ghcr.io/tom-da-costa/ccgx_exporter:latest --host 192.168.1.210

# API HTTP (surcharge l'entrypoint)
docker run -p 4756:4756 --entrypoint uv \
  ghcr.io/tom-da-costa/ccgx_exporter:latest \
  run api_server.py --host 192.168.1.210
```

---

## Exporter Prometheus (`main.py`)

Souscrit au MQTT du CCGX et expose les métriques Prometheus sur `/metrics`.

### Lancement

```bash
uv run main.py --host 192.168.1.210
```

### Options

| Option | Défaut | Description |
|---|---|---|
| `--host` | `192.168.1.210` | IP ou hostname du CCGX |
| `--mqtt-port` | `1883` | Port du broker MQTT |
| `--listen-address` | `0.0.0.0` | Adresse d'écoute du serveur HTTP |
| `--metrics-port` | `9877` | Port d'exposition des métriques |
| `--prefix` | `victron_` | Préfixe des noms de métriques Prometheus |
| `--debug` | — | Active les logs de debug |

### Exemple de métriques

```
victron_dc_battery_voltage_volts{instance="0",portal_id="abc123",service="system"} 24.7
victron_dc_battery_state_of_charge{instance="0",portal_id="abc123",service="system"} 85.0
victron_ac_consumption_phase_power_watts{instance="0",phase="1",portal_id="abc123",service="system"} 1234.0
victron_dc_pv_power_watts{instance="0",portal_id="abc123",service="system"} 3200.0
victron_alarm{alarm="LowBattery",instance="257",phase="",portal_id="abc123",service="vebus"} 0.0
victron_time_on_grid_seconds_total{instance="0",portal_id="abc123",service="system"} 3600.0
```

Chaque métrique porte les labels `portal_id`, `service` et `instance`, ce qui permet de gérer plusieurs appareils Victron dans le même Prometheus.

### Intégration Prometheus

```yaml
# prometheus.yml
scrape_configs:
  - job_name: ccgx
    static_configs:
      - targets: ["localhost:9877"]
```

---

## API HTTP (`api_server.py`)

Souscrit au MQTT du CCGX et expose la dernière valeur connue de chaque topic via une API REST JSON.

### Lancement

```bash
uv run api_server.py --host 192.168.1.210
```

### Options

| Option | Défaut | Description |
|---|---|---|
| `--host` | `192.168.1.210` | IP ou hostname du CCGX |
| `--mqtt-port` | `1883` | Port du broker MQTT |
| `--listen-address` | `0.0.0.0` | Adresse d'écoute du serveur HTTP |
| `--api-port` | `4756` | Port de l'API HTTP |
| `--debug` | — | Active les logs de debug |

### Endpoints

#### `GET /values/<service>/<instance>/<path>`

Retourne la dernière valeur connue pour un topic.

```bash
curl http://localhost:4756/values/vebus/257/Ac/Out/L1/P
```

```json
{
  "portal_id": "abc123",
  "path": "vebus/257/Ac/Out/L1/P",
  "value": 1500.0,
  "updated_at": 1718000000.123
}
```

Si plusieurs portails exposent le même topic, un tableau est retourné.

Retourne `404` si le topic n'a jamais été reçu.

#### `GET /values`

Liste tous les topics connus avec leur dernière valeur.

```bash
curl http://localhost:4756/values
```

```json
[
  {
    "portal_id": "abc123",
    "path": "system/0/Dc/Battery/Soc",
    "value": 85.0,
    "updated_at": 1718000000.123
  },
  ...
]
```

#### `GET /portals`

Liste les identifiants de portail découverts.

```bash
curl http://localhost:4756/portals
```

```json
["abc123"]
```

---

## CI/CD

Le pipeline GitHub Actions (`.github/workflows/ci.yml`) s'exécute à chaque push sur `master` et sur les pull requests :

1. **Lint** — `ruff check` + `ruff format --check`
2. **Tests** — `pytest` avec coverage ≥ 90 %
3. **Build & Push** — construit l'image Docker et la pousse sur `ghcr.io` (skippé sur les PRs)

### Tags Docker publiés

| Événement | Tags |
|---|---|
| Push sur `master` | `latest`, `master`, `sha-<commit>` |
| Tag `v1.2.3` | `1.2.3`, `1.2`, `sha-<commit>` |
| Pull request | build uniquement, pas de push |

---

## Structure du projet

```
main.py            Exporter Prometheus (point d'entrée)
api_server.py      API HTTP (point d'entrée)
collector.py       Collecteur Prometheus custom (thread-safe)
mqtt_client.py     Client MQTT avec keepalive automatique
metrics.py         Mapping topics D-Bus → définitions Prometheus (217 métriques)
pyproject.toml     Dépendances (paho-mqtt, prometheus-client)
Dockerfile         Image Docker basée sur uv
.github/
  workflows/
    ci.yml         Pipeline CI/CD GitHub Actions
tests/
  test_collector.py
  test_mqtt_client.py
  test_metrics.py
  test_api_server.py
  test_main.py
```

---

## Licence

Apache 2.0 — voir [LICENSE](LICENSE).

---

## Notes

- Le champ `updated_at` de l'API est un timestamp Unix. Une valeur non mise à jour depuis longtemps peut indiquer un appareil hors ligne.
- Les topics dont la valeur MQTT est `null` sont ignorés.
- La liste complète des chemins D-Bus supportés est documentée dans [`metrics.py`](metrics.py) et dans le [wiki Venus OS](https://github.com/victronenergy/venus/wiki/dbus).
