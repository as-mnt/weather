# Gemini Project Context: Weather Monitoring

This file maintains the state and roadmap for the Weather Monitoring project. It is intended to be read by Gemini CLI at the start of each session.

## 📝 Current State (Last Updated: Mar 8, 2026)
- **Version:** v0.2.1 (Stable).
- **Multi-City Monitoring:** Active for Bishkek, Kazan, and Vladivostok.
- **Data Fix:** Queries for Bishkek now include legacy data without the `location` tag.
- **Visualization:** Scientific notation disabled on Y-axis for better readability of pressure graphs.
- **Dynamic Content:** Automatic generation of city-specific `index.html` in `/Bishkek/`, `/Kazan/`, and `/Vladivostok/`.
- **Infrastructure:** Telegraf (v3 tags), Prometheus, and Blackbox Exporter fully configured and deployed.
- **Monitoring Audit:** Metric `probe_last_modified_timestamp_seconds` used for staleness alerts.

## 🛠 Tech Stack
- **Backend:** Python 3.9 (Matplotlib, Seaborn, InfluxDB Client).
- **Alerting:** Go (Telegram Proxy for Prometheus Alertmanager).
- **Infrastructure:** Kubernetes, Helm, Telegraf, Prometheus, InfluxDB.
- **Hosting:** Neocities (for static graphs and index.html).

## 🚀 Roadmap & Next Steps
1.  **[x] Fix Monitoring Config:** 
    - Rename `probe_http_last_modified_timestamp_seconds` to `probe_last_modified_timestamp_seconds` in `infra/prometheus/weather-alerts-configmap.yaml`.
    - Stage and commit `infra/prometheus/blackbox-values.yaml`.
    - Finalize `infra/prometheus/values.yaml`.
2.  **[ ] Graceful Shutdown (Python):** Implement signal handling (`SIGTERM`, `SIGINT`) to ensure the loop finishes the current iteration and closes connections before exiting.
3.  **[ ] Network Resilience:** Add retry logic with exponential backoff for InfluxDB queries and Neocities uploads.
4.  **[ ] Telegram Proxy Security:** Implement basic token-based authentication for the `/alert` endpoint.
5.  **[ ] Memory Optimization:** Modify the graph generator to use `io.BytesIO`.

## 📌 Architectural Notes
- The Python app follows a "Generate -> Save -> Upload" cycle controlled by `WAIT_SECONDS`.
- Deployment uses `dev-<sha>` tags for traceability, with `latest` also updated in CI.
- The project is designed to be fully manageable via `Makefile` commands.
