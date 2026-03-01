# Gemini Project Context: Weather Monitoring

This file maintains the state and roadmap for the Weather Monitoring project. It is intended to be read by Gemini CLI at the start of each session.

## 📝 Current State
- **Refactored Python App:** Main script renamed to `app/mkweathergraphs_loop.py`. Code is modularized, uses `plt.close()` to prevent memory leaks, and handles configuration via a central dictionary.
- **Testing:** Comprehensive test suite added in `app/test_weather.py` using `pytest`.
- **CI/CD:** GitHub Actions now includes a `test` stage before building and pushing Docker images.
- **Infrastructure:** Helm charts updated, deployment verified in Kubernetes (namespace: `default`).
- **Documentation:** `README.md` rewritten in English; `.env.example` created for secrets management.

## 🛠 Tech Stack
- **Backend:** Python 3.9 (Matplotlib, Seaborn, InfluxDB Client).
- **Alerting:** Go (Telegram Proxy for Prometheus Alertmanager).
- **Infrastructure:** Kubernetes, Helm, Telegraf, Prometheus, InfluxDB.
- **Hosting:** Neocities (for static graphs and index.html).

## 🚀 Roadmap & Next Steps
1.  **[ ] Graceful Shutdown (Python):** Implement signal handling (`SIGTERM`, `SIGINT`) to ensure the loop finishes the current iteration and closes connections before exiting.
2.  **[ ] Network Resilience:** Add retry logic with exponential backoff for InfluxDB queries and Neocities uploads.
3.  **[ ] Telegram Proxy Security:** Implement basic token-based authentication for the `/alert` endpoint to prevent unauthorized spam.
4.  **[ ] Memory Optimization:** Modify the graph generator to use `io.BytesIO` instead of writing temporary files to disk before uploading.

## 📌 Architectural Notes
- The Python app follows a "Generate -> Save -> Upload" cycle controlled by `WAIT_SECONDS`.
- Deployment uses `dev-<sha>` tags for traceability, with `latest` also updated in CI.
- The project is designed to be fully manageable via `Makefile` commands.
